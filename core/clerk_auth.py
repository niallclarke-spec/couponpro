"""
Clerk JWT verification using JWKS URL for runtime key fetching.
Fetches public keys from Clerk's JWKS endpoint to verify JWTs.
"""
import jwt
from jwt import PyJWKClient
from core.config import Config
from core.logging import get_logger

logger = get_logger(__name__)

_jwks_client = None


def _get_jwks_client():
    """Get or create cached JWKS client."""
    global _jwks_client
    if _jwks_client is None:
        jwks_url = Config.get_clerk_jwks_url()
        if jwks_url:
            _jwks_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
    return _jwks_client


def verify_clerk_jwt(token: str) -> dict | None:
    """
    Verify a Clerk JWT and return claims if valid.
    
    Fetches the signing key from Clerk's JWKS endpoint at runtime.
    Keys are cached for 1 hour to minimize network calls.
    
    Args:
        token: The JWT string from Authorization: Bearer header
        
    Returns:
        dict with 'sub' (clerk_user_id) and 'email' if valid
        None if invalid, expired, or not configured
    """
    jwks_url = Config.get_clerk_jwks_url()
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
        return {
            'sub': claims['sub'],
            'email': claims.get('email')
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
