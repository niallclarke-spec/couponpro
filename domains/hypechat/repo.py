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
                interval_max_minutes: int = 90,
                delay_after_cta_minutes: int = 10, active_days: str = 'mon-fri',
                status: str = 'paused',
                cta_enabled: bool = False, cta_delay_minutes: int = 30,
                cta_intro_text: str = '', cta_vip_label: str = '', cta_vip_url: str = '',
                cta_support_label: str = '', cta_support_url: str = '',
                bump_enabled: bool = False, bump_preset: str = None,
                bump_delay_minutes: int = 0,
                trigger_after_flow_id: str = None,
                trigger_delay_minutes: int = 0) -> Optional[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO hype_flows (tenant_id, prompt_id, name, message_count,
                    interval_minutes, interval_max_minutes, delay_after_cta_minutes, active_days, status,
                    cta_enabled, cta_delay_minutes, cta_intro_text, cta_vip_label, cta_vip_url,
                    cta_support_label, cta_support_url,
                    bump_enabled, bump_preset, bump_delay_minutes,
                    trigger_after_flow_id, trigger_delay_minutes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, tenant_id, prompt_id, name, message_count,
                    interval_minutes, interval_max_minutes, delay_after_cta_minutes, active_days, status,
                    created_at, updated_at,
                    cta_enabled, cta_delay_minutes, cta_intro_text, cta_vip_label, cta_vip_url,
                    cta_support_label, cta_support_url,
                    bump_enabled, bump_preset, bump_delay_minutes,
                    trigger_after_flow_id, trigger_delay_minutes
            """, (tenant_id, prompt_id, name, message_count,
                  interval_minutes, interval_max_minutes, delay_after_cta_minutes, active_days, status,
                  cta_enabled, cta_delay_minutes, cta_intro_text, cta_vip_label, cta_vip_url,
                  cta_support_label, cta_support_url,
                  bump_enabled, bump_preset, bump_delay_minutes,
                  trigger_after_flow_id, trigger_delay_minutes))
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
                    f.interval_minutes, f.interval_max_minutes, f.delay_after_cta_minutes, f.active_days, f.status,
                    f.created_at, f.updated_at,
                    f.cta_enabled, f.cta_delay_minutes, f.cta_intro_text, f.cta_vip_label, f.cta_vip_url,
                    f.cta_support_label, f.cta_support_url,
                    f.bump_enabled, f.bump_preset, f.bump_delay_minutes,
                    f.trigger_after_flow_id, f.trigger_delay_minutes,
                    p.name as prompt_name
                FROM hype_flows f
                LEFT JOIN hype_prompts p ON p.id = f.prompt_id
                WHERE f.tenant_id = %s
                ORDER BY f.created_at DESC
            """, (tenant_id,))
            flows = []
            for row in cursor.fetchall():
                flow = _row_to_flow(row[:24])
                flow['prompt_name'] = row[24]
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
                    f.interval_minutes, f.interval_max_minutes, f.delay_after_cta_minutes, f.active_days, f.status,
                    f.created_at, f.updated_at,
                    f.cta_enabled, f.cta_delay_minutes, f.cta_intro_text, f.cta_vip_label, f.cta_vip_url,
                    f.cta_support_label, f.cta_support_url,
                    f.bump_enabled, f.bump_preset, f.bump_delay_minutes,
                    f.trigger_after_flow_id, f.trigger_delay_minutes,
                    p.name as prompt_name, p.custom_prompt
                FROM hype_flows f
                LEFT JOIN hype_prompts p ON p.id = f.prompt_id
                WHERE f.tenant_id = %s AND f.id = %s
            """, (tenant_id, flow_id))
            row = cursor.fetchone()
            if row:
                flow = _row_to_flow(row[:24])
                flow['prompt_name'] = row[24]
                flow['custom_prompt'] = row[25]
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
                      'interval_max_minutes', 'delay_after_cta_minutes', 'active_days', 'status',
                      'cta_enabled', 'cta_delay_minutes', 'cta_intro_text',
                      'cta_vip_label', 'cta_vip_url', 'cta_support_label', 'cta_support_url',
                      'bump_enabled', 'bump_preset', 'bump_delay_minutes',
                      'trigger_after_flow_id', 'trigger_delay_minutes'}
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
                    interval_minutes, interval_max_minutes, delay_after_cta_minutes, active_days, status,
                    created_at, updated_at,
                    cta_enabled, cta_delay_minutes, cta_intro_text, cta_vip_label, cta_vip_url,
                    cta_support_label, cta_support_url,
                    bump_enabled, bump_preset, bump_delay_minutes,
                    trigger_after_flow_id, trigger_delay_minutes
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
                    f.interval_minutes, f.interval_max_minutes, f.delay_after_cta_minutes, f.active_days, f.status,
                    f.created_at, f.updated_at,
                    f.cta_enabled, f.cta_delay_minutes, f.cta_intro_text, f.cta_vip_label, f.cta_vip_url,
                    f.cta_support_label, f.cta_support_url,
                    f.bump_enabled, f.bump_preset, f.bump_delay_minutes,
                    f.trigger_after_flow_id, f.trigger_delay_minutes,
                    p.name as prompt_name, p.custom_prompt
                FROM hype_flows f
                LEFT JOIN hype_prompts p ON p.id = f.prompt_id
                WHERE f.tenant_id = %s AND f.status = 'active'
                ORDER BY f.created_at ASC
            """, (tenant_id,))
            flows = []
            for row in cursor.fetchall():
                flow = _row_to_flow(row[:24])
                flow['prompt_name'] = row[24]
                flow['custom_prompt'] = row[25]
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
    result = {
        'id': str(row[0]),
        'tenant_id': row[1],
        'prompt_id': row[2],
        'name': row[3],
        'message_count': row[4],
        'interval_minutes': row[5],
        'interval_max_minutes': row[6],
        'delay_after_cta_minutes': row[7],
        'active_days': row[8],
        'status': row[9],
        'created_at': row[10].isoformat() if row[10] else None,
        'updated_at': row[11].isoformat() if row[11] else None,
    }
    if len(row) > 12:
        result['cta_enabled'] = row[12] if row[12] is not None else False
        result['cta_delay_minutes'] = row[13] if row[13] is not None else 30
        result['cta_intro_text'] = row[14] or ''
        result['cta_vip_label'] = row[15] or ''
        result['cta_vip_url'] = row[16] or ''
        result['cta_support_label'] = row[17] or ''
        result['cta_support_url'] = row[18] or ''
    if len(row) > 19:
        result['bump_enabled'] = row[19] if row[19] is not None else False
        result['bump_preset'] = row[20]
        result['bump_delay_minutes'] = row[21] if row[21] is not None else 0
    else:
        result['bump_enabled'] = False
        result['bump_preset'] = None
        result['bump_delay_minutes'] = 0
    if len(row) > 22:
        result['trigger_after_flow_id'] = str(row[22]) if row[22] else None
        result['trigger_delay_minutes'] = row[23] if row[23] is not None else 0
    else:
        result['trigger_after_flow_id'] = None
        result['trigger_delay_minutes'] = 0
    return result


def list_steps(flow_id: str) -> List[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, flow_id, step_order, delay_minutes, step_type,
                       reforward_preset, message_text,
                       cta_intro_text, cta_vip_label, cta_vip_url,
                       cta_support_label, cta_support_url, created_at
                FROM hype_flow_steps
                WHERE flow_id = %s
                ORDER BY step_order ASC
            """, (flow_id,))
            return [_row_to_step(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.exception(f"Error listing steps: {e}")
        return []


def create_step(flow_id: str, step_order: int, delay_minutes: int, step_type: str,
                reforward_preset: str = None, message_text: str = None,
                cta_intro_text: str = None, cta_vip_label: str = None,
                cta_vip_url: str = None, cta_support_label: str = None,
                cta_support_url: str = None) -> Optional[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO hype_flow_steps
                    (flow_id, step_order, delay_minutes, step_type,
                     reforward_preset, message_text,
                     cta_intro_text, cta_vip_label, cta_vip_url,
                     cta_support_label, cta_support_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, flow_id, step_order, delay_minutes, step_type,
                          reforward_preset, message_text,
                          cta_intro_text, cta_vip_label, cta_vip_url,
                          cta_support_label, cta_support_url, created_at
            """, (flow_id, step_order, delay_minutes, step_type,
                  reforward_preset, message_text,
                  cta_intro_text, cta_vip_label, cta_vip_url,
                  cta_support_label, cta_support_url))
            row = cursor.fetchone()
            conn.commit()
            return _row_to_step(row) if row else None
    except Exception as e:
        logger.exception(f"Error creating step: {e}")
        return None


def update_step(step_id: str, flow_id: str, **fields) -> Optional[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    allowed = {'delay_minutes', 'step_type', 'reforward_preset', 'message_text',
               'cta_intro_text', 'cta_vip_label', 'cta_vip_url',
               'cta_support_label', 'cta_support_url'}
    update_fields = {k: v for k, v in fields.items() if k in allowed}
    if not update_fields:
        return None
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            set_clause = ', '.join(f"{k} = %s" for k in update_fields)
            values = list(update_fields.values()) + [step_id, flow_id]
            cursor.execute(f"""
                UPDATE hype_flow_steps
                SET {set_clause}
                WHERE id = %s AND flow_id = %s
                RETURNING id, flow_id, step_order, delay_minutes, step_type,
                          reforward_preset, message_text,
                          cta_intro_text, cta_vip_label, cta_vip_url,
                          cta_support_label, cta_support_url, created_at
            """, values)
            row = cursor.fetchone()
            conn.commit()
            return _row_to_step(row) if row else None
    except Exception as e:
        logger.exception(f"Error updating step: {e}")
        return None


def delete_step(step_id: str, flow_id: str) -> bool:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM hype_flow_steps
                WHERE id = %s AND flow_id = %s
                RETURNING id
            """, (step_id, flow_id))
            result = cursor.fetchone()
            conn.commit()
            return result is not None
    except Exception as e:
        logger.exception(f"Error deleting step: {e}")
        return False


def reorder_steps(flow_id: str, ordered_ids: list) -> bool:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            for idx, step_id in enumerate(ordered_ids):
                cursor.execute("""
                    UPDATE hype_flow_steps
                    SET step_order = %s
                    WHERE id = %s AND flow_id = %s
                """, (idx, step_id, flow_id))
            conn.commit()
            return True
    except Exception as e:
        logger.exception(f"Error reordering steps: {e}")
        return False


def insert_step_after(flow_id: str, after_step_id: Optional[str], step_data: dict) -> Optional[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            if after_step_id is None:
                insert_order = 0
                cursor.execute("""
                    UPDATE hype_flow_steps
                    SET step_order = step_order + 1
                    WHERE flow_id = %s
                """, (flow_id,))
            else:
                cursor.execute("""
                    SELECT step_order FROM hype_flow_steps
                    WHERE id = %s AND flow_id = %s
                """, (after_step_id, flow_id))
                row = cursor.fetchone()
                if not row:
                    return None
                insert_order = row[0] + 1
                cursor.execute("""
                    UPDATE hype_flow_steps
                    SET step_order = step_order + 1
                    WHERE flow_id = %s AND step_order >= %s
                """, (flow_id, insert_order))

            cursor.execute("""
                INSERT INTO hype_flow_steps
                    (flow_id, step_order, delay_minutes, step_type,
                     reforward_preset, message_text,
                     cta_intro_text, cta_vip_label, cta_vip_url,
                     cta_support_label, cta_support_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, flow_id, step_order, delay_minutes, step_type,
                          reforward_preset, message_text,
                          cta_intro_text, cta_vip_label, cta_vip_url,
                          cta_support_label, cta_support_url, created_at
            """, (flow_id, insert_order,
                  step_data.get('delay_minutes', 0),
                  step_data.get('step_type', 'message'),
                  step_data.get('reforward_preset'),
                  step_data.get('message_text'),
                  step_data.get('cta_intro_text'),
                  step_data.get('cta_vip_label'),
                  step_data.get('cta_vip_url'),
                  step_data.get('cta_support_label'),
                  step_data.get('cta_support_url')))
            result = cursor.fetchone()
            conn.commit()
            return _row_to_step(result) if result else None
    except Exception as e:
        logger.exception(f"Error inserting step: {e}")
        return None


def _row_to_step(row) -> Dict:
    return {
        'id': str(row[0]),
        'flow_id': str(row[1]),
        'step_order': row[2],
        'delay_minutes': row[3],
        'step_type': row[4],
        'reforward_preset': row[5],
        'message_text': row[6] or '',
        'cta_intro_text': row[7] or '',
        'cta_vip_label': row[8] or '',
        'cta_vip_url': row[9] or '',
        'cta_support_label': row[10] or '',
        'cta_support_url': row[11] or '',
        'created_at': row[12].isoformat() if row[12] else None,
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
