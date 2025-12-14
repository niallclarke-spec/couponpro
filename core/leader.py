"""
Leader election using PostgreSQL advisory locks.

This module provides a mechanism to ensure only one server instance
runs background schedulers during deploys (avoiding duplicate signals).

If initial lock acquisition fails (another instance holds it), a background
thread retries periodically. When the lock is eventually acquired (after the
old leader dies), the scheduler is started.
"""
import psycopg2
import threading
import time
from core.config import Config

SCHEDULER_LOCK_ID = 8237461823746182
RETRY_INTERVAL_SECONDS = 10
_leader_connection = None
_is_leader = False
_scheduler_start_callback = None


def acquire_scheduler_leader_lock() -> bool:
    """
    Attempt to acquire advisory lock for scheduler leadership.
    
    Uses a dedicated connection that stays open for process lifetime.
    The lock is automatically released when the connection closes.
    
    Returns:
        True if lock acquired (we are leader), False otherwise.
    """
    global _leader_connection, _is_leader
    
    try:
        db_url = Config.get_database_url()
        if not db_url:
            print("[SCHEDULER] No DATABASE_URL, assuming single instance mode")
            _is_leader = True
            return True
        
        if _leader_connection is None:
            _leader_connection = psycopg2.connect(db_url)
            _leader_connection.autocommit = True
        
        cursor = _leader_connection.cursor()
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (SCHEDULER_LOCK_ID,))
        result = cursor.fetchone()[0]
        
        if result:
            _is_leader = True
        
        return result
        
    except Exception as e:
        print(f"[SCHEDULER] Error acquiring leader lock: {e}")
        _is_leader = True
        return True


def start_leader_retry_loop(scheduler_callback):
    """
    Start a background thread that periodically retries lock acquisition.
    
    When lock is eventually acquired (after old leader terminates),
    calls scheduler_callback to start the scheduler.
    """
    global _scheduler_start_callback
    _scheduler_start_callback = scheduler_callback
    
    def retry_loop():
        global _is_leader
        while not _is_leader:
            time.sleep(RETRY_INTERVAL_SECONDS)
            print("[SCHEDULER] Retrying leader lock acquisition...")
            if acquire_scheduler_leader_lock():
                print("[SCHEDULER] Leader lock acquired on retry, starting scheduler")
                if _scheduler_start_callback:
                    _scheduler_start_callback()
                break
    
    thread = threading.Thread(target=retry_loop, daemon=True)
    thread.start()
    print(f"[SCHEDULER] Started leader retry loop (every {RETRY_INTERVAL_SECONDS}s)")
