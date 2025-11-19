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
                conn.rollback()
            raise
        finally:
            if conn:
                self.connection_pool.putconn(conn)
    
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
                
                conn.commit()
                print("✅ Database schema initialized")
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
            
            cursor.execute(f"""
                SELECT 
                    coupon_code, 
                    COUNT(*) as total_uses,
                    COUNT(DISTINCT chat_id) as unique_users
                FROM bot_usage
                WHERE {where_clause}
                AND coupon_code IS NOT NULL
                AND success = true
                {template_where}
                GROUP BY coupon_code
                ORDER BY total_uses DESC
            """, tuple(template_params))
            popular_coupons = [{'coupon': row[0], 'count': row[1], 'unique_users': row[2]} for row in cursor.fetchall()]
            
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

def get_device_stats(days=30):
    """
    Get device usage statistics.
    
    Args:
        days (int): Number of days to analyze
    
    Returns:
        list: Device breakdown with counts and percentages
    """
    try:
        if not db_pool.connection_pool:
            return []
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            interval = f"{days} days"
            
            cursor.execute("""
                SELECT 
                    device_type,
                    COUNT(*) as count,
                    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
                FROM bot_usage
                WHERE created_at >= CURRENT_TIMESTAMP - %s::interval
                AND success = true
                GROUP BY device_type
                ORDER BY count DESC
            """, (interval,))
            
            devices = []
            for row in cursor.fetchall():
                devices.append({
                    'device_type': row[0],
                    'count': row[1],
                    'percentage': float(row[2])
                })
            
            return devices
    except Exception as e:
        print(f"Error getting device stats: {e}")
        return []

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
    Get bot user data including last coupon used and profile information.
    
    Args:
        chat_id (int): Telegram chat ID
    
    Returns:
        dict: User data with chat_id, last_coupon_code, last_used, username, first_name, last_name
        None: If user not found or error
    """
    if not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chat_id, last_coupon_code, last_used, username, first_name, last_name 
                FROM bot_users 
                WHERE chat_id = %s
            """, (chat_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'chat_id': row[0],
                    'last_coupon_code': row[1],
                    'last_used': row[2].isoformat() if row[2] else None,
                    'username': row[3],
                    'first_name': row[4],
                    'last_name': row[5]
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
