"""
OpenAI client integration for AI-powered features.
Centralizes OpenAI client creation and AI message generation.
NO side effects at import time.
"""
import os
from typing import Optional
from openai import OpenAI


_client: Optional[OpenAI] = None


def get_openai_client() -> Optional[OpenAI]:
    """
    Get or create the shared OpenAI client.
    Uses Replit AI Integrations environment variables.
    
    Returns:
        OpenAI client instance or None if not configured
    """
    global _client
    
    if _client is not None:
        return _client
    
    api_key = os.environ.get('AI_INTEGRATIONS_OPENAI_API_KEY')
    base_url = os.environ.get('AI_INTEGRATIONS_OPENAI_BASE_URL')
    
    if not api_key:
        return None
    
    try:
        _client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        return _client
    except Exception as e:
        print(f"[OPENAI] Failed to create client: {e}")
        return None


def reset_client():
    """Reset the cached client (useful for testing)"""
    global _client
    _client = None
