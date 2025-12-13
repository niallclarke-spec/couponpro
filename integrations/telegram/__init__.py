"""
Telegram integration module.

Contains webhook handlers for Telegram bots.
"""

from .webhooks import handle_coupon_telegram_webhook, handle_forex_telegram_webhook

__all__ = ['handle_coupon_telegram_webhook', 'handle_forex_telegram_webhook']
