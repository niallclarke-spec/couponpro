"""
Middleware for API routes.

Thin wrappers that apply auth and availability checks before calling handlers.
These wrappers call the EXISTING check_auth() and availability flags unchanged.
"""
import json
from typing import Callable, Any, Tuple, Optional

from api.routes import Route
from core.host_context import HostType
from core.logging import get_logger

logger = get_logger(__name__)


ENTRYLAB_ONLY_ROUTES = [
    '/api/campaigns', '/api/broadcast', '/api/bot-stats', '/api/bot-users',
    '/api/upload-template', '/api/delete-template', '/api/toggle-telegram-template', '/api/validate-coupon',
    '/api/broadcast-status', '/api/broadcast-jobs', '/api/user-activity', '/api/invalid-coupons',
    '/api/day-of-week-stats', '/api/retention-rates',
    '/api/tenants/map-user'
]

FOREX_SAAS_ROUTES = [
    '/api/forex-signals', '/api/forex-config', '/api/signal-bot/status', 
    '/api/forex-stats', '/api/forex-tp-config', '/api/signal-bot/signals',
    '/api/signal-bot/set-active', '/api/signal-bot/cancel-queue',
    '/api/forex/xauusd-sparkline'
]

# Webhook endpoints must NEVER be blocked by EntryLab-only or Forex SaaS gating
# These are called by external services (Telegram, Stripe) with no auth headers
WEBHOOK_EXEMPT_ROUTES = [
    '/api/telegram-webhook',
    '/api/forex-telegram-webhook',
    '/api/stripe/webhook'
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


def send_forbidden(handler_instance, message: str = 'Forbidden', gate_type: str = 'unknown') -> None:
    """Send a 403 Forbidden response with logging for debugging."""
    path = getattr(handler_instance, 'path', 'unknown').split('?')[0]
    tenant_id = getattr(handler_instance, 'tenant_id', None)
    logger.warning(f"403 Forbidden: path={path}, tenant_id={tenant_id}, gate={gate_type}, message={message}")
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


def send_no_tenant_mapping(handler_instance, clerk_user_id: str) -> None:
    """Send a 403 response when Clerk user has no tenant mapping."""
    handler_instance.send_response(403)
    handler_instance.send_header('Content-type', 'application/json')
    handler_instance.end_headers()
    handler_instance.wfile.write(json.dumps({
        'error': 'No tenant mapping',
        'message': 'Your account is not associated with any tenant. Please contact support.',
        'clerk_user_id': clerk_user_id
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


def is_webhook_exempt_route(path: str) -> bool:
    """
    Check if the path is a webhook endpoint that should be exempt from tenant gating.
    Webhooks are called by external services (Telegram, Stripe) with no browser context.
    """
    for route in WEBHOOK_EXEMPT_ROUTES:
        if path == route or path.startswith(route + '/') or path.startswith(route + '?'):
            return True
    return False


def is_entrylab_admin(handler_instance) -> bool:
    """
    Check if the current request is from an EntryLab admin.
    Uses the existing check_auth() which validates admin_session cookie.
    """
    return handler_instance.check_auth()


def determine_tenant_id(handler_instance) -> Tuple[Optional[str], Optional[str]]:
    """
    Determine the tenant_id for the current request.
    
    Supports admin impersonation: if an admin sends X-Impersonate-Tenant header,
    the request is scoped to that tenant instead of the admin's own tenant.
    
    Returns:
        Tuple of (tenant_id, error_reason):
        - ('entrylab', None) for admin auth (or impersonated tenant for admins)
        - (tenant_id, None) for mapped Clerk user  
        - (None, 'no_tenant_mapping') for valid Clerk but unmapped
        - (None, None) for unauthenticated
    """
    from auth.clerk_auth import get_auth_user_from_request, is_admin_email
    
    auth_user = get_auth_user_from_request(handler_instance)
    
    if auth_user:
        clerk_user_id = auth_user['clerk_user_id']
        user_email = auth_user.get('email') or handler_instance.headers.get('X-Clerk-User-Email', '')
        
        handler_instance.clerk_user_id = clerk_user_id
        handler_instance.clerk_email = user_email
        
        if is_admin_email(user_email):
            impersonate_tenant = handler_instance.headers.get('X-Impersonate-Tenant')
            if impersonate_tenant:
                impersonate_tenant = impersonate_tenant.strip()
                if impersonate_tenant:
                    logger.info(f"Admin impersonating tenant: {impersonate_tenant} (admin_email={user_email})")
                    handler_instance.is_impersonating = True
                    return (impersonate_tenant, None)
            return ('entrylab', None)
        else:
            impersonate_header = handler_instance.headers.get('X-Impersonate-Tenant')
            if impersonate_header:
                logger.warning(f"Non-admin attempted impersonation: {user_email} tried to impersonate {impersonate_header}")
        
        from core.tenant_credentials import get_tenant_for_user
        tenant_id = get_tenant_for_user(clerk_user_id)
        if tenant_id:
            return (tenant_id, None)
        else:
            return (None, 'no_tenant_mapping')
    
    if is_entrylab_admin(handler_instance):
        impersonate_tenant = handler_instance.headers.get('X-Impersonate-Tenant')
        if impersonate_tenant:
            impersonate_tenant = impersonate_tenant.strip()
            if impersonate_tenant:
                logger.info(f"Admin impersonating tenant (legacy auth): {impersonate_tenant}")
                handler_instance.is_impersonating = True
                return (impersonate_tenant, None)
        return ('entrylab', None)
    
    return (None, None)


def apply_route_checks(route: Route, handler_instance, db_available: bool, host_type: Optional[HostType] = None) -> bool:
    """
    Apply middleware checks for a route before calling the handler.
    
    This function applies checks in the following order:
    1. Database availability (if db_required)
    2. Tenant context determination (checks BOTH admin_session cookie AND Clerk JWT)
    3. Host-aware authentication:
       - HostType.DASH: any valid JWT (tenant mapping still applies)
       - HostType.ADMIN or None: requires admin email check (backwards compatible)
    4. EntryLab-only route check
    5. Forex SaaS route setup completion check
    
    Args:
        route: The matched Route with middleware flags
        handler_instance: The MyHTTPRequestHandler instance
        db_available: Current DATABASE_AVAILABLE flag value
        host_type: Optional host type for host-aware auth rules
    
    Returns:
        True if all checks pass and handler should be called
        False if a check failed and response was already sent
    """
    if route.db_required and not db_available:
        send_db_unavailable(handler_instance)
        return False
    
    path = handler_instance.path.split('?')[0]
    
    # Skip tenant checks for public endpoints and page routes
    skip_paths = ['/api/check-auth', '/api/config', '/login', '/admin', '/app', '/setup', '/coupon']
    if path in skip_paths or path.startswith('/campaign/'):
        return True
    
    # Skip tenant mapping requirement for onboarding endpoints (new users don't have mapping yet)
    is_onboarding_route = path.startswith('/api/onboarding/')
    
    tenant_id, error = determine_tenant_id(handler_instance)
    
    if error == 'no_tenant_mapping' and not is_onboarding_route:
        send_no_tenant_mapping(handler_instance, getattr(handler_instance, 'clerk_user_id', ''))
        return False
    
    # Host-aware authentication logic
    if host_type == HostType.DASH:
        # Dash subdomain: any authenticated user can access (tenant mapping already enforced above)
        if route.auth_required:
            if tenant_id is None and not is_onboarding_route:
                send_unauthorized(handler_instance)
                return False
            # For onboarding routes without tenant_id, verify JWT (header or cookie)
            if tenant_id is None and is_onboarding_route:
                from auth.clerk_auth import get_auth_user_from_request
                auth_user = get_auth_user_from_request(handler_instance)
                if not auth_user:
                    send_unauthorized(handler_instance)
                    return False
                handler_instance.clerk_user_id = auth_user['clerk_user_id']
                handler_instance.clerk_email = auth_user.get('email') or handler_instance.headers.get('X-Clerk-User-Email', '')
            handler_instance.tenant_id = tenant_id
        else:
            handler_instance.tenant_id = tenant_id if tenant_id else 'entrylab'
    elif host_type == HostType.ADMIN:
        # Admin subdomain: require both valid JWT AND admin email
        if route.auth_required:
            if tenant_id is None:
                send_unauthorized(handler_instance)
                return False
            # For admin host, verify admin email
            clerk_email = getattr(handler_instance, 'clerk_email', None)
            if clerk_email:
                from auth.clerk_auth import is_admin_email
                if not is_admin_email(clerk_email):
                    send_forbidden(handler_instance, 'Admin access required', gate_type='admin_host')
                    return False
            handler_instance.tenant_id = tenant_id
        else:
            handler_instance.tenant_id = tenant_id if tenant_id else 'entrylab'
    else:
        # Default host (None): keep existing behavior - admin email required for backwards compatibility
        if route.auth_required:
            if tenant_id is None:
                send_unauthorized(handler_instance)
                return False
            handler_instance.tenant_id = tenant_id
        else:
            handler_instance.tenant_id = tenant_id if tenant_id else 'entrylab'
    
    # Webhook endpoints are exempt from EntryLab-only and Forex SaaS gating
    # They are called by external services (Telegram, Stripe) with no browser context
    if is_webhook_exempt_route(path):
        return True
    
    if is_entrylab_only_route(path):
        if tenant_id != 'entrylab':
            send_forbidden(handler_instance, 'This feature is only available for EntryLab', gate_type='entrylab_only')
            return False
    
    if is_forex_saas_route(path) and tenant_id and tenant_id != 'entrylab':
        from core.tenant_credentials import get_tenant_setup_status
        status = get_tenant_setup_status(tenant_id)
        if not status.get('is_complete', False):
            send_setup_required(handler_instance, status)
            return False
    
    return True
