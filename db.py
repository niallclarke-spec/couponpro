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
                    sslmode='prefer'
                )
                print("✅ Database connection pool initialized (using DATABASE_URL)")
            elif db_host:
                self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                    1,
                    20,
                    host=db_host,
                    port=os.environ.get('DB_PORT'),
                    database=os.environ.get('DB_NAME'),
                    user=os.environ.get('DB_USER'),
                    password=os.environ.get('DB_PASSWORD'),
                    sslmode='prefer'
                )
                print("✅ Database connection pool initialized (using DB_HOST)")
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
def log_bot_usage(chat_id, template_slug, coupon_code, success, error_type=None):
    """
    Log Telegram bot usage. Silently fails to avoid disrupting bot operation.
    
    Args:
        chat_id (int): Telegram chat ID
        template_slug (str): Template slug used (or None if template not found)
        coupon_code (str): Coupon code used
        success (bool): Whether the operation succeeded
        error_type (str): Type of error if failed (e.g., 'network', 'invalid_coupon', 'template_not_found')
    """
    try:
        if not db_pool.connection_pool:
            return
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bot_usage 
                (chat_id, template_slug, coupon_code, success, error_type)
                VALUES (%s, %s, %s, %s, %s)
            """, (chat_id, template_slug, coupon_code, success, error_type))
            conn.commit()
    except Exception as e:
        print(f"[BOT_USAGE] Failed to log usage (non-critical): {e}")

def get_bot_stats(days=30):
    """
    Get bot usage statistics for the last N days.
    
    Args:
        days (int): Number of days to include in stats (default: 30)
    
    Returns:
        dict: Statistics including total uses, success rate, popular templates/coupons
    """
    try:
        if not db_pool.connection_pool:
            return None
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            interval = f"{days} days"
            
            # Total usage count
            cursor.execute("""
                SELECT COUNT(*) FROM bot_usage
                WHERE created_at >= CURRENT_TIMESTAMP - %s::interval
            """, (interval,))
            total_uses = cursor.fetchone()[0]
            
            # Success count
            cursor.execute("""
                SELECT COUNT(*) FROM bot_usage
                WHERE created_at >= CURRENT_TIMESTAMP - %s::interval
                AND success = true
            """, (interval,))
            successful_uses = cursor.fetchone()[0]
            
            # Popular templates
            cursor.execute("""
                SELECT template_slug, COUNT(*) as count
                FROM bot_usage
                WHERE created_at >= CURRENT_TIMESTAMP - %s::interval
                AND template_slug IS NOT NULL
                GROUP BY template_slug
                ORDER BY count DESC
                LIMIT 10
            """, (interval,))
            popular_templates = [{'template': row[0], 'count': row[1]} for row in cursor.fetchall()]
            
            # Popular coupon codes
            cursor.execute("""
                SELECT coupon_code, COUNT(*) as count
                FROM bot_usage
                WHERE created_at >= CURRENT_TIMESTAMP - %s::interval
                AND coupon_code IS NOT NULL
                AND success = true
                GROUP BY coupon_code
                ORDER BY count DESC
                LIMIT 10
            """, (interval,))
            popular_coupons = [{'coupon': row[0], 'count': row[1]} for row in cursor.fetchall()]
            
            # Error breakdown
            cursor.execute("""
                SELECT error_type, COUNT(*) as count
                FROM bot_usage
                WHERE created_at >= CURRENT_TIMESTAMP - %s::interval
                AND success = false
                AND error_type IS NOT NULL
                GROUP BY error_type
                ORDER BY count DESC
            """, (interval,))
            errors = [{'type': row[0], 'count': row[1]} for row in cursor.fetchall()]
            
            # Unique users
            cursor.execute("""
                SELECT COUNT(DISTINCT chat_id) FROM bot_usage
                WHERE created_at >= CURRENT_TIMESTAMP - %s::interval
            """, (interval,))
            unique_users = cursor.fetchone()[0]
            
            # Daily usage for chart
            cursor.execute("""
                SELECT DATE(created_at) as date, COUNT(*) as count
                FROM bot_usage
                WHERE created_at >= CURRENT_TIMESTAMP - %s::interval
                GROUP BY DATE(created_at)
                ORDER BY date DESC
            """, (interval,))
            daily_usage = [{'date': row[0].isoformat(), 'count': row[1]} for row in cursor.fetchall()]
            
            success_rate = (successful_uses / total_uses * 100) if total_uses > 0 else 0
            
            return {
                'total_uses': total_uses,
                'successful_uses': successful_uses,
                'success_rate': round(success_rate, 1),
                'unique_users': unique_users,
                'popular_templates': popular_templates,
                'popular_coupons': popular_coupons,
                'errors': errors,
                'daily_usage': daily_usage
            }
    except Exception as e:
        print(f"Error getting bot stats: {e}")
        return None

# Bot user tracking for broadcasts
def track_bot_user(chat_id, coupon_code):
    """
    Track or update a bot user. Creates new user or updates last_used timestamp.
    
    Args:
        chat_id (int): Telegram chat ID
        coupon_code (str): Coupon code the user is using
    """
    try:
        if not db_pool.connection_pool:
            return
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bot_users (chat_id, last_coupon_code, first_used, last_used)
                VALUES (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (chat_id) 
                DO UPDATE SET 
                    last_coupon_code = EXCLUDED.last_coupon_code,
                    last_used = CURRENT_TIMESTAMP
            """, (chat_id, coupon_code))
            conn.commit()
    except Exception as e:
        print(f"[BOT_USER] Failed to track user (non-critical): {e}")

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
