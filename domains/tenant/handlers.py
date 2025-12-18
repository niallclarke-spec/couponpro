"""Tenant domain handlers."""
import json
from core.tenant_credentials import get_tenant_setup_status
from domains.tenant import repo as tenant_repo
from domains.tenant.repo import DatabaseUnavailableError, DatabaseOperationError

from core.logging import get_logger
logger = get_logger(__name__)


VALID_PROVIDERS = {'stripe', 'telegram', 'market_data'}
PROVIDER_REQUIRED_FIELDS = {
    'stripe': ['stripe_account_id', 'webhook_secret'],
    'telegram': ['bot_token'],
    'market_data': ['api_key']
}


def handle_tenant_setup_status(handler, tenant_id):
    """GET /api/tenant/setup-status"""
    status = get_tenant_setup_status(tenant_id)
    handler.send_response(200)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps(status).encode())


def handle_tenant_integrations(handler, tenant_id):
    """POST /api/tenant/integrations"""
    if tenant_id == 'entrylab':
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'EntryLab uses environment credentials'}).encode())
        return
    
    try:
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length)
        data = json.loads(body)
    except Exception as e:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': f'Invalid JSON: {e}'}).encode())
        return
    
    provider = data.get('provider')
    config = data.get('config', {})
    
    if provider not in VALID_PROVIDERS:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': f'Invalid provider: {provider}'}).encode())
        return
    
    required_fields = PROVIDER_REQUIRED_FIELDS.get(provider, [])
    missing = [f for f in required_fields if not config.get(f)]
    if missing:
        handler.send_response(400)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': f'Missing fields: {missing}'}).encode())
        return
    
    try:
        tenant_repo.upsert_integration(tenant_id, provider, config)
        
        handler.send_response(200)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'success': True}).encode())
    except DatabaseUnavailableError:
        handler.send_response(503)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Database not available'}).encode())
    except DatabaseOperationError as e:
        logger.exception(f"Database error saving integration: {e}")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Database operation failed'}).encode())


VALID_ROLES = {'admin', 'member'}


def _send_json(handler, status: int, data: dict):
    """Helper to send JSON response."""
    handler.send_response(status)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode())


def handle_tenant_map_user(handler):
    """
    POST /api/tenants/map-user
    EntryLab-admin-only endpoint to create/update tenant_users mappings.
    
    Option A: 1 Clerk user → 1 tenant (enforced by UNIQUE(clerk_user_id)).
    Uses atomic INSERT ... ON CONFLICT upsert with RETURNING to determine action.
    """
    try:
        content_length = int(handler.headers.get('Content-Length', 0))
        body = handler.rfile.read(content_length)
        data = json.loads(body)
    except Exception as e:
        _send_json(handler, 400, {'error': f'Invalid JSON: {e}'})
        return
    
    tenant_id = (data.get('tenant_id') or '').strip()
    clerk_user_id = (data.get('clerk_user_id') or '').strip()
    role = (data.get('role') or 'admin').strip()
    
    if not tenant_id:
        _send_json(handler, 400, {'error': 'tenant_id is required'})
        return
    
    if not clerk_user_id:
        _send_json(handler, 400, {'error': 'clerk_user_id is required'})
        return
    
    if tenant_id == 'entrylab':
        _send_json(handler, 400, {'error': 'Cannot map users to entrylab tenant'})
        return
    
    if role not in VALID_ROLES:
        _send_json(handler, 400, {'error': f'Invalid role. Must be one of: {", ".join(VALID_ROLES)}'})
        return
    
    try:
        if not tenant_repo.tenant_exists(tenant_id):
            _send_json(handler, 400, {'error': f'Tenant not found: {tenant_id}'})
            return
        
        success, action, previous_tenant_id = tenant_repo.map_user_to_tenant(
            clerk_user_id, tenant_id, role
        )
        
        if not success:
            if action == 'conflict':
                _send_json(handler, 409, {'error': 'User mapping conflict - constraint violation'})
            else:
                _send_json(handler, 500, {'error': 'Failed to create user mapping'})
            return
        
        response = {
            'success': True,
            'action': action,
            'tenant_id': tenant_id,
            'previous_tenant_id': previous_tenant_id,
            'clerk_user_id': clerk_user_id,
            'role': role
        }
        
        _send_json(handler, 200, response)
    except DatabaseUnavailableError:
        _send_json(handler, 503, {'error': 'Database not available'})
    except DatabaseOperationError as e:
        logger.exception(f"Database error mapping user: {e}")
        _send_json(handler, 500, {'error': 'Database operation failed'})
