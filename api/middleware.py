"""
Middleware for API routes.

Thin wrappers that apply auth and availability checks before calling handlers.
These wrappers call the EXISTING check_auth() and availability flags unchanged.
"""
import json
from typing import Callable, Any

from api.routes import Route


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


def apply_route_checks(route: Route, handler_instance, db_available: bool) -> bool:
    """
    Apply middleware checks for a route before calling the handler.
    
    This function applies checks in the same order as the original if/elif chain:
    1. Database availability (if db_required)
    2. Authentication (if auth_required)
    
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
    
    return True
