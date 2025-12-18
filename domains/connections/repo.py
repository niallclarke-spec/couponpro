"""
Connections repository - tenant-scoped database functions for bot connections.

All functions must include tenant_id filters where applicable.
Following the functional pattern established by journeys and crosspromo repos.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from core.logging import get_logger

logger = get_logger(__name__)


class DatabaseUnavailableError(Exception):
    """Raised when the database pool is not available."""
    pass


class DatabaseOperationError(Exception):
    """Raised when a database operation fails."""
    pass


def _get_db_pool():
    """Get the database pool, importing lazily to avoid circular imports."""
    from db import db_pool
    return db_pool


def _require_db_pool():
    """Get database pool or raise DatabaseUnavailableError."""
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        raise DatabaseUnavailableError("Database pool not available")
    return db_pool


def list_connections(tenant_id: str) -> List[Dict[str, Any]]:
    """
    List all bot connections for a tenant.
    
    Returns list of connection dicts with keys:
    - bot_role, bot_username, webhook_url, channel_id
    - vip_channel_id, free_channel_id
    - last_validated_at, last_error
    
    Raises:
        DatabaseUnavailableError: If database pool is not available
    """
    db_pool = _require_db_pool()
    
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
        raise DatabaseOperationError(f"Failed to list connections: {e}") from e


def get_connection(tenant_id: str, bot_role: str) -> Optional[Dict[str, Any]]:
    """
    Get a bot connection for a tenant by role.
    
    Returns connection dict with bot_token, or None if not found.
    
    Raises:
        DatabaseUnavailableError: If database pool is not available
    """
    _require_db_pool()
    
    from db import get_bot_connection as db_get_bot_connection
    return db_get_bot_connection(tenant_id, bot_role)


def upsert_connection(
    tenant_id: str,
    bot_role: str,
    bot_token: str,
    bot_username: str,
    webhook_secret: str,
    webhook_url: str,
    channel_id: Optional[str] = None,
    vip_channel_id: Optional[str] = None,
    free_channel_id: Optional[str] = None
) -> bool:
    """
    Create or update a bot connection for a tenant.
    
    Returns True if upsert succeeded, False on database error.
    
    Raises:
        DatabaseUnavailableError: If database pool is not available
    """
    _require_db_pool()
    
    from db import upsert_bot_connection as db_upsert_bot_connection
    # Pass optional channel IDs as-is - db function accepts None and stores NULL
    return db_upsert_bot_connection(  # type: ignore[arg-type]
        tenant_id=tenant_id,
        bot_role=bot_role,
        bot_token=bot_token,
        bot_username=bot_username,
        webhook_secret=webhook_secret,
        webhook_url=webhook_url,
        channel_id=channel_id,
        vip_channel_id=vip_channel_id,
        free_channel_id=free_channel_id
    )


def delete_connection(tenant_id: str, bot_role: str) -> bool:
    """
    Delete a bot connection for a tenant.
    
    Returns True if deletion succeeded (including if no row existed).
    Returns False on database error.
    
    Raises:
        DatabaseUnavailableError: If database pool is not available
    """
    db_pool = _require_db_pool()
    
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
        raise DatabaseOperationError(f"Failed to delete connection: {e}") from e
