"""
Clerk JWT verification and authentication functions.

Provides JWT verification using JWKS, request authentication helpers,
and role-based access control. Does NOT call DB on import - all DB
lookups happen inside request handler functions.
"""
import os
import re
import jwt
from jwt import PyJWKClient
from http import cookies
from typing import Optional, Dict, Any

from core.logging import get_logger

logger = get_logger(__name__)

_jwks_client = None


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.status_code = status_code


class AuthorizationError(Exception):
    """Raised when user lacks required permissions."""
    def __init__(self, message: str, status_code: int = 403):
        super().__init__(message)
        self.status_code = status_code


def _get_clerk_jwks_url() -> Optional[str]:
    """Get Clerk JWKS URL from environment."""
    return os.environ.get('CLERK_JWKS_URL')


def _get_jwks_client() -> Optional[PyJWKClient]:
    """Get or create cached JWKS client."""
    global _jwks_client
    if _jwks_client is None:
        jwks_url = _get_clerk_jwks_url()
        if jwks_url:
            _jwks_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
    return _jwks_client


def verify_clerk_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a Clerk JWT and return claims if valid.
    
    Fetches the signing key from Clerk's JWKS endpoint at runtime.
    Keys are cached for 1 hour to minimize network calls.
    
    Args:
        token: The JWT string from Authorization: Bearer header or __session cookie
        
    Returns:
        dict with clerk user claims if valid:
        {
            'clerk_user_id': str,
            'email': str | None,
            'name': str | None,
            'avatar_url': str | None
        }
        None if invalid, expired, or not configured
    """
    jwks_url = _get_clerk_jwks_url()
    if not jwks_url:
        logger.warning("CLERK_JWKS_URL not configured - Clerk auth disabled")
        return None
    
    try:
        client = _get_jwks_client()
        if not client:
            logger.error("Failed to create JWKS client")
            return None
        
        signing_key = client.get_signing_key_from_jwt(token)
        
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=['RS256'],
            options={
                'require': ['sub', 'exp', 'iat'],
                'verify_exp': True,
                'verify_iat': True
            }
        )
        
        first_name = claims.get('first_name', '')
        last_name = claims.get('last_name', '')
        name = f"{first_name} {last_name}".strip() if first_name or last_name else claims.get('name')
        
        email = claims.get('email')
        if not email and claims.get('email_addresses'):
            email = claims.get('email_addresses', [{}])[0].get('email_address')
        
        return {
            'clerk_user_id': claims['sub'],
            'email': email,
            'name': name,
            'avatar_url': claims.get('image_url') or claims.get('profile_image_url')
        }
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return None
    except Exception as e:
        logger.exception("Unexpected error verifying JWT")
        return None


def get_auth_user_from_request(request) -> Optional[Dict[str, Any]]:
    """
    Extract and verify Clerk token from request.
    
    Checks Authorization header first (Bearer token), then falls back
    to __session cookie.
    
    Args:
        request: HTTP request handler with headers attribute
        
    Returns:
        Normalized user dict if authenticated:
        {
            'clerk_user_id': str,
            'email': str | None,
            'name': str | None,
            'avatar_url': str | None
        }
        None if not authenticated
    """
    token = None
    token_source = None
    
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        token_source = 'bearer'
        logger.debug("Auth: Found Bearer token in Authorization header")
    
    if not token:
        cookie_header = request.headers.get('Cookie', '')
        if cookie_header:
            c = cookies.SimpleCookie()
            try:
                c.load(cookie_header)
                if '__session' in c:
                    token = c['__session'].value
                    token_source = 'cookie'
                    logger.debug("Auth: Found token in __session cookie")
            except Exception as e:
                logger.debug(f"Failed to parse cookies: {e}")
    
    if not token:
        logger.debug("Auth: No token found (checked Authorization header and __session cookie)")
        return None
    
    result = verify_clerk_token(token)
    if result:
        logger.debug(f"Auth: Token verified successfully (source={token_source}, email={result.get('email')})")
    else:
        logger.debug(f"Auth: Token verification failed (source={token_source})")
    
    return result


def require_auth(request) -> Dict[str, Any]:
    """
    Require authenticated user or raise AuthenticationError.
    
    Args:
        request: HTTP request handler
        
    Returns:
        Authenticated user dict
        
    Raises:
        AuthenticationError: If not authenticated (401)
    """
    auth_user = get_auth_user_from_request(request)
    if not auth_user:
        raise AuthenticationError("Authentication required", 401)
    return auth_user


def get_admin_emails() -> set:
    """
    Get set of allowed admin emails from environment.
    
    Reads ADMIN_EMAILS env var (comma-separated) and always includes
    the primary admin email.
    
    Returns:
        Set of lowercase admin email addresses
    """
    admin_emails = {'niallclarkefs@gmail.com'}
    
    env_emails = os.environ.get('ADMIN_EMAILS', '')
    if env_emails:
        for email in env_emails.split(','):
            email = email.strip().lower()
            if email and '@' in email:
                admin_emails.add(email)
    
    return admin_emails


def is_admin_email(email: str) -> bool:
    """
    Check if email is an allowed admin email.
    
    Args:
        email: Email address to check
        
    Returns:
        True if email is in admin list, False otherwise
    """
    if not email:
        return False
    return email.lower().strip() in get_admin_emails()


def require_admin(request) -> Dict[str, Any]:
    """
    Require admin role or raise AuthorizationError.
    
    First authenticates the user, then verifies their email is in the
    allowed admin list, then looks up their role in the database.
    
    Args:
        request: HTTP request handler
        
    Returns:
        Authenticated admin user dict with role='admin'
        
    Raises:
        AuthenticationError: If not authenticated (401)
        AuthorizationError: If not admin (403)
    """
    auth_user = require_auth(request)
    
    email = auth_user.get('email') or ''
    if not is_admin_email(email):
        logger.warning(f"Admin access denied for email: {email}")
        raise AuthorizationError("Admin access required", 403)
    
    import db as db_module
    user_row = db_module.get_user_by_clerk_id(auth_user['clerk_user_id'])
    
    if not user_row or user_row.get('role') != 'admin':
        raise AuthorizationError("Admin access required", 403)
    
    auth_user['role'] = 'admin'
    auth_user['tenant_id'] = user_row.get('tenant_id')
    return auth_user


def get_effective_tenant_id(user_dict: Dict[str, Any]) -> Optional[str]:
    """
    Get effective tenant_id for database operations.
    
    For clients: returns their assigned tenant_id
    For admins: returns None (can access all tenants)
    
    Compatible with existing tenant_conn() and ENABLE_RLS support.
    
    Args:
        user_dict: User dict from auth functions, must include 'clerk_user_id'
        
    Returns:
        tenant_id string for clients, None for admins
    """
    import db as db_module
    
    clerk_user_id = user_dict.get('clerk_user_id') or ''
    user_row = db_module.get_user_by_clerk_id(clerk_user_id)
    if not user_row:
        return None
    
    if user_row.get('role') == 'admin':
        return None
    
    return user_row.get('tenant_id')


def generate_tenant_id(email: str) -> str:
    """
    Generate deterministic tenant_id from email.
    
    Uses slugified email local part (before @). If result is empty
    or too short, uses hash of full email.
    
    Args:
        email: User's email address
        
    Returns:
        Tenant ID string
    """
    if not email or '@' not in email:
        import hashlib
        return hashlib.sha256(email.encode()).hexdigest()[:12]
    
    local_part = email.split('@')[0]
    slug = re.sub(r'[^a-z0-9]', '', local_part.lower())
    
    if len(slug) < 3:
        import hashlib
        return hashlib.sha256(email.encode()).hexdigest()[:12]
    
    return slug[:50]
