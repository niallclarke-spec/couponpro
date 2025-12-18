"""
Tenant repository - tenant-scoped database functions for tenant management.

All functions must include tenant_id filters where applicable.
Following the functional pattern established by journeys and crosspromo repos.
"""
import json
from typing import Optional, Dict, Any, Tuple
from core.logging import get_logger

logger = get_logger(__name__)


def _get_db_pool():
    """Get the database pool, importing lazily to avoid circular imports."""
    from db import db_pool
    return db_pool


def tenant_exists(tenant_id: str) -> bool:
    """
    Check if a tenant exists in the database.
    
    Returns True if tenant exists, False otherwise.
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM tenants WHERE id = %s", (tenant_id,))
            return cursor.fetchone() is not None
    except Exception as e:
        logger.exception(f"Error checking tenant exists {tenant_id}: {e}")
        return False


def upsert_integration(tenant_id: str, provider: str, config: Dict[str, Any]) -> bool:
    """
    Create or update a tenant integration.
    
    Args:
        tenant_id: The tenant ID
        provider: Integration provider (e.g., 'stripe', 'telegram', 'market_data')
        config: Configuration dict to store as JSON
        
    Returns:
        True if upsert succeeded, False on error.
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tenant_integrations (tenant_id, provider, config_json, updated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (tenant_id, provider) 
                DO UPDATE SET config_json = EXCLUDED.config_json, updated_at = CURRENT_TIMESTAMP
            """, (tenant_id, provider, json.dumps(config)))
            conn.commit()
            
            logger.info(f"Upserted {provider} integration for tenant {tenant_id}")
            return True
    except Exception as e:
        logger.exception(f"Error upserting integration for tenant {tenant_id}: {e}")
        return False


def map_user_to_tenant(
    clerk_user_id: str, 
    tenant_id: str, 
    role: str = 'admin'
) -> Tuple[bool, str, Optional[str]]:
    """
    Create or update a user-to-tenant mapping.
    
    Uses atomic INSERT ... ON CONFLICT upsert with RETURNING to determine action.
    One Clerk user can only belong to one tenant (enforced by UNIQUE constraint).
    
    Args:
        clerk_user_id: The Clerk user ID
        tenant_id: The tenant ID to map to
        role: User role (default 'admin')
        
    Returns:
        Tuple of (success, action, previous_tenant_id):
        - success: True if operation succeeded
        - action: One of 'created', 'updated', 'moved', 'unchanged', 'error'
        - previous_tenant_id: Set only when action is 'moved'
    """
    db_pool = _get_db_pool()
    if not db_pool or not db_pool.connection_pool:
        return False, 'error', None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                WITH prev AS (
                    SELECT tenant_id, role FROM tenant_users WHERE clerk_user_id = %s
                )
                INSERT INTO tenant_users (clerk_user_id, tenant_id, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (clerk_user_id) 
                DO UPDATE SET tenant_id = EXCLUDED.tenant_id, role = EXCLUDED.role
                RETURNING 
                    (SELECT tenant_id FROM prev) AS prev_tenant,
                    (SELECT role FROM prev) AS prev_role,
                    (xmax = 0) AS is_insert
            """, (clerk_user_id, clerk_user_id, tenant_id, role))
            
            row = cursor.fetchone()
            conn.commit()
            
            if not row:
                return False, 'error', None
            
            prev_tenant, prev_role, is_insert = row
            
            if is_insert:
                action = 'created'
                previous_tenant_id = None
            elif prev_tenant == tenant_id and prev_role == role:
                action = 'unchanged'
                previous_tenant_id = None
            elif prev_tenant == tenant_id:
                action = 'updated'
                previous_tenant_id = None
            else:
                action = 'moved'
                previous_tenant_id = prev_tenant
            
            logger.info(f"User mapping {action}: user={clerk_user_id}, tenant={tenant_id}")
            return True, action, previous_tenant_id
            
    except Exception as e:
        error_str = str(e).lower()
        if 'unique' in error_str or 'duplicate' in error_str or 'constraint' in error_str:
            logger.warning(f"Constraint violation mapping user: {e}")
            return False, 'conflict', None
        else:
            logger.exception(f"Error mapping user to tenant: {e}")
            return False, 'error', None
