"""
Telegram Bot API client for sending messages and copying/forwarding content.
Reusable across all tenant bots via BotCredentialResolver.
"""
import requests
from typing import Optional, Dict, Any
from core.logging import get_logger

logger = get_logger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


def send_message(
    bot_token: str,
    chat_id: str,
    text: str,
    parse_mode: Optional[str] = None,
    disable_web_page_preview: bool = True
) -> Dict[str, Any]:
    """
    Send a text message to a chat/channel.
    
    Args:
        bot_token: The bot's API token
        chat_id: Target chat/channel ID
        text: Message text
        parse_mode: Optional 'HTML' or 'Markdown'
        disable_web_page_preview: Disable link previews
        
    Returns:
        dict with 'success' bool and 'response' or 'error'
    """
    url = f"{TELEGRAM_API_BASE}{bot_token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": disable_web_page_preview,
    }
    
    if parse_mode:
        payload["parse_mode"] = parse_mode
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        data = response.json()
        
        if data.get("ok"):
            logger.info(f"Message sent to {chat_id}")
            return {"success": True, "response": data}
        else:
            error = data.get("description", "Unknown error")
            logger.warning(f"Failed to send message: {error}")
            return {"success": False, "error": error}
            
    except requests.RequestException as e:
        logger.exception(f"Request error sending message: {e}")
        return {"success": False, "error": str(e)}


def copy_message(
    bot_token: str,
    from_chat_id: str,
    to_chat_id: str,
    message_id: int
) -> Dict[str, Any]:
    """
    Copy a message from one chat to another (no 'Forwarded from' header).
    Preferred over forwardMessage for cleaner appearance.
    
    Args:
        bot_token: The bot's API token
        from_chat_id: Source chat/channel ID
        to_chat_id: Destination chat/channel ID
        message_id: ID of the message to copy
        
    Returns:
        dict with 'success' bool and 'response' or 'error'
    """
    url = f"{TELEGRAM_API_BASE}{bot_token}/copyMessage"
    
    payload = {
        "chat_id": to_chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        data = response.json()
        
        if data.get("ok"):
            logger.info(f"Message {message_id} copied from {from_chat_id} to {to_chat_id}")
            return {"success": True, "response": data}
        else:
            error = data.get("description", "Unknown error")
            logger.warning(f"copyMessage failed: {error}, trying forwardMessage")
            return forward_message(bot_token, from_chat_id, to_chat_id, message_id)
            
    except requests.RequestException as e:
        logger.exception(f"Request error copying message: {e}")
        return forward_message(bot_token, from_chat_id, to_chat_id, message_id)


def forward_message(
    bot_token: str,
    from_chat_id: str,
    to_chat_id: str,
    message_id: int
) -> Dict[str, Any]:
    """
    Forward a message from one chat to another (shows 'Forwarded from' header).
    Fallback when copyMessage is not available.
    
    Args:
        bot_token: The bot's API token
        from_chat_id: Source chat/channel ID
        to_chat_id: Destination chat/channel ID
        message_id: ID of the message to forward
        
    Returns:
        dict with 'success' bool and 'response' or 'error'
    """
    url = f"{TELEGRAM_API_BASE}{bot_token}/forwardMessage"
    
    payload = {
        "chat_id": to_chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        data = response.json()
        
        if data.get("ok"):
            logger.info(f"Message {message_id} forwarded from {from_chat_id} to {to_chat_id}")
            return {"success": True, "response": data}
        else:
            error = data.get("description", "Unknown error")
            logger.warning(f"Failed to forward message: {error}")
            return {"success": False, "error": error}
            
    except requests.RequestException as e:
        logger.exception(f"Request error forwarding message: {e}")
        return {"success": False, "error": str(e)}
