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
                   status: str = 'draft', re_entry_policy: str = 'block',
                   start_delay_seconds: int = 0) -> Optional[Dict]:
    """Create a new journey."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO journeys (tenant_id, bot_id, name, description, status, re_entry_policy, start_delay_seconds)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, tenant_id, bot_id, name, description, status, re_entry_policy, created_at, updated_at, start_delay_seconds
            """, (tenant_id, bot_id, name, description, status, re_entry_policy, start_delay_seconds))
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
                    'updated_at': row[8].isoformat() if row[8] else None,
                    'start_delay_seconds': row[9]
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
                SELECT id, tenant_id, bot_id, name, description, status, re_entry_policy, created_at, updated_at, start_delay_seconds
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
                    'updated_at': row[8].isoformat() if row[8] else None,
                    'start_delay_seconds': row[9]
                })
            return journeys
    except Exception as e:
        logger.exception(f"Error listing journeys: {e}")
        return []


def list_journeys_with_summary(tenant_id: str) -> List[Dict]:
    """List all journeys with step counts and triggers in a single batched query.
    
    This is an optimized version that avoids N+1 queries by fetching
    step counts and triggers for all journeys at once.
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Single query: journeys with step counts via LEFT JOIN
            cursor.execute("""
                SELECT 
                    j.id, j.tenant_id, j.bot_id, j.name, j.description, 
                    j.status, j.re_entry_policy, j.created_at, j.updated_at,
                    COALESCE(step_counts.cnt, 0) as step_count,
                    j.priority_int, j.is_locked, j.inactivity_timeout_days, j.start_delay_seconds
                FROM journeys j
                LEFT JOIN (
                    SELECT journey_id, COUNT(*) as cnt
                    FROM journey_steps
                    GROUP BY journey_id
                ) step_counts ON step_counts.journey_id = j.id
                WHERE j.tenant_id = %s
                ORDER BY j.created_at DESC
            """, (tenant_id,))
            
            journeys = []
            journey_ids = []
            for row in cursor.fetchall():
                journey_id = str(row[0])
                journey_ids.append(journey_id)
                journeys.append({
                    'id': journey_id,
                    'tenant_id': row[1],
                    'bot_id': row[2],
                    'name': row[3],
                    'description': row[4],
                    'status': row[5],
                    're_entry_policy': row[6],
                    'created_at': row[7].isoformat() if row[7] else None,
                    'updated_at': row[8].isoformat() if row[8] else None,
                    'step_count': row[9],
                    'priority_int': row[10],
                    'is_locked': row[11],
                    'inactivity_timeout_days': row[12],
                    'start_delay_seconds': row[13],
                    'triggers': []
                })
            
            if not journey_ids:
                return journeys
            
            # Second query: all triggers for these journeys
            # Cast to uuid[] to avoid type mismatch (journey_ids are strings)
            cursor.execute("""
                SELECT t.id, t.journey_id, t.trigger_type, t.trigger_config, t.is_active, t.created_at
                FROM journey_triggers t
                WHERE t.journey_id = ANY(%s::uuid[])
            """, (journey_ids,))
            
            # Build triggers map
            triggers_by_journey = {}
            for row in cursor.fetchall():
                journey_id = str(row[1])
                if journey_id not in triggers_by_journey:
                    triggers_by_journey[journey_id] = []
                triggers_by_journey[journey_id].append({
                    'id': str(row[0]),
                    'journey_id': journey_id,
                    'trigger_type': row[2],
                    'trigger_config': row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {},
                    'is_active': row[4],
                    'created_at': row[5].isoformat() if row[5] else None
                })
            
            # Assign triggers to journeys
            for j in journeys:
                j['triggers'] = triggers_by_journey.get(j['id'], [])
            
            # Third query: aggregate stats (total sends, unique users)
            agg_stats = get_journey_aggregate_stats(tenant_id)
            for j in journeys:
                stats = agg_stats.get(j['id'], {})
                j['total_sends'] = stats.get('total_sends', 0)
                j['unique_users'] = stats.get('unique_users', 0)
            
            return journeys
    except Exception as e:
        logger.exception(f"Error listing journeys with summary: {e}")
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
                SELECT id, tenant_id, bot_id, name, description, status, re_entry_policy, created_at, updated_at, start_delay_seconds
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
                    'updated_at': row[8].isoformat() if row[8] else None,
                    'start_delay_seconds': row[9]
                }
            return None
    except Exception as e:
        logger.exception(f"Error getting journey: {e}")
        return None


def update_journey_status(tenant_id: str, journey_id: str, new_status: str) -> bool:
    """Update journey status (draft/active/stopped)."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    
    valid_statuses = ('draft', 'active', 'stopped')
    if new_status not in valid_statuses:
        logger.warning(f"Invalid journey status: {new_status}")
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE journeys SET status = %s, updated_at = NOW()
                WHERE tenant_id = %s AND id = %s
                RETURNING id
            """, (new_status, tenant_id, journey_id))
            result = cursor.fetchone()
            conn.commit()
            if result:
                logger.info(f"Journey {journey_id} status changed to {new_status}")
                return True
            return False
    except Exception as e:
        logger.exception(f"Error updating journey status: {e}")
        return False


def check_active_trigger_keyword_conflict(tenant_id: str, journey_id: str) -> Optional[Dict]:
    """Check if publishing this journey would create a duplicate active trigger keyword.
    
    Returns the conflicting journey info if a conflict exists, None otherwise.
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT t.trigger_type, t.trigger_config
                FROM journey_triggers t
                WHERE t.journey_id = %s
            """, (journey_id,))
            my_triggers = cursor.fetchall()
            
            for trigger_type, trigger_config in my_triggers:
                config = trigger_config if isinstance(trigger_config, dict) else json.loads(trigger_config) if trigger_config else {}
                
                if trigger_type == 'direct_message':
                    keyword = (config.get('keyword') or '').strip().lower()
                    if not keyword:
                        continue
                    
                    cursor.execute("""
                        SELECT j.id, j.name, t.trigger_config
                        FROM journeys j
                        JOIN journey_triggers t ON t.journey_id = j.id
                        WHERE j.tenant_id = %s 
                          AND j.status = 'active'
                          AND j.id != %s
                          AND t.trigger_type = 'direct_message'
                          AND t.is_active = TRUE
                    """, (tenant_id, journey_id))
                    
                    for row in cursor.fetchall():
                        other_config = row[2] if isinstance(row[2], dict) else json.loads(row[2]) if row[2] else {}
                        other_keyword = (other_config.get('keyword') or '').strip().lower()
                        if other_keyword == keyword:
                            return {
                                'conflict_journey_id': str(row[0]),
                                'conflict_journey_name': row[1],
                                'keyword': keyword
                            }
                
                elif trigger_type == 'telegram_deeplink':
                    param = (config.get('start_param') or config.get('param') or '').strip().lower()
                    if not param:
                        continue
                    
                    cursor.execute("""
                        SELECT j.id, j.name, t.trigger_config
                        FROM journeys j
                        JOIN journey_triggers t ON t.journey_id = j.id
                        WHERE j.tenant_id = %s 
                          AND j.status = 'active'
                          AND j.id != %s
                          AND t.trigger_type = 'telegram_deeplink'
                          AND t.is_active = TRUE
                    """, (tenant_id, journey_id))
                    
                    for row in cursor.fetchall():
                        other_config = row[2] if isinstance(row[2], dict) else json.loads(row[2]) if row[2] else {}
                        other_param = (other_config.get('start_param') or other_config.get('param') or '').strip().lower()
                        if other_param == param:
                            return {
                                'conflict_journey_id': str(row[0]),
                                'conflict_journey_name': row[1],
                                'keyword': param
                            }
            
            return None
    except Exception as e:
        logger.exception(f"Error checking trigger conflict: {e}")
        return None


def get_journey_aggregate_stats(tenant_id: str) -> Dict[str, Dict]:
    """Get aggregate stats (total sends, unique users) for all journeys of a tenant.
    
    Returns dict keyed by journey_id with {total_sends, unique_users}.
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return {}
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT js.journey_id, COALESCE(SUM(jsa.sends), 0) as total_sends
                FROM journey_step_analytics jsa
                JOIN journey_steps js ON js.id = jsa.step_id
                WHERE js.journey_id IN (SELECT id FROM journeys WHERE tenant_id = %s)
                GROUP BY js.journey_id
            """, (tenant_id,))
            
            stats = {}
            for row in cursor.fetchall():
                stats[str(row[0])] = {'total_sends': int(row[1]), 'unique_users': 0}
            
            cursor.execute("""
                SELECT journey_id, COUNT(DISTINCT telegram_user_id) as unique_users
                FROM journey_user_sessions
                WHERE tenant_id = %s
                GROUP BY journey_id
            """, (tenant_id,))
            
            for row in cursor.fetchall():
                jid = str(row[0])
                if jid in stats:
                    stats[jid]['unique_users'] = int(row[1])
                else:
                    stats[jid] = {'total_sends': 0, 'unique_users': int(row[1])}
            
            return stats
    except Exception as e:
        logger.exception(f"Error getting journey aggregate stats: {e}")
        return {}


def update_journey(tenant_id: str, journey_id: str, fields: Dict) -> Optional[Dict]:
    """Update a journey's fields."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    allowed_fields = {'name', 'description', 'status', 're_entry_policy', 'bot_id', 'start_delay_seconds'}
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
                RETURNING id, tenant_id, bot_id, name, description, status, re_entry_policy, created_at, updated_at, start_delay_seconds
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
                    'updated_at': row[8].isoformat() if row[8] else None,
                    'start_delay_seconds': row[9]
                }
            return None
    except Exception as e:
        logger.exception(f"Error updating journey: {e}")
        return None


def upsert_trigger(tenant_id: str, journey_id: str, trigger_type: str, 
                   trigger_config: Dict, is_active: bool = True) -> Optional[Dict]:
    """Create or update a journey trigger.
    
    In a single transaction:
    1. Deactivate ALL existing active triggers for this journey_id
    2. If a trigger with the same trigger_type exists (active or not), update it
    3. Otherwise insert a new trigger
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE journey_triggers SET is_active = false
                WHERE journey_id = %s AND is_active = true
            """, (journey_id,))
            
            cursor.execute("""
                SELECT id FROM journey_triggers
                WHERE journey_id = %s AND trigger_type = %s
                LIMIT 1
            """, (journey_id, trigger_type))
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute("""
                    UPDATE journey_triggers
                    SET trigger_config = %s, is_active = %s, tenant_id = %s
                    WHERE id = %s
                    RETURNING id, journey_id, trigger_type, trigger_config, is_active, created_at
                """, (json.dumps(trigger_config), is_active, tenant_id, existing[0]))
            else:
                cursor.execute("""
                    INSERT INTO journey_triggers (journey_id, trigger_type, trigger_config, is_active, tenant_id)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, journey_id, trigger_type, trigger_config, is_active, created_at
                """, (journey_id, trigger_type, json.dumps(trigger_config), is_active, tenant_id))
            
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
    """Get the active trigger for a journey (returns list with at most 1 item)."""
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
                WHERE j.tenant_id = %s AND t.journey_id = %s AND t.is_active = true
                ORDER BY t.created_at DESC
                LIMIT 1
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
                SELECT s.id, s.journey_id, s.step_order, s.step_type, s.config, s.created_at,
                       s.branch_keyword, s.branch_true_step_id, s.branch_false_step_id
                FROM journey_steps s
                JOIN journeys j ON j.id = s.journey_id
                WHERE j.tenant_id = %s AND s.journey_id = %s
                ORDER BY s.step_order ASC
            """, (tenant_id, journey_id))
            
            steps = []
            for row in cursor.fetchall():
                config = row[4] if isinstance(row[4], dict) else json.loads(row[4]) if row[4] else {}
                step_type = row[3]
                branch_keyword = row[6] or ''
                branch_true_step_id = str(row[7]) if row[7] else ''
                branch_false_step_id = str(row[8]) if row[8] else ''
                config['branch_keyword'] = branch_keyword
                config['branch_true_step_id'] = branch_true_step_id
                config['branch_false_step_id'] = branch_false_step_id
                steps.append({
                    'id': str(row[0]),
                    'journey_id': str(row[1]),
                    'step_order': row[2],
                    'step_type': step_type,
                    'config': config,
                    'created_at': row[5].isoformat() if row[5] else None,
                    'message_template': config.get('text', ''),
                    'delay_seconds': config.get('delay_seconds', 0),
                    'wait_for_reply': config.get('wait_for_reply', False) or step_type == 'wait_for_reply',
                    'timeout_action': config.get('timeout_action', 'continue'),
                    'branch_keyword': branch_keyword,
                    'branch_true_step_id': branch_true_step_id,
                    'branch_false_step_id': branch_false_step_id,
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
            
            cursor.execute("""
                UPDATE journey_user_sessions 
                SET current_step_id = NULL 
                WHERE journey_id = %s
            """, (journey_id,))
            
            cursor.execute("""
                DELETE FROM journey_scheduled_messages 
                WHERE step_id IN (SELECT id FROM journey_steps WHERE journey_id = %s)
            """, (journey_id,))
            
            cursor.execute("DELETE FROM journey_steps WHERE journey_id = %s", (journey_id,))
            
            for step in steps:
                step_config = step.get('config', {})
                branch_keyword = step_config.get('branch_keyword', '') or None
                branch_true_step_id = step_config.get('branch_true_step_id', '') or None
                branch_false_step_id = step_config.get('branch_false_step_id', '') or None
                cursor.execute("""
                    INSERT INTO journey_steps (journey_id, step_order, step_type, config,
                                              branch_keyword, branch_true_step_id, branch_false_step_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (journey_id, step['step_order'], step['step_type'], json.dumps(step_config),
                      branch_keyword, branch_true_step_id, branch_false_step_id))
            
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
                       t.id as trigger_id, t.trigger_config, j.start_delay_seconds
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
                    'trigger_config': row[7] if isinstance(row[7], dict) else json.loads(row[7]) if row[7] else {},
                    'start_delay_seconds': row[8] or 0
                }
            return None
    except Exception as e:
        logger.exception(f"Error finding journey by deeplink: {e}")
        return None


def get_active_journey_by_dm_trigger(tenant_id: str, message_text: str) -> Optional[Dict]:
    """Find an active journey matching a direct_message trigger for a given tenant.
    
    If trigger_config has a 'keyword' field, match case-insensitively against message_text.
    If keyword is empty/null, any message matches.
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT j.id, j.tenant_id, j.bot_id, j.name, j.status, j.re_entry_policy,
                       t.id as trigger_id, t.trigger_config, j.start_delay_seconds
                FROM journeys j
                JOIN journey_triggers t ON t.journey_id = j.id
                WHERE j.tenant_id = %s
                  AND j.status = 'active'
                  AND t.trigger_type = 'direct_message'
                  AND t.is_active = TRUE
                  AND j.is_locked = FALSE
                ORDER BY j.priority_int DESC, j.updated_at DESC
            """, (tenant_id,))
            rows = cursor.fetchall()
            
            for row in rows:
                trigger_config = row[7] if isinstance(row[7], dict) else json.loads(row[7]) if row[7] else {}
                keyword = (trigger_config.get('keyword') or '').strip()
                
                if keyword and keyword.lower() not in message_text.lower():
                    continue
                
                return {
                    'id': str(row[0]),
                    'tenant_id': row[1],
                    'bot_id': row[2],
                    'name': row[3],
                    'status': row[4],
                    're_entry_policy': row[5],
                    'trigger_id': str(row[6]),
                    'trigger_config': trigger_config,
                    'start_delay_seconds': row[8] or 0
                }
            return None
    except Exception as e:
        logger.exception(f"Error finding journey by DM trigger: {e}")
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
                       current_step_id, status, answers, started_at, completed_at, last_activity_at, welcome_sent_at
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
                    'last_activity_at': row[10].isoformat() if row[10] else None,
                    'welcome_sent_at': row[11].isoformat() if row[11] else None
                }
            return None
    except Exception as e:
        logger.exception(f"Error getting active session: {e}")
        return None


def create_session(tenant_id: str, journey_id: str, telegram_chat_id: int, 
                   telegram_user_id: int, first_step_id: str = None, first_name: str = '') -> Optional[Dict]:
    """Create a new journey session for a user."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            initial_answers = json.dumps({'_first_name': first_name}) if first_name else None
            cursor.execute("""
                INSERT INTO journey_user_sessions 
                (tenant_id, journey_id, telegram_chat_id, telegram_user_id, current_step_id, status, answers)
                VALUES (%s, %s, %s, %s, %s, 'active', %s)
                RETURNING id, tenant_id, journey_id, telegram_chat_id, telegram_user_id,
                          current_step_id, status, answers, started_at, completed_at, last_activity_at, welcome_sent_at
            """, (tenant_id, journey_id, telegram_chat_id, telegram_user_id, first_step_id, initial_answers))
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
                    'last_activity_at': row[10].isoformat() if row[10] else None,
                    'welcome_sent_at': row[11].isoformat() if row[11] else None
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
                WHERE id = %s AND status IN ('active', 'waiting_delay', 'awaiting_reply')
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
                       current_step_id, status, answers, started_at, completed_at, last_activity_at, welcome_sent_at
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
                    'last_activity_at': row[10].isoformat() if row[10] else None,
                    'welcome_sent_at': row[11].isoformat() if row[11] else None
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
                SELECT id, journey_id, step_order, step_type, config, created_at,
                       branch_keyword, branch_true_step_id, branch_false_step_id
                FROM journey_steps
                WHERE id = %s
            """, (step_id,))
            row = cursor.fetchone()
            
            if row:
                config = row[4] if isinstance(row[4], dict) else json.loads(row[4]) if row[4] else {}
                branch_keyword = row[6] or ''
                branch_true_step_id = str(row[7]) if row[7] else ''
                branch_false_step_id = str(row[8]) if row[8] else ''
                config['branch_keyword'] = branch_keyword
                config['branch_true_step_id'] = branch_true_step_id
                config['branch_false_step_id'] = branch_false_step_id
                return {
                    'id': str(row[0]),
                    'journey_id': str(row[1]),
                    'step_order': row[2],
                    'step_type': row[3],
                    'config': config,
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
    """Fetch and atomically claim scheduled messages that are due for sending."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE journey_scheduled_messages
                SET status = 'processing'
                WHERE id IN (
                    SELECT m.id
                    FROM journey_scheduled_messages m
                    JOIN journey_user_sessions s ON s.id = m.session_id
                    JOIN journeys j ON j.id = s.journey_id
                    WHERE m.status = 'pending' AND m.scheduled_for <= NOW()
                    ORDER BY m.scheduled_for ASC
                    LIMIT %s
                    FOR UPDATE OF m SKIP LOCKED
                )
                RETURNING id, tenant_id, session_id, step_id, telegram_chat_id, 
                          message_content, scheduled_for,
                          (SELECT s.journey_id FROM journey_user_sessions s WHERE s.id = session_id),
                          (SELECT j.bot_id FROM journeys j JOIN journey_user_sessions s2 ON j.id = s2.journey_id WHERE s2.id = session_id)
            """, (limit,))
            conn.commit()
            
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
                    'journey_id': str(row[7]) if row[7] else None,
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


def mark_scheduled_message_failed(message_id: str, error: str, reset_to_pending: bool = False) -> bool:
    """Mark a scheduled message as failed, optionally resetting to pending for retry."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            new_status = 'pending' if reset_to_pending else 'failed'
            cursor.execute("""
                UPDATE journey_scheduled_messages
                SET status = %s, error = %s
                WHERE id = %s
            """, (new_status, error, message_id))
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
    """Get the active or awaiting_reply session for a user who is replying (for answer collection)."""
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
                  AND s.status IN ('active', 'awaiting_reply')
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


def count_journeys(tenant_id: str) -> int:
    """Count journeys for a tenant (used for max limit enforcement)."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return 0
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM journeys WHERE tenant_id = %s
            """, (tenant_id,))
            row = cursor.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logger.exception(f"Error counting journeys: {e}")
        return 0


def delete_journey(tenant_id: str, journey_id: str) -> bool:
    """Delete a journey and all related data (triggers, steps, sessions)."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        logger.error("delete_journey: No database pool available")
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            logger.info(f"delete_journey: Looking for journey_id={journey_id}, tenant_id={tenant_id}")
            
            cursor.execute("""
                SELECT id FROM journeys WHERE tenant_id = %s AND id = %s::uuid
            """, (tenant_id, journey_id))
            row = cursor.fetchone()
            if not row:
                logger.warning(f"delete_journey: Journey not found - journey_id={journey_id}, tenant_id={tenant_id}")
                return False
            
            logger.info(f"delete_journey: Found journey {row[0]}, proceeding with deletion")
            
            cursor.execute("""
                DELETE FROM journey_scheduled_messages 
                WHERE session_id IN (
                    SELECT id FROM journey_user_sessions 
                    WHERE journey_id = %s::uuid
                )
            """, (journey_id,))
            
            cursor.execute("""
                DELETE FROM journey_user_sessions WHERE journey_id = %s::uuid
            """, (journey_id,))
            
            cursor.execute("""
                DELETE FROM journey_steps WHERE journey_id = %s::uuid
            """, (journey_id,))
            
            cursor.execute("""
                DELETE FROM journey_triggers WHERE journey_id = %s::uuid
            """, (journey_id,))
            
            cursor.execute("""
                DELETE FROM journeys WHERE tenant_id = %s AND id = %s::uuid
            """, (tenant_id, journey_id))
            
            conn.commit()
            logger.info(f"Deleted journey {journey_id} for tenant {tenant_id}")
            return True
    except Exception as e:
        logger.exception(f"Error deleting journey: {e}")
        return False


def set_journey_locked(tenant_id: str, journey_id: str, is_locked: bool) -> bool:
    """Set the locked status of a journey."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE journeys SET is_locked = %s, updated_at = NOW()
                WHERE id = %s AND tenant_id = %s
            """, (is_locked, journey_id, tenant_id))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.exception(f"Error setting journey locked: {e}")
        return False


def duplicate_journey(tenant_id: str, journey_id: str) -> Optional[Dict]:
    """Duplicate a journey with all its steps and triggers in a single transaction."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, tenant_id, bot_id, name, description, status, re_entry_policy,
                       priority_int, inactivity_timeout_days, start_delay_seconds
                FROM journeys
                WHERE tenant_id = %s AND id = %s
            """, (tenant_id, journey_id))
            original = cursor.fetchone()
            if not original:
                return None
            
            new_name = original[3] + " (Copy)"
            
            cursor.execute("""
                INSERT INTO journeys (tenant_id, bot_id, name, description, status, re_entry_policy, is_locked,
                                      priority_int, inactivity_timeout_days, start_delay_seconds)
                VALUES (%s, %s, %s, %s, 'draft', %s, FALSE, %s, %s, %s)
                RETURNING id, tenant_id, bot_id, name, description, status, re_entry_policy, created_at, updated_at
            """, (tenant_id, original[2], new_name, original[4], original[6],
                  original[7], original[8], original[9]))
            new_row = cursor.fetchone()
            if not new_row:
                return None
            new_journey_id = new_row[0]
            
            cursor.execute("""
                SELECT step_order, step_type, config
                FROM journey_steps
                WHERE journey_id = %s
                ORDER BY step_order ASC
            """, (journey_id,))
            steps = cursor.fetchall()
            for step in steps:
                cursor.execute("""
                    INSERT INTO journey_steps (journey_id, step_order, step_type, config)
                    VALUES (%s, %s, %s, %s)
                """, (new_journey_id, step[0], step[1], json.dumps(step[2]) if isinstance(step[2], dict) else step[2]))
            
            cursor.execute("""
                SELECT trigger_type, trigger_config, is_active
                FROM journey_triggers
                WHERE journey_id = %s
            """, (journey_id,))
            triggers = cursor.fetchall()
            for trigger in triggers:
                cursor.execute("""
                    INSERT INTO journey_triggers (journey_id, tenant_id, trigger_type, trigger_config, is_active)
                    VALUES (%s, %s, %s, %s, %s)
                """, (new_journey_id, tenant_id, trigger[0],
                      json.dumps(trigger[1]) if isinstance(trigger[1], dict) else trigger[1],
                      trigger[2]))
            
            conn.commit()
            
            return {
                'id': str(new_row[0]),
                'tenant_id': new_row[1],
                'bot_id': new_row[2],
                'name': new_row[3],
                'description': new_row[4],
                'status': new_row[5],
                're_entry_policy': new_row[6],
                'created_at': new_row[7].isoformat() if new_row[7] else None,
                'updated_at': new_row[8].isoformat() if new_row[8] else None
            }
    except Exception as e:
        logger.exception(f"Error duplicating journey: {e}")
        return None


def set_session_awaiting_reply(session_id: str, step_id: str, timeout_minutes: int = None) -> bool:
    """
    Mark a session as awaiting a user reply.
    
    Args:
        session_id: Session ID
        step_id: Current step ID (wait_for_reply step)
        timeout_minutes: Minutes until timeout (None = no timeout)
        
    Returns:
        True if updated successfully
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            if timeout_minutes:
                cursor.execute("""
                    UPDATE journey_user_sessions
                    SET status = 'awaiting_reply', 
                        current_step_id = %s,
                        wait_timeout_at = NOW() + INTERVAL '%s minutes',
                        last_activity_at = NOW()
                    WHERE id = %s
                """, (step_id, timeout_minutes, session_id))
            else:
                cursor.execute("""
                    UPDATE journey_user_sessions
                    SET status = 'awaiting_reply', 
                        current_step_id = %s,
                        wait_timeout_at = NULL,
                        last_activity_at = NOW()
                    WHERE id = %s
                """, (step_id, session_id))
            
            conn.commit()
            logger.info(f"Session {session_id} now awaiting reply (timeout={timeout_minutes}min)")
            return cursor.rowcount > 0
    except Exception as e:
        logger.exception(f"Error setting session awaiting reply: {e}")
        return False


def fetch_timed_out_waiting_sessions(limit: int = 50) -> List[Dict]:
    """
    Fetch sessions that are awaiting_reply and have timed out.
    
    Uses FOR UPDATE SKIP LOCKED for idempotency.
    
    Returns:
        List of timed-out session dicts with reply_received_at included
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, tenant_id, journey_id, telegram_chat_id, telegram_user_id,
                       current_step_id, status, answers, started_at, completed_at, 
                       last_activity_at, wait_timeout_at, reply_received_at
                FROM journey_user_sessions
                WHERE status = 'awaiting_reply' 
                  AND wait_timeout_at IS NOT NULL 
                  AND wait_timeout_at <= NOW()
                ORDER BY wait_timeout_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
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
                    'answers': row[7] if isinstance(row[7], dict) else json.loads(row[7]) if row[7] else {},
                    'started_at': row[8].isoformat() if row[8] else None,
                    'completed_at': row[9].isoformat() if row[9] else None,
                    'last_activity_at': row[10].isoformat() if row[10] else None,
                    'wait_timeout_at': row[11].isoformat() if row[11] else None,
                    'reply_received_at': row[12].isoformat() if row[12] else None
                })
            return sessions
    except Exception as e:
        logger.exception(f"Error fetching timed-out sessions: {e}")
        return []


def get_awaiting_session_for_user(tenant_id: str, telegram_user_id: int) -> Optional[Dict]:
    """
    Get an active or awaiting_reply session for a user.
    
    Args:
        tenant_id: Tenant ID
        telegram_user_id: Telegram user ID
        
    Returns:
        Session dict or None
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, tenant_id, journey_id, telegram_chat_id, telegram_user_id,
                       current_step_id, status, answers, started_at, completed_at, 
                       last_activity_at, wait_timeout_at
                FROM journey_user_sessions
                WHERE tenant_id = %s AND telegram_user_id = %s
                  AND status IN ('active', 'awaiting_reply', 'waiting_delay')
                ORDER BY last_activity_at DESC
                LIMIT 1
            """, (tenant_id, telegram_user_id))
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
                    'last_activity_at': row[10].isoformat() if row[10] else None,
                    'wait_timeout_at': row[11].isoformat() if row[11] else None
                }
            return None
    except Exception as e:
        logger.exception(f"Error getting awaiting session: {e}")
        return None


def clear_reply_received(session_id: str) -> bool:
    """
    Clear the reply_received_at timestamp for a session.
    
    Called after processing a wait_for_reply timeout.
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE journey_user_sessions
                SET reply_received_at = NULL, wait_timeout_at = NULL
                WHERE id = %s
            """, (session_id,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.exception(f"Error clearing reply received: {e}")
        return False


def store_user_reply(session_id: str, reply_text: str) -> bool:
    """
    Store a user's reply in the session answers.
    
    Args:
        session_id: Session ID
        reply_text: User's reply text
        
    Returns:
        True if stored successfully
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT answers FROM journey_user_sessions WHERE id = %s
            """, (session_id,))
            row = cursor.fetchone()
            
            if not row:
                return False
            
            answers = row[0] if isinstance(row[0], dict) else json.loads(row[0]) if row[0] else {}
            replies = answers.get('_replies', [])
            replies.append({
                'text': reply_text,
                'timestamp': datetime.utcnow().isoformat()
            })
            answers['_replies'] = replies
            answers['_last_reply'] = reply_text
            
            cursor.execute("""
                UPDATE journey_user_sessions
                SET answers = %s, last_activity_at = NOW(), reply_received_at = NOW()
                WHERE id = %s
            """, (json.dumps(answers), session_id))
            
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.exception(f"Error storing user reply: {e}")
        return False


def increment_step_send(tenant_id: str, journey_id: str, step_id: str, user_id: int) -> bool:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO journey_step_analytics (step_id, journey_id, tenant_id, sends, unique_users)
                VALUES (%s::uuid, %s::uuid, %s, 1, 1)
                ON CONFLICT (step_id) DO UPDATE
                SET sends = journey_step_analytics.sends + 1,
                    unique_users = journey_step_analytics.unique_users + 1,
                    updated_at = NOW()
            """, (step_id, journey_id, tenant_id))
            conn.commit()
            return True
    except Exception as e:
        logger.exception(f"Error incrementing step send: {e}")
        return False


def increment_step_reads(step_id: str) -> bool:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE journey_step_analytics SET reads = reads + 1, updated_at = NOW()
                WHERE step_id = %s::uuid
            """, (step_id,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.exception(f"Error incrementing step reads: {e}")
        return False


def increment_step_link_clicks(step_id: str) -> bool:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE journey_step_analytics SET link_clicks = link_clicks + 1, updated_at = NOW()
                WHERE step_id = %s::uuid
            """, (step_id,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.exception(f"Error incrementing step link clicks: {e}")
        return False


def get_step_analytics(journey_id: str) -> List[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT step_id, sends, unique_users, reads, link_clicks
                FROM journey_step_analytics
                WHERE journey_id = %s::uuid
            """, (journey_id,))
            results = []
            for row in cursor.fetchall():
                results.append({
                    'step_id': str(row[0]),
                    'sends': row[1] or 0,
                    'unique_users': row[2] or 0,
                    'reads': row[3] or 0,
                    'link_clicks': row[4] or 0
                })
            return results
    except Exception as e:
        logger.exception(f"Error getting step analytics: {e}")
        return []


def create_tracked_link(tenant_id: str, journey_id: str, step_id: str, url: str) -> str:
    import hashlib
    track_id = hashlib.md5(f"{step_id}:{url}".encode()).hexdigest()[:16]

    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return url

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO journey_link_clicks (track_id, step_id, journey_id, tenant_id, destination_url)
                VALUES (%s, %s::uuid, %s::uuid, %s, %s)
                ON CONFLICT (track_id) DO UPDATE SET destination_url = EXCLUDED.destination_url
            """, (track_id, step_id, journey_id, tenant_id, url))
            conn.commit()
            return f"https://dash.promostack.io/api/j/c/{track_id}"
    except Exception as e:
        logger.exception(f"Error creating tracked link: {e}")
        return url


def get_link_click_by_track_id(track_id: str) -> Optional[Dict]:
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return None

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT track_id, step_id, journey_id, tenant_id, destination_url
                FROM journey_link_clicks
                WHERE track_id = %s
            """, (track_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'track_id': row[0],
                    'step_id': str(row[1]),
                    'journey_id': str(row[2]),
                    'tenant_id': row[3],
                    'destination_url': row[4]
                }
            return None
    except Exception as e:
        logger.exception(f"Error getting link click: {e}")
        return None


def get_sessions_by_chat_id(tenant_id: str, chat_id: int) -> List[Dict]:
    """Get active or awaiting_reply sessions for a chat ID."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, tenant_id, journey_id, telegram_chat_id, telegram_user_id,
                       current_step_id, status, answers, started_at, completed_at, last_activity_at
                FROM journey_user_sessions
                WHERE tenant_id = %s AND telegram_chat_id = %s
                  AND status IN ('active', 'awaiting_reply')
                ORDER BY started_at DESC
            """, (tenant_id, chat_id))

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
                    'answers': row[7] if isinstance(row[7], dict) else json.loads(row[7]) if row[7] else {},
                    'started_at': row[8].isoformat() if row[8] else None,
                    'completed_at': row[9].isoformat() if row[9] else None,
                    'last_activity_at': row[10].isoformat() if row[10] else None
                })
            return sessions
    except Exception as e:
        logger.exception(f"Error getting sessions by chat_id: {e}")
        return []


def check_message_dedupe(tenant_id: str, chat_id: int, message_id: int) -> bool:
    """Check if a message has already been processed (dedupe).
    
    Returns True if this is a NEW message (inserted), False if duplicate.
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO journey_inbound_dedupe (tenant_id, chat_id, message_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (tenant_id, chat_id, message_id) DO NOTHING
            """, (tenant_id, chat_id, message_id))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.exception(f"Error checking message dedupe: {e}")
        return False


def cleanup_old_dedupe_records(days: int = 7) -> int:
    """Delete journey_inbound_dedupe records older than N days. Returns count deleted."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return 0

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM journey_inbound_dedupe WHERE received_at < NOW() - make_interval(days => %s)",
                (days,)
            )
            deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old dedupe records (>{days} days)")
            return deleted
    except Exception as e:
        if 'relation "journey_inbound_dedupe" does not exist' in str(e):
            logger.debug("journey_inbound_dedupe table does not exist yet, skipping cleanup")
            return 0
        logger.exception(f"Error cleaning up dedupe records: {e}")
        return 0


def cancel_pending_scheduled_messages(session_id: str) -> int:
    """Cancel all pending scheduled messages for a session.
    
    Returns the count of cancelled messages.
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return 0

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE journey_scheduled_messages
                SET status = 'cancelled'
                WHERE session_id = %s AND status = 'pending'
            """, (session_id,))
            conn.commit()
            cancelled = cursor.rowcount
            if cancelled > 0:
                logger.info(f"Cancelled {cancelled} pending scheduled messages for session {session_id}")
            return cancelled
    except Exception as e:
        logger.exception(f"Error cancelling pending scheduled messages: {e}")
        return 0


def mark_session_broken(session_id: str, reason: str = '') -> bool:
    """Mark a session as broken with an optional reason.
    
    Sets status='broken' and completed_at=NOW().
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE journey_user_sessions
                SET status = 'broken', completed_at = NOW(), last_activity_at = NOW()
                WHERE id = %s
            """, (session_id,))
            conn.commit()
            if cursor.rowcount > 0:
                logger.warning(f"Marked session {session_id} as broken. Reason: {reason}")
                return True
            return False
    except Exception as e:
        logger.exception(f"Error marking session broken: {e}")
        return False


def get_journey_timeout_days(journey_id: str) -> int:
    """Get the inactivity_timeout_days for a journey. Returns 3 as default."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return 3
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT inactivity_timeout_days FROM journeys WHERE id = %s", (journey_id,))
            row = cursor.fetchone()
            return row[0] if row and row[0] else 3
    except Exception as e:
        logger.exception(f"Error getting journey timeout: {e}")
        return 3


def fetch_inactive_awaiting_sessions(limit: int = 50) -> List[Dict]:
    """Fetch sessions in any active state that have exceeded inactivity timeout.
    
    Includes sessions with status IN ('awaiting_reply', 'active', 'waiting_delay')
    that have exceeded their journey's inactivity_timeout_days.
    
    Joins with journeys to get each journey's inactivity_timeout_days.
    Uses FOR UPDATE SKIP LOCKED to allow concurrent processing.
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id, s.tenant_id, s.journey_id, s.telegram_chat_id, s.telegram_user_id,
                       s.current_step_id, s.status, s.answers, s.started_at, s.completed_at, s.last_activity_at
                FROM journey_user_sessions s
                JOIN journeys j ON j.id = s.journey_id
                WHERE s.status IN ('awaiting_reply', 'active', 'waiting_delay')
                  AND s.last_activity_at < NOW() - (j.inactivity_timeout_days || ' days')::interval
                ORDER BY s.last_activity_at ASC
                LIMIT %s
                FOR UPDATE OF s SKIP LOCKED
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
                    'answers': row[7] if isinstance(row[7], dict) else json.loads(row[7]) if row[7] else {},
                    'started_at': row[8].isoformat() if row[8] else None,
                    'completed_at': row[9].isoformat() if row[9] else None,
                    'last_activity_at': row[10].isoformat() if row[10] else None
                })
            return sessions
    except Exception as e:
        logger.exception(f"Error fetching inactive awaiting sessions: {e}")
        return []


def fetch_stale_waiting_delay_sessions(stale_after_seconds: int = 60, limit: int = 20) -> List[Dict]:
    """Fetch waiting_delay sessions that have no pending scheduled messages and are older than stale_after_seconds.
    
    These sessions were likely left by a start_delay that didn't complete
    (e.g., process restart). Recovery: re-execute their first step.
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []

    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.id, s.tenant_id, s.journey_id, s.telegram_chat_id, s.telegram_user_id,
                       s.current_step_id, s.status, s.answers, s.started_at, s.completed_at, s.last_activity_at, s.welcome_sent_at
                FROM journey_user_sessions s
                WHERE s.status = 'waiting_delay'
                  AND s.last_activity_at < NOW() - make_interval(secs => %s)
                  AND NOT EXISTS (
                      SELECT 1 FROM journey_scheduled_messages m
                      WHERE m.session_id = s.id AND m.status = 'pending'
                  )
                ORDER BY s.last_activity_at ASC
                LIMIT %s
                FOR UPDATE OF s SKIP LOCKED
            """, (stale_after_seconds, limit))

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
                    'answers': row[7],
                    'started_at': row[8],
                    'completed_at': row[9],
                    'last_activity_at': row[10],
                    'welcome_sent_at': row[11]
                })
            conn.commit()
            return sessions
    except Exception as e:
        logger.exception(f"Error fetching stale waiting_delay sessions: {e}")
        return []
