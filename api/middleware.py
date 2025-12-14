"""
Middleware for API routes.

Thin wrappers that apply auth and availability checks before calling handlers.
These wrappers call the EXISTING check_auth() and availability flags unchanged.
"""
import json
from typing import Callable, Any

from api.routes import Route


ENTRYLAB_ONLY_ROUTES = [
    '/api/campaigns', '/api/broadcast', '/api/bot-stats', '/api/bot-users',
    '/api/upload-template', '/api/delete-template', '/api/toggle-telegram-template', '/api/validate-coupon',
    '/api/broadcast-status', '/api/broadcast-jobs', '/api/user-activity', '/api/invalid-coupons',
    '/api/telegram-webhook', '/api/day-of-week-stats', '/api/retention-rates'
]

FOREX_SAAS_ROUTES = [
    '/api/forex-signals', '/api/forex-config', '/api/signal-bot/status', 
    '/api/forex-stats', '/api/forex-tp-config', '/api/signal-bot/signals',
    '/api/signal-bot/set-active', '/api/signal-bot/cancel-queue',
    '/api/forex/xauusd-sparkline'
]


def send_unauthorized(handler_instance) -> None:
    """Send a 401 Unauthorized response."""
    handler_instance.send_response(401)
    handler_instance.send_header('Content-type', 'application/json')
    handler_instance.end_headers()
    handler_instance.wfile.write(json.dumps({'error': 'Unauthorized'}).encode())


def send_db_unavailable(handler_instance) -> None:
    """Send a 503 Service Unavailable response for database."""
    handler_instance.send_response(503)
    handler_instance.send_header('Content-type', 'application/json')
    handler_instance.end_headers()
    handler_instance.wfile.write(json.dumps({'error': 'Database not available'}).encode())


def send_forbidden(handler_instance, message: str = 'Forbidden') -> None:
    """Send a 403 Forbidden response."""
    handler_instance.send_response(403)
    handler_instance.send_header('Content-type', 'application/json')
    handler_instance.end_headers()
    handler_instance.wfile.write(json.dumps({'error': message}).encode())


def send_setup_required(handler_instance, status: dict) -> None:
    """Send a 403 response indicating setup is required."""
    handler_instance.send_response(403)
    handler_instance.send_header('Content-type', 'application/json')
    handler_instance.end_headers()
    handler_instance.wfile.write(json.dumps({
        'error': 'Setup required',
        'message': 'Please complete tenant setup before using this feature',
        'setup_status': status
    }).encode())


def is_entrylab_only_route(path: str) -> bool:
    """Check if the path is an EntryLab-only route."""
    for route in ENTRYLAB_ONLY_ROUTES:
        if path == route or path.startswith(route + '/') or path.startswith(route + '?'):
            return True
    return False


def is_forex_saas_route(path: str) -> bool:
    """Check if the path is a Forex SaaS route (requires setup completion)."""
    for route in FOREX_SAAS_ROUTES:
        if path == route or path.startswith(route + '/') or path.startswith(route + '?'):
            return True
    return False


def is_entrylab_admin(handler_instance) -> bool:
    """
    Check if the current request is from an EntryLab admin.
    Uses the existing check_auth() which validates admin_session cookie.
    """
    return handler_instance.check_auth()


def determine_tenant_id(handler_instance) -> str:
    """
    Determine the tenant_id for the current request.
    
    - EntryLab admins (using admin_session cookie) -> 'entrylab'
    - Other authenticated users -> lookup from tenant_users or bootstrap
    - Unauthenticated -> None
    """
    if is_entrylab_admin(handler_instance):
        return 'entrylab'
    
    return None


def apply_route_checks(route: Route, handler_instance, db_available: bool) -> bool:
    """
    Apply middleware checks for a route before calling the handler.
    
    This function applies checks in the following order:
    1. Database availability (if db_required)
    2. Authentication (if auth_required)
    3. Tenant context determination
    4. EntryLab-only route check
    5. Forex SaaS route setup completion check
    
    Args:
        route: The matched Route with middleware flags
        handler_instance: The MyHTTPRequestHandler instance
        db_available: Current DATABASE_AVAILABLE flag value
    
    Returns:
        True if all checks pass and handler should be called
        False if a check failed and response was already sent
    """
    if route.db_required and not db_available:
        send_db_unavailable(handler_instance)
        return False
    
    if route.auth_required and not handler_instance.check_auth():
        send_unauthorized(handler_instance)
        return False
    
    path = handler_instance.path.split('?')[0]
    
    tenant_id = determine_tenant_id(handler_instance)
    handler_instance.tenant_id = tenant_id if tenant_id else 'entrylab'
    
    if is_entrylab_only_route(path):
        if tenant_id != 'entrylab':
            send_forbidden(handler_instance, 'This feature is only available for EntryLab')
            return False
    
    if is_forex_saas_route(path) and tenant_id and tenant_id != 'entrylab':
        from core.tenant_credentials import get_tenant_setup_status
        status = get_tenant_setup_status(tenant_id)
        if not status.get('is_complete', False):
            send_setup_required(handler_instance, status)
            return False
    
    return True
