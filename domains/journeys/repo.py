"""
Journeys repository - tenant-scoped database functions.

All functions must include tenant_id filters where applicable.
"""
import json
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from core.logging import get_logger

logger = get_logger(__name__)


def _get_db_pool():
    """Get the database pool, importing lazily to avoid circular imports."""
    from db import db_pool
    return db_pool


def create_journey(tenant_id: str, bot_id: str, name: str, description: str = None,
                   status: str = 'draft', re_entry_policy: str = 'block') -> Optional[Dict]:
    """Create a new journey."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO journeys (tenant_id, bot_id, name, description, status, re_entry_policy)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, tenant_id, bot_id, name, description, status, re_entry_policy, created_at, updated_at
            """, (tenant_id, bot_id, name, description, status, re_entry_policy))
            row = cursor.fetchone()
            conn.commit()
            
            if row:
                return {
                    'id': str(row[0]),
                    'tenant_id': row[1],
                    'bot_id': row[2],
                    'name': row[3],
                    'description': row[4],
                    'status': row[5],
                    're_entry_policy': row[6],
                    'created_at': row[7].isoformat() if row[7] else None,
                    'updated_at': row[8].isoformat() if row[8] else None
                }
            return None
    except Exception as e:
        logger.exception(f"Error creating journey: {e}")
        return None


def list_journeys(tenant_id: str) -> List[Dict]:
    """List all journeys for a tenant."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, tenant_id, bot_id, name, description, status, re_entry_policy, created_at, updated_at
                FROM journeys
                WHERE tenant_id = %s
                ORDER BY created_at DESC
            """, (tenant_id,))
            
            journeys = []
            for row in cursor.fetchall():
                journeys.append({
                    'id': str(row[0]),
                    'tenant_id': row[1],
                    'bot_id': row[2],
                    'name': row[3],
                    'description': row[4],
                    'status': row[5],
                    're_entry_policy': row[6],
                    'created_at': row[7].isoformat() if row[7] else None,
                    'updated_at': row[8].isoformat() if row[8] else None
                })
            return journeys
    except Exception as e:
        logger.exception(f"Error listing journeys: {e}")
        return []


def get_journey(tenant_id: str, journey_id: str) -> Optional[Dict]:
    """Get a specific journey by ID."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, tenant_id, bot_id, name, description, status, re_entry_policy, created_at, updated_at
                FROM journeys
                WHERE tenant_id = %s AND id = %s
            """, (tenant_id, journey_id))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': str(row[0]),
                    'tenant_id': row[1],
                    'bot_id': row[2],
                    'name': row[3],
                    'description': row[4],
                    'status': row[5],
                    're_entry_policy': row[6],
                    'created_at': row[7].isoformat() if row[7] else None,
                    'updated_at': row[8].isoformat() if row[8] else None
                }
            return None
    except Exception as e:
        logger.exception(f"Error getting journey: {e}")
        return None


def update_journey(tenant_id: str, journey_id: str, fields: Dict) -> Optional[Dict]:
    """Update a journey's fields."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    allowed_fields = {'name', 'description', 'status', 're_entry_policy', 'bot_id'}
    update_fields = {k: v for k, v in fields.items() if k in allowed_fields}
    
    if not update_fields:
        return get_journey(tenant_id, journey_id)
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            set_clause = ', '.join([f"{k} = %s" for k in update_fields.keys()])
            values = list(update_fields.values()) + [tenant_id, journey_id]
            
            cursor.execute(f"""
                UPDATE journeys
                SET {set_clause}, updated_at = NOW()
                WHERE tenant_id = %s AND id = %s
                RETURNING id, tenant_id, bot_id, name, description, status, re_entry_policy, created_at, updated_at
            """, values)
            row = cursor.fetchone()
            conn.commit()
            
            if row:
                return {
                    'id': str(row[0]),
                    'tenant_id': row[1],
                    'bot_id': row[2],
                    'name': row[3],
                    'description': row[4],
                    'status': row[5],
                    're_entry_policy': row[6],
                    'created_at': row[7].isoformat() if row[7] else None,
                    'updated_at': row[8].isoformat() if row[8] else None
                }
            return None
    except Exception as e:
        logger.exception(f"Error updating journey: {e}")
        return None


def upsert_trigger(tenant_id: str, journey_id: str, trigger_type: str, 
                   trigger_config: Dict, is_active: bool = True) -> Optional[Dict]:
    """Create or update a journey trigger."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id FROM journey_triggers
                WHERE journey_id = %s AND trigger_type = %s
            """, (journey_id, trigger_type))
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute("""
                    UPDATE journey_triggers
                    SET trigger_config = %s, is_active = %s
                    WHERE id = %s
                    RETURNING id, journey_id, trigger_type, trigger_config, is_active, created_at
                """, (json.dumps(trigger_config), is_active, existing[0]))
            else:
                cursor.execute("""
                    INSERT INTO journey_triggers (journey_id, trigger_type, trigger_config, is_active)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, journey_id, trigger_type, trigger_config, is_active, created_at
                """, (journey_id, trigger_type, json.dumps(trigger_config), is_active))
            
            row = cursor.fetchone()
            conn.commit()
            
            if row:
                return {
                    'id': str(row[0]),
                    'journey_id': str(row[1]),
                    'trigger_type': row[2],
                    'trigger_config': row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {},
                    'is_active': row[4],
                    'created_at': row[5].isoformat() if row[5] else None
                }
            return None
    except Exception as e:
        logger.exception(f"Error upserting trigger: {e}")
        return None


def get_triggers(tenant_id: str, journey_id: str) -> List[Dict]:
    """Get all triggers for a journey."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.id, t.journey_id, t.trigger_type, t.trigger_config, t.is_active, t.created_at
                FROM journey_triggers t
                JOIN journeys j ON j.id = t.journey_id
                WHERE j.tenant_id = %s AND t.journey_id = %s
            """, (tenant_id, journey_id))
            
            triggers = []
            for row in cursor.fetchall():
                triggers.append({
                    'id': str(row[0]),
                    'journey_id': str(row[1]),
                    'trigger_type': row[2],
                    'trigger_config': row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {},
                    'is_active': row[4],
                    'created_at': row[5].isoformat() if row[5] else None
                })
            return triggers
    except Exception as e:
        logger.exception(f"Error getting triggers: {e}")
        return []


def list_steps(tenant_id: str, journey_id: str) -> List[Dict]:
    """Get all steps for a journey in order."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id, s.journey_id, s.step_order, s.step_type, s.config, s.created_at
                FROM journey_steps s
                JOIN journeys j ON j.id = s.journey_id
                WHERE j.tenant_id = %s AND s.journey_id = %s
                ORDER BY s.step_order ASC
            """, (tenant_id, journey_id))
            
            steps = []
            for row in cursor.fetchall():
                steps.append({
                    'id': str(row[0]),
                    'journey_id': str(row[1]),
                    'step_order': row[2],
                    'step_type': row[3],
                    'config': row[4] if isinstance(row[4], dict) else json.loads(row[4]) if row[4] else {},
                    'created_at': row[5].isoformat() if row[5] else None
                })
            return steps
    except Exception as e:
        logger.exception(f"Error listing steps: {e}")
        return []


def set_steps(tenant_id: str, journey_id: str, steps: List[Dict]) -> bool:
    """Replace all steps for a journey."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 1 FROM journeys WHERE tenant_id = %s AND id = %s
            """, (tenant_id, journey_id))
            if not cursor.fetchone():
                logger.warning(f"Journey {journey_id} not found for tenant {tenant_id}")
                return False
            
            cursor.execute("DELETE FROM journey_steps WHERE journey_id = %s", (journey_id,))
            
            for step in steps:
                cursor.execute("""
                    INSERT INTO journey_steps (journey_id, step_order, step_type, config)
                    VALUES (%s, %s, %s, %s)
                """, (journey_id, step['step_order'], step['step_type'], json.dumps(step.get('config', {}))))
            
            conn.commit()
            logger.info(f"Set {len(steps)} steps for journey {journey_id}")
            return True
    except Exception as e:
        logger.exception(f"Error setting steps: {e}")
        return False


def get_active_journey_by_deeplink(tenant_id: str, bot_id: str, start_param: str) -> Optional[Dict]:
    """Find an active journey matching a Telegram deep link trigger.
    
    Supports backward compatibility: queries both 'start_param' (new) and 'param' (old) keys.
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT j.id, j.tenant_id, j.bot_id, j.name, j.status, j.re_entry_policy,
                       t.id as trigger_id, t.trigger_config
                FROM journeys j
                JOIN journey_triggers t ON t.journey_id = j.id
                WHERE j.tenant_id = %s 
                  AND j.bot_id = %s 
                  AND j.status = 'active'
                  AND t.trigger_type = 'telegram_deeplink'
                  AND t.is_active = TRUE
                  AND (t.trigger_config->>'start_param' = %s OR t.trigger_config->>'param' = %s)
                LIMIT 1
            """, (tenant_id, bot_id, start_param, start_param))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': str(row[0]),
                    'tenant_id': row[1],
                    'bot_id': row[2],
                    'name': row[3],
                    'status': row[4],
                    're_entry_policy': row[5],
                    'trigger_id': str(row[6]),
                    'trigger_config': row[7] if isinstance(row[7], dict) else json.loads(row[7]) if row[7] else {}
                }
            return None
    except Exception as e:
        logger.exception(f"Error finding journey by deeplink: {e}")
        return None


def get_active_session(tenant_id: str, journey_id: str, telegram_user_id: int) -> Optional[Dict]:
    """Get active or waiting_delay session for a user in a journey."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, tenant_id, journey_id, telegram_chat_id, telegram_user_id,
                       current_step_id, status, answers, started_at, completed_at, last_activity_at
                FROM journey_user_sessions
                WHERE tenant_id = %s AND journey_id = %s AND telegram_user_id = %s
                  AND status IN ('active', 'waiting_delay')
                LIMIT 1
            """, (tenant_id, journey_id, telegram_user_id))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': str(row[0]),
                    'tenant_id': row[1],
                    'journey_id': str(row[2]),
                    'telegram_chat_id': row[3],
                    'telegram_user_id': row[4],
                    'current_step_id': str(row[5]) if row[5] else None,
                    'status': row[6],
                    'answers': row[7] if isinstance(row[7], dict) else json.loads(row[7]) if row[7] else {},
                    'started_at': row[8].isoformat() if row[8] else None,
                    'completed_at': row[9].isoformat() if row[9] else None,
                    'last_activity_at': row[10].isoformat() if row[10] else None
                }
            return None
    except Exception as e:
        logger.exception(f"Error getting active session: {e}")
        return None


def create_session(tenant_id: str, journey_id: str, telegram_chat_id: int, 
                   telegram_user_id: int, first_step_id: str = None) -> Optional[Dict]:
    """Create a new journey session for a user."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO journey_user_sessions 
                (tenant_id, journey_id, telegram_chat_id, telegram_user_id, current_step_id, status)
                VALUES (%s, %s, %s, %s, %s, 'active')
                RETURNING id, tenant_id, journey_id, telegram_chat_id, telegram_user_id,
                          current_step_id, status, answers, started_at, completed_at, last_activity_at
            """, (tenant_id, journey_id, telegram_chat_id, telegram_user_id, first_step_id))
            row = cursor.fetchone()
            conn.commit()
            
            if row:
                logger.info(f"Created journey session {row[0]} for user {telegram_user_id}")
                return {
                    'id': str(row[0]),
                    'tenant_id': row[1],
                    'journey_id': str(row[2]),
                    'telegram_chat_id': row[3],
                    'telegram_user_id': row[4],
                    'current_step_id': str(row[5]) if row[5] else None,
                    'status': row[6],
                    'answers': row[7] if isinstance(row[7], dict) else {},
                    'started_at': row[8].isoformat() if row[8] else None,
                    'completed_at': row[9].isoformat() if row[9] else None,
                    'last_activity_at': row[10].isoformat() if row[10] else None
                }
            return None
    except Exception as e:
        logger.exception(f"Error creating session: {e}")
        return None


def cancel_session(session_id: str) -> bool:
    """Cancel an existing session."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE journey_user_sessions
                SET status = 'cancelled', last_activity_at = NOW()
                WHERE id = %s AND status IN ('active', 'waiting_delay')
            """, (session_id,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.exception(f"Error cancelling session: {e}")
        return False


def update_session_status(session_id: str, status: str) -> bool:
    """Update session status."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            if status == 'completed':
                cursor.execute("""
                    UPDATE journey_user_sessions
                    SET status = %s, completed_at = NOW(), last_activity_at = NOW()
                    WHERE id = %s
                """, (status, session_id))
            else:
                cursor.execute("""
                    UPDATE journey_user_sessions
                    SET status = %s, last_activity_at = NOW()
                    WHERE id = %s
                """, (status, session_id))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.exception(f"Error updating session status: {e}")
        return False


def update_session_current_step(session_id: str, step_id: str) -> bool:
    """Update the current step for a session."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE journey_user_sessions
                SET current_step_id = %s, last_activity_at = NOW()
                WHERE id = %s
            """, (step_id, session_id))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.exception(f"Error updating session step: {e}")
        return False


def store_answer(session_id: str, answer_key: str, value: Any) -> bool:
    """Store an answer in the session's answers JSON."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE journey_user_sessions
                SET answers = answers || %s::jsonb, last_activity_at = NOW()
                WHERE id = %s
            """, (json.dumps({answer_key: value}), session_id))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.exception(f"Error storing answer: {e}")
        return False


def get_session_by_id(session_id: str) -> Optional[Dict]:
    """Get a session by ID."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, tenant_id, journey_id, telegram_chat_id, telegram_user_id,
                       current_step_id, status, answers, started_at, completed_at, last_activity_at
                FROM journey_user_sessions
                WHERE id = %s
            """, (session_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': str(row[0]),
                    'tenant_id': row[1],
                    'journey_id': str(row[2]),
                    'telegram_chat_id': row[3],
                    'telegram_user_id': row[4],
                    'current_step_id': str(row[5]) if row[5] else None,
                    'status': row[6],
                    'answers': row[7] if isinstance(row[7], dict) else json.loads(row[7]) if row[7] else {},
                    'started_at': row[8].isoformat() if row[8] else None,
                    'completed_at': row[9].isoformat() if row[9] else None,
                    'last_activity_at': row[10].isoformat() if row[10] else None
                }
            return None
    except Exception as e:
        logger.exception(f"Error getting session: {e}")
        return None


def get_step_by_id(step_id: str) -> Optional[Dict]:
    """Get a step by ID."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, journey_id, step_order, step_type, config, created_at
                FROM journey_steps
                WHERE id = %s
            """, (step_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': str(row[0]),
                    'journey_id': str(row[1]),
                    'step_order': row[2],
                    'step_type': row[3],
                    'config': row[4] if isinstance(row[4], dict) else json.loads(row[4]) if row[4] else {},
                    'created_at': row[5].isoformat() if row[5] else None
                }
            return None
    except Exception as e:
        logger.exception(f"Error getting step: {e}")
        return None


def get_next_step(journey_id: str, current_step_order: int) -> Optional[Dict]:
    """Get the next step in a journey."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, journey_id, step_order, step_type, config, created_at
                FROM journey_steps
                WHERE journey_id = %s AND step_order > %s
                ORDER BY step_order ASC
                LIMIT 1
            """, (journey_id, current_step_order))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': str(row[0]),
                    'journey_id': str(row[1]),
                    'step_order': row[2],
                    'step_type': row[3],
                    'config': row[4] if isinstance(row[4], dict) else json.loads(row[4]) if row[4] else {},
                    'created_at': row[5].isoformat() if row[5] else None
                }
            return None
    except Exception as e:
        logger.exception(f"Error getting next step: {e}")
        return None


def schedule_message(tenant_id: str, session_id: str, step_id: str, telegram_chat_id: int,
                     message_content: Dict, scheduled_for: datetime) -> Optional[str]:
    """Schedule a delayed message."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO journey_scheduled_messages 
                (tenant_id, session_id, step_id, telegram_chat_id, message_content, scheduled_for)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (tenant_id, session_id, step_id, telegram_chat_id, json.dumps(message_content), scheduled_for))
            row = cursor.fetchone()
            conn.commit()
            
            if row:
                logger.info(f"Scheduled message {row[0]} for {scheduled_for}")
                return str(row[0])
            return None
    except Exception as e:
        logger.exception(f"Error scheduling message: {e}")
        return None


def fetch_due_scheduled_messages(limit: int = 50) -> List[Dict]:
    """Fetch scheduled messages that are due for sending."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.id, m.tenant_id, m.session_id, m.step_id, m.telegram_chat_id, 
                       m.message_content, m.scheduled_for,
                       s.journey_id, j.bot_id
                FROM journey_scheduled_messages m
                JOIN journey_user_sessions s ON s.id = m.session_id
                JOIN journeys j ON j.id = s.journey_id
                WHERE m.status = 'pending' AND m.scheduled_for <= NOW()
                ORDER BY m.scheduled_for ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            """, (limit,))
            
            messages = []
            for row in cursor.fetchall():
                messages.append({
                    'id': str(row[0]),
                    'tenant_id': row[1],
                    'session_id': str(row[2]),
                    'step_id': str(row[3]),
                    'telegram_chat_id': row[4],
                    'message_content': row[5] if isinstance(row[5], dict) else json.loads(row[5]) if row[5] else {},
                    'scheduled_for': row[6].isoformat() if row[6] else None,
                    'journey_id': str(row[7]),
                    'bot_id': row[8]
                })
            return messages
    except Exception as e:
        logger.exception(f"Error fetching due messages: {e}")
        return []


def mark_scheduled_message_sent(message_id: str) -> bool:
    """Mark a scheduled message as sent."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE journey_scheduled_messages
                SET status = 'sent', sent_at = NOW()
                WHERE id = %s
            """, (message_id,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.exception(f"Error marking message sent: {e}")
        return False


def mark_scheduled_message_failed(message_id: str, error: str) -> bool:
    """Mark a scheduled message as failed."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE journey_scheduled_messages
                SET status = 'failed', error = %s
                WHERE id = %s
            """, (error, message_id))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.exception(f"Error marking message failed: {e}")
        return False


def list_sessions_debug(tenant_id: str = None, limit: int = 50) -> List[Dict]:
    """List sessions for debugging (admin only)."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            if tenant_id:
                cursor.execute("""
                    SELECT s.id, s.tenant_id, s.journey_id, s.telegram_chat_id, s.telegram_user_id,
                           s.current_step_id, s.status, s.answers, s.started_at, s.last_activity_at,
                           j.name as journey_name
                    FROM journey_user_sessions s
                    JOIN journeys j ON j.id = s.journey_id
                    WHERE s.tenant_id = %s
                    ORDER BY s.last_activity_at DESC
                    LIMIT %s
                """, (tenant_id, limit))
            else:
                cursor.execute("""
                    SELECT s.id, s.tenant_id, s.journey_id, s.telegram_chat_id, s.telegram_user_id,
                           s.current_step_id, s.status, s.answers, s.started_at, s.last_activity_at,
                           j.name as journey_name
                    FROM journey_user_sessions s
                    JOIN journeys j ON j.id = s.journey_id
                    ORDER BY s.last_activity_at DESC
                    LIMIT %s
                """, (limit,))
            
            sessions = []
            for row in cursor.fetchall():
                sessions.append({
                    'id': str(row[0]),
                    'tenant_id': row[1],
                    'journey_id': str(row[2]),
                    'telegram_chat_id': row[3],
                    'telegram_user_id': row[4],
                    'current_step_id': str(row[5]) if row[5] else None,
                    'status': row[6],
                    'answers': row[7] if isinstance(row[7], dict) else {},
                    'started_at': row[8].isoformat() if row[8] else None,
                    'last_activity_at': row[9].isoformat() if row[9] else None,
                    'journey_name': row[10]
                })
            return sessions
    except Exception as e:
        logger.exception(f"Error listing sessions: {e}")
        return []


def get_first_step(journey_id: str) -> Optional[Dict]:
    """Get the first step of a journey."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, journey_id, step_order, step_type, config, created_at
                FROM journey_steps
                WHERE journey_id = %s
                ORDER BY step_order ASC
                LIMIT 1
            """, (journey_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': str(row[0]),
                    'journey_id': str(row[1]),
                    'step_order': row[2],
                    'step_type': row[3],
                    'config': row[4] if isinstance(row[4], dict) else json.loads(row[4]) if row[4] else {},
                    'created_at': row[5].isoformat() if row[5] else None
                }
            return None
    except Exception as e:
        logger.exception(f"Error getting first step: {e}")
        return None


def get_session_for_user_reply(tenant_id: str, telegram_user_id: int, telegram_chat_id: int) -> Optional[Dict]:
    """Get the active session for a user who is replying (for answer collection)."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id, s.tenant_id, s.journey_id, s.telegram_chat_id, s.telegram_user_id,
                       s.current_step_id, s.status, s.answers, s.started_at, s.completed_at, s.last_activity_at
                FROM journey_user_sessions s
                WHERE s.tenant_id = %s 
                  AND s.telegram_user_id = %s 
                  AND s.telegram_chat_id = %s
                  AND s.status = 'active'
                ORDER BY s.last_activity_at DESC
                LIMIT 1
            """, (tenant_id, telegram_user_id, telegram_chat_id))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': str(row[0]),
                    'tenant_id': row[1],
                    'journey_id': str(row[2]),
                    'telegram_chat_id': row[3],
                    'telegram_user_id': row[4],
                    'current_step_id': str(row[5]) if row[5] else None,
                    'status': row[6],
                    'answers': row[7] if isinstance(row[7], dict) else json.loads(row[7]) if row[7] else {},
                    'started_at': row[8].isoformat() if row[8] else None,
                    'completed_at': row[9].isoformat() if row[9] else None,
                    'last_activity_at': row[10].isoformat() if row[10] else None
                }
            return None
    except Exception as e:
        logger.exception(f"Error getting session for reply: {e}")
        return None
