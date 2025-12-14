"""Tenant credential resolution helper."""
import os


def resolve_credentials(tenant_id: str, provider: str) -> dict:
    """
    Returns credentials for a provider.
    EntryLab uses env vars, other tenants use tenant_integrations DB.
    """
    if tenant_id == 'entrylab':
        if provider == 'stripe':
            return {'api_key': os.environ.get('STRIPE_SECRET_KEY')}
        elif provider == 'telegram':
            return {'bot_token': os.environ.get('FOREX_BOT_TOKEN')}
        elif provider == 'market_data':
            return {'api_key': os.environ.get('TWELVE_DATA_API_KEY')}
        return {}
    
    from db import db_pool
    if not db_pool or not db_pool.connection_pool:
        return {}
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT config_json FROM tenant_integrations WHERE tenant_id = %s AND provider = %s",
                (tenant_id, provider)
            )
            row = cursor.fetchone()
            return row[0] if row else {}
    except Exception as e:
        print(f"[TENANT] Error resolving credentials for {tenant_id}/{provider}: {e}")
        return {}


def get_tenant_setup_status(tenant_id: str) -> dict:
    """Returns setup status for a tenant."""
    if tenant_id == 'entrylab':
        return {
            'tenant_id': 'entrylab',
            'is_entrylab': True,
            'required': {'stripe': True, 'telegram': True, 'market_data': True},
            'configured': {'stripe': True, 'telegram': True, 'market_data': True},
            'is_complete': True
        }
    
    from db import db_pool
    if not db_pool or not db_pool.connection_pool:
        return {
            'tenant_id': tenant_id,
            'is_entrylab': False,
            'required': {'stripe': True, 'telegram': True, 'market_data': True},
            'configured': {'stripe': False, 'telegram': False, 'market_data': False},
            'is_complete': False,
            'error': 'Database not available'
        }
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT provider FROM tenant_integrations WHERE tenant_id = %s",
                (tenant_id,)
            )
            configured_providers = {row[0] for row in cursor.fetchall()}
        
        configured = {
            'stripe': 'stripe' in configured_providers,
            'telegram': 'telegram' in configured_providers,
            'market_data': 'market_data' in configured_providers
        }
        
        return {
            'tenant_id': tenant_id,
            'is_entrylab': False,
            'required': {'stripe': True, 'telegram': True, 'market_data': True},
            'configured': configured,
            'is_complete': all(configured.values())
        }
    except Exception as e:
        print(f"[TENANT] Error getting setup status for {tenant_id}: {e}")
        return {
            'tenant_id': tenant_id,
            'is_entrylab': False,
            'required': {'stripe': True, 'telegram': True, 'market_data': True},
            'configured': {'stripe': False, 'telegram': False, 'market_data': False},
            'is_complete': False,
            'error': str(e)
        }


def get_tenant_for_user(clerk_user_id: str) -> str:
    """
    Look up tenant_id for a Clerk user.
    Returns None if not found.
    """
    from db import db_pool
    if not db_pool or not db_pool.connection_pool:
        return None
    
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT tenant_id FROM tenant_users WHERE clerk_user_id = %s",
                (clerk_user_id,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception as e:
        print(f"[TENANT] Error looking up tenant for user {clerk_user_id}: {e}")
        return None


def bootstrap_tenant(clerk_user_id: str, email: str) -> str:
    """
    Create a new tenant and tenant_user mapping if none exists.
    Returns the tenant_id.
    """
    import uuid
    from db import db_pool
    
    if not db_pool or not db_pool.connection_pool:
        return None
    
    existing = get_tenant_for_user(clerk_user_id)
    if existing:
        return existing
    
    try:
        tenant_id = f"tenant_{uuid.uuid4().hex[:8]}"
        tenant_name = email.split('@')[0] if email else tenant_id
        
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tenants (id, name, is_active) VALUES (%s, %s, TRUE) ON CONFLICT (id) DO NOTHING",
                (tenant_id, tenant_name)
            )
            cursor.execute(
                "INSERT INTO tenant_users (clerk_user_id, tenant_id, email, role) VALUES (%s, %s, %s, 'owner')",
                (clerk_user_id, tenant_id, email)
            )
            conn.commit()
        
        print(f"[TENANT] Created new tenant {tenant_id} for user {clerk_user_id}")
        return tenant_id
    except Exception as e:
        print(f"[TENANT] Error bootstrapping tenant for {clerk_user_id}: {e}")
        return None
