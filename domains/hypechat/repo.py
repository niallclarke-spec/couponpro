"""
Hype Chat repository - tenant-scoped database functions for hype prompts, flows, and messages.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from core.logging import get_logger

logger = get_logger(__name__)


def _get_db_pool():
    from db import db_pool
    return db_pool


def create_prompt(tenant_id: str, name: str, custom_prompt: str) -> Optional[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO hype_prompts (tenant_id, name, custom_prompt)
                VALUES (%s, %s, %s)
                RETURNING id, tenant_id, name, custom_prompt, is_default, created_at, updated_at
            """, (tenant_id, name, custom_prompt))
            row = cursor.fetchone()
            conn.commit()
            if row:
                return _row_to_prompt(row)
            return None
    except Exception as e:
        logger.exception(f"Error creating prompt: {e}")
        return None


def list_prompts(tenant_id: str) -> List[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, tenant_id, name, custom_prompt, is_default, created_at, updated_at
                FROM hype_prompts
                WHERE tenant_id = %s
                ORDER BY created_at DESC
            """, (tenant_id,))
            return [_row_to_prompt(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.exception(f"Error listing prompts: {e}")
        return []


def get_prompt(tenant_id: str, prompt_id: str) -> Optional[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, tenant_id, name, custom_prompt, is_default, created_at, updated_at
                FROM hype_prompts
                WHERE tenant_id = %s AND id = %s
            """, (tenant_id, prompt_id))
            row = cursor.fetchone()
            if row:
                return _row_to_prompt(row)
            return None
    except Exception as e:
        logger.exception(f"Error getting prompt: {e}")
        return None


def update_prompt(tenant_id: str, prompt_id: str, name: str, custom_prompt: str) -> Optional[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE hype_prompts
                SET name = %s, custom_prompt = %s, updated_at = NOW()
                WHERE tenant_id = %s AND id = %s
                RETURNING id, tenant_id, name, custom_prompt, is_default, created_at, updated_at
            """, (name, custom_prompt, tenant_id, prompt_id))
            row = cursor.fetchone()
            conn.commit()
            if row:
                return _row_to_prompt(row)
            return None
    except Exception as e:
        logger.exception(f"Error updating prompt: {e}")
        return None


def delete_prompt(tenant_id: str, prompt_id: str) -> bool:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM hype_prompts
                WHERE tenant_id = %s AND id = %s
                RETURNING id
            """, (tenant_id, prompt_id))
            result = cursor.fetchone()
            conn.commit()
            return result is not None
    except Exception as e:
        logger.exception(f"Error deleting prompt: {e}")
        return False


def create_flow(tenant_id: str, prompt_id: str, name: str,
                message_count: int = 3, interval_minutes: int = 90,
                delay_after_cta_minutes: int = 10, active_days: str = 'mon-fri',
                status: str = 'paused') -> Optional[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO hype_flows (tenant_id, prompt_id, name, message_count,
                    interval_minutes, delay_after_cta_minutes, active_days, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, tenant_id, prompt_id, name, message_count,
                    interval_minutes, delay_after_cta_minutes, active_days, status,
                    created_at, updated_at
            """, (tenant_id, prompt_id, name, message_count,
                  interval_minutes, delay_after_cta_minutes, active_days, status))
            row = cursor.fetchone()
            conn.commit()
            if row:
                return _row_to_flow(row)
            return None
    except Exception as e:
        logger.exception(f"Error creating flow: {e}")
        return None


def list_flows(tenant_id: str) -> List[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT f.id, f.tenant_id, f.prompt_id, f.name, f.message_count,
                    f.interval_minutes, f.delay_after_cta_minutes, f.active_days, f.status,
                    f.created_at, f.updated_at, p.name as prompt_name
                FROM hype_flows f
                LEFT JOIN hype_prompts p ON p.id = f.prompt_id
                WHERE f.tenant_id = %s
                ORDER BY f.created_at DESC
            """, (tenant_id,))
            flows = []
            for row in cursor.fetchall():
                flow = _row_to_flow(row[:11])
                flow['prompt_name'] = row[11]
                flows.append(flow)
            return flows
    except Exception as e:
        logger.exception(f"Error listing flows: {e}")
        return []


def get_flow(tenant_id: str, flow_id: str) -> Optional[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT f.id, f.tenant_id, f.prompt_id, f.name, f.message_count,
                    f.interval_minutes, f.delay_after_cta_minutes, f.active_days, f.status,
                    f.created_at, f.updated_at, p.name as prompt_name, p.custom_prompt
                FROM hype_flows f
                LEFT JOIN hype_prompts p ON p.id = f.prompt_id
                WHERE f.tenant_id = %s AND f.id = %s
            """, (tenant_id, flow_id))
            row = cursor.fetchone()
            if row:
                flow = _row_to_flow(row[:11])
                flow['prompt_name'] = row[11]
                flow['custom_prompt'] = row[12]
                return flow
            return None
    except Exception as e:
        logger.exception(f"Error getting flow: {e}")
        return None


def update_flow(tenant_id: str, flow_id: str, fields: Dict) -> Optional[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None

    allowed_fields = {'name', 'prompt_id', 'message_count', 'interval_minutes',
                      'delay_after_cta_minutes', 'active_days', 'status'}
    update_fields = {k: v for k, v in fields.items() if k in allowed_fields}

    if not update_fields:
        return get_flow(tenant_id, flow_id)

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            set_clause = ', '.join([f"{k} = %s" for k in update_fields.keys()])
            values = list(update_fields.values()) + [tenant_id, flow_id]
            cursor.execute(f"""
                UPDATE hype_flows
                SET {set_clause}, updated_at = NOW()
                WHERE tenant_id = %s AND id = %s
                RETURNING id, tenant_id, prompt_id, name, message_count,
                    interval_minutes, delay_after_cta_minutes, active_days, status,
                    created_at, updated_at
            """, values)
            row = cursor.fetchone()
            conn.commit()
            if row:
                return _row_to_flow(row)
            return None
    except Exception as e:
        logger.exception(f"Error updating flow: {e}")
        return None


def delete_flow(tenant_id: str, flow_id: str) -> bool:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM hype_flows
                WHERE tenant_id = %s AND id = %s
                RETURNING id
            """, (tenant_id, flow_id))
            result = cursor.fetchone()
            conn.commit()
            return result is not None
    except Exception as e:
        logger.exception(f"Error deleting flow: {e}")
        return False


def set_flow_status(tenant_id: str, flow_id: str, status: str) -> bool:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False

    valid_statuses = ('active', 'paused')
    if status not in valid_statuses:
        logger.warning(f"Invalid flow status: {status}")
        return False

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE hype_flows SET status = %s, updated_at = NOW()
                WHERE tenant_id = %s AND id = %s
                RETURNING id
            """, (status, tenant_id, flow_id))
            result = cursor.fetchone()
            conn.commit()
            if result:
                logger.info(f"Flow {flow_id} status changed to {status}")
                return True
            return False
    except Exception as e:
        logger.exception(f"Error setting flow status: {e}")
        return False


def log_message(tenant_id: str, flow_id: str, step_number: int,
                content_sent: str, telegram_message_id: int = None) -> Optional[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO hype_messages (tenant_id, flow_id, step_number, content_sent, telegram_message_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, flow_id, tenant_id, step_number, content_sent, telegram_message_id,
                    views_1hr, views_24hr, sent_at
            """, (tenant_id, flow_id, step_number, content_sent, telegram_message_id))
            row = cursor.fetchone()
            conn.commit()
            if row:
                return _row_to_message(row)
            return None
    except Exception as e:
        logger.exception(f"Error logging message: {e}")
        return None


def get_flow_messages(tenant_id: str, flow_id: str, limit: int = 50) -> List[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, flow_id, tenant_id, step_number, content_sent, telegram_message_id,
                    views_1hr, views_24hr, sent_at
                FROM hype_messages
                WHERE tenant_id = %s AND flow_id = %s
                ORDER BY sent_at DESC
                LIMIT %s
            """, (tenant_id, flow_id, limit))
            return [_row_to_message(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.exception(f"Error getting flow messages: {e}")
        return []


def get_today_hype_count(tenant_id: str) -> int:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return 0

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*)
                FROM hype_messages
                WHERE tenant_id = %s AND sent_at >= CURRENT_DATE
            """, (tenant_id,))
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] else 0
    except Exception as e:
        logger.exception(f"Error getting today hype count: {e}")
        return 0


def get_active_flows(tenant_id: str) -> List[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT f.id, f.tenant_id, f.prompt_id, f.name, f.message_count,
                    f.interval_minutes, f.delay_after_cta_minutes, f.active_days, f.status,
                    f.created_at, f.updated_at, p.name as prompt_name, p.custom_prompt
                FROM hype_flows f
                LEFT JOIN hype_prompts p ON p.id = f.prompt_id
                WHERE f.tenant_id = %s AND f.status = 'active'
                ORDER BY f.created_at ASC
            """, (tenant_id,))
            flows = []
            for row in cursor.fetchall():
                flow = _row_to_flow(row[:11])
                flow['prompt_name'] = row[11]
                flow['custom_prompt'] = row[12]
                flows.append(flow)
            return flows
    except Exception as e:
        logger.exception(f"Error getting active flows: {e}")
        return []


def _row_to_prompt(row) -> Dict:
    return {
        'id': str(row[0]),
        'tenant_id': row[1],
        'name': row[2],
        'custom_prompt': row[3],
        'is_default': row[4],
        'created_at': row[5].isoformat() if row[5] else None,
        'updated_at': row[6].isoformat() if row[6] else None,
    }


def _row_to_flow(row) -> Dict:
    return {
        'id': str(row[0]),
        'tenant_id': row[1],
        'prompt_id': row[2],
        'name': row[3],
        'message_count': row[4],
        'interval_minutes': row[5],
        'delay_after_cta_minutes': row[6],
        'active_days': row[7],
        'status': row[8],
        'created_at': row[9].isoformat() if row[9] else None,
        'updated_at': row[10].isoformat() if row[10] else None,
    }


def _row_to_message(row) -> Dict:
    return {
        'id': str(row[0]),
        'flow_id': row[1],
        'tenant_id': row[2],
        'step_number': row[3],
        'content_sent': row[4],
        'telegram_message_id': row[5],
        'views_1hr': row[6],
        'views_24hr': row[7],
        'sent_at': row[8].isoformat() if row[8] else None,
    }
