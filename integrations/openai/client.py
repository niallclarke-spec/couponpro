"""
OpenAI client integration for AI-powered features.
Centralizes OpenAI client creation and AI message generation.
NO side effects at import time.

BEHAVIOR: Matches original forex_ai.py exactly:
- Uses AI_INTEGRATIONS_OPENAI_API_KEY and AI_INTEGRATIONS_OPENAI_BASE_URL
- Always creates client (even if env vars missing) - fails at call time, not creation
"""
import os
from openai import OpenAI


_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    """
    Get or create the shared OpenAI client.
    
    Uses EXACT same env vars as original forex_ai.py:
    - AI_INTEGRATIONS_OPENAI_API_KEY
    - AI_INTEGRATIONS_OPENAI_BASE_URL
    
    BEHAVIOR: Always returns a client. If env vars are missing, the client
    is still created but will fail at call time (matching original behavior).
    
    Returns:
        OpenAI client instance
    """
    global _client
    
    if _client is not None:
        return _client
    
    # EXACT same env vars as original forex_ai.py
    api_key = os.environ.get('AI_INTEGRATIONS_OPENAI_API_KEY')
    base_url = os.environ.get('AI_INTEGRATIONS_OPENAI_BASE_URL')
    
    # Create client regardless of env var presence (matches original behavior)
    # If api_key is None, OpenAI client will fail at call time, not here
    _client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )
    return _client


def reset_client():
    """Reset the cached client (useful for testing)"""
    global _client
    _client = None
