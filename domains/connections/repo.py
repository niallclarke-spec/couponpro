"""
Connections repository - tenant-scoped database functions for bot connections.

All functions must include tenant_id filters where applicable.
Following the functional pattern established by journeys and crosspromo repos.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from core.logging import get_logger

logger = get_logger(__name__)


def _get_db_pool():
    """Get the database pool, importing lazily to avoid circular imports."""
    from db import db_pool
    return db_pool


def list_connections(tenant_id: str) -> List[Dict[str, Any]]:
    """
    List all bot connections for a tenant.
    
    Returns list of connection dicts with keys:
    - bot_role, bot_username, webhook_url, channel_id
    - vip_channel_id, free_channel_id
    - last_validated_at, last_error
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return []
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT bot_role, bot_username, webhook_url, channel_id, 
                       last_validated_at, last_error, vip_channel_id, free_channel_id
                FROM tenant_bot_connections
                WHERE tenant_id = %s
                ORDER BY bot_role
            """, (tenant_id,))
            
            connections = []
            for row in cursor.fetchall():
                connections.append({
                    'bot_role': row[0],
                    'bot_username': row[1],
                    'webhook_url': row[2],
                    'channel_id': row[3],
                    'last_validated_at': row[4].isoformat() if row[4] else None,
                    'last_error': row[5],
                    'vip_channel_id': row[6],
                    'free_channel_id': row[7]
                })
            return connections
    except Exception as e:
        logger.exception(f"Error listing connections for tenant {tenant_id}: {e}")
        return []


def delete_connection(tenant_id: str, bot_role: str) -> bool:
    """
    Delete a bot connection for a tenant.
    
    Returns True if deletion succeeded (including if no row existed).
    Returns False on database error.
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM tenant_bot_connections
                WHERE tenant_id = %s AND bot_role = %s
            """, (tenant_id, bot_role))
            conn.commit()
            
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted connection: tenant={tenant_id}, role={bot_role}")
            return True
    except Exception as e:
        logger.exception(f"Error deleting connection for tenant {tenant_id}, role {bot_role}: {e}")
        return False
