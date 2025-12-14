"""
Leader election using PostgreSQL advisory locks.

This module provides a mechanism to ensure only one server instance
runs background schedulers during deploys (avoiding duplicate signals).

Safety guarantees:
1. Scheduler can ONLY start once per process (threading.Lock protected)
2. Retry loop is resilient to DB connection drops (auto-reconnect)
3. All threads are daemon threads (clean shutdown)
"""
import psycopg2
import threading
import time
from core.config import Config

SCHEDULER_LOCK_ID = 8237461823746182
RETRY_INTERVAL_SECONDS = 10

_leader_connection = None
_is_leader = False
_scheduler_started = False
_scheduler_lock = threading.Lock()
_scheduler_callback = None


def _get_or_create_connection():
    """
    Get existing connection or create new one.
    Handles reconnection if connection was dropped.
    """
    global _leader_connection
    
    db_url = Config.get_database_url()
    if not db_url:
        return None
    
    if _leader_connection is not None:
        try:
            _leader_connection.cursor().execute("SELECT 1")
            return _leader_connection
        except Exception:
            print("[SCHEDULER] Connection dropped, reconnecting...")
            try:
                _leader_connection.close()
            except Exception:
                pass
            _leader_connection = None
    
    _leader_connection = psycopg2.connect(db_url)
    _leader_connection.autocommit = True
    print("[SCHEDULER] Database connection established")
    return _leader_connection


def acquire_scheduler_leader_lock() -> bool:
    """
    Attempt to acquire advisory lock for scheduler leadership.
    
    Uses a dedicated connection that stays open for process lifetime.
    The lock is automatically released when the connection closes.
    
    Returns:
        True if lock acquired (we are leader), False otherwise.
    """
    global _is_leader
    
    try:
        conn = _get_or_create_connection()
        if conn is None:
            print("[SCHEDULER] No DATABASE_URL, assuming single instance mode")
            _is_leader = True
            return True
        
        cursor = conn.cursor()
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (SCHEDULER_LOCK_ID,))
        result = cursor.fetchone()[0]
        
        if result:
            _is_leader = True
        
        return result
        
    except Exception as e:
        print(f"[SCHEDULER] Error acquiring leader lock: {e}")
        _is_leader = True
        return True


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
        print("[SCHEDULER] No scheduler callback registered, cannot start")
        return False
    
    with _scheduler_lock:
        if _scheduler_started:
            print("[SCHEDULER] Scheduler already started, ignoring duplicate call")
            return False
        
        try:
            cb()
            _scheduler_started = True
            return True
        except Exception as e:
            print(f"[SCHEDULER] Callback failed, will retry: {e}")
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
                print("[SCHEDULER] Retrying leader lock acquisition...")
                
                if acquire_scheduler_leader_lock():
                    print("[SCHEDULER] Leader lock acquired on retry")
                    start_scheduler_once()
                    break
                    
            except Exception as e:
                print(f"[SCHEDULER] Retry loop error: {e}")
                continue
    
    thread = threading.Thread(target=retry_loop, daemon=True)
    thread.start()
    print(f"[SCHEDULER] Started leader retry loop (every {RETRY_INTERVAL_SECONDS}s)")
