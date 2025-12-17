"""
Clerk JWT verification and authentication functions.

Provides JWT verification using JWKS, request authentication helpers,
and role-based access control. Does NOT call DB on import - all DB
lookups happen inside request handler functions.

JWKS URL is derived dynamically from the token's issuer (iss) claim,
NOT from any hardcoded environment variable. This ensures the correct
JWKS endpoint is used regardless of environment.

Also provides admin_session cookie verification for legacy/fallback auth.
"""
import os
import re
import jwt
import hmac
import hashlib
import time
import base64
import json
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError
from http import cookies
from typing import Optional, Dict, Any, Tuple, Set
from datetime import datetime
from threading import Lock

from core.logging import get_logger
from core.config import Config
from auth.auth_debug import record_auth_failure, AuthFailureReason

logger = get_logger(__name__)

SESSION_TTL = 86400

_jwks_clients: Dict[str, PyJWKClient] = {}
_jwks_clients_lock = Lock()
_jwks_last_refresh: Dict[str, datetime] = {}
_jwks_key_counts: Dict[str, int] = {}


def create_admin_session() -> str:
    """
    Create an HMAC-signed admin session token.
    
    Returns:
        Signed token string in format "{expiry}.{signature}"
        
    Raises:
        ValueError: If ADMIN_PASSWORD not configured
    """
    expiry = int(time.time()) + SESSION_TTL
    secret = Config.get_admin_password()
    if not secret:
        raise ValueError("ADMIN_PASSWORD required")
    sig = hmac.new(secret.encode(), str(expiry).encode(), hashlib.sha256).hexdigest()
    return f"{expiry}.{sig}"


def verify_admin_session(token: str) -> bool:
    """
    Verify an HMAC-signed admin session token.
    
    Args:
        token: The token string from admin_session cookie
        
    Returns:
        True if valid and not expired, False otherwise
    """
    try:
        if not token or '.' not in token:
            return False
        payload, sig = token.rsplit('.', 1)
        if time.time() > int(payload):
            return False
        secret = Config.get_admin_password()
        if not secret:
            return False
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


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


def _get_allowed_issuers() -> Optional[Set[str]]:
    """
    Get optional allowlist of Clerk issuers from environment.
    
    If CLERK_ALLOWED_ISSUERS is set, only tokens from these issuers
    will be accepted. This prevents accepting tokens from arbitrary
    issuers in production.
    
    Returns:
        Set of allowed issuer URLs (normalized), or None if not configured
    """
    allowed = os.environ.get('CLERK_ALLOWED_ISSUERS', '').strip()
    if not allowed:
        return None
    
    issuers = set()
    for issuer in allowed.split(','):
        issuer = issuer.strip().rstrip('/')
        if issuer:
            issuers.add(issuer)
    
    return issuers if issuers else None


def _decode_jwt_unverified(token: str) -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    Decode JWT without verification to inspect header and payload.
    
    This is safe because we use this only to extract the issuer,
    then verify the token against that issuer's JWKS.
    
    Returns:
        Tuple of (header, payload) or (None, None) on error
    """
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None, None
        
        def decode_part(part: str) -> Dict:
            padding = 4 - len(part) % 4
            if padding != 4:
                part += '=' * padding
            decoded = base64.urlsafe_b64decode(part)
            return json.loads(decoded)
        
        header = decode_part(parts[0])
        payload = decode_part(parts[1])
        return header, payload
    except Exception:
        return None, None


def _derive_jwks_url(issuer: str) -> str:
    """
    Derive JWKS URL from issuer.
    
    Args:
        issuer: The issuer URL from token's iss claim
        
    Returns:
        JWKS URL (e.g., https://clerk.promostack.io/.well-known/jwks.json)
    """
    return issuer.rstrip('/') + '/.well-known/jwks.json'


def _get_jwks_client_for_issuer(issuer: str, force_refresh: bool = False) -> PyJWKClient:
    """
    Get or create JWKS client for a specific issuer.
    
    Clients are cached per issuer. Thread-safe.
    
    Args:
        issuer: The token's issuer URL
        force_refresh: If True, recreate client to fetch fresh keys
        
    Returns:
        PyJWKClient instance for this issuer
    """
    global _jwks_clients, _jwks_last_refresh, _jwks_key_counts
    
    normalized_issuer = issuer.rstrip('/')
    jwks_url = _derive_jwks_url(normalized_issuer)
    
    with _jwks_clients_lock:
        if normalized_issuer not in _jwks_clients or force_refresh:
            logger.info(f"[JWKS] Creating client for issuer: {normalized_issuer} (force_refresh={force_refresh})")
            logger.info(f"[JWKS] JWKS URL derived from token issuer: {jwks_url}")
            
            client = PyJWKClient(jwks_url, cache_keys=True, lifespan=1800)
            _jwks_clients[normalized_issuer] = client
            _jwks_last_refresh[normalized_issuer] = datetime.utcnow()
            
            try:
                keys = client.get_signing_keys()
                _jwks_key_counts[normalized_issuer] = len(keys) if keys else 0
                logger.info(f"[JWKS] Fetched {_jwks_key_counts[normalized_issuer]} signing keys for {normalized_issuer}")
            except Exception as e:
                logger.warning(f"[JWKS] Could not pre-fetch keys for {normalized_issuer}: {e}")
                _jwks_key_counts[normalized_issuer] = 0
        
        return _jwks_clients[normalized_issuer]


def get_jwks_status() -> Dict[str, Any]:
    """
    Get current JWKS client status for debugging.
    
    Returns:
        Dict with cached issuers, their JWKS URLs, last refresh times, and key counts
    """
    allowed = _get_allowed_issuers()
    
    with _jwks_clients_lock:
        issuers_info = {}
        for issuer in _jwks_clients:
            issuers_info[issuer] = {
                'jwks_url': _derive_jwks_url(issuer),
                'last_refresh': _jwks_last_refresh.get(issuer, datetime.min).isoformat() + 'Z',
                'key_count': _jwks_key_counts.get(issuer, 0)
            }
        
        return {
            'mode': 'dynamic_issuer_derived',
            'allowed_issuers': list(allowed) if allowed else None,
            'cached_issuers': issuers_info,
            'total_cached_clients': len(_jwks_clients)
        }


def prefetch_jwks() -> bool:
    """
    Log startup status for issuer-derived JWKS mode.
    
    With dynamic issuer detection, we can't prefetch because we don't
    know which issuer will be used until we see a token. This function
    just logs the configuration status.
    
    Returns:
        True (always ready in dynamic mode)
    """
    allowed = _get_allowed_issuers()
    
    if allowed:
        logger.info(f"[JWKS] Dynamic issuer mode ENABLED with allowlist: {', '.join(allowed)}")
    else:
        logger.info("[JWKS] Dynamic issuer mode ENABLED (no allowlist - accepting any issuer)")
        logger.warning("[JWKS] Consider setting CLERK_ALLOWED_ISSUERS for production security")
    
    logger.info("[JWKS] JWKS URL will be derived from each token's issuer claim")
    return True


def verify_clerk_token(token: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Verify a Clerk JWT and return claims if valid.
    
    JWKS URL is derived dynamically from the token's issuer (iss) claim.
    Keys are cached per issuer for 30 minutes. On kid mismatch, refreshes
    JWKS once and retries.
    
    Args:
        token: The JWT string from Authorization: Bearer header or __session cookie
        
    Returns:
        Tuple of (user_dict, failure_reason):
        - (user_dict, None) if valid
        - (None, failure_reason) if invalid
        
        user_dict contains:
        {
            'clerk_user_id': str,
            'email': str | None,
            'name': str | None,
            'avatar_url': str | None
        }
    """
    header, unverified_payload = _decode_jwt_unverified(token)
    if not header or not unverified_payload:
        logger.warning("[JWKS] Could not decode token header/payload")
        return None, AuthFailureReason.INVALID_SIGNATURE
    
    token_kid = header.get('kid')
    token_iss = unverified_payload.get('iss')
    
    if not token_iss:
        logger.error("[JWKS] Token missing 'iss' claim - cannot derive JWKS URL")
        return None, AuthFailureReason.MISSING_CLAIMS
    
    if not token_kid:
        logger.warning("[JWKS] Token missing 'kid' in header")
        return None, AuthFailureReason.INVALID_SIGNATURE
    
    normalized_issuer = token_iss.rstrip('/')
    jwks_url = _derive_jwks_url(normalized_issuer)
    
    allowed_issuers = _get_allowed_issuers()
    if allowed_issuers and normalized_issuer not in allowed_issuers:
        logger.error(
            f"[JWKS] ISSUER NOT IN ALLOWLIST! token_iss={token_iss}, "
            f"allowed={list(allowed_issuers)}"
        )
        return None, AuthFailureReason.INVALID_ISSUER
    
    def try_verify(force_refresh: bool = False) -> Tuple[Optional[Dict], Optional[str]]:
        try:
            client = _get_jwks_client_for_issuer(normalized_issuer, force_refresh=force_refresh)
            signing_key = client.get_signing_key_from_jwt(token)
            
            decode_options = {
                'require': ['sub', 'exp', 'iat'],
                'verify_exp': True,
                'verify_iat': True
            }
            
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=['RS256'],
                issuer=normalized_issuer,
                options=decode_options
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
            }, None
            
        except PyJWKClientError as e:
            error_msg = str(e)
            if 'Unable to find a signing key' in error_msg and not force_refresh:
                logger.warning(
                    f"[JWKS] Key not found (kid={token_kid}), refreshing JWKS and retrying... "
                    f"issuer={normalized_issuer}, jwks_url={jwks_url}"
                )
                return None, 'RETRY_WITH_REFRESH'
            
            logger.warning(
                f"[JWKS] Fetch failed: {e} | kid={token_kid} | issuer={normalized_issuer} | "
                f"jwks_url={jwks_url}"
            )
            return None, AuthFailureReason.JWKS_FETCH_FAILED
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None, AuthFailureReason.TOKEN_EXPIRED
        except jwt.InvalidIssuerError:
            logger.warning(f"[JWKS] Invalid issuer during verification: token_iss={token_iss}")
            return None, AuthFailureReason.INVALID_ISSUER
        except jwt.InvalidAudienceError:
            logger.warning("Invalid audience")
            return None, AuthFailureReason.INVALID_AUDIENCE
        except jwt.MissingRequiredClaimError as e:
            logger.warning(f"Missing required claim: {e}")
            return None, AuthFailureReason.MISSING_CLAIMS
        except jwt.InvalidSignatureError:
            logger.warning("Invalid signature")
            return None, AuthFailureReason.INVALID_SIGNATURE
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None, AuthFailureReason.INVALID_SIGNATURE
        except Exception as e:
            logger.exception("Unexpected error verifying JWT")
            return None, AuthFailureReason.UNKNOWN_ERROR
    
    result, failure = try_verify(force_refresh=False)
    
    if failure == 'RETRY_WITH_REFRESH':
        logger.info("[JWKS] Retrying verification with refreshed keys...")
        result, failure = try_verify(force_refresh=True)
        if failure:
            logger.error(
                f"[JWKS] Verification still failed after refresh. kid={token_kid}, "
                f"issuer={normalized_issuer}, jwks_url={jwks_url}"
            )
    
    return result, failure


def get_auth_user_from_request(request, record_failure: bool = True) -> Optional[Dict[str, Any]]:
    """
    Extract and verify authentication from request.
    
    Checks in order:
    1. Authorization: Bearer header (Clerk JWT)
    2. __session cookie (Clerk session cookie)
    3. admin_session cookie (HMAC-signed legacy/fallback auth)
    
    Records auth failures to ring buffer for diagnostics.
    
    Args:
        request: HTTP request handler with headers attribute
        record_failure: Whether to record failures to debug buffer (default True)
        
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
    path = getattr(request, 'path', 'unknown')
    host = request.headers.get('Host', 'unknown')
    
    token = None
    token_source = None
    jwt_failure_reason = None
    admin_session_token = None
    
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        token_source = 'bearer'
        logger.debug("Auth: Found Bearer token in Authorization header")
    elif auth_header and not auth_header.startswith('Bearer '):
        jwt_failure_reason = AuthFailureReason.MALFORMED_BEARER
        token_source = 'bearer_malformed'
    
    cookie_header = request.headers.get('Cookie', '')
    parsed_cookies = None
    if cookie_header:
        parsed_cookies = cookies.SimpleCookie()
        try:
            parsed_cookies.load(cookie_header)
        except Exception as e:
            logger.debug(f"Failed to parse cookies: {e}")
            parsed_cookies = None
    
    if not token and parsed_cookies:
        if '__session' in parsed_cookies:
            token = parsed_cookies['__session'].value
            token_source = 'cookie'
            logger.debug("Auth: Found token in __session cookie")
    
    if parsed_cookies and 'admin_session' in parsed_cookies:
        admin_session_token = parsed_cookies['admin_session'].value
    
    if token:
        result, verify_failure = verify_clerk_token(token)
        if result:
            logger.debug(f"Auth: Token verified successfully (source={token_source}, email={result.get('email')})")
            return result
        jwt_failure_reason = verify_failure
    
    if admin_session_token and verify_admin_session(admin_session_token):
        email = request.headers.get('X-Clerk-User-Email', '')
        logger.debug(f"Auth: admin_session cookie verified successfully (email={email})")
        return {
            'clerk_user_id': 'admin_session',
            'email': email if email else None,
            'name': 'Admin',
            'avatar_url': None
        }
    
    if not token and not admin_session_token:
        failure_reason = AuthFailureReason.MISSING_AUTH_HEADER
        token_source = 'none'
    else:
        failure_reason = jwt_failure_reason or AuthFailureReason.ADMIN_SESSION_INVALID
        if admin_session_token and not token:
            token_source = 'admin_session'
    
    if record_failure and failure_reason:
        logger.warning(f"Auth failure: reason={failure_reason} path={path} host={host} source={token_source}")
        record_auth_failure(
            reason=failure_reason,
            path=path,
            host=host,
            token_source=token_source
        )
    
    return None


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
