"""Tenant domain handlers."""
import json
from core.tenant_credentials import get_tenant_setup_status


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
    
    from db import db_pool
    if not db_pool or not db_pool.connection_pool:
        handler.send_response(503)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': 'Database not available'}).encode())
        return
    
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
        print(f"[TENANT] Saved {provider} integration for tenant {tenant_id}")
    except Exception as e:
        print(f"[TENANT] Error saving integration: {e}")
        handler.send_response(500)
        handler.send_header('Content-type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({'error': str(e)}).encode())
        return
    
    handler.send_response(200)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps({'success': True}).encode())
