"""
Journey triggers - parsing and detection logic.
"""
from typing import Optional, Tuple
from core.logging import get_logger

logger = get_logger(__name__)


def parse_telegram_deeplink(text: str) -> Optional[str]:
    """
    Parse a Telegram deep link /start command and extract the parameter.
    
    Args:
        text: The message text (e.g., "/start broker_access")
        
    Returns:
        The start parameter if present, None otherwise
    """
    if not text:
        return None
    
    text = text.strip()
    
    if not text.startswith('/start'):
        return None
    
    parts = text.split(maxsplit=1)
    
    if len(parts) < 2:
        return None
    
    param = parts[1].strip()
    return param if param else None


def is_journey_trigger(text: str) -> Tuple[bool, Optional[str]]:
    """
    Check if a message could be a journey trigger.
    
    Args:
        text: The message text
        
    Returns:
        Tuple of (is_trigger, start_param)
    """
    param = parse_telegram_deeplink(text)
    if param:
        return (True, param)
    return (False, None)
