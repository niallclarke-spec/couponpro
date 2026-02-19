"""
Forex Signals Scheduler - CLI Entrypoint

Thin CLI wrapper that wires together TenantRuntime and scheduler modules.
Handles CLI argument parsing and main loop orchestration.
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime

from core.logging import get_logger
from core.runtime import require_tenant_runtime, TenantRuntime
from core.alerts import notify_error
from scheduler import SignalGenerator, SignalMonitor, Messenger
from forex_ai import generate_daily_recap, generate_weekly_recap, generate_detailed_daily_recap
from domains.crosspromo.service import build_morning_news_message

logger = get_logger(__name__)


def check_db_pool_ready() -> bool:
    """
    Check if database pool is ready for operations.
    
    Returns:
        True if pool is initialized and reachable, False otherwise.
    """
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        return True
    
    try:
        import db as db_module
        if not db_module.db_pool or not db_module.db_pool.connection_pool:
            return False
        
        with db_module.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True
    except Exception:
        return False


def require_db_pool_or_exit():
    """
    Verify database pool is ready, exit non-zero if DATABASE_URL is set but pool fails.
    
    This is a fail-fast check at startup to prevent running scheduler logic
    without a working database connection.
    """
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        return
    
    try:
        import db as db_module
        if not db_module.db_pool or not db_module.db_pool.connection_pool:
            print("FATAL: DATABASE_URL is set but database pool initialization failed", file=sys.stderr)
            sys.exit(1)
        
        with db_module.db_pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        logger.debug("Database pool connectivity verified")
    except Exception as e:
        debug_mode = os.environ.get('DEBUG', '').lower() in ('1', 'true')
        if debug_mode:
            logger.exception(f"Database pool verification failed: {e}")
        print(f"FATAL: DATABASE_URL is set but database connection failed: {e}", file=sys.stderr)
        sys.exit(1)

# Scheduler timing constants (in seconds)
SIGNAL_CHECK_INTERVAL = 900      # 15 minutes - check for new signals
MONITOR_INTERVAL = 5             # 5 seconds - monitor active signals for TP/SL

STAGNANT_CHECK_INTERVAL = 300    # 5 minutes - check stagnant signals for revalidation
SCHEDULED_CHECK_INTERVAL = 60   # 1 minute - check briefings, recaps, crosspromo


class ForexSchedulerRunner:
    """
    Orchestrates the forex scheduler using TenantRuntime and modular components.
    
    This is a thin orchestration layer that:
    - Initializes runtime and modules
    - Runs the main scheduling loop
    - Delegates actual work to generator, monitor, messenger
    """
    
    def __init__(self, runtime: TenantRuntime):
        self.runtime = runtime
        self.tenant_id = runtime.tenant_id
        
        # Initialize modules
        self.messenger = Messenger(runtime)
        self.generator = SignalGenerator(runtime, self.messenger)
        self.monitor = SignalMonitor(runtime, self.messenger)
        
        # Timing
        self.signal_check_interval = SIGNAL_CHECK_INTERVAL
        self.monitor_interval = MONITOR_INTERVAL
    
    async def check_morning_briefing(self):
        """Post morning briefing at 6:20 AM UTC with news and market levels (weekdays only)"""
        try:
            now = datetime.utcnow()
            current_date_str = now.date().isoformat()
            
            # Skip weekends - markets are closed
            if now.weekday() >= 5:  # Saturday=5, Sunday=6
                return
            
            if now.hour == 6 and 20 <= now.minute < 25:
                db = self.runtime.db
                last_posted = db.get_last_recap_date('morning_briefing', tenant_id=self.tenant_id)
                
                if last_posted != current_date_str:
                    logger.info("Generating morning briefing with Alpha Vantage news...")
                    
                    news_message = build_morning_news_message(self.tenant_id)
                    
                    bot = self.runtime.get_telegram_bot()
                    await bot.post_morning_briefing(ai_message=news_message)
                    db.set_last_recap_date('morning_briefing', current_date_str, tenant_id=self.tenant_id)
                    logger.info("✅ Morning briefing posted with news")
        
        except Exception as e:
            logger.error(f"❌ Error posting morning briefing: {e}")
    
    async def check_daily_recap(self):
        """Post daily recap at 6:30 AM UTC (yesterday's signals, weekdays only)
        
        Skip conditions:
        - Weekend (no trading on Sat/Sun)
        - 0 signals yesterday (nothing to recap)
        - Net pips <= 0 (only show profitable days)
        - Recap generation failed (retry next cycle)
        """
        try:
            now = datetime.utcnow()
            current_date_str = now.date().isoformat()
            
            # Skip weekends - no trading on Sat/Sun
            if now.weekday() >= 5:  # Saturday=5, Sunday=6
                return
            
            if now.hour == 6 and 30 <= now.minute < 35:
                db = self.runtime.db
                last_posted = db.get_last_recap_date('daily', tenant_id=self.tenant_id)
                
                if last_posted != current_date_str:
                    logger.info("Generating detailed daily recap for yesterday...")
                    
                    recap_result = generate_detailed_daily_recap(
                        tenant_id=self.tenant_id, 
                        period='yesterday'
                    )
                    
                    if not recap_result or not isinstance(recap_result, dict):
                        logger.error("❌ Daily recap generation returned invalid result, will retry")
                        return
                    
                    if recap_result.get('error'):
                        logger.error(f"❌ Daily recap generation failed: {recap_result.get('error')}, will retry")
                        return
                    
                    stats = recap_result.get('stats', {})
                    total_signals = stats.get('total_signals', 0)
                    wins = stats.get('wins', 0)
                    total_pips = stats.get('total_pips', 0)
                    win_rate = (wins / total_signals * 100) if total_signals > 0 else 0
                    
                    if total_signals == 0:
                        logger.info("⏭️ Skipping daily recap: no signals yesterday")
                        db.set_last_recap_date('daily', current_date_str, tenant_id=self.tenant_id)
                        return
                    
                    # Only post recap if day was profitable (net positive pips)
                    if total_pips <= 0:
                        logger.info(f"⏭️ Skipping daily recap: net pips {total_pips:+.1f} <= 0")
                        db.set_last_recap_date('daily', current_date_str, tenant_id=self.tenant_id)
                        return
                    
                    message = recap_result.get('message')
                    if not message:
                        logger.error("❌ Daily recap message is empty, will retry")
                        return
                    
                    bot = self.runtime.get_telegram_bot()
                    await bot.post_detailed_recap(message)
                    
                    db.set_last_recap_date('daily', current_date_str, tenant_id=self.tenant_id)
                    logger.info(f"✅ Daily recap posted: {total_signals} signals, {win_rate:.0f}% win rate, {stats.get('total_pips', 0):+.1f} pips")
                else:
                    logger.info("Daily recap already posted today, skipping")
        
        except Exception as e:
            logger.error(f"❌ Error posting daily recap: {e}")
    
    async def check_weekly_recap(self):
        """Post weekly recap on Sunday"""
        try:
            now = datetime.utcnow()
            
            if now.weekday() == 6 and now.hour == 6 and 30 <= now.minute < 35:
                week_number = str(now.isocalendar()[1])
                
                db = self.runtime.db
                last_posted = db.get_last_recap_date('weekly', tenant_id=self.tenant_id)
                
                if last_posted != week_number:
                    logger.info("Generating weekly recap...")
                    
                    ai_recap = generate_weekly_recap(tenant_id=self.tenant_id)
                    bot = self.runtime.get_telegram_bot()
                    result = await bot.post_weekly_recap(ai_recap)
                    
                    db.set_last_recap_date('weekly', week_number, tenant_id=self.tenant_id)
                    
                    if result and result is not False:
                        db.set_last_recap_date('weekly_recap_msg_id', str(result), tenant_id=self.tenant_id)
                        logger.info(f"✅ Weekly recap posted (msg_id: {result})")
                    else:
                        logger.info("✅ Weekly recap posted")
                else:
                    logger.info("Weekly recap already posted this week, skipping")
        
        except Exception as e:
            logger.error(f"❌ Error posting weekly recap: {e}")
    
    async def check_crosspromo_daily(self):
        """Enqueue cross promo daily sequence at configured time (Mon-Fri only)"""
        try:
            now = datetime.utcnow()
            
            if now.weekday() > 4:
                return
            
            from domains.crosspromo import repo as crosspromo_repo
            settings = crosspromo_repo.get_settings(self.tenant_id)
            
            if not settings or not settings.get('enabled'):
                return
            
            morning_time_str = settings.get('morning_post_time_utc', '07:00')
            try:
                parts = morning_time_str.split(':')
                target_hour = int(parts[0])
                target_minute = int(parts[1]) if len(parts) > 1 else 0
            except (ValueError, IndexError):
                target_hour, target_minute = 7, 0
            
            if now.hour == target_hour and target_minute <= now.minute < target_minute + 5:
                current_date_str = now.date().isoformat()
                
                db = self.runtime.db
                last_enqueued = db.get_last_recap_date('crosspromo_daily', tenant_id=self.tenant_id)
                
                if last_enqueued != current_date_str:
                    logger.info(f"Enqueueing cross promo daily sequence (scheduled for {morning_time_str})...")
                    
                    from domains.crosspromo import service as crosspromo_service
                    result = crosspromo_service.enqueue_daily_sequence(self.tenant_id)
                    
                    if result.get('success'):
                        db.set_last_recap_date('crosspromo_daily', current_date_str, tenant_id=self.tenant_id)
                        jobs = result.get('jobs_created', [])
                        logger.info(f"✅ Cross promo daily sequence enqueued: {jobs}")
                    else:
                        error = result.get('error', 'Unknown error')
                        logger.warning(f"Cross promo daily sequence skipped: {error}")
        
        except Exception as e:
            logger.error(f"❌ Error enqueueing cross promo daily: {e}")
    
    async def run_once(self):
        """Run a single signal check cycle and exit."""
        with self.runtime.request_context():
            logger.info(f"Running single signal check for tenant={self.tenant_id}")
            await self.generator.run_signal_check()
            logger.info("Single check completed")
    
    async def run_forever(self):
        """Main scheduler loop"""
        logger.info("")
        logger.info("=" * 60)
        logger.info("🚀 FOREX SIGNALS SCHEDULER STARTED")
        logger.info(f"   Tenant: {self.tenant_id}")
        logger.info("=" * 60)
        logger.info("📊 Signal checks: 15min timeframe every 15 minutes")
        logger.info("📊 Signal checks: 1h timeframe every 30 minutes")
        logger.info("🔍 Price monitoring: Every 5 seconds")
        logger.info("💡 Signal guidance: Every 5 seconds (reuses cached price, 10min cooldown)")
        logger.info("🔄 Stagnant re-validation: First at 90min, then every 30min")
        logger.info("⏰ Signal timeout: 4 hours (atomic close in price monitor)")
        logger.info("☀️ Morning briefing: 6:20 AM UTC")
        logger.info("📅 Daily recap: 6:30 AM UTC")
        logger.info("📅 Weekly recap: Sunday 6:30 AM UTC")
        logger.info("📣 Cross promo daily: Configured time from settings (Mon-Fri)")
        logger.info("⏰ Trading hours: 8AM-10PM GMT (Mon-Fri only)")
        logger.info("=" * 60)
        
        tick_counter = 0
        signal_every = self.signal_check_interval // self.monitor_interval       # 900/5 = 180 ticks
        stagnant_every = STAGNANT_CHECK_INTERVAL // self.monitor_interval         # 300/5 = 60 ticks
        scheduled_every = SCHEDULED_CHECK_INTERVAL // self.monitor_interval       # 60/5 = 12 ticks
        
        while True:
            try:
                with self.runtime.request_context():
                    # Signal generation check (every 15 minutes)
                    if tick_counter % signal_every == 0:
                        await self.generator.run_signal_check()
                    
                    # Price monitoring (every 5 seconds)
                    await self.monitor.run_signal_monitoring()
                    
                    # Milestone guidance (every 5 seconds, reuses cached price from monitoring)
                    await self.monitor.run_signal_guidance()
                    
                    # Stagnant signal checks (every 5 minutes)
                    if tick_counter % stagnant_every == 0:
                        await self.monitor.run_stagnant_signal_checks()
                    
                    # Scheduled messages (every 1 minute)
                    if tick_counter % scheduled_every == 0:
                        await self.check_morning_briefing()
                        await self.check_daily_recap()
                        await self.check_weekly_recap()
                        await self.check_crosspromo_daily()
                
                tick_counter += 1
                await asyncio.sleep(self.monitor_interval)
                
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.exception(f"❌ Unexpected error: {e}")
                await asyncio.sleep(60)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Forex Signals Scheduler')
    parser.add_argument('--once', action='store_true', help='Run one signal check cycle and exit')
    parser.add_argument('--tenant', type=str, help='Tenant ID (single tenant mode)')
    parser.add_argument('--all-tenants', action='store_true', help='Run for all active tenants')
    parser.add_argument('--shard', type=str, help='Shard assignment N/M (e.g., 0/3 for shard 0 of 3)')
    return parser.parse_args()


def parse_shard(shard_str: str) -> tuple:
    """Parse shard string like '0/3' into (shard_index, total_shards)."""
    if not shard_str or '/' not in shard_str:
        return None, None
    parts = shard_str.split('/')
    if len(parts) != 2:
        return None, None
    try:
        shard_index = int(parts[0])
        total_shards = int(parts[1])
        if shard_index < 0 or shard_index >= total_shards or total_shards < 1:
            return None, None
        return shard_index, total_shards
    except ValueError:
        return None, None


def tenant_in_shard(tenant_id: str, shard_index: int, total_shards: int) -> bool:
    """Determine if a tenant belongs to a shard using consistent hashing.
    
    Uses SHA256 for deterministic hashing (Python's hash() is randomized per process).
    """
    import hashlib
    hash_value = int(hashlib.sha256(tenant_id.encode()).hexdigest(), 16)
    return hash_value % total_shards == shard_index


TENANT_TIMEOUT_SECONDS = 120  # 2 minute per-tenant execution budget


async def run_tenant_with_timeout(tenant_id: str, once: bool) -> dict:
    """
    Run scheduler for a single tenant with timeout protection.
    
    Returns dict with 'success', 'tenant_id', 'error' keys.
    """
    result = {'tenant_id': tenant_id, 'success': False, 'error': None}
    
    try:
        runtime = require_tenant_runtime(tenant_id)
        signal_engine = runtime.get_signal_engine()
        signal_engine.set_tenant_id(runtime.tenant_id)
        
        scheduler = ForexSchedulerRunner(runtime)
        
        if once:
            await asyncio.wait_for(
                scheduler.run_once(),
                timeout=TENANT_TIMEOUT_SECONDS
            )
        else:
            await scheduler.run_forever()
        
        result['success'] = True
    except asyncio.TimeoutError:
        result['error'] = f"Timeout after {TENANT_TIMEOUT_SECONDS}s"
        logger.warning(f"Tenant {tenant_id} timed out after {TENANT_TIMEOUT_SECONDS}s")
        notify_error(
            f"Scheduler timeout after {TENANT_TIMEOUT_SECONDS}s",
            tenant_id=tenant_id,
            context={"error_type": "timeout", "duration_s": TENANT_TIMEOUT_SECONDS}
        )
    except Exception as e:
        result['error'] = str(e)
        logger.exception(f"Tenant {tenant_id} failed: {e}")
        notify_error(
            f"Scheduler failed: {e}",
            tenant_id=tenant_id,
            context={"error_type": "exception", "exception_class": type(e).__name__}
        )
    
    return result


async def run_all_tenants(once: bool, shard_index: int = None, total_shards: int = None):
    """
    Run scheduler for all active tenants (or a shard of them).
    
    Args:
        once: If True, run once and exit. If False, run forever (not supported in multi-tenant).
        shard_index: Optional shard index (0-based)
        total_shards: Optional total number of shards
    """
    import db as db_module
    
    all_tenants = db_module.get_active_tenants()
    
    if not all_tenants:
        logger.warning("No active tenants found")
        return
    
    if shard_index is not None and total_shards is not None:
        tenants = [t for t in all_tenants if tenant_in_shard(t, shard_index, total_shards)]
        logger.info(f"Shard {shard_index}/{total_shards}: {len(tenants)} of {len(all_tenants)} tenants")
    else:
        tenants = all_tenants
        logger.info(f"All tenants mode: {len(tenants)} tenants")
    
    if not tenants:
        logger.info("No tenants in this shard, exiting")
        return
    
    if not once:
        logger.error("--all-tenants mode requires --once flag (continuous multi-tenant not supported)")
        return
    
    succeeded = 0
    failed = 0
    skipped = 0
    
    for tenant_id in tenants:
        logger.info(f"Processing tenant: {tenant_id}")
        result = await run_tenant_with_timeout(tenant_id, once=True)
        
        if result['success']:
            succeeded += 1
            logger.info(f"✅ Tenant {tenant_id} completed successfully")
        else:
            failed += 1
            logger.error(f"❌ Tenant {tenant_id} failed: {result['error']}")
    
    total = succeeded + failed + skipped
    logger.info("=" * 50)
    logger.info(f"MULTI-TENANT RUN SUMMARY")
    logger.info(f"  Total:     {total}")
    logger.info(f"  Succeeded: {succeeded}")
    logger.info(f"  Failed:    {failed}")
    logger.info(f"  Skipped:   {skipped}")
    logger.info("=" * 50)


async def main():
    """Async entry point"""
    require_db_pool_or_exit()
    
    args = parse_args()
    
    if args.all_tenants:
        shard_index, total_shards = parse_shard(args.shard) if args.shard else (None, None)
        await run_all_tenants(args.once, shard_index, total_shards)
    else:
        runtime = require_tenant_runtime(args.tenant)
        
        signal_engine = runtime.get_signal_engine()
        signal_engine.set_tenant_id(runtime.tenant_id)
        
        scheduler = ForexSchedulerRunner(runtime)
        
        if args.once:
            await scheduler.run_once()
        else:
            await scheduler.run_forever()


async def start_forex_scheduler(tenant_id: str = None):
    """
    Start the forex scheduler - programmatic entry point.
    
    Runs the full forex scheduler (signal checks, price monitoring, guidance,
    briefings) for a single tenant continuously.
    
    Args:
        tenant_id: Tenant ID. If None, reads from TENANT_ID env var.
        
    Note:
        The scheduler requires a tenant_id because it runs continuously with
        multiple background tasks (price monitoring, guidance, briefings).
        For production, set TENANT_ID env var in your deployment config.
    """
    require_db_pool_or_exit()
    
    resolved_tenant = tenant_id or os.environ.get('TENANT_ID')
    
    if not resolved_tenant:
        logger.error(
            "[SCHEDULER] No tenant_id provided. "
            "Set TENANT_ID env var in production (e.g., TENANT_ID=entrylab). "
            "For CLI usage, use: python forex_scheduler.py --tenant <tenant_id>"
        )
        return
    
    logger.info(f"Starting forex scheduler for tenant: {resolved_tenant}")
    runtime = TenantRuntime(tenant_id=resolved_tenant)
    
    signal_engine = runtime.get_signal_engine()
    signal_engine.set_tenant_id(runtime.tenant_id)
    
    scheduler = ForexSchedulerRunner(runtime)
    await scheduler.run_forever()


if __name__ == '__main__':
    asyncio.run(main())
