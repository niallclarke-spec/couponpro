"""
Database module for PromoStack campaigns and submissions
"""
import os
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
from datetime import datetime

class DatabasePool:
    def __init__(self):
        self.connection_pool = None
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Initialize PostgreSQL connection pool"""
        try:
            database_url = os.environ.get('DATABASE_URL')
            db_host = os.environ.get('DB_HOST')
            
            if database_url:
                self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                    1,
                    20,
                    database_url,
                    sslmode='prefer',
                    connect_timeout=10,
                    options='-c statement_timeout=30000'
                )
                print("✅ Database connection pool initialized (using DATABASE_URL, timeout=10s)")
            elif db_host:
                self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                    1,
                    20,
                    host=db_host,
                    port=os.environ.get('DB_PORT'),
                    database=os.environ.get('DB_NAME'),
                    user=os.environ.get('DB_USER'),
                    password=os.environ.get('DB_PASSWORD'),
                    sslmode='prefer',
                    connect_timeout=10,
                    options='-c statement_timeout=30000'
                )
                print("✅ Database connection pool initialized (using DB_HOST, timeout=10s)")
            else:
                print("ℹ️  Database not configured (missing DATABASE_URL or DB_HOST), campaigns feature disabled")
                self.connection_pool = None
                return
                
        except Exception as e:
            print(f"❌ Failed to initialize database pool: {e}")
            self.connection_pool = None
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        if not self.connection_pool:
            raise Exception("Database connection pool not initialized")
        
        conn = None
        try:
            conn = self.connection_pool.getconn()
            yield conn
        except Exception as e:
            print(f"Database connection error: {e}")
            if conn:
                try:
                    # Only rollback if connection is still alive
                    if not conn.closed:
                        conn.rollback()
                except Exception as rollback_error:
                    print(f"Rollback failed (connection may be closed): {rollback_error}")
            raise
        finally:
            if conn:
                try:
                    # Check if connection is still usable
                    if conn.closed:
                        # Close it completely and don't return to pool
                        self.connection_pool.putconn(conn, close=True)
                    else:
                        # Return healthy connection to pool
                        self.connection_pool.putconn(conn)
                except Exception as cleanup_error:
                    print(f"Connection cleanup error: {cleanup_error}")
    
    def initialize_schema(self):
        """Create campaigns and submissions tables if they don't exist. Returns True on success."""
        if not self.connection_pool:
            return False
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Create campaigns table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS campaigns (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(255) NOT NULL,
                        description TEXT,
                        start_date TIMESTAMP NOT NULL,
                        end_date TIMESTAMP NOT NULL,
                        prize TEXT,
                        platforms JSONB DEFAULT '[]',
                        overlay_url TEXT,
                        status VARCHAR(50) DEFAULT 'scheduled',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Add overlay_url column if it doesn't exist (migration for existing tables)
                cursor.execute("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name='campaigns' AND column_name='overlay_url'
                        ) THEN
                            ALTER TABLE campaigns ADD COLUMN overlay_url TEXT;
                        END IF;
                    END $$;
                """)
                
                # Create submissions table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS submissions (
                        id SERIAL PRIMARY KEY,
                        campaign_id INTEGER REFERENCES campaigns(id) ON DELETE CASCADE,
                        email VARCHAR(255) NOT NULL,
                        instagram_url TEXT,
                        twitter_url TEXT,
                        facebook_url TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create index on campaign_id for faster lookups
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_submissions_campaign_id 
                    ON submissions(campaign_id)
                """)
                
                # Create bot_usage table for tracking Telegram bot activity
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bot_usage (
                        id SERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        template_slug VARCHAR(255),
                        coupon_code VARCHAR(255),
                        success BOOLEAN NOT NULL,
                        error_type VARCHAR(100),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Add error_type column if it doesn't exist (migration for existing tables)
                print("[MIGRATION] Checking if bot_usage.error_type column exists...")
                cursor.execute("""
                    SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name='bot_usage' AND column_name='error_type'
                """)
                column_exists = cursor.fetchone()[0] > 0
                
                if not column_exists:
                    print("[MIGRATION] Adding error_type column to bot_usage table...")
                    cursor.execute("ALTER TABLE bot_usage ADD COLUMN error_type VARCHAR(100)")
                    print("[MIGRATION] ✅ error_type column added successfully")
                else:
                    print("[MIGRATION] error_type column already exists, skipping")
                
                # Add device_type column if it doesn't exist (migration for existing tables)
                print("[MIGRATION] Checking if bot_usage.device_type column exists...")
                cursor.execute("""
                    SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name='bot_usage' AND column_name='device_type'
                """)
                device_type_exists = cursor.fetchone()[0] > 0
                
                if not device_type_exists:
                    print("[MIGRATION] Adding device_type column to bot_usage table...")
                    cursor.execute("""
                        ALTER TABLE bot_usage 
                        ADD COLUMN device_type VARCHAR(20) DEFAULT 'unknown' 
                        CHECK (device_type IN ('mobile', 'desktop', 'tablet', 'unknown'))
                    """)
                    print("[MIGRATION] ✅ device_type column added successfully")
                else:
                    print("[MIGRATION] device_type column already exists, skipping")
                
                # Create index on created_at for faster date-based queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_bot_usage_created_at 
                    ON bot_usage(created_at)
                """)
                
                # Create index on chat_id for user-based queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_bot_usage_chat_id 
                    ON bot_usage(chat_id)
                """)
                
                # Create bot_users table for tracking active users
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bot_users (
                        chat_id BIGINT PRIMARY KEY,
                        last_coupon_code VARCHAR(255),
                        first_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create index on last_used for active user queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_bot_users_last_used 
                    ON bot_users(last_used)
                """)
                
                # Migration: Add user profile columns to bot_users table
                print("[MIGRATION] Checking if bot_users user profile columns exist...")
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='bot_users' AND column_name IN ('username', 'first_name', 'last_name')
                """)
                existing_columns = {row[0] for row in cursor.fetchall()}
                
                if 'username' not in existing_columns:
                    print("[MIGRATION] Adding username column to bot_users table...")
                    cursor.execute("ALTER TABLE bot_users ADD COLUMN username VARCHAR(255)")
                    print("[MIGRATION] ✅ username column added successfully")
                else:
                    print("[MIGRATION] username column already exists, skipping")
                
                if 'first_name' not in existing_columns:
                    print("[MIGRATION] Adding first_name column to bot_users table...")
                    cursor.execute("ALTER TABLE bot_users ADD COLUMN first_name VARCHAR(255)")
                    print("[MIGRATION] ✅ first_name column added successfully")
                else:
                    print("[MIGRATION] first_name column already exists, skipping")
                
                if 'last_name' not in existing_columns:
                    print("[MIGRATION] Adding last_name column to bot_users table...")
                    cursor.execute("ALTER TABLE bot_users ADD COLUMN last_name VARCHAR(255)")
                    print("[MIGRATION] ✅ last_name column added successfully")
                else:
                    print("[MIGRATION] last_name column already exists, skipping")
                
                # Create broadcast_jobs table for tracking broadcasts
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS broadcast_jobs (
                        id SERIAL PRIMARY KEY,
                        message TEXT NOT NULL,
                        target_days INTEGER NOT NULL,
                        status VARCHAR(50) DEFAULT 'pending',
                        total_users INTEGER DEFAULT 0,
                        sent_count INTEGER DEFAULT 0,
                        failed_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP
                    )
                """)
                
                # Create index on status for job queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_broadcast_jobs_status 
                    ON broadcast_jobs(status)
                """)
                
                # Create forex_signals table for forex trading bot
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS forex_signals (
                        id SERIAL PRIMARY KEY,
                        signal_type VARCHAR(10) NOT NULL,
                        pair VARCHAR(20) NOT NULL,
                        timeframe VARCHAR(10) NOT NULL,
                        entry_price DECIMAL(10, 2) NOT NULL,
                        take_profit DECIMAL(10, 2),
                        stop_loss DECIMAL(10, 2),
                        status VARCHAR(20) DEFAULT 'pending',
                        rsi_value DECIMAL(5, 2),
                        macd_value DECIMAL(10, 4),
                        atr_value DECIMAL(10, 2),
                        posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        closed_at TIMESTAMP,
                        result_pips DECIMAL(10, 2)
                    )
                """)
                
                # Create indexes on forex_signals
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_forex_signals_status 
                    ON forex_signals(status)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_forex_signals_posted_at 
                    ON forex_signals(posted_at)
                """)
                
                # Migration: Add new forex_signals columns for signal bot system
                print("[MIGRATION] Checking forex_signals table for new signal bot columns...")
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='forex_signals' AND column_name IN (
                        'bot_type', 'telegram_message_id', 'breakeven_set', 'breakeven_price',
                        'guidance_count', 'last_guidance_at', 'indicators_used', 'notes'
                    )
                """)
                existing_signal_columns = {row[0] for row in cursor.fetchall()}
                
                if 'bot_type' not in existing_signal_columns:
                    print("[MIGRATION] Adding bot_type column to forex_signals table...")
                    cursor.execute("""
                        ALTER TABLE forex_signals 
                        ADD COLUMN bot_type VARCHAR(20) DEFAULT 'aggressive'
                    """)
                    print("[MIGRATION] ✅ bot_type column added successfully")
                else:
                    print("[MIGRATION] bot_type column already exists, skipping")
                
                if 'telegram_message_id' not in existing_signal_columns:
                    print("[MIGRATION] Adding telegram_message_id column to forex_signals table...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN telegram_message_id BIGINT")
                    print("[MIGRATION] ✅ telegram_message_id column added successfully")
                else:
                    print("[MIGRATION] telegram_message_id column already exists, skipping")
                
                if 'breakeven_set' not in existing_signal_columns:
                    print("[MIGRATION] Adding breakeven_set column to forex_signals table...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN breakeven_set BOOLEAN DEFAULT FALSE")
                    print("[MIGRATION] ✅ breakeven_set column added successfully")
                else:
                    print("[MIGRATION] breakeven_set column already exists, skipping")
                
                if 'breakeven_price' not in existing_signal_columns:
                    print("[MIGRATION] Adding breakeven_price column to forex_signals table...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN breakeven_price DECIMAL(10, 2)")
                    print("[MIGRATION] ✅ breakeven_price column added successfully")
                else:
                    print("[MIGRATION] breakeven_price column already exists, skipping")
                
                if 'guidance_count' not in existing_signal_columns:
                    print("[MIGRATION] Adding guidance_count column to forex_signals table...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN guidance_count INTEGER DEFAULT 0")
                    print("[MIGRATION] ✅ guidance_count column added successfully")
                else:
                    print("[MIGRATION] guidance_count column already exists, skipping")
                
                if 'last_guidance_at' not in existing_signal_columns:
                    print("[MIGRATION] Adding last_guidance_at column to forex_signals table...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN last_guidance_at TIMESTAMP")
                    print("[MIGRATION] ✅ last_guidance_at column added successfully")
                else:
                    print("[MIGRATION] last_guidance_at column already exists, skipping")
                
                if 'indicators_used' not in existing_signal_columns:
                    print("[MIGRATION] Adding indicators_used column to forex_signals table...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN indicators_used JSONB")
                    print("[MIGRATION] ✅ indicators_used column added successfully")
                else:
                    print("[MIGRATION] indicators_used column already exists, skipping")
                
                if 'notes' not in existing_signal_columns:
                    print("[MIGRATION] Adding notes column to forex_signals table...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN notes TEXT")
                    print("[MIGRATION] ✅ notes column added successfully")
                else:
                    print("[MIGRATION] notes column already exists, skipping")
                
                # Migration: Add indicator re-validation columns
                print("[MIGRATION] Checking forex_signals for indicator re-validation columns...")
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='forex_signals' AND column_name IN (
                        'original_rsi', 'original_macd', 'original_adx', 'original_stoch_k',
                        'last_revalidation_at', 'revalidation_count', 'thesis_status',
                        'thesis_changed_at', 'timeout_notified'
                    )
                """)
                existing_reval_columns = {row[0] for row in cursor.fetchall()}
                
                if 'original_rsi' not in existing_reval_columns:
                    print("[MIGRATION] Adding original_rsi column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN original_rsi DECIMAL(5, 2)")
                    print("[MIGRATION] ✅ original_rsi column added")
                
                if 'original_macd' not in existing_reval_columns:
                    print("[MIGRATION] Adding original_macd column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN original_macd DECIMAL(10, 4)")
                    print("[MIGRATION] ✅ original_macd column added")
                
                if 'original_adx' not in existing_reval_columns:
                    print("[MIGRATION] Adding original_adx column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN original_adx DECIMAL(5, 2)")
                    print("[MIGRATION] ✅ original_adx column added")
                
                if 'original_stoch_k' not in existing_reval_columns:
                    print("[MIGRATION] Adding original_stoch_k column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN original_stoch_k DECIMAL(5, 2)")
                    print("[MIGRATION] ✅ original_stoch_k column added")
                
                if 'last_revalidation_at' not in existing_reval_columns:
                    print("[MIGRATION] Adding last_revalidation_at column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN last_revalidation_at TIMESTAMP")
                    print("[MIGRATION] ✅ last_revalidation_at column added")
                
                if 'revalidation_count' not in existing_reval_columns:
                    print("[MIGRATION] Adding revalidation_count column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN revalidation_count INTEGER DEFAULT 0")
                    print("[MIGRATION] ✅ revalidation_count column added")
                
                if 'thesis_status' not in existing_reval_columns:
                    print("[MIGRATION] Adding thesis_status column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN thesis_status VARCHAR(20) DEFAULT 'intact'")
                    print("[MIGRATION] ✅ thesis_status column added")
                
                if 'thesis_changed_at' not in existing_reval_columns:
                    print("[MIGRATION] Adding thesis_changed_at column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN thesis_changed_at TIMESTAMP")
                    print("[MIGRATION] ✅ thesis_changed_at column added")
                
                if 'timeout_notified' not in existing_reval_columns:
                    print("[MIGRATION] Adding timeout_notified column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN timeout_notified BOOLEAN DEFAULT FALSE")
                    print("[MIGRATION] ✅ timeout_notified column added")
                
                # Migration: Add JSONB column for dynamic indicator storage
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='forex_signals' AND column_name = 'original_indicators_json'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding original_indicators_json column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN original_indicators_json JSONB")
                    print("[MIGRATION] ✅ original_indicators_json column added")
                else:
                    print("[MIGRATION] original_indicators_json column already exists, skipping")
                
                # Migration: Add guidance zone tracking columns
                print("[MIGRATION] Checking forex_signals for guidance zone columns...")
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='forex_signals' AND column_name IN (
                        'last_progress_zone', 'last_caution_zone'
                    )
                """)
                existing_zone_columns = {row[0] for row in cursor.fetchall()}
                
                if 'last_progress_zone' not in existing_zone_columns:
                    print("[MIGRATION] Adding last_progress_zone column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN last_progress_zone INTEGER DEFAULT 0")
                    print("[MIGRATION] ✅ last_progress_zone column added")
                else:
                    print("[MIGRATION] last_progress_zone column already exists, skipping")
                
                if 'last_caution_zone' not in existing_zone_columns:
                    print("[MIGRATION] Adding last_caution_zone column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN last_caution_zone INTEGER DEFAULT 0")
                    print("[MIGRATION] ✅ last_caution_zone column added")
                else:
                    print("[MIGRATION] last_caution_zone column already exists, skipping")
                
                # Create index on bot_type for filtering by bot type
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_forex_signals_bot_type 
                    ON forex_signals(bot_type)
                """)
                
                # Create bot_config table for signal bot configuration
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bot_config (
                        setting_key VARCHAR(100) PRIMARY KEY,
                        setting_value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create forex_config table for forex bot configuration
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS forex_config (
                        id SERIAL PRIMARY KEY,
                        setting_key VARCHAR(100) UNIQUE NOT NULL,
                        setting_value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create index on forex_config
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_forex_config_setting_key 
                    ON forex_config(setting_key)
                """)
                
                # Create signal_narrative table for tracking indicator changes throughout trade lifecycle
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS signal_narrative (
                        id SERIAL PRIMARY KEY,
                        signal_id INTEGER REFERENCES forex_signals(id) ON DELETE CASCADE,
                        event_type VARCHAR(50) NOT NULL,
                        event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        current_price DECIMAL(10, 2),
                        progress_percent DECIMAL(5, 2),
                        indicators JSONB,
                        indicator_deltas JSONB,
                        guidance_type VARCHAR(50),
                        message_sent TEXT,
                        notes TEXT
                    )
                """)
                
                # Create indexes on signal_narrative
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_signal_narrative_signal_id 
                    ON signal_narrative(signal_id)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_signal_narrative_event_type 
                    ON signal_narrative(event_type)
                """)
                
                # Create recent_phrases table for AI repetition avoidance
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS recent_phrases (
                        id SERIAL PRIMARY KEY,
                        phrase_type VARCHAR(50) NOT NULL,
                        phrase_text TEXT NOT NULL,
                        used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create index on recent_phrases
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_recent_phrases_type_time 
                    ON recent_phrases(phrase_type, used_at DESC)
                """)
                
                # Create telegram_subscriptions table for EntryLab integration
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS telegram_subscriptions (
                        id SERIAL PRIMARY KEY,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        name VARCHAR(255),
                        telegram_user_id BIGINT UNIQUE,
                        telegram_username VARCHAR(255),
                        stripe_customer_id VARCHAR(255),
                        stripe_subscription_id VARCHAR(255) UNIQUE,
                        plan_type VARCHAR(50),
                        amount_paid DECIMAL(10, 2),
                        status VARCHAR(50) DEFAULT 'pending',
                        invite_link TEXT,
                        joined_at TIMESTAMP,
                        last_seen_at TIMESTAMP,
                        revoked_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create indexes on telegram_subscriptions
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_telegram_subscriptions_email 
                    ON telegram_subscriptions(email)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_telegram_subscriptions_telegram_user_id 
                    ON telegram_subscriptions(telegram_user_id)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_telegram_subscriptions_status 
                    ON telegram_subscriptions(status)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_telegram_subscriptions_stripe_subscription_id 
                    ON telegram_subscriptions(stripe_subscription_id)
                """)
                
                # Migration: Add conversion tracking columns to telegram_subscriptions
                print("[MIGRATION] Checking telegram_subscriptions for conversion tracking columns...")
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'telegram_subscriptions'
                """)
                existing_sub_columns = {row[0] for row in cursor.fetchall()}
                
                if 'free_signup_at' not in existing_sub_columns:
                    print("[MIGRATION] Adding free_signup_at column...")
                    cursor.execute("ALTER TABLE telegram_subscriptions ADD COLUMN free_signup_at TIMESTAMP")
                    print("[MIGRATION] ✅ free_signup_at column added")
                else:
                    print("[MIGRATION] free_signup_at column already exists, skipping")
                
                if 'is_converted' not in existing_sub_columns:
                    print("[MIGRATION] Adding is_converted column...")
                    cursor.execute("ALTER TABLE telegram_subscriptions ADD COLUMN is_converted BOOLEAN DEFAULT FALSE")
                    print("[MIGRATION] ✅ is_converted column added")
                else:
                    print("[MIGRATION] is_converted column already exists, skipping")
                
                if 'converted_at' not in existing_sub_columns:
                    print("[MIGRATION] Adding converted_at column...")
                    cursor.execute("ALTER TABLE telegram_subscriptions ADD COLUMN converted_at TIMESTAMP")
                    print("[MIGRATION] ✅ converted_at column added")
                else:
                    print("[MIGRATION] converted_at column already exists, skipping")
                
                if 'conversion_days' not in existing_sub_columns:
                    print("[MIGRATION] Adding conversion_days column...")
                    cursor.execute("ALTER TABLE telegram_subscriptions ADD COLUMN conversion_days INTEGER")
                    print("[MIGRATION] ✅ conversion_days column added")
                else:
                    print("[MIGRATION] conversion_days column already exists, skipping")
                
                if 'utm_source' not in existing_sub_columns:
                    print("[MIGRATION] Adding UTM tracking columns...")
                    cursor.execute("ALTER TABLE telegram_subscriptions ADD COLUMN utm_source VARCHAR(255)")
                    cursor.execute("ALTER TABLE telegram_subscriptions ADD COLUMN utm_medium VARCHAR(255)")
                    cursor.execute("ALTER TABLE telegram_subscriptions ADD COLUMN utm_campaign VARCHAR(255)")
                    cursor.execute("ALTER TABLE telegram_subscriptions ADD COLUMN utm_content VARCHAR(255)")
                    cursor.execute("ALTER TABLE telegram_subscriptions ADD COLUMN utm_term VARCHAR(255)")
                    print("[MIGRATION] ✅ UTM columns added (utm_source, utm_medium, utm_campaign, utm_content, utm_term)")
                else:
                    print("[MIGRATION] UTM columns already exist, skipping")
                
                # Create index on is_converted for quick conversion queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_telegram_subscriptions_is_converted 
                    ON telegram_subscriptions(is_converted)
                """)
                
                # Create processed_webhook_events table for idempotency
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS processed_webhook_events (
                        event_id VARCHAR(255) PRIMARY KEY,
                        event_type VARCHAR(100),
                        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create index for cleanup (events older than 24 hours can be deleted)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_processed_webhook_events_processed_at 
                    ON processed_webhook_events(processed_at)
                """)
                
                # ============================================================
                # Multi-tenancy: Create tenants table
                # ============================================================
                print("[MIGRATION] Checking for tenants table...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tenants (
                        id VARCHAR(50) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE
                    )
                """)
                cursor.execute("""
                    INSERT INTO tenants (id, name) VALUES ('entrylab', 'EntryLab')
                    ON CONFLICT (id) DO NOTHING
                """)
                print("[MIGRATION] tenants table ready, 'entrylab' tenant seeded")
                
                # Create tenant_users table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tenant_users (
                        id SERIAL PRIMARY KEY,
                        clerk_user_id VARCHAR(255) UNIQUE NOT NULL,
                        tenant_id VARCHAR(50) NOT NULL REFERENCES tenants(id),
                        email VARCHAR(255),
                        role VARCHAR(50) DEFAULT 'member',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_tenant_users_tenant_id ON tenant_users(tenant_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_tenant_users_email ON tenant_users(email)")
                print("[MIGRATION] tenant_users table ready")
                
                # Create tenant_integrations table (future credential storage)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tenant_integrations (
                        id SERIAL PRIMARY KEY,
                        tenant_id VARCHAR(50) NOT NULL REFERENCES tenants(id),
                        provider VARCHAR(50) NOT NULL,
                        config_json JSONB NOT NULL DEFAULT '{}',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (tenant_id, provider)
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_tenant_integrations_tenant_id ON tenant_integrations(tenant_id)")
                print("[MIGRATION] tenant_integrations table ready")
                
                # ============================================================
                # Add tenant_id to existing tables
                # ============================================================
                
                # Add tenant_id to forex_signals
                cursor.execute("""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_schema='public' AND table_name='forex_signals' AND column_name='tenant_id'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding tenant_id to forex_signals...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN tenant_id VARCHAR(50) DEFAULT 'entrylab'")
                    print("[MIGRATION] ✅ tenant_id added to forex_signals")
                else:
                    print("[MIGRATION] tenant_id already exists on forex_signals, skipping")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_forex_signals_tenant_id ON forex_signals(tenant_id)")
                
                # Add tenant_id to forex_config
                cursor.execute("""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_schema='public' AND table_name='forex_config' AND column_name='tenant_id'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding tenant_id to forex_config...")
                    cursor.execute("ALTER TABLE forex_config ADD COLUMN tenant_id VARCHAR(50) DEFAULT 'entrylab'")
                    print("[MIGRATION] ✅ tenant_id added to forex_config")
                else:
                    print("[MIGRATION] tenant_id already exists on forex_config, skipping")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_forex_config_tenant_id ON forex_config(tenant_id)")
                
                # Add tenant_id to telegram_subscriptions
                cursor.execute("""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_schema='public' AND table_name='telegram_subscriptions' AND column_name='tenant_id'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding tenant_id to telegram_subscriptions...")
                    cursor.execute("ALTER TABLE telegram_subscriptions ADD COLUMN tenant_id VARCHAR(50) DEFAULT 'entrylab'")
                    print("[MIGRATION] ✅ tenant_id added to telegram_subscriptions")
                else:
                    print("[MIGRATION] tenant_id already exists on telegram_subscriptions, skipping")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_telegram_subscriptions_tenant_id ON telegram_subscriptions(tenant_id)")
                
                # Add tenant_id to recent_phrases
                cursor.execute("""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_schema='public' AND table_name='recent_phrases' AND column_name='tenant_id'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding tenant_id to recent_phrases...")
                    cursor.execute("ALTER TABLE recent_phrases ADD COLUMN tenant_id VARCHAR(50) DEFAULT 'entrylab'")
                    print("[MIGRATION] ✅ tenant_id added to recent_phrases")
                else:
                    print("[MIGRATION] tenant_id already exists on recent_phrases, skipping")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_recent_phrases_tenant_id ON recent_phrases(tenant_id)")
                
                # Add tenant_id to campaigns
                cursor.execute("""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_schema='public' AND table_name='campaigns' AND column_name='tenant_id'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding tenant_id to campaigns...")
                    cursor.execute("ALTER TABLE campaigns ADD COLUMN tenant_id VARCHAR(50) DEFAULT 'entrylab'")
                    print("[MIGRATION] ✅ tenant_id added to campaigns")
                else:
                    print("[MIGRATION] tenant_id already exists on campaigns, skipping")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_tenant_id ON campaigns(tenant_id)")
                
                # Add tenant_id to bot_usage
                cursor.execute("""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_schema='public' AND table_name='bot_usage' AND column_name='tenant_id'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding tenant_id to bot_usage...")
                    cursor.execute("ALTER TABLE bot_usage ADD COLUMN tenant_id VARCHAR(50) DEFAULT 'entrylab'")
                    print("[MIGRATION] ✅ tenant_id added to bot_usage")
                else:
                    print("[MIGRATION] tenant_id already exists on bot_usage, skipping")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bot_usage_tenant_id ON bot_usage(tenant_id)")
                
                # Add tenant_id to bot_users
                cursor.execute("""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_schema='public' AND table_name='bot_users' AND column_name='tenant_id'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding tenant_id to bot_users...")
                    cursor.execute("ALTER TABLE bot_users ADD COLUMN tenant_id VARCHAR(50) DEFAULT 'entrylab'")
                    print("[MIGRATION] ✅ tenant_id added to bot_users")
                else:
                    print("[MIGRATION] tenant_id already exists on bot_users, skipping")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bot_users_tenant_id ON bot_users(tenant_id)")
                
                # Add tenant_id to broadcast_jobs
                cursor.execute("""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_schema='public' AND table_name='broadcast_jobs' AND column_name='tenant_id'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding tenant_id to broadcast_jobs...")
                    cursor.execute("ALTER TABLE broadcast_jobs ADD COLUMN tenant_id VARCHAR(50) DEFAULT 'entrylab'")
                    print("[MIGRATION] ✅ tenant_id added to broadcast_jobs")
                else:
                    print("[MIGRATION] tenant_id already exists on broadcast_jobs, skipping")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_broadcast_jobs_tenant_id ON broadcast_jobs(tenant_id)")
                
                # Add tenant_id to bot_config
                cursor.execute("""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_schema='public' AND table_name='bot_config' AND column_name='tenant_id'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding tenant_id to bot_config...")
                    cursor.execute("ALTER TABLE bot_config ADD COLUMN tenant_id VARCHAR(50) DEFAULT 'entrylab'")
                    print("[MIGRATION] ✅ tenant_id added to bot_config")
                else:
                    print("[MIGRATION] tenant_id already exists on bot_config, skipping")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bot_config_tenant_id ON bot_config(tenant_id)")
                
                # ============================================================
                # Migrate processed_webhook_events to v2 with tenant_id
                # ============================================================
                print("[MIGRATION] Checking processed_webhook_events migration...")
                
                # Create v2 table if not exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS processed_webhook_events_v2 (
                        id SERIAL PRIMARY KEY,
                        tenant_id VARCHAR(50) NOT NULL DEFAULT 'entrylab',
                        event_id VARCHAR(255) NOT NULL,
                        event_source VARCHAR(50) NOT NULL DEFAULT 'stripe',
                        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (tenant_id, event_id)
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_processed_webhook_events_v2_tenant_id ON processed_webhook_events_v2(tenant_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_processed_webhook_events_v2_processed_at ON processed_webhook_events_v2(processed_at)")
                
                # Check if old table exists and v2 is empty (need to copy)
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema='public' AND table_name='processed_webhook_events'
                    )
                """)
                old_exists = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM processed_webhook_events_v2")
                v2_count = cursor.fetchone()[0]
                
                if old_exists and v2_count == 0:
                    # Check if old table has event_type column
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_schema='public' AND table_name='processed_webhook_events' AND column_name='event_type'
                        )
                    """)
                    has_event_type = cursor.fetchone()[0]
                    
                    if has_event_type:
                        cursor.execute("""
                            INSERT INTO processed_webhook_events_v2 (tenant_id, event_id, event_source, processed_at)
                            SELECT 'entrylab', event_id, COALESCE(event_type, 'stripe'), processed_at
                            FROM processed_webhook_events
                        """)
                    else:
                        cursor.execute("""
                            INSERT INTO processed_webhook_events_v2 (tenant_id, event_id, event_source, processed_at)
                            SELECT 'entrylab', event_id, 'stripe', processed_at
                            FROM processed_webhook_events
                        """)
                    print(f"[MIGRATION] Copied {cursor.rowcount} rows to processed_webhook_events_v2")
                
                # Swap tables if old exists and _old doesn't exist yet
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema='public' AND table_name='processed_webhook_events_old'
                    )
                """)
                old_backup_exists = cursor.fetchone()[0]
                
                if old_exists and not old_backup_exists:
                    cursor.execute("ALTER TABLE processed_webhook_events RENAME TO processed_webhook_events_old")
                    cursor.execute("ALTER TABLE processed_webhook_events_v2 RENAME TO processed_webhook_events")
                    print("[MIGRATION] ✅ Swapped processed_webhook_events tables")
                else:
                    print("[MIGRATION] processed_webhook_events swap already done or skipped")
                
                # Migration: Add multi-TP columns for modular strategy system
                print("[MIGRATION] Checking forex_signals for multi-TP columns...")
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='forex_signals' AND column_name IN (
                        'take_profit_2', 'take_profit_3', 
                        'tp1_percentage', 'tp2_percentage', 'tp3_percentage',
                        'tp1_hit', 'tp2_hit', 'tp3_hit',
                        'tp1_hit_at', 'tp2_hit_at', 'tp3_hit_at',
                        'breakeven_triggered', 'breakeven_triggered_at'
                    )
                """)
                existing_tp_columns = {row[0] for row in cursor.fetchall()}
                
                if 'take_profit_2' not in existing_tp_columns:
                    print("[MIGRATION] Adding take_profit_2 column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN take_profit_2 DECIMAL(10, 2)")
                    print("[MIGRATION] ✅ take_profit_2 column added")
                
                if 'take_profit_3' not in existing_tp_columns:
                    print("[MIGRATION] Adding take_profit_3 column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN take_profit_3 DECIMAL(10, 2)")
                    print("[MIGRATION] ✅ take_profit_3 column added")
                
                if 'tp1_percentage' not in existing_tp_columns:
                    print("[MIGRATION] Adding TP percentage columns...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN tp1_percentage INTEGER DEFAULT 100")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN tp2_percentage INTEGER DEFAULT 0")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN tp3_percentage INTEGER DEFAULT 0")
                    print("[MIGRATION] ✅ TP percentage columns added")
                
                if 'tp1_hit' not in existing_tp_columns:
                    print("[MIGRATION] Adding TP hit tracking columns...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN tp1_hit BOOLEAN DEFAULT FALSE")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN tp2_hit BOOLEAN DEFAULT FALSE")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN tp3_hit BOOLEAN DEFAULT FALSE")
                    print("[MIGRATION] ✅ TP hit columns added")
                
                if 'tp1_hit_at' not in existing_tp_columns:
                    print("[MIGRATION] Adding TP hit timestamp columns...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN tp1_hit_at TIMESTAMP")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN tp2_hit_at TIMESTAMP")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN tp3_hit_at TIMESTAMP")
                    print("[MIGRATION] ✅ TP hit timestamp columns added")
                
                if 'breakeven_triggered' not in existing_tp_columns:
                    print("[MIGRATION] Adding breakeven_triggered columns...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN breakeven_triggered BOOLEAN DEFAULT FALSE")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN breakeven_triggered_at TIMESTAMP")
                    print("[MIGRATION] ✅ breakeven_triggered columns added")
                
                print("[MIGRATION] Checking forex_signals for milestone tracking columns...")
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='forex_signals' AND column_name IN (
                        'last_milestone_at', 'milestones_sent'
                    )
                """)
                existing_milestone_columns = {row[0] for row in cursor.fetchall()}
                
                if 'last_milestone_at' not in existing_milestone_columns:
                    print("[MIGRATION] Adding last_milestone_at column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN last_milestone_at TIMESTAMP")
                    print("[MIGRATION] ✅ last_milestone_at column added")
                
                if 'milestones_sent' not in existing_milestone_columns:
                    print("[MIGRATION] Adding milestones_sent column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN milestones_sent TEXT DEFAULT ''")
                    print("[MIGRATION] ✅ milestones_sent column added")
                
                # Migration: Add close_price column for tracking exit price
                print("[MIGRATION] Checking forex_signals for close_price column...")
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='forex_signals' AND column_name = 'close_price'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding close_price column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN close_price DECIMAL(10, 2)")
                    print("[MIGRATION] ✅ close_price column added")
                else:
                    print("[MIGRATION] close_price column already exists, skipping")
                
                # Migration: Add effective_sl column for tracking guided stop loss
                print("[MIGRATION] Checking forex_signals for effective_sl column...")
                cursor.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='forex_signals' AND column_name = 'effective_sl'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding effective_sl column...")
                    cursor.execute("ALTER TABLE forex_signals ADD COLUMN effective_sl DECIMAL(10, 2)")
                    print("[MIGRATION] ✅ effective_sl column added")
                else:
                    print("[MIGRATION] effective_sl column already exists, skipping")
                
                # ============================================================
                # Phase 2B: Add unique constraints (tenant_id + natural_key)
                # ============================================================
                
                # 1. bot_users: UNIQUE (tenant_id, chat_id)
                print("[MIGRATION] Checking bot_users unique constraint (tenant_id, chat_id)...")
                cursor.execute("""
                    SELECT 1 FROM pg_constraint c
                    JOIN pg_namespace n ON n.oid = c.connamespace
                    WHERE c.conname = 'uq_bot_users_tenant_chat' AND n.nspname = 'public'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding unique constraint uq_bot_users_tenant_chat...")
                    cursor.execute("ALTER TABLE bot_users DROP CONSTRAINT IF EXISTS bot_users_pkey")
                    cursor.execute("ALTER TABLE bot_users ADD CONSTRAINT uq_bot_users_tenant_chat UNIQUE (tenant_id, chat_id)")
                    print("[MIGRATION] ✅ uq_bot_users_tenant_chat constraint added")
                else:
                    print("[MIGRATION] uq_bot_users_tenant_chat already exists, skipping")
                
                # 2. forex_config: UNIQUE (tenant_id, setting_key)
                print("[MIGRATION] Checking forex_config unique constraint (tenant_id, setting_key)...")
                cursor.execute("""
                    SELECT 1 FROM pg_constraint c
                    JOIN pg_namespace n ON n.oid = c.connamespace
                    WHERE c.conname = 'uq_forex_config_tenant_key' AND n.nspname = 'public'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding unique constraint uq_forex_config_tenant_key...")
                    cursor.execute("ALTER TABLE forex_config DROP CONSTRAINT IF EXISTS forex_config_setting_key_key")
                    cursor.execute("ALTER TABLE forex_config ADD CONSTRAINT uq_forex_config_tenant_key UNIQUE (tenant_id, setting_key)")
                    print("[MIGRATION] ✅ uq_forex_config_tenant_key constraint added")
                else:
                    print("[MIGRATION] uq_forex_config_tenant_key already exists, skipping")
                
                # 3. bot_config: UNIQUE (tenant_id, setting_key) + add id column
                print("[MIGRATION] Checking bot_config unique constraint (tenant_id, setting_key)...")
                cursor.execute("""
                    SELECT 1 FROM pg_constraint c
                    JOIN pg_namespace n ON n.oid = c.connamespace
                    WHERE c.conname = 'uq_bot_config_tenant_key' AND n.nspname = 'public'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding id column and unique constraint to bot_config...")
                    cursor.execute("""
                        SELECT column_name FROM information_schema.columns 
                        WHERE table_name='bot_config' AND column_name='id'
                    """)
                    if not cursor.fetchone():
                        cursor.execute("ALTER TABLE bot_config ADD COLUMN id SERIAL")
                        print("[MIGRATION] ✅ id column added to bot_config")
                    cursor.execute("ALTER TABLE bot_config DROP CONSTRAINT IF EXISTS bot_config_pkey")
                    cursor.execute("ALTER TABLE bot_config ADD CONSTRAINT bot_config_pkey PRIMARY KEY (id)")
                    cursor.execute("ALTER TABLE bot_config ADD CONSTRAINT uq_bot_config_tenant_key UNIQUE (tenant_id, setting_key)")
                    print("[MIGRATION] ✅ uq_bot_config_tenant_key constraint added")
                else:
                    print("[MIGRATION] uq_bot_config_tenant_key already exists, skipping")
                
                # 4. telegram_subscriptions: UNIQUE (tenant_id, email)
                print("[MIGRATION] Checking telegram_subscriptions unique constraint (tenant_id, email)...")
                cursor.execute("""
                    SELECT 1 FROM pg_constraint c
                    JOIN pg_namespace n ON n.oid = c.connamespace
                    WHERE c.conname = 'uq_telegram_subscriptions_tenant_email' AND n.nspname = 'public'
                """)
                if not cursor.fetchone():
                    print("[MIGRATION] Adding unique constraint uq_telegram_subscriptions_tenant_email...")
                    cursor.execute("ALTER TABLE telegram_subscriptions DROP CONSTRAINT IF EXISTS telegram_subscriptions_email_key")
                    cursor.execute("ALTER TABLE telegram_subscriptions ADD CONSTRAINT uq_telegram_subscriptions_tenant_email UNIQUE (tenant_id, email)")
                    print("[MIGRATION] ✅ uq_telegram_subscriptions_tenant_email constraint added")
                else:
                    print("[MIGRATION] uq_telegram_subscriptions_tenant_email already exists, skipping")
                
                conn.commit()
                print("✅ Database schema initialized")
                
                # Initialize default forex config
                initialize_default_forex_config()
                
                # Initialize default bot config
                initialize_default_bot_config()
                
                return True
        except Exception as e:
            print(f"❌ Failed to initialize schema: {e}")
            return False

# Global database pool instance
db_pool = DatabasePool()

# Campaign CRUD operations
def create_campaign(title, description, start_date, end_date, prize, platforms, overlay_url=None, tenant_id='entrylab'):
    """Create a new campaign"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO campaigns 
                (tenant_id, title, description, start_date, end_date, prize, platforms, overlay_url, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                RETURNING id
            """, (tenant_id, title, description, start_date, end_date, prize, platforms, overlay_url, 'scheduled'))
            campaign_id = cursor.fetchone()[0]
            conn.commit()
            return campaign_id
    except Exception as e:
        print(f"Error creating campaign: {e}")
        raise

def get_all_campaigns(tenant_id='entrylab'):
    """Get all campaigns ordered by start_date descending"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, description, start_date, end_date, prize, platforms, overlay_url, status, created_at
                FROM campaigns
                WHERE tenant_id = %s
                ORDER BY start_date DESC
            """, (tenant_id,))
            campaigns = []
            for row in cursor.fetchall():
                campaigns.append({
                    'id': row[0],
                    'title': row[1],
                    'description': row[2],
                    'start_date': row[3].isoformat() if row[3] else None,
                    'end_date': row[4].isoformat() if row[4] else None,
                    'prize': row[5],
                    'platforms': row[6],
                    'overlay_url': row[7],
                    'status': row[8],
                    'created_at': row[9].isoformat() if row[9] else None
                })
            return campaigns
    except Exception as e:
        print(f"Error getting campaigns: {e}")
        return []

def get_campaign_by_id(campaign_id, tenant_id='entrylab'):
    """Get a single campaign by ID"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, description, start_date, end_date, prize, platforms, overlay_url, status, created_at
                FROM campaigns
                WHERE id = %s AND tenant_id = %s
            """, (campaign_id, tenant_id))
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'title': row[1],
                    'description': row[2],
                    'start_date': row[3].isoformat() if row[3] else None,
                    'end_date': row[4].isoformat() if row[4] else None,
                    'prize': row[5],
                    'platforms': row[6],
                    'overlay_url': row[7],
                    'status': row[8],
                    'created_at': row[9].isoformat() if row[9] else None
                }
            return None
    except Exception as e:
        print(f"Error getting campaign: {e}")
        return None

def update_campaign(campaign_id, title, description, start_date, end_date, prize, platforms, overlay_url=None, tenant_id='entrylab'):
    """Update an existing campaign"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE campaigns
                SET title = %s, description = %s, start_date = %s, end_date = %s,
                    prize = %s, platforms = %s::jsonb, overlay_url = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND tenant_id = %s
            """, (title, description, start_date, end_date, prize, platforms, overlay_url, campaign_id, tenant_id))
            conn.commit()
            return True
    except Exception as e:
        print(f"Error updating campaign: {e}")
        raise

def delete_campaign(campaign_id, tenant_id='entrylab'):
    """Delete a campaign and its submissions"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM campaigns WHERE id = %s AND tenant_id = %s", (campaign_id, tenant_id))
            conn.commit()
            return True
    except Exception as e:
        print(f"Error deleting campaign: {e}")
        raise

def update_campaign_statuses():
    """Update campaign statuses based on current time"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow()
            
            # Update to ongoing
            cursor.execute("""
                UPDATE campaigns
                SET status = 'ongoing'
                WHERE start_date <= %s AND end_date >= %s AND status != 'ongoing'
            """, (now, now))
            
            # Update to expired
            cursor.execute("""
                UPDATE campaigns
                SET status = 'expired'
                WHERE end_date < %s AND status != 'expired'
            """, (now,))
            
            conn.commit()
    except Exception as e:
        print(f"Error updating campaign statuses: {e}")

# Submission operations
def create_submission(campaign_id, email, instagram_url, twitter_url, facebook_url):
    """Create a new submission"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO submissions 
                (campaign_id, email, instagram_url, twitter_url, facebook_url)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (campaign_id, email, instagram_url or None, twitter_url or None, facebook_url or None))
            submission_id = cursor.fetchone()[0]
            conn.commit()
            return submission_id
    except Exception as e:
        print(f"Error creating submission: {e}")
        raise

def get_campaign_submissions(campaign_id):
    """Get all submissions for a campaign"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, campaign_id, email, instagram_url, twitter_url, facebook_url, created_at
                FROM submissions
                WHERE campaign_id = %s
                ORDER BY created_at DESC
            """, (campaign_id,))
            submissions = []
            for row in cursor.fetchall():
                submissions.append({
                    'id': row[0],
                    'campaign_id': row[1],
                    'email': row[2],
                    'instagram_url': row[3],
                    'twitter_url': row[4],
                    'facebook_url': row[5],
                    'created_at': row[6].isoformat() if row[6] else None
                })
            return submissions
    except Exception as e:
        print(f"Error getting submissions: {e}")
        return []

def get_submission_count(campaign_id):
    """Get the number of submissions for a campaign"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM submissions WHERE campaign_id = %s
            """, (campaign_id,))
            return cursor.fetchone()[0]
    except Exception as e:
        print(f"Error getting submission count: {e}")
        return 0

# Bot usage tracking
def log_bot_usage(chat_id, template_slug, coupon_code, success, error_type=None, device_type='unknown', tenant_id='entrylab'):
    """
    Log Telegram bot usage. Silently fails to avoid disrupting bot operation.
    
    Args:
        chat_id (int): Telegram chat ID
        template_slug (str): Template slug used (or None if template not found)
        coupon_code (str): Coupon code used
        success (bool): Whether the operation succeeded
        error_type (str): Type of error if failed (e.g., 'network', 'invalid_coupon', 'template_not_found')
        device_type (str): Device type ('mobile', 'desktop', 'tablet', 'unknown')
        tenant_id (str): Tenant ID (default: 'entrylab')
    """
    import sys
    msg = f"[BOT_USAGE] Attempting to log: chat_id={chat_id}, template={template_slug}, coupon={coupon_code}, success={success}, error={error_type}, device={device_type}"
    print(msg, flush=True)
    sys.stdout.flush()
    
    try:
        if not db_pool.connection_pool:
            err_msg = f"[BOT_USAGE] ERROR: No database connection pool available"
            print(err_msg, flush=True)
            sys.stdout.flush()
            return
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bot_usage 
                (tenant_id, chat_id, template_slug, coupon_code, success, error_type, device_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (tenant_id, chat_id, template_slug, coupon_code, success, error_type, device_type))
            conn.commit()
            success_msg = f"[BOT_USAGE] ✅ Successfully logged usage"
            print(success_msg, flush=True)
            sys.stdout.flush()
    except Exception as e:
        error_msg = f"[BOT_USAGE] ❌ Failed to log usage: {e}"
        print(error_msg, flush=True)
        sys.stdout.flush()

def get_bot_stats(days=30, template_filter=None, tenant_id='entrylab'):
    """
    Get bot usage statistics for the last N days, or 'today'/'yesterday' for exact day filtering.
    
    Args:
        days (int|str): Number of days, or 'today'/'yesterday' for exact date filtering (default: 30)
        template_filter (str, optional): Filter popular coupons by specific template slug
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: Statistics including total uses, success rate, popular templates/coupons
    """
    try:
        if not db_pool.connection_pool:
            return None
        
        # Input validation to prevent SQL injection and ensure correct types
        if isinstance(days, str):
            if days not in ['today', 'yesterday']:
                raise ValueError(f"Invalid days parameter: '{days}'. Must be 'today', 'yesterday', or a positive integer.")
        elif isinstance(days, int):
            if days < 0:
                raise ValueError(f"Invalid days parameter: {days}. Must be a positive integer.")
        else:
            raise TypeError(f"Invalid days type: {type(days).__name__}. Must be int or str ('today'/'yesterday').")
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build WHERE clause based on filter type
            if days == 'today':
                where_clause = "tenant_id = %s AND created_at >= CURRENT_DATE AND created_at < CURRENT_DATE + INTERVAL '1 day'"
                where_params = (tenant_id,)
            elif days == 'yesterday':
                where_clause = "tenant_id = %s AND created_at >= CURRENT_DATE - INTERVAL '1 day' AND created_at < CURRENT_DATE"
                where_params = (tenant_id,)
            else:
                where_clause = "tenant_id = %s AND created_at >= CURRENT_TIMESTAMP - %s::interval"
                where_params = (tenant_id, f"{days} days")
            
            # Total usage count
            cursor.execute(f"""
                SELECT COUNT(*) FROM bot_usage
                WHERE {where_clause}
            """, where_params)
            total_uses = cursor.fetchone()[0]
            
            # Success count
            cursor.execute(f"""
                SELECT COUNT(*) FROM bot_usage
                WHERE {where_clause}
                AND success = true
            """, where_params)
            successful_uses = cursor.fetchone()[0]
            
            # Popular templates
            cursor.execute(f"""
                SELECT template_slug, COUNT(*) as count
                FROM bot_usage
                WHERE {where_clause}
                AND template_slug IS NOT NULL
                GROUP BY template_slug
                ORDER BY count DESC
                LIMIT 10
            """, where_params)
            popular_templates = [{'template': row[0], 'count': row[1]} for row in cursor.fetchall()]
            
            # Popular coupon codes with unique user counts (fetch all for pagination and CSV export)
            # Add template filter if provided
            template_where = ""
            template_params = list(where_params)
            if template_filter:
                template_where = " AND template_slug = %s"
                template_params.append(template_filter)
            
            # Duplicate template_params for the CTE query
            cte_params = list(template_params)
            
            cursor.execute(f"""
                WITH first_usage AS (
                    SELECT DISTINCT ON (coupon_code)
                        coupon_code,
                        chat_id
                    FROM bot_usage
                    WHERE {where_clause}
                    AND coupon_code IS NOT NULL
                    AND success = true
                    {template_where}
                    ORDER BY coupon_code, created_at ASC
                )
                SELECT 
                    bu.coupon_code, 
                    COUNT(*) as total_uses,
                    COUNT(DISTINCT bu.chat_id) as unique_users,
                    COALESCE(u.username, u.first_name, u.last_name, 'Unknown') as generated_by
                FROM bot_usage bu
                LEFT JOIN first_usage fu ON bu.coupon_code = fu.coupon_code
                LEFT JOIN bot_users u ON fu.chat_id = u.chat_id
                WHERE {where_clause}
                AND bu.coupon_code IS NOT NULL
                AND bu.success = true
                {template_where}
                GROUP BY bu.coupon_code, COALESCE(u.username, u.first_name, u.last_name, 'Unknown')
                ORDER BY total_uses DESC
            """, tuple(cte_params + template_params))
            popular_coupons = [{'coupon': row[0], 'count': row[1], 'unique_users': row[2], 'generated_by': row[3]} for row in cursor.fetchall()]
            
            # Error breakdown
            cursor.execute(f"""
                SELECT error_type, COUNT(*) as count
                FROM bot_usage
                WHERE {where_clause}
                AND success = false
                AND error_type IS NOT NULL
                GROUP BY error_type
                ORDER BY count DESC
            """, where_params)
            errors = [{'type': row[0], 'count': row[1]} for row in cursor.fetchall()]
            
            # Unique users
            cursor.execute(f"""
                SELECT COUNT(DISTINCT chat_id) FROM bot_usage
                WHERE {where_clause}
            """, where_params)
            unique_users = cursor.fetchone()[0]
            
            # Usage chart - hourly for today/yesterday, daily for longer periods
            if days in ['today', 'yesterday']:
                # Hourly aggregation for single-day views
                cursor.execute(f"""
                    SELECT 
                        EXTRACT(HOUR FROM created_at)::INTEGER as hour, 
                        DATE(created_at) as date,
                        COUNT(*) as count
                    FROM bot_usage
                    WHERE {where_clause}
                    GROUP BY EXTRACT(HOUR FROM created_at), DATE(created_at)
                    ORDER BY date DESC, hour ASC
                """, where_params)
                
                # Build hourly data map and get the date
                hourly_data = {}
                target_date = None
                for row in cursor.fetchall():
                    hour, date_val, count = row
                    hourly_data[hour] = count
                    if target_date is None:
                        target_date = date_val.isoformat()
                
                # If no data, use current date based on filter
                if target_date is None:
                    from datetime import date as dt_date, timedelta
                    if days == 'today':
                        target_date = dt_date.today().isoformat()
                    else:  # yesterday
                        target_date = (dt_date.today() - timedelta(days=1)).isoformat()
                
                # Fill in missing hours (0-23) with zero counts, include date for backward compatibility
                usage_data = [{
                    'label': f'{h:02d}:00', 
                    'date': f'{target_date}T{h:02d}:00:00',  # Backward compatibility
                    'count': hourly_data.get(h, 0)
                } for h in range(24)]
                granularity = 'hourly'
            else:
                # Daily aggregation for multi-day views
                cursor.execute(f"""
                    SELECT DATE(created_at) as date, COUNT(*) as count
                    FROM bot_usage
                    WHERE {where_clause}
                    GROUP BY DATE(created_at)
                    ORDER BY date DESC
                """, where_params)
                # Include both 'label' and 'date' for backward compatibility
                usage_data = [{'label': row[0].isoformat(), 'date': row[0].isoformat(), 'count': row[1]} for row in cursor.fetchall()]
                granularity = 'daily'
            
            success_rate = (successful_uses / total_uses * 100) if total_uses > 0 else 0
            
            return {
                'total_uses': total_uses,
                'successful_uses': successful_uses,
                'success_rate': round(success_rate, 1),
                'unique_users': unique_users,
                'popular_templates': popular_templates,
                'popular_coupons': popular_coupons,
                'errors': errors,
                'usage_data': usage_data,
                'granularity': granularity,
                'daily_usage': usage_data  # Backward compatibility
            }
    except Exception as e:
        print(f"Error getting bot stats: {e}")
        return None

def get_day_of_week_stats(days=30, tenant_id='entrylab'):
    """
    Get day-of-week or hour-of-day usage statistics.
    
    Args:
        days (int or str): Number of days to analyze, or 'today'/'yesterday' for hourly stats
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: {
            'type': 'hourly' or 'daily',
            'data': list of {label, count}
        }
    """
    try:
        if not db_pool.connection_pool:
            return {'type': 'daily', 'data': []}
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # For today/yesterday, show hourly breakdown (0-23)
            if days in ['today', 'yesterday']:
                if days == 'today':
                    where_clause = "created_at >= CURRENT_DATE AND created_at < CURRENT_DATE + INTERVAL '1 day'"
                else:  # yesterday
                    where_clause = "created_at >= CURRENT_DATE - INTERVAL '1 day' AND created_at < CURRENT_DATE"
                
                cursor.execute(f"""
                    SELECT 
                        EXTRACT(HOUR FROM created_at) as hour_num,
                        COUNT(*) as count
                    FROM bot_usage
                    WHERE {where_clause}
                    AND success = true
                    AND tenant_id = %s
                    GROUP BY hour_num
                    ORDER BY hour_num
                """, (tenant_id,))
                
                # Ensure all 24 hours are present (0-23)
                hour_data = {i: 0 for i in range(24)}
                for row in cursor.fetchall():
                    hour_num = int(row[0])
                    count = row[1]
                    hour_data[hour_num] = count
                
                # Format as list
                hourly_stats = []
                for hour in range(24):
                    hourly_stats.append({
                        'label': f"{hour:02d}:00",
                        'count': hour_data[hour]
                    })
                
                return {'type': 'hourly', 'data': hourly_stats}
            
            # For 7/30/90 days, show day-of-week breakdown
            else:
                interval = f"{days} days"
                
                cursor.execute("""
                    SELECT 
                        TO_CHAR(created_at, 'Day') as day_name,
                        EXTRACT(DOW FROM created_at) as day_num,
                        COUNT(*) as count
                    FROM bot_usage
                    WHERE created_at >= CURRENT_TIMESTAMP - %s::interval
                    AND success = true
                    AND tenant_id = %s
                    GROUP BY day_name, day_num
                    ORDER BY day_num
                """, (interval, tenant_id))
                
                # Map to ensure all days are present
                day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                day_data = {i: 0 for i in range(7)}  # 0=Sunday, 1=Monday, etc.
                
                for row in cursor.fetchall():
                    day_num = int(row[1])
                    count = row[2]
                    day_data[day_num] = count
                
                # Reorder to start with Monday (PostgreSQL: 0=Sunday, 1=Monday, ... 6=Saturday)
                ordered_days = []
                for i in range(1, 7):  # Monday to Saturday
                    ordered_days.append({
                        'label': day_names[i - 1],
                        'count': day_data[i]
                    })
                ordered_days.append({  # Sunday
                    'label': day_names[6],
                    'count': day_data[0]
                })
                
                return {'type': 'daily', 'data': ordered_days}
    except Exception as e:
        print(f"Error getting day-of-week stats: {e}")
        return {'type': 'daily', 'data': []}

# Bot user tracking for broadcasts
def track_bot_user(chat_id, coupon_code, username=None, first_name=None, last_name=None):
    """
    Track or update a bot user. Creates new user or updates last_used timestamp.
    
    Args:
        chat_id (int): Telegram chat ID
        coupon_code (str): Coupon code the user is using
        username (str, optional): Telegram username (without @)
        first_name (str, optional): User's first name
        last_name (str, optional): User's last name
    """
    try:
        if not db_pool.connection_pool:
            return
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bot_users (tenant_id, chat_id, last_coupon_code, username, first_name, last_name, first_used, last_used)
                VALUES ('entrylab', %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (tenant_id, chat_id) 
                DO UPDATE SET 
                    last_coupon_code = EXCLUDED.last_coupon_code,
                    username = COALESCE(EXCLUDED.username, bot_users.username),
                    first_name = COALESCE(EXCLUDED.first_name, bot_users.first_name),
                    last_name = COALESCE(EXCLUDED.last_name, bot_users.last_name),
                    last_used = CURRENT_TIMESTAMP
            """, (chat_id, coupon_code, username, first_name, last_name))
            conn.commit()
    except Exception as e:
        print(f"[BOT_USER] Failed to track user (non-critical): {e}")

def get_bot_user(chat_id, tenant_id='entrylab'):
    """
    Get bot user data including last coupon used, profile information, and activity stats.
    
    Args:
        chat_id (int): Telegram chat ID
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: User data with chat_id, last_coupon_code, last_used, username, first_name, last_name, total_generations, unique_coupons
        None: If user not found or error
    """
    if not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    u.chat_id, 
                    u.last_coupon_code, 
                    u.last_used, 
                    u.username, 
                    u.first_name, 
                    u.last_name,
                    COUNT(b.id) FILTER (WHERE b.success = true) as total_generations,
                    COUNT(DISTINCT b.coupon_code) FILTER (WHERE b.success = true) as unique_coupons
                FROM bot_users u
                LEFT JOIN bot_usage b ON u.chat_id = b.chat_id AND b.tenant_id = %s
                WHERE u.chat_id = %s AND u.tenant_id = %s
                GROUP BY u.chat_id, u.last_coupon_code, u.last_used, u.username, u.first_name, u.last_name
            """, (tenant_id, chat_id, tenant_id))
            row = cursor.fetchone()
            if row:
                return {
                    'chat_id': row[0],
                    'last_coupon_code': row[1],
                    'last_used': row[2].isoformat() if row[2] else None,
                    'username': row[3],
                    'first_name': row[4],
                    'last_name': row[5],
                    'total_generations': row[6] or 0,
                    'unique_coupons': row[7] or 0
                }
            return None
    except Exception as e:
        print(f"[DB] Error getting bot user: {e}")
        return None

def get_active_bot_users(days=30, tenant_id='entrylab'):
    """
    Get all active bot users within the last N days for broadcasting.
    
    Args:
        days (int): Number of days to consider "active" (default: 30)
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        list: List of dicts with chat_id and last_coupon_code
    """
    try:
        if not db_pool.connection_pool:
            return []
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            interval = f"{days} days"
            
            cursor.execute("""
                SELECT chat_id, last_coupon_code, last_used
                FROM bot_users
                WHERE last_used >= CURRENT_TIMESTAMP - %s::interval
                AND tenant_id = %s
                ORDER BY last_used DESC
            """, (interval, tenant_id))
            
            users = []
            for row in cursor.fetchall():
                users.append({
                    'chat_id': row[0],
                    'last_coupon_code': row[1],
                    'last_used': row[2].isoformat() if row[2] else None
                })
            return users
    except Exception as e:
        print(f"Error getting active bot users: {e}")
        return []

def get_bot_user_count(days=30, tenant_id='entrylab'):
    """
    Get count of active bot users within the last N days.
    
    Args:
        days (int): Number of days to consider "active" (default: 30)
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        int: Number of active users
    """
    try:
        if not db_pool.connection_pool:
            return 0
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            interval = f"{days} days"
            
            cursor.execute("""
                SELECT COUNT(*) FROM bot_users
                WHERE last_used >= CURRENT_TIMESTAMP - %s::interval
                AND tenant_id = %s
            """, (interval, tenant_id))
            return cursor.fetchone()[0]
    except Exception as e:
        print(f"Error getting bot user count: {e}")
        return 0

def get_retention_rates(tenant_id='entrylab'):
    """
    Calculate Day 1, Day 7, and Day 30 retention rates.
    
    Retention is calculated as the percentage of users who returned to use the bot
    after their first usage.
    
    Args:
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: {
            'day1': float (0-100),
            'day7': float (0-100),
            'day30': float (0-100)
        }
    """
    try:
        if not db_pool.connection_pool:
            return {'day1': 0, 'day7': 0, 'day30': 0}
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Day 1 retention: Users who joined 2+ days ago and came back within 24-48 hours
            cursor.execute("""
                WITH cohort AS (
                    SELECT chat_id, first_used
                    FROM bot_users
                    WHERE first_used < CURRENT_TIMESTAMP - INTERVAL '2 days'
                    AND tenant_id = %s
                ),
                returned AS (
                    SELECT DISTINCT c.chat_id
                    FROM cohort c
                    INNER JOIN bot_usage b ON c.chat_id = b.chat_id
                    WHERE b.created_at >= c.first_used + INTERVAL '1 day'
                    AND b.created_at < c.first_used + INTERVAL '2 days'
                    AND b.success = true
                    AND b.tenant_id = %s
                )
                SELECT 
                    COUNT(DISTINCT c.chat_id) as cohort_size,
                    COUNT(DISTINCT r.chat_id) as returned_count
                FROM cohort c
                LEFT JOIN returned r ON c.chat_id = r.chat_id
            """, (tenant_id, tenant_id))
            row = cursor.fetchone()
            day1_cohort = row[0] or 0
            day1_returned = row[1] or 0
            day1_retention = round((day1_returned / day1_cohort * 100), 1) if day1_cohort > 0 else 0
            
            # Day 7 retention: Users who joined 14+ days ago and came back within days 7-14
            cursor.execute("""
                WITH cohort AS (
                    SELECT chat_id, first_used
                    FROM bot_users
                    WHERE first_used < CURRENT_TIMESTAMP - INTERVAL '14 days'
                    AND tenant_id = %s
                ),
                returned AS (
                    SELECT DISTINCT c.chat_id
                    FROM cohort c
                    INNER JOIN bot_usage b ON c.chat_id = b.chat_id
                    WHERE b.created_at >= c.first_used + INTERVAL '7 days'
                    AND b.created_at < c.first_used + INTERVAL '14 days'
                    AND b.success = true
                    AND b.tenant_id = %s
                )
                SELECT 
                    COUNT(DISTINCT c.chat_id) as cohort_size,
                    COUNT(DISTINCT r.chat_id) as returned_count
                FROM cohort c
                LEFT JOIN returned r ON c.chat_id = r.chat_id
            """, (tenant_id, tenant_id))
            row = cursor.fetchone()
            day7_cohort = row[0] or 0
            day7_returned = row[1] or 0
            day7_retention = round((day7_returned / day7_cohort * 100), 1) if day7_cohort > 0 else 0
            
            # Day 30 retention: Users who joined 60+ days ago and came back within days 30-60
            cursor.execute("""
                WITH cohort AS (
                    SELECT chat_id, first_used
                    FROM bot_users
                    WHERE first_used < CURRENT_TIMESTAMP - INTERVAL '60 days'
                    AND tenant_id = %s
                ),
                returned AS (
                    SELECT DISTINCT c.chat_id
                    FROM cohort c
                    INNER JOIN bot_usage b ON c.chat_id = b.chat_id
                    WHERE b.created_at >= c.first_used + INTERVAL '30 days'
                    AND b.created_at < c.first_used + INTERVAL '60 days'
                    AND b.success = true
                    AND b.tenant_id = %s
                )
                SELECT 
                    COUNT(DISTINCT c.chat_id) as cohort_size,
                    COUNT(DISTINCT r.chat_id) as returned_count
                FROM cohort c
                LEFT JOIN returned r ON c.chat_id = r.chat_id
            """, (tenant_id, tenant_id))
            row = cursor.fetchone()
            day30_cohort = row[0] or 0
            day30_returned = row[1] or 0
            day30_retention = round((day30_returned / day30_cohort * 100), 1) if day30_cohort > 0 else 0
            
            return {
                'day1': day1_retention,
                'day7': day7_retention,
                'day30': day30_retention
            }
    except Exception as e:
        print(f"Error calculating retention rates: {e}")
        return {'day1': 0, 'day7': 0, 'day30': 0}

def get_all_bot_users(limit=100, offset=0, tenant_id='entrylab'):
    """
    Get all bot users with their activity stats.
    
    Args:
        limit (int): Number of users to return
        offset (int): Offset for pagination
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: {
            'users': list of user dicts with stats,
            'total': total count of users
        }
    """
    try:
        if not db_pool.connection_pool:
            return {'users': [], 'total': 0}
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get total count
            cursor.execute("SELECT COUNT(*) FROM bot_users WHERE tenant_id = %s", (tenant_id,))
            total = cursor.fetchone()[0]
            
            # Get users with stats (count only successful generations)
            cursor.execute("""
                SELECT 
                    u.chat_id,
                    u.username,
                    u.first_name,
                    u.last_name,
                    u.first_used,
                    u.last_used,
                    COUNT(b.id) FILTER (WHERE b.success = true) as total_generations,
                    COUNT(DISTINCT b.coupon_code) FILTER (WHERE b.success = true) as unique_coupons
                FROM bot_users u
                LEFT JOIN bot_usage b ON u.chat_id = b.chat_id AND b.tenant_id = %s
                WHERE u.tenant_id = %s
                GROUP BY u.chat_id, u.username, u.first_name, u.last_name, u.first_used, u.last_used
                ORDER BY COALESCE(COUNT(b.id) FILTER (WHERE b.success = true), 0) DESC, u.last_used DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, (tenant_id, tenant_id, limit, offset))
            
            users = []
            for row in cursor.fetchall():
                users.append({
                    'chat_id': row[0],
                    'username': row[1],
                    'first_name': row[2],
                    'last_name': row[3],
                    'first_used': row[4].isoformat() if row[4] else None,
                    'last_used': row[5].isoformat() if row[5] else None,
                    'total_generations': row[6],
                    'unique_coupons': row[7]
                })
            
            return {'users': users, 'total': total}
    except Exception as e:
        print(f"Error getting all bot users: {e}")
        return {'users': [], 'total': 0}

def get_user_activity_history(chat_id, limit=100, tenant_id='entrylab'):
    """
    Get complete activity history for a specific user.
    
    Args:
        chat_id (int): Telegram chat ID
        limit (int): Max number of records to return
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        list: List of activity records for the user
    """
    try:
        if not db_pool.connection_pool:
            return []
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    created_at,
                    template_slug,
                    coupon_code,
                    success,
                    error_type
                FROM bot_usage
                WHERE chat_id = %s AND tenant_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (chat_id, tenant_id, limit))
            
            history = []
            for row in cursor.fetchall():
                history.append({
                    'timestamp': row[0].isoformat() if row[0] else None,
                    'template': row[1],
                    'coupon_code': row[2],
                    'success': row[3],
                    'error_type': row[4]
                })
            
            return history
    except Exception as e:
        print(f"Error getting user activity history: {e}")
        return []

def get_invalid_coupon_attempts(limit=100, offset=0, template_filter=None, days=None, tenant_id='entrylab'):
    """
    Get all invalid coupon validation attempts.
    
    Args:
        limit (int): Number of records to return
        offset (int): Offset for pagination
        template_filter (str, optional): Filter by template name
        days (int, optional): Filter by number of days (e.g., 7 for last 7 days)
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: {
            'attempts': list of invalid coupon attempts,
            'total': total count
        }
    """
    try:
        if not db_pool.connection_pool:
            return {'attempts': [], 'total': 0}
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build query with optional template filter and date range
            where_clause = "WHERE success = FALSE AND b.tenant_id = %s"
            params = [tenant_id]
            
            if days is not None:
                where_clause += " AND created_at >= NOW() - INTERVAL '%s days'"
                params.append(days)
            
            if template_filter:
                where_clause += " AND template_slug = %s"
                params.append(template_filter)
            
            # Get total count
            count_where = where_clause.replace("b.tenant_id", "tenant_id")
            cursor.execute(f"SELECT COUNT(*) FROM bot_usage {count_where}", params)
            total = cursor.fetchone()[0]
            
            # Get attempts with user info
            query_params = params + [limit, offset]
            cursor.execute(f"""
                SELECT 
                    b.coupon_code,
                    b.template_slug,
                    b.created_at,
                    b.error_type,
                    b.chat_id,
                    u.username,
                    u.first_name,
                    u.last_name,
                    COUNT(*) OVER (PARTITION BY b.coupon_code) as attempt_count
                FROM bot_usage b
                LEFT JOIN bot_users u ON b.chat_id = u.chat_id AND u.tenant_id = %s
                {where_clause}
                ORDER BY b.created_at DESC
                LIMIT %s OFFSET %s
            """, [tenant_id] + query_params)
            
            attempts = []
            for row in cursor.fetchall():
                attempts.append({
                    'coupon_code': row[0],
                    'template_name': row[1],
                    'timestamp': row[2].isoformat() if row[2] else None,
                    'error_type': row[3],
                    'chat_id': row[4],
                    'username': row[5],
                    'first_name': row[6],
                    'last_name': row[7],
                    'attempt_count': row[8]
                })
            
            return {'attempts': attempts, 'total': total}
    except Exception as e:
        print(f"Error getting invalid coupon attempts: {e}")
        return {'attempts': [], 'total': 0}

def remove_bot_user(chat_id, tenant_id='entrylab'):
    """
    Remove a bot user (e.g., when they block the bot).
    
    Args:
        chat_id (int): Telegram chat ID to remove
        tenant_id (str): Tenant ID (default: 'entrylab')
    """
    try:
        if not db_pool.connection_pool:
            return
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bot_users WHERE chat_id = %s AND tenant_id = %s", (chat_id, tenant_id))
            conn.commit()
    except Exception as e:
        print(f"[BOT_USER] Failed to remove user {chat_id}: {e}")

# Broadcast job management
def create_broadcast_job(message, target_days, total_users, tenant_id='entrylab'):
    """
    Create a new broadcast job.
    
    Args:
        message (str): Message to broadcast
        target_days (int): Days of activity to target
        total_users (int): Total number of users to broadcast to
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        int: Job ID
    """
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO broadcast_jobs (tenant_id, message, target_days, status, total_users)
                VALUES (%s, %s, %s, 'pending', %s)
                RETURNING id
            """, (tenant_id, message, target_days, total_users))
            job_id = cursor.fetchone()[0]
            conn.commit()
            return job_id
    except Exception as e:
        print(f"Error creating broadcast job: {e}")
        return None

def update_broadcast_job(job_id, status=None, sent_count=None, failed_count=None, completed=False, tenant_id='entrylab'):
    """
    Update broadcast job progress.
    
    Args:
        job_id (int): Job ID
        status (str): Job status ('pending', 'processing', 'completed', 'failed')
        sent_count (int): Number of successfully sent messages
        failed_count (int): Number of failed messages
        completed (bool): Whether job is completed
        tenant_id (str): Tenant ID (default: 'entrylab')
    """
    try:
        if not db_pool.connection_pool:
            return
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if status is not None:
                updates.append("status = %s")
                params.append(status)
            
            if sent_count is not None:
                updates.append("sent_count = %s")
                params.append(sent_count)
            
            if failed_count is not None:
                updates.append("failed_count = %s")
                params.append(failed_count)
            
            if completed:
                updates.append("completed_at = CURRENT_TIMESTAMP")
            
            if updates:
                params.append(job_id)
                params.append(tenant_id)
                query = f"UPDATE broadcast_jobs SET {', '.join(updates)} WHERE id = %s AND tenant_id = %s"
                cursor.execute(query, params)
                conn.commit()
    except Exception as e:
        print(f"Error updating broadcast job {job_id}: {e}")

def get_broadcast_job(job_id, tenant_id='entrylab'):
    """
    Get broadcast job details.
    
    Args:
        job_id (int): Job ID
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: Job details or None if not found
    """
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, message, target_days, status, total_users, 
                       sent_count, failed_count, created_at, completed_at
                FROM broadcast_jobs
                WHERE id = %s AND tenant_id = %s
            """, (job_id, tenant_id))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': row[0],
                    'message': row[1],
                    'target_days': row[2],
                    'status': row[3],
                    'total_users': row[4],
                    'sent_count': row[5],
                    'failed_count': row[6],
                    'created_at': row[7].isoformat() if row[7] else None,
                    'completed_at': row[8].isoformat() if row[8] else None
                }
            return None
    except Exception as e:
        print(f"Error getting broadcast job {job_id}: {e}")
        return None

def get_recent_broadcast_jobs(limit=10, tenant_id='entrylab'):
    """
    Get recent broadcast jobs.
    
    Args:
        limit (int): Number of jobs to return
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        list: List of job dicts
    """
    try:
        if not db_pool.connection_pool:
            return []
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, message, target_days, status, total_users, 
                       sent_count, failed_count, created_at, completed_at
                FROM broadcast_jobs
                WHERE tenant_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (tenant_id, limit))
            
            jobs = []
            for row in cursor.fetchall():
                jobs.append({
                    'id': row[0],
                    'message': row[1],
                    'target_days': row[2],
                    'status': row[3],
                    'total_users': row[4],
                    'sent_count': row[5],
                    'failed_count': row[6],
                    'created_at': row[7].isoformat() if row[7] else None,
                    'completed_at': row[8].isoformat() if row[8] else None
                })
            return jobs
    except Exception as e:
        print(f"Error getting recent broadcast jobs: {e}")
        return []

# Forex signals operations
def create_forex_signal(signal_type, pair, timeframe, entry_price, take_profit=None, 
                       stop_loss=None, rsi_value=None, macd_value=None, atr_value=None,
                       bot_type='aggressive', indicators_used=None, notes=None,
                       take_profit_2=None, take_profit_3=None,
                       tp1_percentage=100, tp2_percentage=0, tp3_percentage=0,
                       status='draft', tenant_id='entrylab'):
    """
    Create a new forex signal with multi-TP support.
    
    Args:
        signal_type (str): 'BUY' or 'SELL'
        pair (str): Currency pair (e.g., 'XAU/USD', 'EUR/USD')
        timeframe (str): Timeframe (e.g., '15m', '30m', '1h')
        entry_price (float): Entry price for the signal
        take_profit (float, optional): Take profit price (TP1)
        stop_loss (float, optional): Stop loss price
        rsi_value (float, optional): RSI indicator value
        macd_value (float, optional): MACD indicator value
        atr_value (float, optional): ATR indicator value
        bot_type (str): Bot type identifier
        indicators_used (str, optional): JSON string of indicators used
        notes (str, optional): Notes about the signal
        take_profit_2 (float, optional): Second take profit price (TP2)
        take_profit_3 (float, optional): Third take profit price (TP3)
        tp1_percentage (int): Percentage to close at TP1 (default 100)
        tp2_percentage (int): Percentage to close at TP2 (default 0)
        tp3_percentage (int): Percentage to close at TP3 (default 0)
        status (str): Initial status ('draft', 'pending', etc.) - default 'draft'
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        int: Signal ID
    """
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO forex_signals 
                (tenant_id, signal_type, pair, timeframe, entry_price, take_profit, stop_loss,
                 rsi_value, macd_value, atr_value, status, bot_type, indicators_used, notes,
                 take_profit_2, take_profit_3, tp1_percentage, tp2_percentage, tp3_percentage)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (tenant_id, signal_type, pair, timeframe, entry_price, take_profit, stop_loss,
                  rsi_value, macd_value, atr_value, status, bot_type, indicators_used, notes,
                  take_profit_2, take_profit_3, tp1_percentage, tp2_percentage, tp3_percentage))
            signal_id = cursor.fetchone()[0]
            conn.commit()
            return signal_id
    except Exception as e:
        print(f"Error creating forex signal: {e}")
        raise

def update_signal_status(signal_id, new_status, telegram_message_id=None, tenant_id='entrylab'):
    """
    Update a signal's status (e.g., from 'draft' to 'pending' or 'broadcast_failed').
    
    Args:
        signal_id (int): The signal ID to update
        new_status (str): New status ('pending', 'broadcast_failed', etc.)
        telegram_message_id (int, optional): Telegram message ID if broadcast succeeded
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        bool: True if update succeeded, False otherwise
    """
    conn = None
    try:
        conn = db_pool.connection_pool.getconn()
        cursor = conn.cursor()
        if telegram_message_id is not None:
            cursor.execute("""
                UPDATE forex_signals 
                SET status = %s, telegram_message_id = %s
                WHERE id = %s AND tenant_id = %s
            """, (new_status, telegram_message_id, signal_id, tenant_id))
        else:
            cursor.execute("""
                UPDATE forex_signals 
                SET status = %s
                WHERE id = %s AND tenant_id = %s
            """, (new_status, signal_id, tenant_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating signal status: {e}")
        if conn:
            try:
                conn.rollback()
            except Exception as rollback_error:
                print(f"Rollback failed: {rollback_error}")
        return False
    finally:
        if conn:
            try:
                db_pool.connection_pool.putconn(conn)
            except Exception as cleanup_error:
                print(f"Connection cleanup error: {cleanup_error}")

def get_forex_signals(status=None, limit=100, tenant_id='entrylab'):
    """
    Get forex signals with optional status filtering.
    
    Args:
        status (str, optional): Filter by status ('pending', 'won', 'lost', 'expired')
        limit (int): Maximum number of signals to return (default: 100)
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        list: List of signal dictionaries
    """
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            if status:
                cursor.execute("""
                    SELECT id, signal_type, pair, timeframe, entry_price, take_profit, 
                           stop_loss, status, rsi_value, macd_value, atr_value, 
                           posted_at, closed_at, result_pips, bot_type,
                           breakeven_set, guidance_count, last_guidance_at,
                           last_progress_zone, last_caution_zone,
                           original_rsi, original_macd, original_adx, original_stoch_k,
                           last_revalidation_at, revalidation_count, thesis_status,
                           thesis_changed_at, timeout_notified, original_indicators_json,
                           take_profit_2, take_profit_3,
                           tp1_percentage, tp2_percentage, tp3_percentage,
                           tp1_hit, tp2_hit, tp3_hit,
                           tp1_hit_at, tp2_hit_at, tp3_hit_at,
                           breakeven_triggered, breakeven_triggered_at, close_price, effective_sl
                    FROM forex_signals
                    WHERE tenant_id = %s AND status = %s
                    ORDER BY posted_at DESC
                    LIMIT %s
                """, (tenant_id, status, limit))
            else:
                cursor.execute("""
                    SELECT id, signal_type, pair, timeframe, entry_price, take_profit, 
                           stop_loss, status, rsi_value, macd_value, atr_value, 
                           posted_at, closed_at, result_pips, bot_type,
                           breakeven_set, guidance_count, last_guidance_at,
                           last_progress_zone, last_caution_zone,
                           original_rsi, original_macd, original_adx, original_stoch_k,
                           last_revalidation_at, revalidation_count, thesis_status,
                           thesis_changed_at, timeout_notified, original_indicators_json,
                           take_profit_2, take_profit_3,
                           tp1_percentage, tp2_percentage, tp3_percentage,
                           tp1_hit, tp2_hit, tp3_hit,
                           tp1_hit_at, tp2_hit_at, tp3_hit_at,
                           breakeven_triggered, breakeven_triggered_at, close_price, effective_sl
                    FROM forex_signals
                    WHERE tenant_id = %s AND status NOT IN ('draft', 'broadcast_failed')
                    ORDER BY posted_at DESC
                    LIMIT %s
                """, (tenant_id, limit))
            
            signals = []
            for row in cursor.fetchall():
                signals.append({
                    'id': row[0],
                    'signal_type': row[1],
                    'pair': row[2],
                    'timeframe': row[3],
                    'entry_price': float(row[4]) if row[4] else None,
                    'take_profit': float(row[5]) if row[5] else None,
                    'stop_loss': float(row[6]) if row[6] else None,
                    'status': row[7],
                    'rsi_value': float(row[8]) if row[8] else None,
                    'macd_value': float(row[9]) if row[9] else None,
                    'atr_value': float(row[10]) if row[10] else None,
                    'posted_at': row[11].isoformat() if row[11] else None,
                    'closed_at': row[12].isoformat() if row[12] else None,
                    'result_pips': float(row[13]) if row[13] else None,
                    'bot_type': row[14] if row[14] else 'custom',
                    'breakeven_set': row[15] or False,
                    'guidance_count': row[16] or 0,
                    'last_guidance_at': row[17].isoformat() if row[17] else None,
                    'last_progress_zone': row[18] or 0,
                    'last_caution_zone': row[19] or 0,
                    'original_rsi': float(row[20]) if row[20] else None,
                    'original_macd': float(row[21]) if row[21] else None,
                    'original_adx': float(row[22]) if row[22] else None,
                    'original_stoch_k': float(row[23]) if row[23] else None,
                    'last_revalidation_at': row[24].isoformat() if row[24] else None,
                    'revalidation_count': row[25] or 0,
                    'thesis_status': row[26] or 'intact',
                    'thesis_changed_at': row[27].isoformat() if row[27] else None,
                    'timeout_notified': row[28] or False,
                    'original_indicators_json': row[29] if row[29] else None,
                    'take_profit_2': float(row[30]) if row[30] else None,
                    'take_profit_3': float(row[31]) if row[31] else None,
                    'tp1_percentage': row[32] or 100,
                    'tp2_percentage': row[33] or 0,
                    'tp3_percentage': row[34] or 0,
                    'tp1_hit': row[35] or False,
                    'tp2_hit': row[36] or False,
                    'tp3_hit': row[37] or False,
                    'tp1_hit_at': row[38].isoformat() if row[38] else None,
                    'tp2_hit_at': row[39].isoformat() if row[39] else None,
                    'tp3_hit_at': row[40].isoformat() if row[40] else None,
                    'breakeven_triggered': row[41] or False,
                    'breakeven_triggered_at': row[42].isoformat() if row[42] else None,
                    'close_price': float(row[43]) if row[43] else None,
                    'effective_sl': float(row[44]) if row[44] else None
                })
            return signals
    except Exception as e:
        print(f"Error getting forex signals: {e}")
        return []

def update_forex_signal_status(signal_id, status, result_pips=None, close_price=None, tenant_id='entrylab'):
    """
    Update forex signal status and optionally set result.
    
    Args:
        signal_id (int): Signal ID to update
        status (str): New status ('pending', 'won', 'lost', 'expired')
        result_pips (float, optional): Result in pips (positive for profit, negative for loss)
        close_price (float, optional): Price at which the signal closed
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        bool: True if successful
    """
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            if result_pips is not None and close_price is not None:
                cursor.execute("""
                    UPDATE forex_signals
                    SET status = %s, result_pips = %s, close_price = %s, closed_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND tenant_id = %s
                """, (status, result_pips, close_price, signal_id, tenant_id))
            elif result_pips is not None:
                cursor.execute("""
                    UPDATE forex_signals
                    SET status = %s, result_pips = %s, closed_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND tenant_id = %s
                """, (status, result_pips, signal_id, tenant_id))
            elif close_price is not None:
                cursor.execute("""
                    UPDATE forex_signals
                    SET status = %s, close_price = %s, closed_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND tenant_id = %s
                """, (status, close_price, signal_id, tenant_id))
            else:
                cursor.execute("""
                    UPDATE forex_signals
                    SET status = %s, closed_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND tenant_id = %s
                """, (status, signal_id, tenant_id))
            
            conn.commit()
            
            if status in ('won', 'lost', 'expired', 'cancelled'):
                promoted = promote_queued_bot()
                if promoted:
                    print(f"[SIGNAL CLOSE] Automatically activated queued bot: {promoted}")
            
            return True
    except Exception as e:
        print(f"Error updating forex signal status: {e}")
        raise

def get_forex_stats(days=7, tenant_id='entrylab'):
    """
    Get forex signals statistics for the last N days.
    
    Args:
        days (int): Number of days to analyze (default: 7)
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: Statistics including total signals, win rate, profit/loss, etc.
    """
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Total signals in the period
            cursor.execute("""
                SELECT COUNT(*) FROM forex_signals
                WHERE tenant_id = %s AND posted_at >= CURRENT_TIMESTAMP - %s::interval
            """, (tenant_id, f"{days} days"))
            total_signals = cursor.fetchone()[0]
            
            # Closed signals (won + lost)
            cursor.execute("""
                SELECT COUNT(*) FROM forex_signals
                WHERE tenant_id = %s AND posted_at >= CURRENT_TIMESTAMP - %s::interval
                AND status IN ('won', 'lost')
            """, (tenant_id, f"{days} days"))
            closed_signals = cursor.fetchone()[0]
            
            # Won signals
            cursor.execute("""
                SELECT COUNT(*) FROM forex_signals
                WHERE tenant_id = %s AND posted_at >= CURRENT_TIMESTAMP - %s::interval
                AND status = 'won'
            """, (tenant_id, f"{days} days"))
            won_signals = cursor.fetchone()[0]
            
            # Lost signals
            cursor.execute("""
                SELECT COUNT(*) FROM forex_signals
                WHERE tenant_id = %s AND posted_at >= CURRENT_TIMESTAMP - %s::interval
                AND status = 'lost'
            """, (tenant_id, f"{days} days"))
            lost_signals = cursor.fetchone()[0]
            
            # Pending signals
            cursor.execute("""
                SELECT COUNT(*) FROM forex_signals
                WHERE tenant_id = %s AND posted_at >= CURRENT_TIMESTAMP - %s::interval
                AND status = 'pending'
            """, (tenant_id, f"{days} days"))
            pending_signals = cursor.fetchone()[0]
            
            # Total pips (profit/loss)
            cursor.execute("""
                SELECT COALESCE(SUM(result_pips), 0) FROM forex_signals
                WHERE tenant_id = %s AND posted_at >= CURRENT_TIMESTAMP - %s::interval
                AND result_pips IS NOT NULL
            """, (tenant_id, f"{days} days"))
            total_pips = float(cursor.fetchone()[0])
            
            # Signals by pair
            cursor.execute("""
                SELECT pair, COUNT(*) as count
                FROM forex_signals
                WHERE tenant_id = %s AND posted_at >= CURRENT_TIMESTAMP - %s::interval
                GROUP BY pair
                ORDER BY count DESC
                LIMIT 10
            """, (tenant_id, f"{days} days"))
            signals_by_pair = [{'pair': row[0], 'count': row[1]} for row in cursor.fetchall()]
            
            # Daily signal count
            cursor.execute("""
                SELECT DATE(posted_at) as date, COUNT(*) as count
                FROM forex_signals
                WHERE tenant_id = %s AND posted_at >= CURRENT_TIMESTAMP - %s::interval
                GROUP BY DATE(posted_at)
                ORDER BY date DESC
            """, (tenant_id, f"{days} days"))
            daily_signals = [{'date': row[0].isoformat(), 'count': row[1]} for row in cursor.fetchall()]
            
            # Calculate win rate
            win_rate = (won_signals / closed_signals * 100) if closed_signals > 0 else 0
            
            return {
                'total_signals': total_signals,
                'closed_signals': closed_signals,
                'won_signals': won_signals,
                'lost_signals': lost_signals,
                'pending_signals': pending_signals,
                'win_rate': round(win_rate, 1),
                'total_pips': round(total_pips, 2),
                'signals_by_pair': signals_by_pair,
                'daily_signals': daily_signals
            }
    except Exception as e:
        print(f"Error getting forex stats: {e}")
        return None

def get_forex_signals_by_period(period='today', tenant_id='entrylab'):
    """
    Get forex signals for a specific time period.
    
    Args:
        period (str): Time period - 'today', 'yesterday', 'week', 'month'
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        list: List of signals for that period
    """
    try:
        if not db_pool.connection_pool:
            return []
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            if period == 'today':
                query = """
                    SELECT id, signal_type, pair, timeframe, entry_price, take_profit, 
                           stop_loss, status, rsi_value, macd_value, atr_value, 
                           posted_at, closed_at, result_pips
                    FROM forex_signals
                    WHERE posted_at >= CURRENT_DATE AND tenant_id = %s
                    ORDER BY posted_at DESC
                """
            elif period == 'yesterday':
                query = """
                    SELECT id, signal_type, pair, timeframe, entry_price, take_profit, 
                           stop_loss, status, rsi_value, macd_value, atr_value, 
                           posted_at, closed_at, result_pips
                    FROM forex_signals
                    WHERE posted_at >= CURRENT_DATE - INTERVAL '1 day'
                    AND posted_at < CURRENT_DATE AND tenant_id = %s
                    ORDER BY posted_at DESC
                """
            elif period == 'week':
                query = """
                    SELECT id, signal_type, pair, timeframe, entry_price, take_profit, 
                           stop_loss, status, rsi_value, macd_value, atr_value, 
                           posted_at, closed_at, result_pips
                    FROM forex_signals
                    WHERE posted_at >= CURRENT_DATE - INTERVAL '7 days' AND tenant_id = %s
                    ORDER BY posted_at DESC
                """
            else:
                query = """
                    SELECT id, signal_type, pair, timeframe, entry_price, take_profit, 
                           stop_loss, status, rsi_value, macd_value, atr_value, 
                           posted_at, closed_at, result_pips
                    FROM forex_signals
                    WHERE posted_at >= CURRENT_DATE - INTERVAL '30 days' AND tenant_id = %s
                    ORDER BY posted_at DESC
                """
            
            cursor.execute(query, (tenant_id,))
            
            signals = []
            for row in cursor.fetchall():
                signals.append({
                    'id': row[0],
                    'signal_type': row[1],
                    'pair': row[2],
                    'timeframe': row[3],
                    'entry_price': float(row[4]) if row[4] else None,
                    'take_profit': float(row[5]) if row[5] else None,
                    'stop_loss': float(row[6]) if row[6] else None,
                    'status': row[7],
                    'rsi_value': float(row[8]) if row[8] else None,
                    'macd_value': float(row[9]) if row[9] else None,
                    'atr_value': float(row[10]) if row[10] else None,
                    'posted_at': row[11].isoformat() if row[11] else None,
                    'closed_at': row[12].isoformat() if row[12] else None,
                    'result_pips': float(row[13]) if row[13] else None
                })
            return signals
    except Exception as e:
        print(f"Error getting forex signals by period: {e}")
        return []

def get_forex_stats_by_period(period='today', tenant_id='entrylab'):
    """
    Get forex statistics for a specific time period.
    
    Args:
        period (str): 'today', 'yesterday', 'week', 'month'
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: Statistics for that period
    """
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            if period == 'today':
                time_filter = "posted_at >= CURRENT_DATE"
            elif period == 'yesterday':
                time_filter = "posted_at >= CURRENT_DATE - INTERVAL '1 day' AND posted_at < CURRENT_DATE"
            elif period == 'week':
                time_filter = "posted_at >= CURRENT_DATE - INTERVAL '7 days'"
            else:
                time_filter = "posted_at >= CURRENT_DATE - INTERVAL '30 days'"
            
            cursor.execute(f"""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) as won,
                    SUM(CASE WHEN status = 'lost' THEN 1 ELSE 0 END) as lost,
                    SUM(CASE WHEN status = 'expired' THEN 1 ELSE 0 END) as expired,
                    COALESCE(SUM(result_pips), 0) as total_pips
                FROM forex_signals
                WHERE {time_filter} AND tenant_id = %s
            """, (tenant_id,))
            
            row = cursor.fetchone()
            
            return {
                'total_signals': row[0],
                'won_signals': row[1] if row[1] else 0,
                'lost_signals': row[2] if row[2] else 0,
                'expired_signals': row[3] if row[3] else 0,
                'total_pips': float(row[4]) if row[4] else 0.0
            }
    except Exception as e:
        print(f"Error getting forex stats by period: {e}")
        return None

def get_daily_pnl(tenant_id='entrylab'):
    """
    Get today's profit/loss in pips for daily loss cap checking.
    
    Args:
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        float: Total pips for today (negative = loss)
    """
    try:
        if not db_pool.connection_pool:
            return 0.0
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COALESCE(SUM(result_pips), 0) as daily_pips
                FROM forex_signals
                WHERE posted_at >= CURRENT_DATE
                AND status IN ('won', 'lost', 'expired')
                AND tenant_id = %s
            """, (tenant_id,))
            
            row = cursor.fetchone()
            return float(row[0]) if row and row[0] else 0.0
    except Exception as e:
        print(f"Error getting daily P/L: {e}")
        return 0.0

def get_signal_metrics(tenant_id='entrylab'):
    """
    Get advanced signal metrics: avg hold time and avg pips per trade.
    
    Args:
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: {avg_hold_time_minutes, avg_pips_per_trade, total_completed}
    """
    try:
        if not db_pool.connection_pool:
            return {'avg_hold_time_minutes': 0, 'avg_pips_per_trade': 0, 'total_completed': 0}
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    AVG(EXTRACT(EPOCH FROM (closed_at - posted_at)) / 60) as avg_hold_minutes,
                    AVG(result_pips) as avg_pips,
                    COUNT(*) as total_completed
                FROM forex_signals
                WHERE status IN ('won', 'lost')
                AND closed_at IS NOT NULL
                AND posted_at IS NOT NULL
                AND tenant_id = %s
            """, (tenant_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'avg_hold_time_minutes': float(row[0]) if row[0] else 0,
                    'avg_pips_per_trade': float(row[1]) if row[1] else 0,
                    'total_completed': int(row[2]) if row[2] else 0
                }
            return {'avg_hold_time_minutes': 0, 'avg_pips_per_trade': 0, 'total_completed': 0}
    except Exception as e:
        print(f"Error getting signal metrics: {e}")
        return {'avg_hold_time_minutes': 0, 'avg_pips_per_trade': 0, 'total_completed': 0}

def get_last_completed_signal(tenant_id='entrylab'):
    """
    Get the most recently closed signal for back-to-back throttle checking.
    
    Args:
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: Last completed signal with status and closed_at, or None
    """
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, status, closed_at, result_pips
                FROM forex_signals
                WHERE tenant_id = %s AND status IN ('won', 'lost')
                AND closed_at IS NOT NULL
                ORDER BY closed_at DESC
                LIMIT 1
            """, (tenant_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'status': row[1],
                    'closed_at': row[2],
                    'result_pips': float(row[3]) if row[3] else 0.0
                }
            return None
    except Exception as e:
        print(f"Error getting last completed signal: {e}")
        return None

def get_recent_signal_streak(limit=5, tenant_id='entrylab'):
    """
    Get the recent win/loss streak for context-aware AI prompts.
    
    Args:
        limit: Number of recent signals to check
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: Streak info with type ('win', 'loss', 'mixed'), count, and recent signals
    """
    try:
        if not db_pool.connection_pool:
            return {'type': 'mixed', 'count': 0, 'signals': []}
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, status, result_pips, closed_at
                FROM forex_signals
                WHERE tenant_id = %s AND status IN ('won', 'lost')
                ORDER BY closed_at DESC
                LIMIT %s
            """, (tenant_id, limit))
            
            signals = []
            for row in cursor.fetchall():
                signals.append({
                    'id': row[0],
                    'status': row[1],
                    'result_pips': float(row[2]) if row[2] else 0.0,
                    'closed_at': row[3]
                })
            
            if not signals:
                return {'type': 'mixed', 'count': 0, 'signals': []}
            
            first_status = signals[0]['status']
            streak_count = 0
            for s in signals:
                if s['status'] == first_status:
                    streak_count += 1
                else:
                    break
            
            return {
                'type': 'win' if first_status == 'won' else 'loss',
                'count': streak_count,
                'signals': signals
            }
    except Exception as e:
        print(f"Error getting recent streak: {e}")
        return {'type': 'mixed', 'count': 0, 'signals': []}

# Forex configuration operations
def initialize_default_forex_config():
    """
    Initialize forex config with default values if not already set.
    Should be called on startup.
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        default_config = {
            'rsi_oversold': '40',
            'rsi_overbought': '60',
            'adx_threshold': '15',
            'atr_sl_multiplier': '2.0',
            'atr_tp_multiplier': '4.0',
            'trading_start_hour': '8',
            'trading_end_hour': '22',
            'daily_loss_cap_pips': '50.0',
            'back_to_back_throttle_minutes': '30',
            'session_filter_enabled': 'true',
            'session_start_hour_utc': '8',
            'session_end_hour_utc': '21'
        }
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            for key, value in default_config.items():
                cursor.execute("""
                    INSERT INTO forex_config (tenant_id, setting_key, setting_value, updated_at)
                    VALUES ('entrylab', %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (tenant_id, setting_key) 
                    DO NOTHING
                """, (key, value))
            
            conn.commit()
            print("✅ Forex config initialized with defaults")
            return True
    except Exception as e:
        print(f"Error initializing forex config: {e}")
        return False

def get_forex_config(tenant_id='entrylab'):
    """
    Get current forex configuration as a dictionary.
    
    Args:
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: Configuration with keys:
            - rsi_oversold (int)
            - rsi_overbought (int)
            - adx_threshold (int)
            - atr_sl_multiplier (float)
            - atr_tp_multiplier (float)
            - trading_start_hour (int)
            - trading_end_hour (int)
            - updated_at (datetime)
    """
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT setting_key, setting_value, updated_at
                FROM forex_config
                WHERE tenant_id = %s
            """, (tenant_id,))
            
            config = {}
            latest_update = None
            
            for row in cursor.fetchall():
                key = row[0]
                value = row[1]
                updated_at = row[2]
                
                # Convert to appropriate type
                if key in ['rsi_oversold', 'rsi_overbought', 'adx_threshold', 'trading_start_hour', 'trading_end_hour', 'session_start_hour_utc', 'session_end_hour_utc', 'back_to_back_throttle_minutes']:
                    config[key] = int(value) if value else 0
                elif key in ['atr_sl_multiplier', 'atr_tp_multiplier']:
                    config[key] = float(value) if value else 0.0
                else:
                    config[key] = value
                
                # Track latest update time
                if updated_at and (latest_update is None or updated_at > latest_update):
                    latest_update = updated_at
            
            # Set default values if config is empty
            if not config:
                config = {
                    'rsi_oversold': 40,
                    'rsi_overbought': 60,
                    'adx_threshold': 15,
                    'atr_sl_multiplier': 2.0,
                    'atr_tp_multiplier': 4.0,
                    'trading_start_hour': 8,
                    'trading_end_hour': 22
                }
            
            config['updated_at'] = latest_update.isoformat() if latest_update else None
            
            return config
    except Exception as e:
        print(f"Error getting forex config: {e}")
        return None

def update_forex_config(config_updates):
    """
    Update forex configuration values.
    
    Args:
        config_updates (dict): Dictionary with config keys and new values
    
    Returns:
        bool: True if successful
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            for key, value in config_updates.items():
                cursor.execute("""
                    INSERT INTO forex_config (tenant_id, setting_key, setting_value, updated_at)
                    VALUES ('entrylab', %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (tenant_id, setting_key) 
                    DO UPDATE SET 
                        setting_value = EXCLUDED.setting_value,
                        updated_at = CURRENT_TIMESTAMP
                """, (key, str(value)))
            
            conn.commit()
            print(f"✅ Forex config updated: {list(config_updates.keys())}")
            return True
    except Exception as e:
        print(f"Error updating forex config: {e}")
        raise


def get_bot_config(tenant_id='entrylab'):
    """
    Get bot configuration from forex_config table.
    Returns dict with active_bot_type and other bot settings.
    """
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT setting_key, setting_value
                FROM forex_config
                WHERE tenant_id = %s AND setting_key LIKE 'bot_%'
            """, (tenant_id,))
            
            config = {'active_bot_type': 'aggressive'}
            for row in cursor.fetchall():
                key = row[0].replace('bot_', '')
                config[key] = row[1]
            
            return config
    except Exception as e:
        print(f"Error getting bot config: {e}")
        return None

def init_bot_config():
    """Initialize default bot config settings"""
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO forex_config (tenant_id, setting_key, setting_value, updated_at)
                VALUES ('entrylab', 'bot_active_bot_type', 'aggressive', CURRENT_TIMESTAMP)
                ON CONFLICT (tenant_id, setting_key) DO NOTHING
            """)
            conn.commit()
            print("✅ Bot config initialized with defaults")
            return True
    except Exception as e:
        print(f"Error initializing bot config: {e}")
        return False

def update_breakeven_triggered(signal_id, breakeven_price, tenant_id='entrylab'):
    """
    Record that breakeven alert was triggered for a signal.
    
    Args:
        signal_id: The signal ID
        breakeven_price: The entry price (used for breakeven SL)
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        bool: True if successful
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE forex_signals 
                SET breakeven_triggered = TRUE, 
                    breakeven_triggered_at = CURRENT_TIMESTAMP,
                    breakeven_price = %s
                WHERE id = %s AND tenant_id = %s
            """, (breakeven_price, signal_id, tenant_id))
            conn.commit()
            print(f"✅ Signal #{signal_id}: Breakeven triggered at ${breakeven_price:.2f}")
            return True
    except Exception as e:
        print(f"Error updating breakeven triggered: {e}")
        return False

def get_last_recap_date(recap_type, tenant_id='entrylab'):
    """
    Get the last date a recap was posted (persisted to survive restarts).
    
    Args:
        recap_type: 'daily' or 'weekly'
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        str or None: Last recap date/week as string
    """
    try:
        if not db_pool.connection_pool:
            return None
        
        key = f'last_{recap_type}_recap'
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT setting_value FROM forex_config 
                WHERE tenant_id = %s AND setting_key = %s
            """, (tenant_id, key))
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception as e:
        print(f"Error getting last {recap_type} recap: {e}")
        return None


def set_last_recap_date(recap_type, value):
    """
    Set the last date a recap was posted (persisted to survive restarts).
    
    Args:
        recap_type: 'daily' or 'weekly'
        value: Date string or week number
    
    Returns:
        bool: Success
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        key = f'last_{recap_type}_recap'
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO forex_config (tenant_id, setting_key, setting_value, updated_at)
                VALUES ('entrylab', %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (tenant_id, setting_key) 
                DO UPDATE SET 
                    setting_value = EXCLUDED.setting_value,
                    updated_at = CURRENT_TIMESTAMP
            """, (key, str(value)))
            conn.commit()
            return True
    except Exception as e:
        print(f"Error setting last {recap_type} recap: {e}")
        return False

# ===== Bot Config Functions =====

def initialize_default_bot_config():
    """
    Initialize bot_config with default values if not already set.
    Should be called on startup.
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        default_config = {
            'active_bot': 'aggressive'
        }
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            for key, value in default_config.items():
                cursor.execute("""
                    INSERT INTO bot_config (tenant_id, setting_key, setting_value, updated_at)
                    VALUES ('entrylab', %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (tenant_id, setting_key) 
                    DO NOTHING
                """, (key, value))
            
            conn.commit()
            print("✅ Bot config initialized with defaults")
            return True
    except Exception as e:
        print(f"Error initializing bot config: {e}")
        return False

def get_active_bot(tenant_id='entrylab'):
    """
    Get the current active bot type.
    
    Args:
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        str: Active bot type ('aggressive', 'conservative', or 'custom')
    """
    try:
        if not db_pool.connection_pool:
            return 'aggressive'
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT setting_value FROM bot_config
                WHERE tenant_id = %s AND setting_key = 'active_bot'
            """, (tenant_id,))
            
            result = cursor.fetchone()
            if result:
                return result[0]
            return 'aggressive'
    except Exception as e:
        print(f"Error getting active bot: {e}")
        return 'aggressive'

def set_active_bot(bot_type):
    """
    Set the active bot type.
    
    Args:
        bot_type (str): Bot type ('aggressive', 'conservative', or 'custom')
    
    Returns:
        bool: True if successful
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        if bot_type not in ('aggressive', 'conservative', 'custom', 'raja_banks'):
            raise ValueError(f"Invalid bot type: {bot_type}")
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO bot_config (tenant_id, setting_key, setting_value, updated_at)
                VALUES ('entrylab', 'active_bot', %s, CURRENT_TIMESTAMP)
                ON CONFLICT (tenant_id, setting_key) 
                DO UPDATE SET 
                    setting_value = EXCLUDED.setting_value,
                    updated_at = CURRENT_TIMESTAMP
            """, (bot_type,))
            
            conn.commit()
            print(f"✅ Active bot set to: {bot_type}")
            return True
    except Exception as e:
        print(f"Error setting active bot: {e}")
        raise


def get_queued_bot(tenant_id='entrylab'):
    """
    Get the queued bot type (bot scheduled to activate after current signal closes).
    
    Args:
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        str or None: Queued bot type, or None if no bot is queued
    """
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT setting_value FROM bot_config
                WHERE tenant_id = %s AND setting_key = 'queued_bot'
            """, (tenant_id,))
            
            result = cursor.fetchone()
            if result and result[0]:
                return result[0]
            return None
    except Exception as e:
        print(f"Error getting queued bot: {e}")
        return None


def set_queued_bot(bot_type):
    """
    Set a bot to be queued (will activate after current signal closes).
    
    Args:
        bot_type (str): Bot type to queue
    
    Returns:
        bool: True if successful
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        if bot_type not in ('aggressive', 'conservative', 'custom', 'raja_banks'):
            raise ValueError(f"Invalid bot type: {bot_type}")
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO bot_config (tenant_id, setting_key, setting_value, updated_at)
                VALUES ('entrylab', 'queued_bot', %s, CURRENT_TIMESTAMP)
                ON CONFLICT (tenant_id, setting_key) 
                DO UPDATE SET 
                    setting_value = EXCLUDED.setting_value,
                    updated_at = CURRENT_TIMESTAMP
            """, (bot_type,))
            
            conn.commit()
            print(f"✅ Bot queued: {bot_type}")
            return True
    except Exception as e:
        print(f"Error setting queued bot: {e}")
        raise


def clear_queued_bot(tenant_id='entrylab'):
    """
    Clear the queued bot (cancel pending bot switch).
    
    Args:
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        bool: True if successful
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM bot_config
                WHERE tenant_id = %s AND setting_key = 'queued_bot'
            """, (tenant_id,))
            
            conn.commit()
            print("✅ Queued bot cleared")
            return True
    except Exception as e:
        print(f"Error clearing queued bot: {e}")
        return False


def promote_queued_bot():
    """
    Promote queued bot to active (called when signal closes).
    
    Returns:
        str or None: The bot type that was promoted, or None if no queued bot
    """
    try:
        queued = get_queued_bot()
        if not queued:
            return None
        
        set_active_bot(queued)
        clear_queued_bot()
        
        print(f"✅ Promoted queued bot to active: {queued}")
        return queued
    except Exception as e:
        print(f"Error promoting queued bot: {e}")
        return None


def get_open_signal(tenant_id='entrylab'):
    """
    Get the currently open signal if any.
    
    Args:
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: Signal dictionary or None if no open signal exists
    """
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, signal_type, pair, timeframe, entry_price, take_profit, 
                       stop_loss, status, rsi_value, macd_value, atr_value, 
                       posted_at, closed_at, result_pips, bot_type, telegram_message_id,
                       breakeven_set, breakeven_price, guidance_count, last_guidance_at,
                       indicators_used, notes, effective_sl
                FROM forex_signals
                WHERE tenant_id = %s AND status IN ('open', 'pending')
                ORDER BY posted_at DESC
                LIMIT 1
            """, (tenant_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'signal_type': row[1],
                    'pair': row[2],
                    'timeframe': row[3],
                    'entry_price': float(row[4]) if row[4] else None,
                    'take_profit': float(row[5]) if row[5] else None,
                    'stop_loss': float(row[6]) if row[6] else None,
                    'status': row[7],
                    'rsi_value': float(row[8]) if row[8] else None,
                    'macd_value': float(row[9]) if row[9] else None,
                    'atr_value': float(row[10]) if row[10] else None,
                    'posted_at': row[11].isoformat() if row[11] else None,
                    'closed_at': row[12].isoformat() if row[12] else None,
                    'result_pips': float(row[13]) if row[13] else None,
                    'bot_type': row[14] or 'aggressive',
                    'telegram_message_id': row[15],
                    'breakeven_set': row[16] or False,
                    'breakeven_price': float(row[17]) if row[17] else None,
                    'guidance_count': row[18] or 0,
                    'last_guidance_at': row[19].isoformat() if row[19] else None,
                    'indicators_used': row[20],
                    'notes': row[21],
                    'effective_sl': float(row[22]) if row[22] else None
                }
            return None
    except Exception as e:
        print(f"Error getting open signal: {e}")
        return None

def get_signals_by_bot_type(bot_type, status=None, limit=50, tenant_id='entrylab'):
    """
    Get forex signals filtered by bot type.
    
    Args:
        bot_type (str): Bot type ('aggressive', 'conservative', or 'custom')
        status (str, optional): Filter by status ('pending', 'open', 'won', 'lost')
        limit (int): Maximum number of signals to return (default: 50)
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        list: List of signal dictionaries
    """
    try:
        if not db_pool.connection_pool:
            return []
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT id, signal_type, pair, timeframe, entry_price, take_profit, 
                       stop_loss, status, rsi_value, macd_value, atr_value, 
                       posted_at, closed_at, result_pips, bot_type, telegram_message_id,
                       breakeven_set, breakeven_price, guidance_count, last_guidance_at,
                       indicators_used, notes
                FROM forex_signals
                WHERE tenant_id = %s AND bot_type = %s
            """
            params = [tenant_id, bot_type]
            
            if status:
                query += " AND status = %s"
                params.append(status)
            
            query += " ORDER BY posted_at DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            
            signals = []
            for row in cursor.fetchall():
                signals.append({
                    'id': row[0],
                    'signal_type': row[1],
                    'pair': row[2],
                    'timeframe': row[3],
                    'entry_price': float(row[4]) if row[4] else None,
                    'take_profit': float(row[5]) if row[5] else None,
                    'stop_loss': float(row[6]) if row[6] else None,
                    'status': row[7],
                    'rsi_value': float(row[8]) if row[8] else None,
                    'macd_value': float(row[9]) if row[9] else None,
                    'atr_value': float(row[10]) if row[10] else None,
                    'posted_at': row[11].isoformat() if row[11] else None,
                    'closed_at': row[12].isoformat() if row[12] else None,
                    'result_pips': float(row[13]) if row[13] else None,
                    'bot_type': row[14] or 'aggressive',
                    'telegram_message_id': row[15],
                    'breakeven_set': row[16] or False,
                    'breakeven_price': float(row[17]) if row[17] else None,
                    'guidance_count': row[18] or 0,
                    'last_guidance_at': row[19].isoformat() if row[19] else None,
                    'indicators_used': row[20],
                    'notes': row[21]
                })
            return signals
    except Exception as e:
        print(f"Error getting signals by bot type: {e}")
        return []


def count_signals_today_by_bot(bot_type, tenant_id='entrylab'):
    """
    Count signals generated today by a specific bot type.
    
    Args:
        bot_type (str): Bot type ('aggressive', 'conservative', 'raja_banks', etc.)
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        int: Number of signals today for this bot type
    """
    try:
        if not db_pool.connection_pool:
            return 0
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*) FROM forex_signals
                WHERE tenant_id = %s AND bot_type = %s 
                AND DATE(posted_at) = CURRENT_DATE
                AND status NOT IN ('draft', 'broadcast_failed')
            """, (tenant_id, bot_type))
            
            row = cursor.fetchone()
            return row[0] if row else 0
    except Exception as e:
        print(f"Error counting signals today for bot {bot_type}: {e}")
        return 0


def get_last_signal_time_by_bot(bot_type, tenant_id='entrylab'):
    """
    Get the timestamp of the last signal generated by a specific bot type.
    
    Args:
        bot_type (str): Bot type ('aggressive', 'conservative', 'raja_banks', etc.)
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        datetime or None: Timestamp of last signal, or None if no signals
    """
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT posted_at FROM forex_signals
                WHERE tenant_id = %s AND bot_type = %s 
                ORDER BY posted_at DESC
                LIMIT 1
            """, (tenant_id, bot_type))
            
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception as e:
        print(f"Error getting last signal time for bot {bot_type}: {e}")
        return None


def update_signal_telegram_message_id(signal_id, message_id, tenant_id='entrylab'):
    """
    Update the telegram_message_id for a signal.
    
    Args:
        signal_id (int): Signal ID
        message_id (int): Telegram message ID
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        bool: True if successful
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE forex_signals
                SET telegram_message_id = %s
                WHERE id = %s AND tenant_id = %s
            """, (message_id, signal_id, tenant_id))
            
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating signal telegram message ID: {e}")
        return False

def update_signal_breakeven(signal_id, breakeven_price, tenant_id='entrylab'):
    """
    Update breakeven status for a signal.
    
    Args:
        signal_id (int): Signal ID
        breakeven_price (float): Breakeven price (entry price)
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        bool: True if successful
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE forex_signals
                SET breakeven_set = TRUE,
                    breakeven_price = %s
                WHERE id = %s AND tenant_id = %s
            """, (breakeven_price, signal_id, tenant_id))
            
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating signal breakeven: {e}")
        return False

def update_tp_hit(signal_id, tp_level, tenant_id='entrylab'):
    """
    Mark a specific TP level as hit.
    
    Args:
        signal_id (int): Signal ID
        tp_level (int): TP level (1, 2, or 3)
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        bool: True if successful
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        if tp_level not in [1, 2, 3]:
            print(f"Invalid TP level: {tp_level}")
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            hit_column = f"tp{tp_level}_hit"
            hit_at_column = f"tp{tp_level}_hit_at"
            
            cursor.execute(f"""
                UPDATE forex_signals
                SET {hit_column} = TRUE,
                    {hit_at_column} = CURRENT_TIMESTAMP
                WHERE id = %s AND tenant_id = %s
            """, (signal_id, tenant_id))
            
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating TP{tp_level} hit: {e}")
        return False

def update_signal_guidance(signal_id, notes, progress_zone=None, caution_zone=None):
    """
    Update guidance information for a signal with zone tracking.
    Increments guidance_count and updates last_guidance_at, notes, and zone levels.
    
    Args:
        signal_id (int): Signal ID
        notes (str): AI guidance notes/reasons
        progress_zone (int, optional): Progress zone reached (30, 60, 85)
        caution_zone (int, optional): Caution zone reached (30, 60)
    
    Returns:
        bool: True if successful
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            if progress_zone is not None:
                cursor.execute("""
                    UPDATE forex_signals
                    SET guidance_count = COALESCE(guidance_count, 0) + 1,
                        last_guidance_at = CURRENT_TIMESTAMP,
                        notes = %s,
                        last_progress_zone = GREATEST(COALESCE(last_progress_zone, 0), %s)
                    WHERE id = %s
                """, (notes, progress_zone, signal_id))
            elif caution_zone is not None:
                cursor.execute("""
                    UPDATE forex_signals
                    SET guidance_count = COALESCE(guidance_count, 0) + 1,
                        last_guidance_at = CURRENT_TIMESTAMP,
                        notes = %s,
                        last_caution_zone = GREATEST(COALESCE(last_caution_zone, 0), %s)
                    WHERE id = %s
                """, (notes, caution_zone, signal_id))
            else:
                cursor.execute("""
                    UPDATE forex_signals
                    SET guidance_count = COALESCE(guidance_count, 0) + 1,
                        last_guidance_at = CURRENT_TIMESTAMP,
                        notes = %s
                    WHERE id = %s
                """, (notes, signal_id))
            
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating signal guidance: {e}")
        return False

def is_milestone_already_sent(signal_id, milestone_key, tenant_id='entrylab'):
    """
    Check if a milestone has already been sent for a signal.
    Used for race condition prevention with multiple workers.
    
    Args:
        signal_id (int): Signal ID
        milestone_key (str): Milestone key like 'tp1_40', 'tp1_70', 'tp2_50', 'sl_60'
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        bool: True if milestone was already sent
    """
    try:
        if not db_pool.connection_pool:
            return True  # Fail safe - assume sent if can't check
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT milestones_sent FROM forex_signals WHERE id = %s AND tenant_id = %s
            """, (signal_id, tenant_id))
            
            row = cursor.fetchone()
            if row and row[0]:
                return milestone_key in row[0]
            return False
    except Exception as e:
        print(f"Error checking milestone sent: {e}")
        return True  # Fail safe

def update_milestone_sent(signal_id, milestone_key, tenant_id='entrylab'):
    """
    Record that a milestone notification was sent.
    Uses atomic UPDATE with WHERE NOT LIKE to prevent race conditions.
    
    Args:
        signal_id (int): Signal ID
        milestone_key (str): Milestone key like 'tp1_40', 'tp1_70', 'tp2_50', 'sl_60'
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        bool: True if successfully claimed (was not already sent)
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Atomic update - only succeeds if milestone wasn't already sent
            cursor.execute("""
                UPDATE forex_signals
                SET last_milestone_at = CURRENT_TIMESTAMP,
                    milestones_sent = COALESCE(milestones_sent, '') || %s || ','
                WHERE id = %s AND tenant_id = %s
                  AND (milestones_sent IS NULL OR milestones_sent NOT LIKE %s)
            """, (milestone_key, signal_id, tenant_id, f'%{milestone_key}%'))
            
            conn.commit()
            return cursor.rowcount > 0  # True only if we successfully claimed it
    except Exception as e:
        print(f"Error updating milestone sent: {e}")
        return False

def update_effective_sl(signal_id, new_sl_price):
    """
    Update the effective stop loss for a signal.
    
    This is called when we advise traders to move their SL:
    - At 70% toward TP1: set to entry price (breakeven)
    - At TP1 hit: set to TP1 price (lock profit)
    - At TP2 hit: set to TP2 price (lock more profit)
    
    The effective_sl is used for:
    - SL hit detection in price monitoring
    - Pips calculations in daily/weekly recaps
    
    Args:
        signal_id (int): Signal ID
        new_sl_price (float): New effective stop loss price
    
    Returns:
        bool: True if successful
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE forex_signals
                SET effective_sl = %s
                WHERE id = %s
            """, (new_sl_price, signal_id))
            
            conn.commit()
            print(f"[EFFECTIVE_SL] Updated signal {signal_id} effective_sl to {new_sl_price}")
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating effective SL: {e}")
        return False

def update_signal_original_indicators(signal_id, rsi=None, macd=None, adx=None, stoch_k=None, indicators_dict=None):
    """
    Store original indicator values when signal is created for later re-validation.
    
    Supports both legacy individual parameters and new dynamic indicators_dict.
    The indicators_dict is the recommended approach for future-proof storage.
    
    Args:
        signal_id (int): Signal ID
        rsi (float, optional): Original RSI value (legacy)
        macd (float, optional): Original MACD value (legacy)
        adx (float, optional): Original ADX value (legacy)
        stoch_k (float, optional): Original Stochastic K value (legacy)
        indicators_dict (dict, optional): Dictionary of all indicators {'rsi': 45.2, 'macd': 0.0012, ...}
    
    Returns:
        bool: True if successful
    """
    import json
    
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build the full indicators dict from either source
            all_indicators = {}
            if indicators_dict:
                all_indicators = indicators_dict.copy()
            else:
                # Build from individual params for backward compatibility
                if rsi is not None:
                    all_indicators['rsi'] = rsi
                if macd is not None:
                    all_indicators['macd'] = macd
                if adx is not None:
                    all_indicators['adx'] = adx
                if stoch_k is not None:
                    all_indicators['stochastic'] = stoch_k
            
            # Update both legacy columns and new JSON column
            cursor.execute("""
                UPDATE forex_signals
                SET original_rsi = %s,
                    original_macd = %s,
                    original_adx = %s,
                    original_stoch_k = %s,
                    original_indicators_json = %s
                WHERE id = %s
            """, (
                rsi or all_indicators.get('rsi'),
                macd or all_indicators.get('macd'),
                adx or all_indicators.get('adx'),
                stoch_k or all_indicators.get('stochastic'),
                json.dumps(all_indicators) if all_indicators else None,
                signal_id
            ))
            
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating signal original indicators: {e}")
        return False

def update_signal_revalidation(signal_id, thesis_status, notes=None):
    """
    Update revalidation data for a signal (for stagnant trade monitoring).
    
    Args:
        signal_id (int): Signal ID
        thesis_status (str): 'intact', 'weakening', or 'broken'
        notes (str, optional): Notes about revalidation
    
    Returns:
        bool: True if successful
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE forex_signals
                SET last_revalidation_at = CURRENT_TIMESTAMP,
                    revalidation_count = COALESCE(revalidation_count, 0) + 1,
                    thesis_status = %s,
                    thesis_changed_at = CASE 
                        WHEN thesis_status != %s THEN CURRENT_TIMESTAMP 
                        ELSE thesis_changed_at 
                    END,
                    notes = COALESCE(%s, notes)
                WHERE id = %s
            """, (thesis_status, thesis_status, notes, signal_id))
            
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating signal revalidation: {e}")
        return False

def update_signal_timeout_notified(signal_id):
    """
    Mark a signal as having received the timeout notification.
    
    Args:
        signal_id (int): Signal ID
    
    Returns:
        bool: True if successful
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE forex_signals
                SET timeout_notified = TRUE
                WHERE id = %s
            """, (signal_id,))
            
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating signal timeout notified: {e}")
        return False

# ===== Signal Narrative Functions =====

def add_signal_narrative(signal_id, event_type, current_price=None, progress_percent=None, 
                         indicators=None, indicator_deltas=None, guidance_type=None, 
                         message_sent=None, notes=None):
    """
    Add a narrative event to track indicator changes throughout trade lifecycle.
    
    Event types: 'entry', 'progress_update', 'breakeven', 'thesis_check', 
                 'guidance_sent', 'close_advisory', 'tp_hit', 'sl_hit'
    
    Guidance types: 'momentum', 'volatility', 'structure', 'divergence', 'stagnant'
    """
    import json
    
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO signal_narrative 
                (signal_id, event_type, current_price, progress_percent, indicators, 
                 indicator_deltas, guidance_type, message_sent, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                signal_id, 
                event_type,
                current_price,
                progress_percent,
                json.dumps(indicators) if indicators else None,
                json.dumps(indicator_deltas) if indicator_deltas else None,
                guidance_type,
                message_sent,
                notes
            ))
            
            narrative_id = cursor.fetchone()[0]
            conn.commit()
            return narrative_id
    except Exception as e:
        print(f"Error adding signal narrative: {e}")
        return None

def get_signal_narrative(signal_id):
    """
    Get all narrative events for a signal in chronological order.
    
    Returns:
        list: List of narrative events with timestamps and indicator changes
    """
    import json
    
    try:
        if not db_pool.connection_pool:
            return []
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, event_type, event_time, current_price, progress_percent,
                       indicators, indicator_deltas, guidance_type, message_sent, notes
                FROM signal_narrative
                WHERE signal_id = %s
                ORDER BY event_time ASC
            """, (signal_id,))
            
            events = []
            for row in cursor.fetchall():
                events.append({
                    'id': row[0],
                    'event_type': row[1],
                    'event_time': row[2],
                    'current_price': float(row[3]) if row[3] else None,
                    'progress_percent': float(row[4]) if row[4] else None,
                    'indicators': json.loads(row[5]) if row[5] else None,
                    'indicator_deltas': json.loads(row[6]) if row[6] else None,
                    'guidance_type': row[7],
                    'message_sent': row[8],
                    'notes': row[9]
                })
            return events
    except Exception as e:
        print(f"Error getting signal narrative: {e}")
        return []

def get_latest_indicators_for_signal(signal_id):
    """
    Get the most recent indicator snapshot for a signal.
    
    Returns:
        dict: Latest indicators and their values, or None
    """
    import json
    
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT indicators, indicator_deltas, event_time
                FROM signal_narrative
                WHERE signal_id = %s AND indicators IS NOT NULL
                ORDER BY event_time DESC
                LIMIT 1
            """, (signal_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'indicators': json.loads(row[0]) if row[0] else None,
                    'indicator_deltas': json.loads(row[1]) if row[1] else None,
                    'captured_at': row[2]
                }
            return None
    except Exception as e:
        print(f"Error getting latest indicators: {e}")
        return None

# ===== Recent Phrases Functions (Repetition Avoidance) =====

def add_recent_phrase(phrase_type, phrase_text, tenant_id='entrylab'):
    """
    Record a phrase that was used in a message for repetition avoidance.
    
    Args:
        phrase_type: Type of phrase ('greeting', 'closing', 'update', 'celebration', etc.)
        phrase_text: The actual phrase used
        tenant_id (str): Tenant ID (default: 'entrylab')
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO recent_phrases (tenant_id, phrase_type, phrase_text, used_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            """, (tenant_id, phrase_type, phrase_text))
            
            conn.commit()
            return True
    except Exception as e:
        print(f"Error adding recent phrase: {e}")
        return False

def get_recent_phrases(phrase_type, limit=10, tenant_id='entrylab'):
    """
    Get recently used phrases of a specific type to avoid repetition.
    
    Args:
        phrase_type: Type of phrase to retrieve
        limit: Number of recent phrases to return (default 10)
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        list: List of recently used phrases
    """
    try:
        if not db_pool.connection_pool:
            return []
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT phrase_text, used_at
                FROM recent_phrases
                WHERE phrase_type = %s AND tenant_id = %s
                ORDER BY used_at DESC
                LIMIT %s
            """, (phrase_type, tenant_id, limit))
            
            return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error getting recent phrases: {e}")
        return []

def cleanup_old_phrases(days_to_keep=7, tenant_id='entrylab'):
    """
    Remove phrases older than specified days to prevent unbounded growth.
    
    Args:
        days_to_keep (int): Number of days of phrases to keep (default: 7)
        tenant_id (str): Tenant ID (default: 'entrylab')
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM recent_phrases
                WHERE used_at < CURRENT_TIMESTAMP - INTERVAL '%s days'
                AND tenant_id = %s
            """, (days_to_keep, tenant_id))
            
            deleted_count = cursor.rowcount
            conn.commit()
            if deleted_count > 0:
                print(f"[DB] Cleaned up {deleted_count} old phrases")
            return True
    except Exception as e:
        print(f"Error cleaning up old phrases: {e}")
        return False

# ===== Telegram Subscriptions Functions =====

def create_telegram_subscription(email, stripe_customer_id=None, stripe_subscription_id=None, plan_type='premium', amount_paid=49.00, name=None, utm_source=None, utm_medium=None, utm_campaign=None, utm_content=None, utm_term=None, tenant_id='entrylab'):
    """
    Create or update a telegram subscription record (UPSERT) with conversion tracking.
    
    Supports both paid (Stripe) and free users:
    - Paid users: Include stripeCustomerId and stripeSubscriptionId
    - Free users: Pass None for Stripe fields, set planType='Free Gold Signals' and amountPaid=0
    
    If email already exists and was previously a free user upgrading to paid,
    marks them as a conversion and calculates conversion_days.
    
    Args:
        email (str): Customer email (required)
        stripe_customer_id (str): Stripe customer ID (optional, None for free users)
        stripe_subscription_id (str): Stripe subscription ID (optional, None for free users)
        plan_type (str): Plan type (default: 'premium', use 'Free Gold Signals' for free users)
        amount_paid (float): Amount paid (default: 49.00, use 0 for free users)
        name (str): Customer name (optional)
        utm_source (str): UTM source parameter (optional)
        utm_medium (str): UTM medium parameter (optional)
        utm_campaign (str): UTM campaign parameter (optional)
        utm_content (str): UTM content parameter (optional)
        utm_term (str): UTM term parameter (optional)
    
    Returns:
        tuple: (subscription_dict or None, error_message or None)
    """
    try:
        if not db_pool.connection_pool:
            print("[DB] No connection pool available")
            return None, "Database connection pool not available"
        
        # Normalize Stripe IDs - empty/placeholder strings become NULL
        placeholders = {'', 'free', 'free_signup', 'test', 'null', 'none', 'n/a', 'undefined'}
        if stripe_customer_id and str(stripe_customer_id).lower().strip() in placeholders:
            stripe_customer_id = None
        if stripe_subscription_id and str(stripe_subscription_id).lower().strip() in placeholders:
            stripe_subscription_id = None
        
        is_free_signup = amount_paid == 0 or 'free' in plan_type.lower() if plan_type else False
        is_paid_signup = not is_free_signup and amount_paid > 0
        
        print(f"[DB] Creating subscription: email={email}, stripe_sub_id={stripe_subscription_id}, plan_type={plan_type}, is_free={is_free_signup}")
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if email already exists and was a free user (for conversion tracking)
            existing_subscription = None
            is_conversion = False
            conversion_days = None
            
            cursor.execute("""
                SELECT id, plan_type, amount_paid, free_signup_at, created_at, is_converted
                FROM telegram_subscriptions WHERE email = %s AND tenant_id = %s
            """, (email, tenant_id))
            existing = cursor.fetchone()
            
            if existing:
                existing_id, existing_plan, existing_amount, existing_free_signup, existing_created, already_converted = existing
                was_free = (existing_amount == 0 or existing_amount is None or 
                           (existing_plan and 'free' in existing_plan.lower()))
                
                # Detect free-to-paid conversion
                if was_free and is_paid_signup and not already_converted:
                    is_conversion = True
                    # Use existing free_signup_at or created_at as the free signup timestamp
                    free_signup_date = existing_free_signup or existing_created
                    if free_signup_date:
                        from datetime import datetime
                        now = datetime.utcnow()
                        if isinstance(free_signup_date, str):
                            free_signup_date = datetime.fromisoformat(free_signup_date.replace('Z', '+00:00'))
                        conversion_days = (now - free_signup_date).days
                        print(f"[DB] 🎉 Conversion detected! {email} upgraded from free to paid after {conversion_days} days")
            
            if is_free_signup:
                # For free signups, set free_signup_at and UTM params
                cursor.execute("""
                    INSERT INTO telegram_subscriptions 
                    (tenant_id, email, name, stripe_customer_id, stripe_subscription_id, plan_type, amount_paid, 
                     status, created_at, updated_at, free_signup_at, utm_source, utm_medium, utm_campaign, utm_content, utm_term)
                    VALUES ('entrylab', %s, %s, %s, %s, %s, %s, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 
                            CURRENT_TIMESTAMP, %s, %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, email) DO UPDATE SET
                        name = COALESCE(EXCLUDED.name, telegram_subscriptions.name),
                        plan_type = EXCLUDED.plan_type,
                        amount_paid = EXCLUDED.amount_paid,
                        updated_at = CURRENT_TIMESTAMP,
                        free_signup_at = COALESCE(telegram_subscriptions.free_signup_at, CURRENT_TIMESTAMP),
                        utm_source = COALESCE(telegram_subscriptions.utm_source, EXCLUDED.utm_source),
                        utm_medium = COALESCE(telegram_subscriptions.utm_medium, EXCLUDED.utm_medium),
                        utm_campaign = COALESCE(telegram_subscriptions.utm_campaign, EXCLUDED.utm_campaign),
                        utm_content = COALESCE(telegram_subscriptions.utm_content, EXCLUDED.utm_content),
                        utm_term = COALESCE(telegram_subscriptions.utm_term, EXCLUDED.utm_term)
                    RETURNING id, email, stripe_customer_id, stripe_subscription_id, status, created_at, is_converted
                """, (email, name, stripe_customer_id, stripe_subscription_id, plan_type, amount_paid,
                      utm_source, utm_medium, utm_campaign, utm_content, utm_term))
            else:
                # For paid signups, also handle conversion tracking
                if is_conversion:
                    cursor.execute("""
                        UPDATE telegram_subscriptions SET
                            name = COALESCE(%s, name),
                            stripe_customer_id = COALESCE(%s, stripe_customer_id),
                            stripe_subscription_id = COALESCE(%s, stripe_subscription_id),
                            plan_type = %s,
                            amount_paid = %s,
                            status = 'pending',
                            updated_at = CURRENT_TIMESTAMP,
                            is_converted = TRUE,
                            converted_at = CURRENT_TIMESTAMP,
                            conversion_days = %s
                        WHERE email = %s
                        RETURNING id, email, stripe_customer_id, stripe_subscription_id, status, created_at, is_converted
                    """, (name, stripe_customer_id, stripe_subscription_id, plan_type, amount_paid,
                          conversion_days, email))
                else:
                    cursor.execute("""
                        INSERT INTO telegram_subscriptions 
                        (tenant_id, email, name, stripe_customer_id, stripe_subscription_id, plan_type, amount_paid, 
                         status, created_at, updated_at, utm_source, utm_medium, utm_campaign, utm_content, utm_term)
                        VALUES ('entrylab', %s, %s, %s, %s, %s, %s, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 
                                %s, %s, %s, %s, %s)
                        ON CONFLICT (tenant_id, email) DO UPDATE SET
                            name = COALESCE(EXCLUDED.name, telegram_subscriptions.name),
                            stripe_customer_id = COALESCE(EXCLUDED.stripe_customer_id, telegram_subscriptions.stripe_customer_id),
                            stripe_subscription_id = COALESCE(EXCLUDED.stripe_subscription_id, telegram_subscriptions.stripe_subscription_id),
                            plan_type = EXCLUDED.plan_type,
                            amount_paid = EXCLUDED.amount_paid,
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING id, email, stripe_customer_id, stripe_subscription_id, status, created_at, is_converted
                    """, (email, name, stripe_customer_id, stripe_subscription_id, plan_type, amount_paid,
                          utm_source, utm_medium, utm_campaign, utm_content, utm_term))
            
            result = cursor.fetchone()
            conn.commit()
            
            if result:
                return {
                    'id': result[0],
                    'email': result[1],
                    'stripe_customer_id': result[2],
                    'stripe_subscription_id': result[3],
                    'status': result[4],
                    'created_at': result[5].isoformat() if result[5] else None,
                    'is_converted': result[6] if len(result) > 6 else False
                }, None
            
            return None, "No result returned from database"
    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"[DB ERROR] Failed to create telegram subscription for {email}")
        print(f"[DB ERROR] {error_msg}")
        print(f"[DB ERROR] Traceback: {traceback.format_exc()}")
        return None, error_msg

# Alias for backwards compatibility with webhook handlers
create_or_update_telegram_subscription = create_telegram_subscription

def get_telegram_subscription_by_email(email, tenant_id='entrylab'):
    """Get telegram subscription by email"""
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, email, name, telegram_user_id, telegram_username, 
                       stripe_customer_id, stripe_subscription_id, plan_type, amount_paid,
                       status, invite_link, joined_at, last_seen_at, revoked_at, created_at, updated_at
                FROM telegram_subscriptions
                WHERE email = %s AND tenant_id = %s
            """, (email, tenant_id))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return {
                'id': row[0],
                'email': row[1],
                'name': row[2],
                'telegram_user_id': row[3],
                'telegram_username': row[4],
                'stripe_customer_id': row[5],
                'stripe_subscription_id': row[6],
                'plan_type': row[7],
                'amount_paid': float(row[8]) if row[8] else 0.0,
                'status': row[9],
                'invite_link': row[10],
                'joined_at': row[11].isoformat() if row[11] else None,
                'last_seen_at': row[12].isoformat() if row[12] else None,
                'revoked_at': row[13].isoformat() if row[13] else None,
                'created_at': row[14].isoformat() if row[14] else None,
                'updated_at': row[15].isoformat() if row[15] else None
            }
    except Exception as e:
        print(f"Error getting telegram subscription by email: {e}")
        return None

def get_telegram_subscription_by_id(subscription_id, tenant_id='entrylab'):
    """Get telegram subscription by ID"""
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, email, name, telegram_user_id, telegram_username, 
                       stripe_customer_id, stripe_subscription_id, plan_type, amount_paid,
                       status, invite_link, joined_at, last_seen_at, revoked_at, created_at, updated_at
                FROM telegram_subscriptions
                WHERE id = %s AND tenant_id = %s
            """, (subscription_id, tenant_id))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return {
                'id': row[0],
                'email': row[1],
                'name': row[2],
                'telegram_user_id': row[3],
                'telegram_username': row[4],
                'stripe_customer_id': row[5],
                'stripe_subscription_id': row[6],
                'plan_type': row[7],
                'amount_paid': float(row[8]) if row[8] else 0.0,
                'status': row[9],
                'invite_link': row[10],
                'joined_at': row[11].isoformat() if row[11] else None,
                'last_seen_at': row[12].isoformat() if row[12] else None,
                'revoked_at': row[13].isoformat() if row[13] else None,
                'created_at': row[14].isoformat() if row[14] else None,
                'updated_at': row[15].isoformat() if row[15] else None
            }
    except Exception as e:
        print(f"Error getting telegram subscription by id: {e}")
        return None

def update_telegram_subscription_invite(email, invite_link, tenant_id='entrylab'):
    """Update telegram subscription with invite link"""
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE telegram_subscriptions
                SET invite_link = %s, status = 'active', updated_at = CURRENT_TIMESTAMP
                WHERE email = %s AND tenant_id = %s
            """, (invite_link, email, tenant_id))
            
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating telegram subscription invite: {e}")
        return False

def update_telegram_subscription_user_joined(email, telegram_user_id, telegram_username, tenant_id='entrylab'):
    """Update telegram subscription when user joins channel"""
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE telegram_subscriptions
                SET telegram_user_id = %s, telegram_username = %s, 
                    joined_at = CURRENT_TIMESTAMP, last_seen_at = CURRENT_TIMESTAMP,
                    status = 'active', updated_at = CURRENT_TIMESTAMP
                WHERE email = %s AND tenant_id = %s
            """, (telegram_user_id, telegram_username, email, tenant_id))
            
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating telegram subscription user joined: {e}")
        return False

def update_subscription_status(email=None, stripe_subscription_id=None, status=None, reason=None, tenant_id='entrylab'):
    """
    Update subscription status based on email or stripe_subscription_id.
    
    Args:
        email: Customer email (optional if stripe_subscription_id provided)
        stripe_subscription_id: Stripe subscription ID (optional if email provided)
        status: New status (e.g., 'payment_failed', 'past_due', 'active')
        reason: Optional reason for the status change
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        tuple: (success: bool, email: str or None, telegram_user_id: int or None)
    """
    try:
        if not db_pool.connection_pool:
            return False, None, None
        
        if not email and not stripe_subscription_id:
            return False, None, None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            if stripe_subscription_id:
                cursor.execute("""
                    UPDATE telegram_subscriptions
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE stripe_subscription_id = %s AND tenant_id = %s
                    RETURNING email, telegram_user_id
                """, (status, stripe_subscription_id, tenant_id))
            else:
                cursor.execute("""
                    UPDATE telegram_subscriptions
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE email = %s AND tenant_id = %s
                    RETURNING email, telegram_user_id
                """, (status, email, tenant_id))
            
            result = cursor.fetchone()
            conn.commit()
            
            if result:
                print(f"[DB] Subscription status updated: {result[0]} -> {status} (reason: {reason})")
                return True, result[0], result[1]
            return False, None, None
    except Exception as e:
        print(f"Error updating subscription status: {e}")
        return False, None, None


def revoke_telegram_subscription(email, reason='subscription_canceled', tenant_id='entrylab'):
    """Revoke telegram subscription access"""
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE telegram_subscriptions
                SET status = 'revoked', revoked_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE email = %s AND tenant_id = %s
                RETURNING telegram_user_id
            """, (email, tenant_id))
            
            result = cursor.fetchone()
            conn.commit()
            
            if result:
                return result[0]
            return None
    except Exception as e:
        print(f"Error revoking telegram subscription: {e}")
        return None

def delete_subscription_by_stripe_customer(stripe_customer_id, tenant_id='entrylab'):
    """Delete subscription record by Stripe customer ID"""
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM telegram_subscriptions
                WHERE stripe_customer_id = %s AND tenant_id = %s
                RETURNING email
            """, (stripe_customer_id, tenant_id))
            
            result = cursor.fetchone()
            conn.commit()
            
            if result:
                print(f"[DB] Deleted subscription for customer {stripe_customer_id}: {result[0]}")
                return True
            return False
    except Exception as e:
        print(f"Error deleting subscription by customer ID: {e}")
        return False


def delete_subscription_by_email(email, tenant_id='entrylab'):
    """Delete subscription record by email"""
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM telegram_subscriptions
                WHERE email = %s AND tenant_id = %s
                RETURNING id
            """, (email, tenant_id))
            
            result = cursor.fetchone()
            conn.commit()
            
            if result:
                print(f"[DB] Deleted subscription for email {email}")
                return True
            return False
    except Exception as e:
        print(f"Error deleting subscription by email: {e}")
        return False


def clear_all_telegram_subscriptions(tenant_id='entrylab'):
    """Delete all telegram subscriptions (for testing/cleanup)"""
    try:
        if not db_pool.connection_pool:
            return 0
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM telegram_subscriptions WHERE tenant_id = %s", (tenant_id,))
            deleted_count = cursor.rowcount
            
            # Reset the ID sequence
            cursor.execute("ALTER SEQUENCE telegram_subscriptions_id_seq RESTART WITH 1")
            
            conn.commit()
            print(f"[DB] Cleared {deleted_count} telegram subscriptions")
            return deleted_count
    except Exception as e:
        print(f"Error clearing telegram subscriptions: {e}")
        raise

def cleanup_test_telegram_subscriptions(tenant_id='entrylab'):
    """Delete test telegram subscriptions (fake paid records with test emails)"""
    try:
        if not db_pool.connection_pool:
            return []
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Delete test records with fake payments and return what was deleted
            cursor.execute("""
                DELETE FROM telegram_subscriptions 
                WHERE amount_paid > 0 
                AND tenant_id = %s
                AND (
                    email LIKE 'test%@%' OR 
                    email LIKE 'demo%@%' OR
                    email LIKE '%@example.com'
                )
                RETURNING id, email, amount_paid
            """, (tenant_id,))
            
            deleted_records = cursor.fetchall()
            conn.commit()
            
            deleted_info = [{'id': r[0], 'email': r[1], 'amount': float(r[2])} for r in deleted_records]
            print(f"[DB] Cleaned up {len(deleted_records)} test records: {deleted_info}")
            return deleted_info
    except Exception as e:
        print(f"Error cleaning up test telegram subscriptions: {e}")
        raise

def delete_telegram_subscription(subscription_id, tenant_id='entrylab'):
    """Delete a specific telegram subscription by ID"""
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM telegram_subscriptions 
                WHERE id = %s AND tenant_id = %s
                RETURNING id
            """, (subscription_id, tenant_id))
            
            deleted = cursor.fetchone()
            conn.commit()
            
            if deleted:
                print(f"[DB] Deleted telegram subscription ID={subscription_id}")
                return True
            return False
    except Exception as e:
        print(f"Error deleting telegram subscription {subscription_id}: {e}")
        raise

def get_all_telegram_subscriptions(status_filter=None, include_test=False, tenant_id='entrylab'):
    """Get all telegram subscriptions with optional status filter and test/live filter"""
    try:
        if not db_pool.connection_pool:
            print("[DB] No connection pool for get_all_telegram_subscriptions")
            return []
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if is_test column exists
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'telegram_subscriptions' AND column_name = 'is_test'
            """)
            has_is_test_column = cursor.fetchone() is not None
            
            conditions = ["tenant_id = %s"]
            params = [tenant_id]
            
            if status_filter:
                conditions.append("status = %s")
                params.append(status_filter)
            
            # Only filter by is_test if the column exists
            if has_is_test_column and not include_test:
                conditions.append("(is_test = FALSE OR is_test IS NULL)")
            
            where_clause = "WHERE " + " AND ".join(conditions)
            
            # Build query based on whether is_test column exists
            if has_is_test_column:
                query = f"""
                    SELECT id, email, name, telegram_user_id, telegram_username, 
                           stripe_customer_id, stripe_subscription_id, plan_type, amount_paid,
                           status, invite_link, joined_at, last_seen_at, revoked_at, created_at, updated_at,
                           COALESCE(is_test, FALSE) as is_test
                    FROM telegram_subscriptions
                    {where_clause}
                    ORDER BY created_at DESC
                """
            else:
                query = f"""
                    SELECT id, email, name, telegram_user_id, telegram_username, 
                           stripe_customer_id, stripe_subscription_id, plan_type, amount_paid,
                           status, invite_link, joined_at, last_seen_at, revoked_at, created_at, updated_at,
                           FALSE as is_test
                    FROM telegram_subscriptions
                    {where_clause}
                    ORDER BY created_at DESC
                """
            
            cursor.execute(query, params)
            print(f"[DB] get_all_telegram_subscriptions: found {cursor.rowcount} rows")
            
            subscriptions = []
            for row in cursor.fetchall():
                subscriptions.append({
                    'id': row[0],
                    'email': row[1],
                    'name': row[2],
                    'telegram_user_id': row[3],
                    'telegram_username': row[4],
                    'stripe_customer_id': row[5],
                    'stripe_subscription_id': row[6],
                    'plan_type': row[7],
                    'amount_paid': float(row[8]) if row[8] else 0.0,
                    'status': row[9],
                    'invite_link': row[10],
                    'joined_at': row[11].isoformat() if row[11] else None,
                    'last_seen_at': row[12].isoformat() if row[12] else None,
                    'revoked_at': row[13].isoformat() if row[13] else None,
                    'created_at': row[14].isoformat() if row[14] else None,
                    'updated_at': row[15].isoformat() if row[15] else None,
                    'is_test': row[16]
                })
            
            return subscriptions
    except Exception as e:
        print(f"Error getting all telegram subscriptions: {e}")
        return []

def update_telegram_subscription_last_seen(telegram_user_id, tenant_id='entrylab'):
    """Update last_seen_at for a telegram user"""
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE telegram_subscriptions
                SET last_seen_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = %s AND tenant_id = %s
            """, (telegram_user_id, tenant_id))
            
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating telegram subscription last seen: {e}")
        return False

def link_subscription_to_telegram_user(invite_link, telegram_user_id, telegram_username, joined_at, tenant_id='entrylab'):
    """
    Auto-link a Telegram user ID to a subscription record when they join the channel.
    
    This function is called by the Telegram bot join tracker when a user joins the private channel.
    It matches the join event to a subscription record using the invite link (or fallback logic).
    
    Args:
        invite_link (str): Invite link used to join (may be None if not available)
        telegram_user_id (int): Telegram user ID
        telegram_username (str): Telegram username (may be None)
        joined_at (datetime): Timestamp when user joined
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: Updated subscription record or None if no match found
    """
    try:
        if not db_pool.connection_pool:
            print("[JOIN_TRACKER] Database not available")
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Try to find subscription by invite_link first
            subscription_id = None
            if invite_link:
                cursor.execute("""
                    SELECT id, email FROM telegram_subscriptions
                    WHERE invite_link = %s AND status = 'pending' AND tenant_id = %s
                    LIMIT 1
                """, (invite_link, tenant_id))
                result = cursor.fetchone()
                if result:
                    subscription_id = result[0]
                    email = result[1]
                    print(f"[JOIN_TRACKER] Found subscription by invite_link: {email}")
            
            # Fallback: Find most recent pending subscription if no invite_link match
            if not subscription_id:
                cursor.execute("""
                    SELECT id, email FROM telegram_subscriptions
                    WHERE status = 'pending' AND telegram_user_id IS NULL AND tenant_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (tenant_id,))
                result = cursor.fetchone()
                if result:
                    subscription_id = result[0]
                    email = result[1]
                    print(f"[JOIN_TRACKER] Fallback: Using most recent pending subscription: {email}")
                else:
                    print(f"[JOIN_TRACKER] ⚠️ No pending subscription found for user {telegram_user_id} (@{telegram_username})")
                    return None
            
            # Update the subscription with user info atomically
            cursor.execute("""
                UPDATE telegram_subscriptions
                SET telegram_user_id = %s,
                    telegram_username = %s,
                    joined_at = %s,
                    last_seen_at = %s,
                    status = 'active',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, email, telegram_user_id, telegram_username, status, joined_at
            """, (telegram_user_id, telegram_username, joined_at, joined_at, subscription_id))
            
            result = cursor.fetchone()
            conn.commit()
            
            if result:
                print(f"[JOIN_TRACKER] ✅ Successfully linked subscription {result[1]} to Telegram user {telegram_user_id} (@{telegram_username})")
                return {
                    'id': result[0],
                    'email': result[1],
                    'telegram_user_id': result[2],
                    'telegram_username': result[3],
                    'status': result[4],
                    'joined_at': result[5].isoformat() if result[5] else None
                }
            
            return None
            
    except Exception as e:
        print(f"[JOIN_TRACKER] ❌ Error linking subscription to telegram user: {e}")
        import traceback
        traceback.print_exc()
        return None

# ===== Conversion Analytics Functions =====

def get_conversion_analytics(tenant_id='entrylab'):
    """
    Get comprehensive conversion analytics for free-to-VIP tracking.
    
    Args:
        tenant_id (str): Tenant ID (default: 'entrylab')
    
    Returns:
        dict: Analytics data including conversion rate, top sources, etc.
    """
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Total free signups
            cursor.execute("""
                SELECT COUNT(*) FROM telegram_subscriptions 
                WHERE free_signup_at IS NOT NULL AND tenant_id = %s
            """, (tenant_id,))
            total_free_signups = cursor.fetchone()[0] or 0
            
            # Total conversions
            cursor.execute("""
                SELECT COUNT(*) FROM telegram_subscriptions 
                WHERE is_converted = TRUE AND tenant_id = %s
            """, (tenant_id,))
            total_conversions = cursor.fetchone()[0] or 0
            
            # Conversion rate
            conversion_rate = (total_conversions / total_free_signups * 100) if total_free_signups > 0 else 0
            
            # Average conversion time
            cursor.execute("""
                SELECT AVG(conversion_days) FROM telegram_subscriptions 
                WHERE is_converted = TRUE AND conversion_days IS NOT NULL AND tenant_id = %s
            """, (tenant_id,))
            avg_conversion_days = cursor.fetchone()[0] or 0
            
            # Total revenue from conversions
            cursor.execute("""
                SELECT SUM(amount_paid) FROM telegram_subscriptions 
                WHERE is_converted = TRUE AND tenant_id = %s
            """, (tenant_id,))
            conversion_revenue = float(cursor.fetchone()[0] or 0)
            
            # Conversions by UTM source
            cursor.execute("""
                SELECT 
                    COALESCE(utm_source, 'direct') as source,
                    COUNT(*) as conversions,
                    SUM(amount_paid) as revenue
                FROM telegram_subscriptions 
                WHERE is_converted = TRUE AND tenant_id = %s
                GROUP BY utm_source
                ORDER BY conversions DESC
                LIMIT 10
            """, (tenant_id,))
            by_source = [{'source': row[0], 'conversions': row[1], 'revenue': float(row[2] or 0)} 
                         for row in cursor.fetchall()]
            
            # Conversions by UTM campaign
            cursor.execute("""
                SELECT 
                    COALESCE(utm_campaign, 'none') as campaign,
                    COUNT(*) as conversions,
                    SUM(amount_paid) as revenue
                FROM telegram_subscriptions 
                WHERE is_converted = TRUE AND tenant_id = %s
                GROUP BY utm_campaign
                ORDER BY conversions DESC
                LIMIT 10
            """, (tenant_id,))
            by_campaign = [{'campaign': row[0], 'conversions': row[1], 'revenue': float(row[2] or 0)} 
                           for row in cursor.fetchall()]
            
            # Free signups by source (for funnel analysis)
            cursor.execute("""
                SELECT 
                    COALESCE(utm_source, 'direct') as source,
                    COUNT(*) as signups,
                    SUM(CASE WHEN is_converted = TRUE THEN 1 ELSE 0 END) as converted
                FROM telegram_subscriptions 
                WHERE free_signup_at IS NOT NULL AND tenant_id = %s
                GROUP BY utm_source
                ORDER BY signups DESC
                LIMIT 10
            """, (tenant_id,))
            funnel_by_source = [
                {
                    'source': row[0], 
                    'signups': row[1], 
                    'converted': row[2],
                    'conversion_rate': round((row[2] / row[1] * 100) if row[1] > 0 else 0, 1)
                } 
                for row in cursor.fetchall()
            ]
            
            # Recent conversions
            cursor.execute("""
                SELECT email, utm_source, utm_campaign, amount_paid, conversion_days, converted_at
                FROM telegram_subscriptions 
                WHERE is_converted = TRUE AND tenant_id = %s
                ORDER BY converted_at DESC
                LIMIT 10
            """, (tenant_id,))
            recent_conversions = [
                {
                    'email': row[0],
                    'source': row[1] or 'direct',
                    'campaign': row[2] or 'none',
                    'amount': float(row[3] or 0),
                    'days_to_convert': row[4],
                    'converted_at': row[5].isoformat() if row[5] else None
                }
                for row in cursor.fetchall()
            ]
            
            # All leads table (free signups with conversion status)
            cursor.execute("""
                SELECT 
                    email, name, utm_source, utm_campaign, 
                    free_signup_at, is_converted, converted_at, 
                    amount_paid, plan_type, status, telegram_username
                FROM telegram_subscriptions 
                WHERE tenant_id = %s
                ORDER BY 
                    CASE WHEN is_converted = TRUE THEN 0 ELSE 1 END,
                    free_signup_at DESC NULLS LAST,
                    created_at DESC
                LIMIT 50
            """, (tenant_id,))
            all_leads = [
                {
                    'email': row[0],
                    'name': row[1] or '',
                    'source': row[2] or 'direct',
                    'campaign': row[3] or '',
                    'signup_date': row[4].isoformat() if row[4] else None,
                    'is_converted': row[5] or False,
                    'converted_at': row[6].isoformat() if row[6] else None,
                    'amount': float(row[7] or 0),
                    'plan_type': row[8] or 'Free',
                    'status': row[9] or 'pending',
                    'telegram': row[10] or ''
                }
                for row in cursor.fetchall()
            ]
            
            return {
                'summary': {
                    'total_free_signups': total_free_signups,
                    'total_conversions': total_conversions,
                    'conversion_rate': round(conversion_rate, 1),
                    'avg_conversion_days': round(float(avg_conversion_days), 1),
                    'conversion_revenue': round(conversion_revenue, 2)
                },
                'by_source': by_source,
                'by_campaign': by_campaign,
                'funnel_by_source': funnel_by_source,
                'recent_conversions': recent_conversions,
                'all_leads': all_leads
            }
            
    except Exception as e:
        print(f"Error getting conversion analytics: {e}")
        import traceback
        traceback.print_exc()
        return None


# ===== Webhook Idempotency Functions =====

def is_webhook_event_processed(event_id, tenant_id='entrylab'):
    """
    Check if a webhook event has already been processed.
    Used to prevent duplicate processing of Stripe webhook events.
    
    Args:
        event_id (str): The Stripe event ID (e.g., 'evt_xxx')
        tenant_id (str): The tenant ID (default: 'entrylab')
    
    Returns:
        bool: True if event was already processed, False otherwise
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM processed_webhook_events 
                WHERE event_id = %s AND tenant_id = %s
            """, (event_id, tenant_id))
            return cursor.fetchone() is not None
    except Exception as e:
        print(f"[IDEMPOTENCY] Error checking webhook event: {e}")
        return False

def record_webhook_event_processed(event_id, event_source='stripe', tenant_id='entrylab'):
    """
    Record that a webhook event has been processed.
    
    Args:
        event_id (str): The Stripe event ID
        event_source (str): The event source (e.g., 'stripe', 'telegram')
        tenant_id (str): The tenant ID (default: 'entrylab')
    
    Returns:
        bool: True if recorded successfully
    """
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO processed_webhook_events (tenant_id, event_id, event_source, processed_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (tenant_id, event_id) DO NOTHING
            """, (tenant_id, event_id, event_source))
            conn.commit()
            return True
    except Exception as e:
        print(f"[IDEMPOTENCY] Error recording webhook event: {e}")
        return False

def cleanup_old_webhook_events(hours=24, tenant_id='entrylab'):
    """
    Clean up old processed webhook events to prevent table growth.
    Events older than specified hours are deleted.
    
    Args:
        hours (int): Delete events older than this many hours
        tenant_id (str): The tenant ID (default: 'entrylab')
    
    Returns:
        int: Number of events deleted
    """
    try:
        if not db_pool.connection_pool:
            return 0
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM processed_webhook_events 
                WHERE tenant_id = %s 
                AND processed_at < (CURRENT_TIMESTAMP - (%s * INTERVAL '1 hour'))
            """, (tenant_id, hours))
            deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                print(f"[IDEMPOTENCY] Cleaned up {deleted} old webhook events")
            return deleted
    except Exception as e:
        print(f"[IDEMPOTENCY] Error cleaning up webhook events: {e}")
        return 0
