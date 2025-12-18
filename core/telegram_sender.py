"""
Telegram Send Infrastructure - Production-grade, tenant-isolated message sending.

This module provides the ONLY authorized way to send Telegram messages.
All sends go through _send_message() which:
1. Resolves fresh credentials from DB (with short TTL cache)
2. Constructs a short-lived telegram.Bot per send
3. Handles failures gracefully with crisp logging
4. Never falls back to a default bot - missing credentials = fail fast

Architecture:
- _resolve_bot_connection(tenant_id, bot_role) -> connection dict with token, channel_id, etc.
- _send_message(tenant_id, bot_role, chat_id, text, ...) -> sends message using fresh credentials
- TTL cache (60s) prevents DB hammering during bursts while ensuring near-instant token updates
- send_message_sync() - sync wrapper for use in non-async contexts (e.g., scheduler, engine)
"""
import asyncio
import time
import threading
from dataclasses import dataclass
from typing import Optional, Dict, Any
from telegram import Bot
from telegram.error import TelegramError

from core.logging import get_logger
from core.bot_credentials import get_bot_credentials, BotNotConfiguredError, SIGNAL_BOT, MESSAGE_BOT

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 60


@dataclass
class BotConnection:
    """Resolved bot connection with all required fields for sending."""
    tenant_id: str
    bot_role: str
    token: str
    channel_id: Optional[str]
    bot_username: Optional[str]
    vip_channel_id: Optional[str]
    free_channel_id: Optional[str]
    resolved_at: float
    
    def is_expired(self) -> bool:
        """Check if this cached connection has expired."""
        return (time.time() - self.resolved_at) > CACHE_TTL_SECONDS
    
    def mask_token(self) -> str:
        """Return masked token for logging (never log full tokens)."""
        if not self.token:
            return "None"
        parts = self.token.split(':')
        if len(parts) == 2:
            return f"{parts[0]}:****"
        return "****"


class ConnectionCache:
    """Thread-safe TTL cache for bot connections."""
    
    def __init__(self):
        self._cache: Dict[str, BotConnection] = {}
        self._lock = threading.Lock()
    
    def _cache_key(self, tenant_id: str, bot_role: str) -> str:
        return f"{tenant_id}:{bot_role}"
    
    def get(self, tenant_id: str, bot_role: str) -> Optional[BotConnection]:
        """Get cached connection if valid (not expired)."""
        key = self._cache_key(tenant_id, bot_role)
        with self._lock:
            conn = self._cache.get(key)
            if conn and not conn.is_expired():
                return conn
            if conn and conn.is_expired():
                del self._cache[key]
            return None
    
    def set(self, connection: BotConnection) -> None:
        """Cache a resolved connection."""
        key = self._cache_key(connection.tenant_id, connection.bot_role)
        with self._lock:
            self._cache[key] = connection
    
    def invalidate(self, tenant_id: str, bot_role: str) -> None:
        """Explicitly invalidate a cached connection (e.g., after token update)."""
        key = self._cache_key(tenant_id, bot_role)
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.info(f"Cache invalidated: tenant={tenant_id}, role={bot_role}")
    
    def clear(self) -> None:
        """Clear all cached connections."""
        with self._lock:
            self._cache.clear()


_connection_cache = ConnectionCache()


def _resolve_bot_connection(tenant_id: str, bot_role: str, force_refresh: bool = False) -> BotConnection:
    """
    Resolve bot connection from database with TTL caching.
    
    Args:
        tenant_id: Tenant ID (required, no defaults)
        bot_role: Bot role ('signal_bot' or 'message_bot')
        force_refresh: Skip cache and fetch fresh from DB
        
    Returns:
        BotConnection with all required fields
        
    Raises:
        BotNotConfiguredError: If no connection found for tenant/role
    """
    if not tenant_id:
        raise ValueError("tenant_id is required - no implicit tenant inference allowed")
    
    if not force_refresh:
        cached = _connection_cache.get(tenant_id, bot_role)
        if cached:
            logger.debug(
                f"Cache hit: tenant={tenant_id}, role={bot_role}, "
                f"bot={cached.bot_username}, age={time.time() - cached.resolved_at:.1f}s"
            )
            return cached
    
    creds = get_bot_credentials(tenant_id, bot_role)
    
    if not creds.get('bot_token'):
        logger.error(
            f"SEND BLOCKED: No token configured for tenant={tenant_id}, role={bot_role}. "
            f"Configure bot in Connections settings."
        )
        raise BotNotConfiguredError(tenant_id, bot_role)
    
    connection = BotConnection(
        tenant_id=tenant_id,
        bot_role=bot_role,
        token=creds['bot_token'],
        channel_id=creds.get('channel_id'),
        bot_username=creds.get('bot_username'),
        vip_channel_id=creds.get('vip_channel_id'),
        free_channel_id=creds.get('free_channel_id'),
        resolved_at=time.time()
    )
    
    _connection_cache.set(connection)
    
    if bot_role == 'signal_bot':
        logger.info(
            f"Connection resolved: tenant={tenant_id}, role={bot_role}, "
            f"bot={connection.bot_username}, token={connection.mask_token()}, "
            f"vip_channel={connection.vip_channel_id}, free_channel={connection.free_channel_id}"
        )
    else:
        logger.info(
            f"Connection resolved: tenant={tenant_id}, role={bot_role}, "
            f"bot={connection.bot_username}, token={connection.mask_token()}, "
            f"channel={connection.channel_id}"
        )
    
    return connection


def invalidate_connection_cache(tenant_id: str, bot_role: str) -> None:
    """
    Explicitly invalidate cached connection after token update.
    Call this from Connections API when credentials are updated.
    """
    _connection_cache.invalidate(tenant_id, bot_role)


@dataclass
class SendResult:
    """Result of a send operation."""
    success: bool
    message_id: Optional[int] = None
    error: Optional[str] = None
    error_code: Optional[int] = None


async def send_message(
    tenant_id: str,
    bot_role: str,
    chat_id: str,
    text: str,
    parse_mode: str = 'HTML',
    reply_to_message_id: Optional[int] = None,
    disable_notification: bool = False
) -> SendResult:
    """
    Send a Telegram message using fresh credentials.
    
    This is the SINGLE entrypoint for all Telegram sends.
    Creates a short-lived Bot instance per send - no caching.
    
    Args:
        tenant_id: Tenant ID (required)
        bot_role: 'signal_bot' or 'message_bot'
        chat_id: Target chat/channel ID
        text: Message text
        parse_mode: 'HTML' or 'Markdown'
        reply_to_message_id: Optional message to reply to
        disable_notification: Send silently
        
    Returns:
        SendResult with success status, message_id if sent, error details if failed
    """
    try:
        connection = _resolve_bot_connection(tenant_id, bot_role)
    except BotNotConfiguredError as e:
        logger.error(
            f"SEND FAILED: {e} | "
            f"tenant={tenant_id}, role={bot_role}, chat={chat_id}"
        )
        return SendResult(success=False, error=str(e))
    except Exception as e:
        logger.exception(
            f"SEND FAILED: Unexpected error resolving credentials | "
            f"tenant={tenant_id}, role={bot_role}, error={e}"
        )
        return SendResult(success=False, error=f"Credential resolution error: {e}")
    
    try:
        bot = Bot(token=connection.token)
        
        sent = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_to_message_id=reply_to_message_id,
            disable_notification=disable_notification
        )
        
        logger.info(
            f"SEND OK: tenant={tenant_id}, role={bot_role}, "
            f"bot={connection.bot_username}, chat={chat_id}, msg_id={sent.message_id}"
        )
        
        return SendResult(success=True, message_id=sent.message_id)
        
    except TelegramError as e:
        logger.error(
            f"SEND FAILED: Telegram API error | "
            f"tenant={tenant_id}, role={bot_role}, bot={connection.bot_username}, "
            f"chat={chat_id}, error={e.message}"
        )
        return SendResult(
            success=False, 
            error=e.message,
            error_code=getattr(e, 'error_code', None)
        )
    except Exception as e:
        logger.exception(
            f"SEND FAILED: Unexpected error | "
            f"tenant={tenant_id}, role={bot_role}, chat={chat_id}, error={e}"
        )
        return SendResult(success=False, error=str(e))


def send_message_sync(
    tenant_id: str,
    chat_id: int,
    text: str,
    bot_role: str = 'message_bot',
    parse_mode: str = 'HTML'
) -> bool:
    """
    Synchronous wrapper for send_message - for use in non-async contexts.
    
    This is the canonical way to send messages from sync code like the
    journey scheduler and engine. Uses asyncio.run() internally.
    
    Args:
        tenant_id: Tenant ID (required)
        chat_id: Telegram chat ID
        text: Message text
        bot_role: Bot role, defaults to 'message_bot'
        parse_mode: 'HTML' or 'Markdown'
        
    Returns:
        True if sent successfully, False otherwise
    """
    try:
        result = asyncio.run(send_message(
            tenant_id=tenant_id,
            bot_role=bot_role,
            chat_id=str(chat_id),
            text=text,
            parse_mode=parse_mode
        ))
        return result.success
    except Exception as e:
        logger.exception(f"send_message_sync failed: tenant={tenant_id}, chat={chat_id}, error={e}")
        return False


async def send_to_channel(
    tenant_id: str,
    bot_role: str,
    text: str,
    parse_mode: str = 'HTML',
    channel_type: str = 'default'
) -> SendResult:
    """
    Send message to the configured channel for a bot.
    
    Args:
        tenant_id: Tenant ID
        bot_role: 'signal_bot' or 'message_bot'
        text: Message text
        parse_mode: 'HTML' or 'Markdown'
        channel_type: 'default', 'vip', or 'free' (for signal_bot)
        
    Returns:
        SendResult
    """
    try:
        connection = _resolve_bot_connection(tenant_id, bot_role)
    except BotNotConfiguredError as e:
        return SendResult(success=False, error=str(e))
    
    if channel_type == 'vip':
        chat_id = connection.vip_channel_id
    elif channel_type == 'free':
        chat_id = connection.free_channel_id
    else:
        chat_id = connection.channel_id
    
    if not chat_id:
        error = f"No {channel_type} channel configured for tenant={tenant_id}, role={bot_role}"
        logger.error(f"SEND BLOCKED: {error}")
        return SendResult(success=False, error=error)
    
    return await send_message(
        tenant_id=tenant_id,
        bot_role=bot_role,
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode
    )


async def copy_message(
    tenant_id: str,
    bot_role: str,
    from_chat_id: str,
    to_chat_id: str,
    message_id: int
) -> SendResult:
    """
    Copy a message from one chat to another (no attribution).
    
    Args:
        tenant_id: Tenant ID
        bot_role: Bot role
        from_chat_id: Source chat ID
        to_chat_id: Destination chat ID
        message_id: Message to copy
        
    Returns:
        SendResult
    """
    try:
        connection = _resolve_bot_connection(tenant_id, bot_role)
    except BotNotConfiguredError as e:
        return SendResult(success=False, error=str(e))
    
    try:
        bot = Bot(token=connection.token)
        
        result = await bot.copy_message(
            chat_id=to_chat_id,
            from_chat_id=from_chat_id,
            message_id=message_id
        )
        
        logger.info(
            f"COPY OK: tenant={tenant_id}, role={bot_role}, "
            f"from={from_chat_id}, to={to_chat_id}, msg={message_id}"
        )
        
        return SendResult(success=True, message_id=result.message_id)
        
    except TelegramError as e:
        logger.error(
            f"COPY FAILED: Telegram API error | "
            f"tenant={tenant_id}, role={bot_role}, error={e.message}"
        )
        return SendResult(success=False, error=e.message)


async def validate_bot_credentials(tenant_id: str, bot_role: str) -> Dict[str, Any]:
    """
    Validate bot credentials by calling Telegram API (dry-run).
    
    Calls getMe() to validate token and optionally getChat() for channel.
    
    Args:
        tenant_id: Tenant ID
        bot_role: Bot role
        
    Returns:
        Dict with validation results:
        {
            'ok': bool,
            'bot_username': str or None,
            'bot_id': int or None,
            'channel_valid': bool or None,
            'channel_title': str or None,
            'error': str or None
        }
    """
    result = {
        'ok': False,
        'bot_username': None,
        'bot_id': None,
        'channel_valid': None,
        'channel_title': None,
        'error': None
    }
    
    try:
        connection = _resolve_bot_connection(tenant_id, bot_role, force_refresh=True)
    except BotNotConfiguredError as e:
        result['error'] = str(e)
        return result
    
    try:
        bot = Bot(token=connection.token)
        me = await bot.get_me()
        
        result['bot_username'] = f"@{me.username}"
        result['bot_id'] = me.id
        result['ok'] = True
        
        if connection.channel_id:
            try:
                chat = await bot.get_chat(connection.channel_id)
                result['channel_valid'] = True
                result['channel_title'] = chat.title or chat.username or str(chat.id)
            except TelegramError as e:
                result['channel_valid'] = False
                result['error'] = f"Channel error: {e.message}"
                result['ok'] = False
        
        logger.info(
            f"VALIDATE OK: tenant={tenant_id}, role={bot_role}, "
            f"bot={result['bot_username']}, channel_ok={result['channel_valid']}"
        )
        
    except TelegramError as e:
        result['error'] = f"Bot token invalid: {e.message}"
        logger.error(
            f"VALIDATE FAILED: tenant={tenant_id}, role={bot_role}, error={e.message}"
        )
    
    return result


def get_connection_for_send(tenant_id: str, bot_role: str) -> Optional[BotConnection]:
    """
    Get resolved connection for inspection (e.g., to check channel_id before send).
    Does NOT create a Bot instance.
    
    Returns None if credentials not configured.
    """
    try:
        return _resolve_bot_connection(tenant_id, bot_role)
    except BotNotConfiguredError:
        return None


def resolve_signal_bot_connection(tenant_id: str, force_refresh: bool = False) -> BotConnection:
    """
    Resolve signal bot connection for a tenant.
    
    This is the canonical way to get signal bot credentials including both
    VIP and FREE channel IDs. Uses TTL cache for efficiency.
    
    Args:
        tenant_id: Tenant ID (required)
        force_refresh: Skip cache and fetch fresh from DB
        
    Returns:
        BotConnection with token, vip_channel_id, free_channel_id, bot_username
        
    Raises:
        BotNotConfiguredError: If signal bot not configured for tenant
    """
    return _resolve_bot_connection(tenant_id, SIGNAL_BOT, force_refresh=force_refresh)


def get_signal_channel_id(connection: BotConnection, channel_type: str) -> Optional[str]:
    """
    Get specific channel ID from a signal bot connection.
    
    Separates "what is the connection?" from "which channel are we using?"
    
    Args:
        connection: Resolved BotConnection
        channel_type: 'vip' or 'free'
        
    Returns:
        Channel ID string, or None if not configured
        
    Raises:
        ValueError: If channel_type is not 'vip' or 'free'
    """
    if channel_type == 'vip':
        return connection.vip_channel_id
    elif channel_type == 'free':
        return connection.free_channel_id
    else:
        raise ValueError(f"Invalid channel_type '{channel_type}'. Must be 'vip' or 'free'.")
