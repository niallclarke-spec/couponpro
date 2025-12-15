"""
Host context detection for dual-subdomain architecture.

Determines host_type (admin, dash, default) from the Host header.
Admin subdomain requires ADMIN_EMAILS, Dash subdomain accepts any valid JWT.
"""
from enum import Enum
from typing import NamedTuple, Optional


class HostType(Enum):
    ADMIN = "admin"
    DASH = "dash"
    DEFAULT = "default"


class HostContext(NamedTuple):
    host_type: HostType
    canonical_domain: str
    is_dev: bool


def parse_host_context(host_header: str) -> HostContext:
    """
    Parse the Host header to determine routing context.
    
    Args:
        host_header: The Host header value (e.g., 'admin.promostack.io:443')
        
    Returns:
        HostContext with host_type, canonical_domain, and is_dev flag
    """
    host = host_header.lower().strip()
    
    host_without_port = host.split(':')[0] if ':' in host else host
    
    is_dev = any(pattern in host for pattern in [
        'localhost',
        '127.0.0.1',
        'replit',
        '.repl.co',
        '.replit.dev',
        '.replit.app'
    ])
    
    if host_without_port.startswith('admin.'):
        return HostContext(
            host_type=HostType.ADMIN,
            canonical_domain=host_without_port,
            is_dev=is_dev
        )
    elif host_without_port.startswith('dash.'):
        return HostContext(
            host_type=HostType.DASH,
            canonical_domain=host_without_port,
            is_dev=is_dev
        )
    else:
        return HostContext(
            host_type=HostType.DEFAULT,
            canonical_domain=host_without_port,
            is_dev=is_dev
        )


def get_redirect_for_host(host_context: HostContext, is_authenticated: bool, is_admin: bool) -> Optional[str]:
    """
    Determine redirect path based on host and auth state.
    
    Args:
        host_context: Parsed host context
        is_authenticated: Whether user has valid JWT
        is_admin: Whether user email is in ADMIN_EMAILS
        
    Returns:
        Redirect path or None if no redirect needed
    """
    if host_context.host_type == HostType.ADMIN:
        if is_authenticated and is_admin:
            return '/admin'
        else:
            return '/login'
    elif host_context.host_type == HostType.DASH:
        if is_authenticated:
            return '/app'
        else:
            return '/login'
    else:
        return '/login'
