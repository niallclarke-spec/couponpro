"""
Clerk JWT verification using networkless RS256 validation.
Uses CLERK_JWT_KEY (PEM public key) instead of runtime JWKS fetching.
"""
import jwt
from core.config import Config


def verify_clerk_jwt(token: str) -> dict | None:
    """
    Verify a Clerk JWT and return claims if valid.
    
    Uses the pre-configured CLERK_JWT_KEY (PEM public key) for networkless
    verification - no external API calls needed at runtime.
    
    Args:
        token: The JWT string from Authorization: Bearer header
        
    Returns:
        dict with 'sub' (clerk_user_id) and 'email' if valid
        None if invalid, expired, or not configured
    """
    public_key = Config.get_clerk_jwt_key()
    if not public_key:
        print("[CLERK] CLERK_JWT_KEY not configured - Clerk auth disabled")
        return None
    
    try:
        claims = jwt.decode(
            token,
            public_key,
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
        print("[CLERK] Token expired")
        return None
    except jwt.InvalidTokenError as e:
        print(f"[CLERK] Invalid token: {e}")
        return None
    except Exception as e:
        print(f"[CLERK] Unexpected error verifying JWT: {e}")
        return None
