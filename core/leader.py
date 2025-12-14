"""
Leader election using PostgreSQL advisory locks.

This module provides a mechanism to ensure only one server instance
runs background schedulers during deploys (avoiding duplicate signals).

Safety guarantees:
1. Scheduler can ONLY start once per process (threading.Lock protected)
2. Retry loop is resilient to DB connection drops (auto-reconnect)
3. All threads are daemon threads (clean shutdown)
4. Fail-safe: if no DB connection possible, scheduler does NOT start
"""
import psycopg2
import threading
import time
from core.config import Config
from core.logging import get_logger

logger = get_logger(__name__)

SCHEDULER_LOCK_ID = 8237461823746182
RETRY_INTERVAL_SECONDS = 10

_leader_connection = None
_is_leader = False
_scheduler_started = False
_scheduler_lock = threading.Lock()
_scheduler_callback = None
_connection_mode = None


def _build_dsn_from_db_vars():
    """
    Build a PostgreSQL DSN from individual DB_* environment variables.
    Returns tuple of (dsn_string, missing_vars_list).
    """
    host = Config.get_db_host()
    port = Config.get_db_port() or '5432'
    name = Config.get_db_name()
    user = Config.get_db_user()
    password = Config.get_db_password()
    sslmode = Config.get_db_sslmode()
    
    missing = []
    if not host:
        missing.append('DB_HOST')
    if not name:
        missing.append('DB_NAME')
    if not user:
        missing.append('DB_USER')
    if not password:
        missing.append('DB_PASSWORD')
    
    if missing:
        return None, missing
    
    dsn = f"postgresql://{user}:{password}@{host}:{port}/{name}?sslmode={sslmode}"
    return dsn, []


def _get_or_create_connection():
    """
    Get existing connection or create new one.
    Handles reconnection if connection was dropped.
    
    Connection priority:
    1. DATABASE_URL environment variable
    2. Build DSN from DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    
    Returns:
        Connection object if successful, None if no credentials available.
    
    Raises:
        Exception if connection fails (credentials exist but connection error).
    """
    global _leader_connection, _connection_mode
    
    if _leader_connection is not None:
        try:
            _leader_connection.cursor().execute("SELECT 1")
            return _leader_connection
        except Exception:
            logger.warning("Connection dropped, reconnecting...")
            try:
                _leader_connection.close()
            except Exception:
                pass
            _leader_connection = None
    
    db_url = Config.get_database_url()
    if db_url:
        _connection_mode = "DATABASE_URL"
        logger.info("Leader lock using DATABASE_URL")
        _leader_connection = psycopg2.connect(db_url)
        _leader_connection.autocommit = True
        logger.info("Database connection established")
        return _leader_connection
    
    dsn, missing = _build_dsn_from_db_vars()
    if dsn:
        _connection_mode = "DB_* vars"
        logger.info("Leader lock using DB_HOST/DB_* vars")
        _leader_connection = psycopg2.connect(dsn)
        _leader_connection.autocommit = True
        logger.info("Database connection established")
        return _leader_connection
    
    _connection_mode = None
    return None


def acquire_scheduler_leader_lock() -> bool:
    """
    Attempt to acquire advisory lock for scheduler leadership.
    
    Uses a dedicated connection that stays open for process lifetime.
    The lock is automatically released when the connection closes.
    
    FAIL-SAFE BEHAVIOR:
    - If no DB credentials available: returns False (scheduler does NOT start)
    - If connection fails: returns False (scheduler does NOT start)
    - If lock not acquired: returns False (another instance is leader)
    
    Returns:
        True if lock acquired (we are leader), False otherwise.
    """
    global _is_leader
    
    try:
        conn = _get_or_create_connection()
        if conn is None:
            logger.warning("No database credentials available (need DATABASE_URL or DB_HOST/DB_* vars)")
            logger.warning("Scheduler will NOT start - cannot ensure single instance")
            return False
        
        cursor = conn.cursor()
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (SCHEDULER_LOCK_ID,))
        result = cursor.fetchone()[0]
        
        if result:
            _is_leader = True
            return True
        else:
            logger.info("Leader lock not acquired, another instance is leader (standby mode)")
            return False
        
    except Exception as e:
        logger.warning(f"Failed to acquire leader lock: {e}")
        logger.warning("Scheduler will NOT start - cannot ensure single instance")
        return False


def start_scheduler_once(callback=None):
    """
    Start the scheduler exactly once per process.
    
    Thread-safe: uses threading.Lock to ensure only one caller succeeds.
    Both the immediate-start path and retry-loop path call this.
    
    If the callback raises an exception, the started flag remains False
    so a later retry can attempt again.
    
    Args:
        callback: Function to call to start the scheduler. If None, uses
                  the callback registered via start_leader_retry_loop.
    
    Returns:
        True if scheduler was started, False if already running or no callback.
    """
    global _scheduler_started
    
    cb = callback or _scheduler_callback
    if not cb:
        logger.warning("No scheduler callback registered, cannot start")
        return False
    
    with _scheduler_lock:
        if _scheduler_started:
            logger.info("Scheduler already started, ignoring duplicate call")
            return False
        
        try:
            cb()
            _scheduler_started = True
            return True
        except Exception as e:
            logger.exception("Callback failed, will retry")
            return False


def start_leader_retry_loop(scheduler_callback):
    """
    Start a background thread that periodically retries lock acquisition.
    
    When lock is eventually acquired (after old leader terminates),
    calls start_scheduler_once() to start the scheduler.
    
    The retry loop is resilient:
    - Wraps lock attempts in try/except
    - Reconnects if DB connection drops
    - Runs as daemon thread (auto-cleanup on process exit)
    """
    global _scheduler_callback
    _scheduler_callback = scheduler_callback
    
    def retry_loop():
        global _is_leader
        
        while not _is_leader and not _scheduler_started:
            time.sleep(RETRY_INTERVAL_SECONDS)
            
            try:
                logger.info("Retrying leader lock acquisition...")
                
                if acquire_scheduler_leader_lock():
                    logger.info("Leader lock acquired on retry")
                    start_scheduler_once()
                    break
                    
            except Exception as e:
                logger.exception("Retry loop error")
                continue
    
    thread = threading.Thread(target=retry_loop, daemon=True)
    thread.start()
    logger.info(f"Started leader retry loop (every {RETRY_INTERVAL_SECONDS}s)")
