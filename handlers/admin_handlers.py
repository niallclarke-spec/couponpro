"""
Admin handlers for platform-wide admin operations.
"""
import json
import db

from core.logging import get_logger
logger = get_logger(__name__)


def _send_json_response(handler, status: int, data: dict):
    """Helper to send JSON response."""
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode('utf-8'))


def handle_get_tenants(handler):
    """GET /api/admin/tenants - List all tenants with stats."""
    try:
        tenants = db.get_all_tenants()
        
        total = len(tenants)
        complete = sum(1 for t in tenants if t.get('onboarding_complete'))
        pending = total - complete
        
        response = {
            'tenants': tenants,
            'stats': {
                'total': total,
                'complete': complete,
                'pending': pending
            }
        }
        
        _send_json_response(handler, 200, response)
    except Exception as e:
        logger.exception("Error getting tenants list")
        _send_json_response(handler, 500, {'error': str(e)})
