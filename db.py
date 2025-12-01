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
                
                conn.commit()
                print("✅ Database schema initialized")
                
                # Initialize default forex config
                initialize_default_forex_config()
                
                return True
        except Exception as e:
            print(f"❌ Failed to initialize schema: {e}")
            return False

# Global database pool instance
db_pool = DatabasePool()

# Campaign CRUD operations
def create_campaign(title, description, start_date, end_date, prize, platforms, overlay_url=None):
    """Create a new campaign"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO campaigns 
                (title, description, start_date, end_date, prize, platforms, overlay_url, status)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                RETURNING id
            """, (title, description, start_date, end_date, prize, platforms, overlay_url, 'scheduled'))
            campaign_id = cursor.fetchone()[0]
            conn.commit()
            return campaign_id
    except Exception as e:
        print(f"Error creating campaign: {e}")
        raise

def get_all_campaigns():
    """Get all campaigns ordered by start_date descending"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, description, start_date, end_date, prize, platforms, overlay_url, status, created_at
                FROM campaigns
                ORDER BY start_date DESC
            """)
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

def get_campaign_by_id(campaign_id):
    """Get a single campaign by ID"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, description, start_date, end_date, prize, platforms, overlay_url, status, created_at
                FROM campaigns
                WHERE id = %s
            """, (campaign_id,))
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

def update_campaign(campaign_id, title, description, start_date, end_date, prize, platforms, overlay_url=None):
    """Update an existing campaign"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE campaigns
                SET title = %s, description = %s, start_date = %s, end_date = %s,
                    prize = %s, platforms = %s::jsonb, overlay_url = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (title, description, start_date, end_date, prize, platforms, overlay_url, campaign_id))
            conn.commit()
            return True
    except Exception as e:
        print(f"Error updating campaign: {e}")
        raise

def delete_campaign(campaign_id):
    """Delete a campaign and its submissions"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM campaigns WHERE id = %s", (campaign_id,))
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
def log_bot_usage(chat_id, template_slug, coupon_code, success, error_type=None, device_type='unknown'):
    """
    Log Telegram bot usage. Silently fails to avoid disrupting bot operation.
    
    Args:
        chat_id (int): Telegram chat ID
        template_slug (str): Template slug used (or None if template not found)
        coupon_code (str): Coupon code used
        success (bool): Whether the operation succeeded
        error_type (str): Type of error if failed (e.g., 'network', 'invalid_coupon', 'template_not_found')
        device_type (str): Device type ('mobile', 'desktop', 'tablet', 'unknown')
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
                (chat_id, template_slug, coupon_code, success, error_type, device_type)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (chat_id, template_slug, coupon_code, success, error_type, device_type))
            conn.commit()
            success_msg = f"[BOT_USAGE] ✅ Successfully logged usage"
            print(success_msg, flush=True)
            sys.stdout.flush()
    except Exception as e:
        error_msg = f"[BOT_USAGE] ❌ Failed to log usage: {e}"
        print(error_msg, flush=True)
        sys.stdout.flush()

def get_bot_stats(days=30, template_filter=None):
    """
    Get bot usage statistics for the last N days, or 'today'/'yesterday' for exact day filtering.
    
    Args:
        days (int|str): Number of days, or 'today'/'yesterday' for exact date filtering (default: 30)
        template_filter (str, optional): Filter popular coupons by specific template slug
    
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
                where_clause = "created_at >= CURRENT_DATE AND created_at < CURRENT_DATE + INTERVAL '1 day'"
                where_params = ()
            elif days == 'yesterday':
                where_clause = "created_at >= CURRENT_DATE - INTERVAL '1 day' AND created_at < CURRENT_DATE"
                where_params = ()
            else:
                where_clause = "created_at >= CURRENT_TIMESTAMP - %s::interval"
                where_params = (f"{days} days",)
            
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

def get_day_of_week_stats(days=30):
    """
    Get day-of-week or hour-of-day usage statistics.
    
    Args:
        days (int or str): Number of days to analyze, or 'today'/'yesterday' for hourly stats
    
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
                    GROUP BY hour_num
                    ORDER BY hour_num
                """)
                
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
                    GROUP BY day_name, day_num
                    ORDER BY day_num
                """, (interval,))
                
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
                INSERT INTO bot_users (chat_id, last_coupon_code, username, first_name, last_name, first_used, last_used)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (chat_id) 
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

def get_bot_user(chat_id):
    """
    Get bot user data including last coupon used, profile information, and activity stats.
    
    Args:
        chat_id (int): Telegram chat ID
    
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
                LEFT JOIN bot_usage b ON u.chat_id = b.chat_id
                WHERE u.chat_id = %s
                GROUP BY u.chat_id, u.last_coupon_code, u.last_used, u.username, u.first_name, u.last_name
            """, (chat_id,))
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

def get_active_bot_users(days=30):
    """
    Get all active bot users within the last N days for broadcasting.
    
    Args:
        days (int): Number of days to consider "active" (default: 30)
    
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
                ORDER BY last_used DESC
            """, (interval,))
            
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

def get_bot_user_count(days=30):
    """
    Get count of active bot users within the last N days.
    
    Args:
        days (int): Number of days to consider "active" (default: 30)
    
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
            """, (interval,))
            return cursor.fetchone()[0]
    except Exception as e:
        print(f"Error getting bot user count: {e}")
        return 0

def get_retention_rates():
    """
    Calculate Day 1, Day 7, and Day 30 retention rates.
    
    Retention is calculated as the percentage of users who returned to use the bot
    after their first usage.
    
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
                ),
                returned AS (
                    SELECT DISTINCT c.chat_id
                    FROM cohort c
                    INNER JOIN bot_usage b ON c.chat_id = b.chat_id
                    WHERE b.created_at >= c.first_used + INTERVAL '1 day'
                    AND b.created_at < c.first_used + INTERVAL '2 days'
                    AND b.success = true
                )
                SELECT 
                    COUNT(DISTINCT c.chat_id) as cohort_size,
                    COUNT(DISTINCT r.chat_id) as returned_count
                FROM cohort c
                LEFT JOIN returned r ON c.chat_id = r.chat_id
            """)
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
                ),
                returned AS (
                    SELECT DISTINCT c.chat_id
                    FROM cohort c
                    INNER JOIN bot_usage b ON c.chat_id = b.chat_id
                    WHERE b.created_at >= c.first_used + INTERVAL '7 days'
                    AND b.created_at < c.first_used + INTERVAL '14 days'
                    AND b.success = true
                )
                SELECT 
                    COUNT(DISTINCT c.chat_id) as cohort_size,
                    COUNT(DISTINCT r.chat_id) as returned_count
                FROM cohort c
                LEFT JOIN returned r ON c.chat_id = r.chat_id
            """)
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
                ),
                returned AS (
                    SELECT DISTINCT c.chat_id
                    FROM cohort c
                    INNER JOIN bot_usage b ON c.chat_id = b.chat_id
                    WHERE b.created_at >= c.first_used + INTERVAL '30 days'
                    AND b.created_at < c.first_used + INTERVAL '60 days'
                    AND b.success = true
                )
                SELECT 
                    COUNT(DISTINCT c.chat_id) as cohort_size,
                    COUNT(DISTINCT r.chat_id) as returned_count
                FROM cohort c
                LEFT JOIN returned r ON c.chat_id = r.chat_id
            """)
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

def get_all_bot_users(limit=100, offset=0):
    """
    Get all bot users with their activity stats.
    
    Args:
        limit (int): Number of users to return
        offset (int): Offset for pagination
    
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
            cursor.execute("SELECT COUNT(*) FROM bot_users")
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
                LEFT JOIN bot_usage b ON u.chat_id = b.chat_id
                GROUP BY u.chat_id, u.username, u.first_name, u.last_name, u.first_used, u.last_used
                ORDER BY COALESCE(COUNT(b.id) FILTER (WHERE b.success = true), 0) DESC, u.last_used DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, (limit, offset))
            
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

def get_user_activity_history(chat_id, limit=100):
    """
    Get complete activity history for a specific user.
    
    Args:
        chat_id (int): Telegram chat ID
        limit (int): Max number of records to return
    
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
                WHERE chat_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (chat_id, limit))
            
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

def get_invalid_coupon_attempts(limit=100, offset=0, template_filter=None, days=None):
    """
    Get all invalid coupon validation attempts.
    
    Args:
        limit (int): Number of records to return
        offset (int): Offset for pagination
        template_filter (str, optional): Filter by template name
        days (int, optional): Filter by number of days (e.g., 7 for last 7 days)
    
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
            where_clause = "WHERE success = FALSE"
            params = []
            
            if days is not None:
                where_clause += " AND created_at >= NOW() - INTERVAL '%s days'"
                params.append(days)
            
            if template_filter:
                where_clause += " AND template_slug = %s"
                params.append(template_filter)
            
            # Get total count
            cursor.execute(f"SELECT COUNT(*) FROM bot_usage {where_clause}", params)
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
                LEFT JOIN bot_users u ON b.chat_id = u.chat_id
                {where_clause}
                ORDER BY b.created_at DESC
                LIMIT %s OFFSET %s
            """, query_params)
            
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

def remove_bot_user(chat_id):
    """
    Remove a bot user (e.g., when they block the bot).
    
    Args:
        chat_id (int): Telegram chat ID to remove
    """
    try:
        if not db_pool.connection_pool:
            return
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bot_users WHERE chat_id = %s", (chat_id,))
            conn.commit()
    except Exception as e:
        print(f"[BOT_USER] Failed to remove user {chat_id}: {e}")

# Broadcast job management
def create_broadcast_job(message, target_days, total_users):
    """
    Create a new broadcast job.
    
    Args:
        message (str): Message to broadcast
        target_days (int): Days of activity to target
        total_users (int): Total number of users to broadcast to
    
    Returns:
        int: Job ID
    """
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO broadcast_jobs (message, target_days, status, total_users)
                VALUES (%s, %s, 'pending', %s)
                RETURNING id
            """, (message, target_days, total_users))
            job_id = cursor.fetchone()[0]
            conn.commit()
            return job_id
    except Exception as e:
        print(f"Error creating broadcast job: {e}")
        return None

def update_broadcast_job(job_id, status=None, sent_count=None, failed_count=None, completed=False):
    """
    Update broadcast job progress.
    
    Args:
        job_id (int): Job ID
        status (str): Job status ('pending', 'processing', 'completed', 'failed')
        sent_count (int): Number of successfully sent messages
        failed_count (int): Number of failed messages
        completed (bool): Whether job is completed
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
                query = f"UPDATE broadcast_jobs SET {', '.join(updates)} WHERE id = %s"
                cursor.execute(query, params)
                conn.commit()
    except Exception as e:
        print(f"Error updating broadcast job {job_id}: {e}")

def get_broadcast_job(job_id):
    """
    Get broadcast job details.
    
    Args:
        job_id (int): Job ID
    
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
                WHERE id = %s
            """, (job_id,))
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

def get_recent_broadcast_jobs(limit=10):
    """
    Get recent broadcast jobs.
    
    Args:
        limit (int): Number of jobs to return
    
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
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))
            
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
                       stop_loss=None, rsi_value=None, macd_value=None, atr_value=None):
    """
    Create a new forex signal.
    
    Args:
        signal_type (str): 'BUY' or 'SELL'
        pair (str): Currency pair (e.g., 'XAU/USD', 'EUR/USD')
        timeframe (str): Timeframe (e.g., '15m', '30m', '1h')
        entry_price (float): Entry price for the signal
        take_profit (float, optional): Take profit price
        stop_loss (float, optional): Stop loss price
        rsi_value (float, optional): RSI indicator value
        macd_value (float, optional): MACD indicator value
        atr_value (float, optional): ATR indicator value
    
    Returns:
        int: Signal ID
    """
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO forex_signals 
                (signal_type, pair, timeframe, entry_price, take_profit, stop_loss,
                 rsi_value, macd_value, atr_value, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                RETURNING id
            """, (signal_type, pair, timeframe, entry_price, take_profit, stop_loss,
                  rsi_value, macd_value, atr_value))
            signal_id = cursor.fetchone()[0]
            conn.commit()
            return signal_id
    except Exception as e:
        print(f"Error creating forex signal: {e}")
        raise

def get_forex_signals(status=None, limit=100):
    """
    Get forex signals with optional status filtering.
    
    Args:
        status (str, optional): Filter by status ('pending', 'won', 'lost', 'expired')
        limit (int): Maximum number of signals to return (default: 100)
    
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
                           posted_at, closed_at, result_pips
                    FROM forex_signals
                    WHERE status = %s
                    ORDER BY posted_at DESC
                    LIMIT %s
                """, (status, limit))
            else:
                cursor.execute("""
                    SELECT id, signal_type, pair, timeframe, entry_price, take_profit, 
                           stop_loss, status, rsi_value, macd_value, atr_value, 
                           posted_at, closed_at, result_pips
                    FROM forex_signals
                    ORDER BY posted_at DESC
                    LIMIT %s
                """, (limit,))
            
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
        print(f"Error getting forex signals: {e}")
        return []

def update_forex_signal_status(signal_id, status, result_pips=None):
    """
    Update forex signal status and optionally set result.
    
    Args:
        signal_id (int): Signal ID to update
        status (str): New status ('pending', 'won', 'lost', 'expired')
        result_pips (float, optional): Result in pips (positive for profit, negative for loss)
    
    Returns:
        bool: True if successful
    """
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            if result_pips is not None:
                cursor.execute("""
                    UPDATE forex_signals
                    SET status = %s, result_pips = %s, closed_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (status, result_pips, signal_id))
            else:
                cursor.execute("""
                    UPDATE forex_signals
                    SET status = %s, closed_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (status, signal_id))
            
            conn.commit()
            return True
    except Exception as e:
        print(f"Error updating forex signal status: {e}")
        raise

def get_forex_stats(days=7):
    """
    Get forex signals statistics for the last N days.
    
    Args:
        days (int): Number of days to analyze (default: 7)
    
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
                WHERE posted_at >= CURRENT_TIMESTAMP - %s::interval
            """, (f"{days} days",))
            total_signals = cursor.fetchone()[0]
            
            # Closed signals (won + lost)
            cursor.execute("""
                SELECT COUNT(*) FROM forex_signals
                WHERE posted_at >= CURRENT_TIMESTAMP - %s::interval
                AND status IN ('won', 'lost')
            """, (f"{days} days",))
            closed_signals = cursor.fetchone()[0]
            
            # Won signals
            cursor.execute("""
                SELECT COUNT(*) FROM forex_signals
                WHERE posted_at >= CURRENT_TIMESTAMP - %s::interval
                AND status = 'won'
            """, (f"{days} days",))
            won_signals = cursor.fetchone()[0]
            
            # Lost signals
            cursor.execute("""
                SELECT COUNT(*) FROM forex_signals
                WHERE posted_at >= CURRENT_TIMESTAMP - %s::interval
                AND status = 'lost'
            """, (f"{days} days",))
            lost_signals = cursor.fetchone()[0]
            
            # Pending signals
            cursor.execute("""
                SELECT COUNT(*) FROM forex_signals
                WHERE posted_at >= CURRENT_TIMESTAMP - %s::interval
                AND status = 'pending'
            """, (f"{days} days",))
            pending_signals = cursor.fetchone()[0]
            
            # Total pips (profit/loss)
            cursor.execute("""
                SELECT COALESCE(SUM(result_pips), 0) FROM forex_signals
                WHERE posted_at >= CURRENT_TIMESTAMP - %s::interval
                AND result_pips IS NOT NULL
            """, (f"{days} days",))
            total_pips = float(cursor.fetchone()[0])
            
            # Signals by pair
            cursor.execute("""
                SELECT pair, COUNT(*) as count
                FROM forex_signals
                WHERE posted_at >= CURRENT_TIMESTAMP - %s::interval
                GROUP BY pair
                ORDER BY count DESC
                LIMIT 10
            """, (f"{days} days",))
            signals_by_pair = [{'pair': row[0], 'count': row[1]} for row in cursor.fetchall()]
            
            # Daily signal count
            cursor.execute("""
                SELECT DATE(posted_at) as date, COUNT(*) as count
                FROM forex_signals
                WHERE posted_at >= CURRENT_TIMESTAMP - %s::interval
                GROUP BY DATE(posted_at)
                ORDER BY date DESC
            """, (f"{days} days",))
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

def get_forex_signals_by_period(period='today'):
    """
    Get forex signals for a specific time period.
    
    Args:
        period (str): Time period - 'today', 'yesterday', 'week', 'month'
    
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
                    WHERE posted_at >= CURRENT_DATE
                    ORDER BY posted_at DESC
                """
            elif period == 'yesterday':
                query = """
                    SELECT id, signal_type, pair, timeframe, entry_price, take_profit, 
                           stop_loss, status, rsi_value, macd_value, atr_value, 
                           posted_at, closed_at, result_pips
                    FROM forex_signals
                    WHERE posted_at >= CURRENT_DATE - INTERVAL '1 day'
                    AND posted_at < CURRENT_DATE
                    ORDER BY posted_at DESC
                """
            elif period == 'week':
                query = """
                    SELECT id, signal_type, pair, timeframe, entry_price, take_profit, 
                           stop_loss, status, rsi_value, macd_value, atr_value, 
                           posted_at, closed_at, result_pips
                    FROM forex_signals
                    WHERE posted_at >= CURRENT_DATE - INTERVAL '7 days'
                    ORDER BY posted_at DESC
                """
            else:
                query = """
                    SELECT id, signal_type, pair, timeframe, entry_price, take_profit, 
                           stop_loss, status, rsi_value, macd_value, atr_value, 
                           posted_at, closed_at, result_pips
                    FROM forex_signals
                    WHERE posted_at >= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY posted_at DESC
                """
            
            cursor.execute(query)
            
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

def get_forex_stats_by_period(period='today'):
    """
    Get forex statistics for a specific time period.
    
    Args:
        period (str): 'today', 'yesterday', 'week', 'month'
    
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
                WHERE {time_filter}
            """)
            
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
            'trading_end_hour': '22'
        }
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            for key, value in default_config.items():
                cursor.execute("""
                    INSERT INTO forex_config (setting_key, setting_value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (setting_key) 
                    DO NOTHING
                """, (key, value))
            
            conn.commit()
            print("✅ Forex config initialized with defaults")
            return True
    except Exception as e:
        print(f"Error initializing forex config: {e}")
        return False

def get_forex_config():
    """
    Get current forex configuration as a dictionary.
    
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
            """)
            
            config = {}
            latest_update = None
            
            for row in cursor.fetchall():
                key = row[0]
                value = row[1]
                updated_at = row[2]
                
                # Convert to appropriate type
                if key in ['rsi_oversold', 'rsi_overbought', 'adx_threshold', 'trading_start_hour', 'trading_end_hour']:
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
                    INSERT INTO forex_config (setting_key, setting_value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (setting_key) 
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

# ===== Telegram Subscriptions Functions =====

def create_telegram_subscription(email, stripe_customer_id=None, stripe_subscription_id=None, plan_type='premium', amount_paid=49.00, name=None):
    """
    Create or update a telegram subscription record (UPSERT).
    
    Supports both paid (Stripe) and free users:
    - Paid users: Include stripeCustomerId and stripeSubscriptionId
    - Free users: Pass None for Stripe fields, set planType='Free Gold Signals' and amountPaid=0
    
    If email already exists, updates the existing record.
    
    Args:
        email (str): Customer email (required)
        stripe_customer_id (str): Stripe customer ID (optional, None for free users)
        stripe_subscription_id (str): Stripe subscription ID (optional, None for free users)
        plan_type (str): Plan type (default: 'premium', use 'Free Gold Signals' for free users)
        amount_paid (float): Amount paid (default: 49.00, use 0 for free users)
        name (str): Customer name (optional)
    
    Returns:
        dict: Created/updated subscription record or None if failed
    """
    try:
        if not db_pool.connection_pool:
            print("[DB] No connection pool available")
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # UPSERT: Insert or update if email already exists
            cursor.execute("""
                INSERT INTO telegram_subscriptions 
                (email, name, stripe_customer_id, stripe_subscription_id, plan_type, amount_paid, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (email) DO UPDATE SET
                    name = COALESCE(EXCLUDED.name, telegram_subscriptions.name),
                    stripe_customer_id = COALESCE(EXCLUDED.stripe_customer_id, telegram_subscriptions.stripe_customer_id),
                    stripe_subscription_id = COALESCE(EXCLUDED.stripe_subscription_id, telegram_subscriptions.stripe_subscription_id),
                    plan_type = EXCLUDED.plan_type,
                    amount_paid = EXCLUDED.amount_paid,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id, email, stripe_customer_id, stripe_subscription_id, status, created_at
            """, (email, name, stripe_customer_id, stripe_subscription_id, plan_type, amount_paid))
            
            result = cursor.fetchone()
            conn.commit()
            
            if result:
                return {
                    'id': result[0],
                    'email': result[1],
                    'stripe_customer_id': result[2],
                    'stripe_subscription_id': result[3],
                    'status': result[4],
                    'created_at': result[5].isoformat() if result[5] else None
                }
            
            return None
    except Exception as e:
        print(f"Error creating telegram subscription: {e}")
        return None

def get_telegram_subscription_by_email(email):
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
                WHERE email = %s
            """, (email,))
            
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

def update_telegram_subscription_invite(email, invite_link):
    """Update telegram subscription with invite link"""
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE telegram_subscriptions
                SET invite_link = %s, status = 'active', updated_at = CURRENT_TIMESTAMP
                WHERE email = %s
            """, (invite_link, email))
            
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating telegram subscription invite: {e}")
        return False

def update_telegram_subscription_user_joined(email, telegram_user_id, telegram_username):
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
                WHERE email = %s
            """, (telegram_user_id, telegram_username, email))
            
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating telegram subscription user joined: {e}")
        return False

def revoke_telegram_subscription(email, reason='subscription_canceled'):
    """Revoke telegram subscription access"""
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE telegram_subscriptions
                SET status = 'revoked', revoked_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE email = %s
                RETURNING telegram_user_id
            """, (email,))
            
            result = cursor.fetchone()
            conn.commit()
            
            if result:
                return result[0]
            return None
    except Exception as e:
        print(f"Error revoking telegram subscription: {e}")
        return None

def get_all_telegram_subscriptions(status_filter=None, include_test=False):
    """Get all telegram subscriptions with optional status filter and test/live filter"""
    try:
        if not db_pool.connection_pool:
            return []
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            conditions = []
            params = []
            
            if status_filter:
                conditions.append("status = %s")
                params.append(status_filter)
            
            if not include_test:
                conditions.append("(is_test = FALSE OR is_test IS NULL)")
            
            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)
            
            cursor.execute(f"""
                SELECT id, email, name, telegram_user_id, telegram_username, 
                       stripe_customer_id, stripe_subscription_id, plan_type, amount_paid,
                       status, invite_link, joined_at, last_seen_at, revoked_at, created_at, updated_at,
                       COALESCE(is_test, FALSE) as is_test
                FROM telegram_subscriptions
                {where_clause}
                ORDER BY created_at DESC
            """, params)
            
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

def update_telegram_subscription_last_seen(telegram_user_id):
    """Update last_seen_at for a telegram user"""
    try:
        if not db_pool.connection_pool:
            return False
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE telegram_subscriptions
                SET last_seen_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = %s
            """, (telegram_user_id,))
            
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Error updating telegram subscription last seen: {e}")
        return False

def link_subscription_to_telegram_user(invite_link, telegram_user_id, telegram_username, joined_at):
    """
    Auto-link a Telegram user ID to a subscription record when they join the channel.
    
    This function is called by the Telegram bot join tracker when a user joins the private channel.
    It matches the join event to a subscription record using the invite link (or fallback logic).
    
    Args:
        invite_link (str): Invite link used to join (may be None if not available)
        telegram_user_id (int): Telegram user ID
        telegram_username (str): Telegram username (may be None)
        joined_at (datetime): Timestamp when user joined
    
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
                    WHERE invite_link = %s AND status = 'pending'
                    LIMIT 1
                """, (invite_link,))
                result = cursor.fetchone()
                if result:
                    subscription_id = result[0]
                    email = result[1]
                    print(f"[JOIN_TRACKER] Found subscription by invite_link: {email}")
            
            # Fallback: Find most recent pending subscription if no invite_link match
            if not subscription_id:
                cursor.execute("""
                    SELECT id, email FROM telegram_subscriptions
                    WHERE status = 'pending' AND telegram_user_id IS NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                """)
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
