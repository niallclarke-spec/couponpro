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
            self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                1,
                20,
                host=os.environ.get('DB_HOST'),
                port=os.environ.get('DB_PORT'),
                database=os.environ.get('DB_NAME'),
                user=os.environ.get('DB_USER'),
                password=os.environ.get('DB_PASSWORD'),
                sslmode='require'
            )
            print("✅ Database connection pool initialized")
        except Exception as e:
            print(f"❌ Failed to initialize database pool: {e}")
            self.connection_pool = None
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = None
        try:
            if self.connection_pool:
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
        """Create campaigns and submissions tables if they don't exist"""
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
                        status VARCHAR(50) DEFAULT 'scheduled',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
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
                
                conn.commit()
                print("✅ Database schema initialized")
        except Exception as e:
            print(f"❌ Failed to initialize schema: {e}")

# Global database pool instance
db_pool = DatabasePool()

# Campaign CRUD operations
def create_campaign(title, description, start_date, end_date, prize, platforms):
    """Create a new campaign"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO campaigns 
                (title, description, start_date, end_date, prize, platforms, status)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                RETURNING id
            """, (title, description, start_date, end_date, prize, platforms, 'scheduled'))
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
                SELECT id, title, description, start_date, end_date, prize, platforms, status, created_at
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
                    'status': row[7],
                    'created_at': row[8].isoformat() if row[8] else None
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
                SELECT id, title, description, start_date, end_date, prize, platforms, status, created_at
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
                    'status': row[7],
                    'created_at': row[8].isoformat() if row[8] else None
                }
            return None
    except Exception as e:
        print(f"Error getting campaign: {e}")
        return None

def update_campaign(campaign_id, title, description, start_date, end_date, prize, platforms):
    """Update an existing campaign"""
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE campaigns
                SET title = %s, description = %s, start_date = %s, end_date = %s,
                    prize = %s, platforms = %s::jsonb, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (title, description, start_date, end_date, prize, platforms, campaign_id))
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
