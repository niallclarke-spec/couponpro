"""
Cross Promo Repository - Database access for settings and job queue.
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
import db
from core.logging import get_logger

logger = get_logger(__name__)


def get_net_pips_over_days(tenant_id: str, days: int) -> float:
    """
    Get net pips (sum of result_pips) over the past N days.
    
    Args:
        tenant_id: Tenant ID
        days: Number of days to look back (e.g., 2, 5, 7, 14)
        
    Returns:
        Net pips as float (can be positive or negative)
    """
    try:
        if not db.db_pool or not db.db_pool.connection_pool:
            logger.warning("Database pool not available for pip query")
            return 0.0
        
        with db.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COALESCE(SUM(result_pips), 0)
                FROM forex_signals
                WHERE tenant_id = %s
                AND closed_at >= NOW() - INTERVAL '%s days'
                AND result_pips IS NOT NULL
            """, (tenant_id, days))
            
            row = cursor.fetchone()
            return float(row[0]) if row and row[0] else 0.0
    except Exception as e:
        logger.exception(f"Error getting pips over {days} days: {e}")
        return 0.0


def get_wins_forwarded_today(tenant_id: str) -> int:
    """
    Count how many winning signals were forwarded to FREE channel today.
    Used to skip end-of-day recap if wins were already sent.
    
    Checks for TP1 sequence forwards which indicate wins were shared.
    Uses 'sent' status which is the terminal status after execution.
    
    Returns:
        Number of win forward jobs completed today
    """
    try:
        if not db.db_pool or not db.db_pool.connection_pool:
            return 0
        
        with db.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            # forward_tp1_sequence is the primary job that forwards winning signals
            # Also check forward_tp3_update as backup (indicates full TP hit was forwarded)
            cursor.execute("""
                SELECT COUNT(*)
                FROM crosspromo_jobs
                WHERE tenant_id = %s
                AND job_type IN ('forward_tp1_sequence', 'forward_tp3_update')
                AND status = 'sent'
                AND run_at >= CURRENT_DATE
            """, (tenant_id,))
            
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] else 0
    except Exception as e:
        logger.exception(f"Error counting forwarded wins: {e}")
        return 0


def get_settings(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Get cross promo settings for a tenant."""
    try:
        with db.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tenant_id, enabled, bot_role, vip_channel_id, free_channel_id,
                       cta_url, morning_post_time_utc, timezone, created_at, updated_at,
                       vip_soon_delay_minutes
                FROM tenant_crosspromo_settings
                WHERE tenant_id = %s
            """, (tenant_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                'tenant_id': row[0],
                'enabled': row[1],
                'bot_role': row[2],
                'vip_channel_id': row[3],
                'free_channel_id': row[4],
                'cta_url': row[5],
                'morning_post_time_utc': row[6],
                'timezone': row[7],
                'created_at': row[8].isoformat() if row[8] else None,
                'updated_at': row[9].isoformat() if row[9] else None,
                'vip_soon_delay_minutes': row[10] if len(row) > 10 else 45,
            }
    except Exception as e:
        logger.exception(f"Error getting crosspromo settings: {e}")
        return None


def upsert_settings(tenant_id: str, **kwargs) -> Optional[Dict[str, Any]]:
    """Create or update cross promo settings for a tenant."""
    try:
        with db.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            enabled = kwargs.get('enabled', False)
            bot_role = kwargs.get('bot_role', 'signal_bot')
            vip_channel_id = kwargs.get('vip_channel_id')
            free_channel_id = kwargs.get('free_channel_id')
            cta_url = kwargs.get('cta_url', 'https://entrylab.io/subscribe')
            morning_post_time_utc = kwargs.get('morning_post_time_utc', '07:00')
            timezone = kwargs.get('timezone', 'UTC')
            vip_soon_delay_minutes = kwargs.get('vip_soon_delay_minutes', 45)
            
            cursor.execute("""
                INSERT INTO tenant_crosspromo_settings 
                    (tenant_id, enabled, bot_role, vip_channel_id, free_channel_id, 
                     cta_url, morning_post_time_utc, timezone, vip_soon_delay_minutes, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (tenant_id) DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    bot_role = EXCLUDED.bot_role,
                    vip_channel_id = EXCLUDED.vip_channel_id,
                    free_channel_id = EXCLUDED.free_channel_id,
                    cta_url = EXCLUDED.cta_url,
                    morning_post_time_utc = EXCLUDED.morning_post_time_utc,
                    timezone = EXCLUDED.timezone,
                    vip_soon_delay_minutes = EXCLUDED.vip_soon_delay_minutes,
                    updated_at = NOW()
                RETURNING tenant_id, enabled, bot_role, vip_channel_id, free_channel_id,
                          cta_url, morning_post_time_utc, timezone, created_at, updated_at,
                          vip_soon_delay_minutes
            """, (tenant_id, enabled, bot_role, vip_channel_id, free_channel_id,
                  cta_url, morning_post_time_utc, timezone, vip_soon_delay_minutes))
            
            row = cursor.fetchone()
            conn.commit()
            
            if not row:
                return None
            
            logger.info(f"Upserted crosspromo settings for tenant {tenant_id}")
            return {
                'tenant_id': row[0],
                'enabled': row[1],
                'bot_role': row[2],
                'vip_channel_id': row[3],
                'free_channel_id': row[4],
                'cta_url': row[5],
                'morning_post_time_utc': row[6],
                'timezone': row[7],
                'created_at': row[8].isoformat() if row[8] else None,
                'updated_at': row[9].isoformat() if row[9] else None,
                'vip_soon_delay_minutes': row[10] if len(row) > 10 else 45,
            }
    except Exception as e:
        logger.exception(f"Error upserting crosspromo settings: {e}")
        return None


def enqueue_job(
    tenant_id: str,
    job_type: str,
    run_at: datetime,
    payload: Optional[Dict[str, Any]] = None,
    dedupe_key: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Add a job to the queue. Returns the job dict or None if dedupe conflict.
    """
    try:
        with db.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            job_id = str(uuid.uuid4())
            payload_json = payload or {}
            
            cursor.execute("""
                INSERT INTO crosspromo_jobs 
                    (id, tenant_id, job_type, run_at, payload, dedupe_key, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'queued')
                ON CONFLICT (tenant_id, dedupe_key) WHERE dedupe_key IS NOT NULL
                DO NOTHING
                RETURNING id, tenant_id, status, run_at, job_type, payload, dedupe_key, error, created_at
            """, (job_id, tenant_id, job_type, run_at, 
                  db.json_module.dumps(payload_json) if hasattr(db, 'json_module') else __import__('json').dumps(payload_json),
                  dedupe_key))
            
            row = cursor.fetchone()
            conn.commit()
            
            if not row:
                logger.info(f"Job dedupe conflict: {tenant_id}/{dedupe_key}")
                return None
            
            logger.info(f"Enqueued job {job_id} type={job_type} for tenant {tenant_id}")
            return _row_to_job(row)
    except Exception as e:
        logger.exception(f"Error enqueueing job: {e}")
        return None


def list_jobs(tenant_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """List jobs for a tenant, most recent first."""
    try:
        with db.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, tenant_id, status, run_at, job_type, payload, dedupe_key, error, created_at
                FROM crosspromo_jobs
                WHERE tenant_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (tenant_id, limit))
            
            rows = cursor.fetchall()
            return [_row_to_job(row) for row in rows]
    except Exception as e:
        logger.exception(f"Error listing jobs: {e}")
        return []


def claim_due_jobs(batch_size: int = 20) -> List[Dict[str, Any]]:
    """
    Atomically claim jobs that are due for processing.
    Uses FOR UPDATE SKIP LOCKED for safe concurrent access.
    """
    try:
        with db.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE crosspromo_jobs
                SET status = 'sending', updated_at = NOW()
                WHERE id IN (
                    SELECT id FROM crosspromo_jobs
                    WHERE status = 'queued' AND run_at <= NOW()
                    ORDER BY run_at
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, tenant_id, status, run_at, job_type, payload, dedupe_key, error, created_at
            """, (batch_size,))
            
            rows = cursor.fetchall()
            conn.commit()
            
            if rows:
                logger.info(f"Claimed {len(rows)} due jobs")
            
            return [_row_to_job(row) for row in rows]
    except Exception as e:
        logger.exception(f"Error claiming jobs: {e}")
        return []


def mark_sent(job_id: str) -> bool:
    """Mark a job as successfully sent."""
    try:
        with db.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE crosspromo_jobs
                SET status = 'sent', updated_at = NOW()
                WHERE id = %s
            """, (job_id,))
            conn.commit()
            logger.info(f"Job {job_id} marked as sent")
            return True
    except Exception as e:
        logger.exception(f"Error marking job sent: {e}")
        return False


def mark_failed(job_id: str, error: str) -> bool:
    """Mark a job as failed with error message."""
    try:
        with db.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE crosspromo_jobs
                SET status = 'failed', error = %s, updated_at = NOW()
                WHERE id = %s
            """, (error, job_id))
            conn.commit()
            logger.warning(f"Job {job_id} marked as failed: {error}")
            return True
    except Exception as e:
        logger.exception(f"Error marking job failed: {e}")
        return False


def cancel_pending_jobs_by_dedupe(dedupe_key: str) -> int:
    """
    Cancel (mark as 'cancelled') all pending jobs with a given dedupe_key.
    Used to reschedule CTA jobs when TP3 is hit.
    
    Returns the number of jobs cancelled.
    """
    try:
        with db.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE crosspromo_jobs
                SET status = 'cancelled', updated_at = NOW()
                WHERE dedupe_key = %s AND status = 'queued'
            """, (dedupe_key,))
            count = cursor.rowcount
            conn.commit()
            
            if count > 0:
                logger.info(f"Cancelled {count} job(s) with dedupe_key={dedupe_key}")
            return count
    except Exception as e:
        logger.exception(f"Error cancelling jobs by dedupe: {e}")
        return 0


def _row_to_job(row) -> Dict[str, Any]:
    """Convert a database row to a job dict."""
    import json
    payload = row[5]
    if isinstance(payload, str):
        payload = json.loads(payload)
    
    return {
        'id': str(row[0]),
        'tenant_id': row[1],
        'status': row[2],
        'run_at': row[3].isoformat() if row[3] else None,
        'job_type': row[4],
        'payload': payload,
        'dedupe_key': row[6],
        'error': row[7],
        'created_at': row[8].isoformat() if row[8] else None,
    }
