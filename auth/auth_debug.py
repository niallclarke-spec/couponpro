"""
Auth debug ring buffer for tracking authentication failures.

Stores sanitized auth failure records in memory for diagnostics.
Does NOT store raw tokens, cookies, or secrets.
"""
from collections import deque
from datetime import datetime
from typing import Dict, Any, List, Optional
import threading

_failure_buffer: deque = deque(maxlen=50)
_buffer_lock = threading.Lock()


class AuthFailureReason:
    """Enumeration of auth failure reason codes."""
    MISSING_AUTH_HEADER = 'missing_auth_header'
    MALFORMED_BEARER = 'malformed_bearer'
    JWKS_NOT_CONFIGURED = 'jwks_not_configured'
    JWKS_FETCH_FAILED = 'jwks_fetch_failed'
    INVALID_SIGNATURE = 'invalid_signature'
    TOKEN_EXPIRED = 'token_expired'
    INVALID_ISSUER = 'invalid_issuer'
    INVALID_AUDIENCE = 'invalid_audience'
    MISSING_CLAIMS = 'missing_claims'
    COOKIE_PARSE_FAILED = 'cookie_parse_failed'
    UNKNOWN_ERROR = 'unknown_error'


def record_auth_failure(
    reason: str,
    path: str,
    host: Optional[str] = None,
    host_type: Optional[str] = None,
    token_source: Optional[str] = None,
    tenant_id: Optional[str] = None,
    clerk_user_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Record an auth failure to the ring buffer.
    
    Args:
        reason: One of AuthFailureReason codes
        path: Request path (e.g., /api/check-auth)
        host: Host header value
        host_type: Resolved host type (admin, client, default)
        token_source: Where token came from (bearer, cookie, none)
        tenant_id: Extracted tenant_id if any
        clerk_user_id: Extracted clerk_user_id if any
        extra: Additional context (no secrets!)
        
    Returns:
        The recorded failure dict
    """
    record = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'reason': reason,
        'path': path,
        'host': host,
        'host_type': host_type,
        'token_source': token_source,
        'tenant_id': tenant_id,
        'clerk_user_id': clerk_user_id,
    }
    if extra:
        record['extra'] = extra
    
    with _buffer_lock:
        _failure_buffer.append(record)
    
    return record


def get_recent_failures(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get recent auth failures from the ring buffer.
    
    Args:
        limit: Max number of records to return (default 50)
        
    Returns:
        List of failure records, newest first
    """
    with _buffer_lock:
        records = list(_failure_buffer)
    
    records.reverse()
    return records[:limit]


def clear_failures() -> int:
    """
    Clear all failures from the buffer.
    
    Returns:
        Number of records cleared
    """
    with _buffer_lock:
        count = len(_failure_buffer)
        _failure_buffer.clear()
    return count


def get_failure_count() -> int:
    """Get current count of failures in buffer."""
    with _buffer_lock:
        return len(_failure_buffer)
