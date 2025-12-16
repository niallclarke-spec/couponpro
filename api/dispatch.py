"""
Centralized request dispatcher for the HTTP API.

Provides a single entry point for routing requests through the route table
and applying middleware checks.
"""
from typing import List
from urllib.parse import urlparse

from api.routes import Route, match_route
from api.middleware import apply_route_checks
from core.host_context import HostContext

from core.logging import get_logger
logger = get_logger(__name__)


def dispatch_request(handler, method: str, path: str, routes: List[Route], 
                     host_context: HostContext, db_available: bool) -> bool:
    """
    Dispatch a request through the routing table.
    
    This function:
    1. Normalizes trailing slashes (redirect /api/foo/ to /api/foo)
    2. Matches the route
    3. If no match: returns False (caller falls back to static files)
    4. If match: applies route checks (auth, db requirements)
    5. If middleware denies: returns True (response already sent)
    6. Otherwise: calls the handler method and returns True
    
    Args:
        handler: The MyHTTPRequestHandler instance
        method: HTTP method ('GET', 'POST', 'PUT', 'DELETE')
        path: The URL path (without query string)
        routes: List of Route objects to match against
        host_context: Parsed host context for routing decisions
        db_available: Whether database is available
        
    Returns:
        True if request was handled (even if error response sent)
        False if no route matched (caller should fall back to static files or 404)
    """
    parsed_path = urlparse(path)
    clean_path = parsed_path.path
    
    if method == 'GET' and clean_path.startswith('/api/') and clean_path.endswith('/') and len(clean_path) > 5:
        normalized = clean_path.rstrip('/')
        query = parsed_path.query
        if query:
            normalized += '?' + query
        handler.send_response(301)
        handler.send_header('Location', normalized)
        handler.end_headers()
        return True
    
    route = match_route(method, clean_path, routes)
    if not route:
        return False
    
    if not apply_route_checks(route, handler, db_available, host_context.host_type):
        return True
    
    handler_method = getattr(handler, route.handler, None)
    if handler_method:
        handler_method()
        return True
    
    logger.warning(f"Handler method not found: {route.handler}")
    return False
