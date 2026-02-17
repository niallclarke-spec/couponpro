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
from core.logging import configure_logging, get_logger

_started = False

logger = get_logger(__name__)


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
    
    configure_logging()
    
    if _started:
        logger.debug("Already started, skipping")
        return
    
    _started = True
    logger.info("Starting application...")
    
    if ctx.database_available:
        try:
            import db
            schema_ok = db.db_pool.initialize_schema()
            if schema_ok:
                logger.info("Database schema initialized")
                ctx.database_available = True
            else:
                logger.error("Database schema initialization failed")
                ctx.database_available = False
                ctx.forex_scheduler_available = False
        except Exception as e:
            logger.exception("Database import failed")
            ctx.database_available = False
            ctx.forex_scheduler_available = False
    
    if ctx.telegram_bot_available and ctx.coupon_bot_token:
        try:
            import telegram_bot
            logger.info("Initializing coupon bot webhook...")
            telegram_bot.start_webhook_bot(ctx.coupon_bot_token)
            logger.info("Coupon bot webhook started")
        except Exception as e:
            logger.exception("Coupon bot startup failed")
    
    if ctx.telegram_bot_available and ctx.forex_bot_token:
        try:
            import telegram_bot
            webhook_url = "https://dash.promostack.io/api/forex-telegram-webhook"
            success = telegram_bot.setup_forex_webhook(ctx.forex_bot_token, webhook_url)
            if success:
                logger.info(f"Forex bot webhook configured: {webhook_url}")
            else:
                logger.warning("Forex bot webhook setup failed")
        except Exception as e:
            logger.exception("Forex bot webhook error")
    
    if ctx.forex_scheduler_available:
        try:
            from core.leader import acquire_scheduler_leader_lock, start_leader_retry_loop, start_scheduler_once
            from workers.scheduler import start_forex_scheduler
            
            def _do_start_scheduler():
                """Actual scheduler startup - called via start_scheduler_once()"""
                def run_forex_scheduler():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(start_forex_scheduler())
                    except Exception as e:
                        logger.exception("Scheduler error")
                
                scheduler_thread = threading.Thread(target=run_forex_scheduler, daemon=True)
                scheduler_thread.start()
                logger.info("Forex scheduler started in background thread")
            
            if acquire_scheduler_leader_lock():
                logger.info("Leader lock acquired, starting scheduler")
                start_scheduler_once(_do_start_scheduler)
            else:
                logger.info("Leader lock not acquired, waiting for leader to terminate")
                start_leader_retry_loop(_do_start_scheduler)
        except Exception as e:
            logger.exception("Forex scheduler startup failed")
    
    try:
        from auth.clerk_auth import prefetch_jwks
        prefetch_jwks()
        logger.info("Clerk JWKS prefetch complete")
    except Exception as e:
        logger.warning(f"Clerk JWKS prefetch failed: {e}")
    
    if ctx.stripe_available:
        try:
            from stripe_client import get_stripe_client
            get_stripe_client()
            logger.info("Stripe client initialized")
        except Exception as e:
            logger.exception("Stripe initialization failed")
            ctx.stripe_available = False
    
    if ctx.database_available:
        try:
            from domains.journeys.scheduler import start_journey_scheduler
            start_journey_scheduler(interval_seconds=30)
            logger.info("Journey scheduler started")
        except Exception as e:
            logger.exception("Journey scheduler startup failed")
        
        try:
            from scheduler.crosspromo_worker import start_worker_thread
            start_worker_thread()
            logger.info("Cross promo worker started")
        except Exception as e:
            logger.exception("Cross promo worker startup failed")
        
        import os
        telethon_auto_connect = os.environ.get('TELETHON_AUTO_CONNECT', 'true').lower()
        if telethon_auto_connect == 'false':
            logger.info("Telethon auto-connect disabled (TELETHON_AUTO_CONNECT=false)")
        else:
            try:
                from integrations.telegram.user_client import get_client
                from integrations.telegram.user_listener import start_listener_sync
                tc = get_client('entrylab')
                connected = tc.is_connected() or tc.connect_sync()
                if connected:
                    start_listener_sync('entrylab')
                    logger.info("Telethon listener started for entrylab")
                else:
                    logger.info(f"Telethon client not ready (status={tc.status}), listener skipped")
            except Exception as e:
                logger.warning(f"Telethon listener startup skipped: {e}")
    
    logger.info("Application started")
