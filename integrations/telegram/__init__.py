"""
Telegram integration module.

Contains webhook handlers for Telegram bots and Telethon user client.
"""

from .webhooks import handle_coupon_telegram_webhook, handle_forex_telegram_webhook
from .user_client import TelethonUserClient, get_client, remove_client
from .user_session import save_session, restore_session, delete_session
from .user_auth import send_verification_code, verify_code, verify_2fa
from .user_handlers import (
    handle_telethon_status,
    handle_telethon_send_code,
    handle_telethon_verify_code,
    handle_telethon_verify_2fa,
    handle_telethon_reconnect,
    handle_telethon_disconnect,
)

__all__ = [
    'handle_coupon_telegram_webhook',
    'handle_forex_telegram_webhook',
    'TelethonUserClient',
    'get_client',
    'remove_client',
    'save_session',
    'restore_session',
    'delete_session',
    'send_verification_code',
    'verify_code',
    'verify_2fa',
    'handle_telethon_status',
    'handle_telethon_send_code',
    'handle_telethon_verify_code',
    'handle_telethon_verify_2fa',
    'handle_telethon_reconnect',
    'handle_telethon_disconnect',
]
