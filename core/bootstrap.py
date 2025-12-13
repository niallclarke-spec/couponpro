"""
Application Bootstrap - Start the application with all side effects.

This module contains start_app(ctx) which is the ONLY place that:
- Imports side-effect modules (telegram_bot, forex_scheduler, db, etc.)
- Runs database migrations
- Registers Telegram webhooks
- Starts scheduler threads

All deferred imports happen here to avoid import-time side effects.
"""
import os
import threading
import asyncio

from core.app_context import AppContext

_started = False


def start_app(ctx: AppContext) -> None:
    """
    Start the application with ALL side effects.
    
    This function is IDEMPOTENT - calling it multiple times has no effect
    after the first call (protected by _started flag).
    
    Side effects performed:
    1. Import and initialize database module (runs schema migrations)
    2. Import and start Telegram coupon bot webhook
    3. Import and set up Forex bot webhook
    4. Import and start Forex scheduler in background thread
    5. Initialize Stripe client
    
    Args:
        ctx: The AppContext created by create_app_context()
    """
    global _started
    
    if _started:
        print("[BOOTSTRAP] Already started, skipping")
        return
    
    _started = True
    print("[BOOTSTRAP] Starting application...")
    
    if ctx.database_available:
        try:
            import db
            schema_ok = db.db_pool.initialize_schema()
            if schema_ok:
                print("[BOOTSTRAP] Database schema initialized")
                ctx.database_available = True
            else:
                print("[BOOTSTRAP] Database schema initialization failed")
                ctx.database_available = False
                ctx.forex_scheduler_available = False
        except Exception as e:
            print(f"[BOOTSTRAP] Database import failed: {e}")
            ctx.database_available = False
            ctx.forex_scheduler_available = False
    
    if ctx.telegram_bot_available and ctx.coupon_bot_token:
        try:
            import telegram_bot
            print("[BOOTSTRAP] Initializing coupon bot webhook...")
            telegram_bot.start_webhook_bot(ctx.coupon_bot_token)
            print("[BOOTSTRAP] Coupon bot webhook started")
        except Exception as e:
            print(f"[BOOTSTRAP] Coupon bot startup failed: {e}")
            import traceback
            traceback.print_exc()
    
    if ctx.telegram_bot_available and ctx.forex_bot_token:
        try:
            import telegram_bot
            webhook_url = "https://dash.promostack.io/api/forex-telegram-webhook"
            success = telegram_bot.setup_forex_webhook(ctx.forex_bot_token, webhook_url)
            if success:
                print(f"[BOOTSTRAP] Forex bot webhook configured: {webhook_url}")
            else:
                print("[BOOTSTRAP] Forex bot webhook setup failed")
        except Exception as e:
            print(f"[BOOTSTRAP] Forex bot webhook error: {e}")
    
    if ctx.forex_scheduler_available:
        try:
            from forex_scheduler import start_forex_scheduler
            
            def run_forex_scheduler():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(start_forex_scheduler())
                except Exception as e:
                    print(f"[BOOTSTRAP] Scheduler error: {e}")
                    import traceback
                    traceback.print_exc()
            
            scheduler_thread = threading.Thread(target=run_forex_scheduler, daemon=True)
            scheduler_thread.start()
            print("[BOOTSTRAP] Forex scheduler started in background thread")
        except Exception as e:
            print(f"[BOOTSTRAP] Forex scheduler startup failed: {e}")
            import traceback
            traceback.print_exc()
    
    if ctx.stripe_available:
        try:
            from stripe_client import get_stripe_client
            get_stripe_client()
            print("[BOOTSTRAP] Stripe client initialized")
        except Exception as e:
            print(f"[BOOTSTRAP] Stripe initialization failed: {e}")
            ctx.stripe_available = False
    
    print("[BOOTSTRAP] Application started")
