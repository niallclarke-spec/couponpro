"""
DEPRECATED: Clerk JWT verification module.

This module is deprecated. All Clerk JWT verification should use
auth/clerk_auth.py instead, which implements dynamic issuer-derived
JWKS URL verification.

This file exists for backward compatibility and redirects to the
new implementation.
"""
from auth.clerk_auth import verify_clerk_token

from core.logging import get_logger

logger = get_logger(__name__)


def verify_clerk_jwt(token: str) -> dict | None:
    """
    DEPRECATED: Use auth.clerk_auth.verify_clerk_token instead.
    
    This is a thin wrapper that calls the new implementation.
    
    Args:
        token: The JWT string from Authorization: Bearer header
        
    Returns:
        dict with 'sub' (clerk_user_id) and 'email' if valid
        None if invalid, expired, or not configured
    """
    logger.warning("core.clerk_auth.verify_clerk_jwt is deprecated, use auth.clerk_auth.verify_clerk_token")
    
    result, failure = verify_clerk_token(token)
    if result:
        return {
            'sub': result.get('clerk_user_id'),
            'email': result.get('email')
        }
    return None
