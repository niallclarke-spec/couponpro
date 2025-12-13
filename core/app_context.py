"""
Application Context - Centralized container for application state and availability flags.

This module provides AppContext and create_app_context(), which are PURE:
- NO side effects at import time
- NO network calls
- NO webhook registration
- NO background threads
- NO database migrations

All side effects happen in bootstrap.start_app(ctx).
"""
import os
from dataclasses import dataclass
from typing import Optional

from core.config import Config


@dataclass
class AppContext:
    """
    Centralized application context holding availability flags and tokens.
    
    Services are accessed via their existing module singletons.
    This context ensures server.py uses ctx fields instead of module globals.
    """
    object_storage_available: bool = False
    telegram_bot_available: bool = False
    database_available: bool = False
    coupon_validator_available: bool = False
    forex_scheduler_available: bool = False
    stripe_available: bool = False
    
    coupon_bot_token: Optional[str] = None
    forex_bot_token: Optional[str] = None
    
    config: Optional[Config] = None


def create_app_context() -> AppContext:
    """
    Create the application context with availability flags and tokens.
    
    This is a PURE function:
    - NO imports of side-effect modules (telegram_bot, forex_scheduler, db, etc.)
    - NO network calls
    - NO webhook registration
    - NO background threads
    - NO database migrations
    
    All side effects are deferred to bootstrap.start_app(ctx).
    
    Returns:
        AppContext with availability flags set based on environment.
    """
    ctx = AppContext()
    
    ctx.coupon_bot_token = os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('TELEGRAM_BOT_TOKEN_TEST')
    
    is_replit = os.environ.get('REPL_ID') or os.environ.get('REPLIT')
    if is_replit:
        ctx.forex_bot_token = os.environ.get('ENTRYLAB_TEST_BOT')
    if not ctx.forex_bot_token:
        ctx.forex_bot_token = os.environ.get('FOREX_BOT_TOKEN')
    
    ctx.object_storage_available = bool(
        os.environ.get('SPACES_ACCESS_KEY') and os.environ.get('SPACES_SECRET_KEY')
    )
    
    ctx.telegram_bot_available = bool(ctx.coupon_bot_token)
    
    ctx.database_available = bool(
        os.environ.get('DATABASE_URL') or os.environ.get('DB_HOST')
    )
    
    ctx.coupon_validator_available = ctx.database_available
    
    ctx.forex_scheduler_available = bool(ctx.forex_bot_token) and ctx.database_available
    
    stripe_available = bool(
        os.environ.get('STRIPE_SECRET_KEY') or 
        os.environ.get('STRIPE_SECRET') or
        os.environ.get('TEST_STRIPE_SECRET') or
        os.environ.get('REPLIT_CONNECTORS_HOSTNAME')
    )
    ctx.stripe_available = stripe_available
    
    return ctx
