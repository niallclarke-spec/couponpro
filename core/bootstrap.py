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


def _register_webhooks_from_db():
    """
    Register Telegram webhooks for all bot connections stored in the database.
    
    This replaces the legacy hardcoded webhook setup. The connections system
    (tenant_bot_connections table) is the single source of truth for webhook URLs.
    On each server start, we re-register webhooks to ensure they're correctly
    configured with the right allowed_updates.
    """
    import requests
    
    try:
        import db
        if not db.db_pool or not db.db_pool.connection_pool:
            logger.warning("Webhook registration skipped: database pool not available")
            return
        
        with db.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tenant_id, bot_role, bot_token, bot_username, webhook_url
                FROM tenant_bot_connections
                WHERE webhook_url IS NOT NULL AND bot_token IS NOT NULL
                ORDER BY tenant_id, bot_role
            """)
            connections = cursor.fetchall()
        
        if not connections:
            logger.info("Webhook registration: no bot connections found in database")
            return
        
        registered = 0
        for tenant_id, bot_role, bot_token, bot_username, webhook_url in connections:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
                response = requests.post(url, json={
                    'url': webhook_url,
                    'allowed_updates': ['message', 'chat_member']
                }, timeout=10)
                result = response.json()
                
                if result.get('ok'):
                    logger.info(f"Webhook registered: tenant={tenant_id}, role={bot_role}, bot=@{bot_username}, url={webhook_url}")
                    registered += 1
                else:
                    logger.warning(f"Webhook registration failed: tenant={tenant_id}, role={bot_role}: {result.get('description')}")
            except Exception as e:
                logger.warning(f"Webhook registration error: tenant={tenant_id}, role={bot_role}: {e}")
        
        logger.info(f"Webhook registration complete: {registered}/{len(connections)} registered")
    
    except Exception as e:
        logger.exception(f"Webhook registration from DB failed: {e}")


def start_app(ctx: AppContext) -> None:
    """
    Start the application with ALL side effects.
    
    This function is IDEMPOTENT - calling it multiple times has no effect
    after the first call (protected by _started flag).
    
    Side effects performed:
    1. Import and initialize database module (runs schema migrations)
    2. Import and start Telegram coupon bot webhook
    3. Register Telegram webhooks from DB (connections system is source of truth)
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
    
    if ctx.database_available:
        _register_webhooks_from_db()
    
    if ctx.database_available:
        try:
            from core.leader import acquire_scheduler_leader_lock, start_leader_retry_loop, start_scheduler_once
            
            def _do_start_all_workers():
                """Start all background workers - called via start_scheduler_once() on leader only"""
                if ctx.forex_scheduler_available:
                    from workers.scheduler import start_forex_scheduler
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

                try:
                    from domains.journeys.scheduler import start_journey_scheduler
                    start_journey_scheduler(interval_seconds=10)
                    logger.info("Journey scheduler started")
                except Exception as e:
                    logger.exception("Journey scheduler startup failed")

                try:
                    from scheduler.crosspromo_worker import start_worker_thread
                    start_worker_thread()
                    logger.info("Cross promo worker started")
                except Exception as e:
                    logger.exception("Cross promo worker startup failed")

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
            
            if acquire_scheduler_leader_lock():
                logger.info("Leader lock acquired, starting all workers")
                start_scheduler_once(_do_start_all_workers)
            else:
                logger.info("Leader lock not acquired, waiting for leader to terminate")
                start_leader_retry_loop(_do_start_all_workers)
        except Exception as e:
            logger.exception("Worker startup failed")
    
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
    
    logger.info("Application started")
