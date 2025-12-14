"""
Forex Signals Scheduler - CLI Entrypoint

Thin CLI wrapper that wires together TenantRuntime and scheduler modules.
Handles CLI argument parsing and main loop orchestration.
"""
import argparse
import asyncio
import os
from datetime import datetime

from core.logging import get_logger
from core.runtime import require_tenant_runtime, TenantRuntime
from scheduler import SignalGenerator, SignalMonitor, Messenger
from forex_ai import generate_daily_recap, generate_weekly_recap

logger = get_logger(__name__)

# Scheduler timing constants (in seconds)
SIGNAL_CHECK_INTERVAL = 900      # 15 minutes - check for new signals
MONITOR_INTERVAL = 60            # 1 minute - monitor active signals for TP/SL
GUIDANCE_INTERVAL = 60           # 1 minute - check for guidance updates
STAGNANT_CHECK_INTERVAL = 300    # 5 minutes - check stagnant signals for revalidation


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
        """Post morning briefing at 6:20 AM UTC with news and market levels"""
        try:
            now = datetime.utcnow()
            current_date_str = now.date().isoformat()
            
            if now.hour == 6 and 20 <= now.minute < 25:
                db = self.runtime.db
                last_posted = db.get_last_recap_date('morning_briefing', tenant_id=self.tenant_id)
                
                if last_posted != current_date_str:
                    logger.info("Generating morning briefing...")
                    bot = self.runtime.get_telegram_bot()
                    await bot.post_morning_briefing()
                    db.set_last_recap_date('morning_briefing', current_date_str, tenant_id=self.tenant_id)
                    logger.info("✅ Morning briefing posted")
        
        except Exception as e:
            logger.error(f"❌ Error posting morning briefing: {e}")
    
    async def check_daily_recap(self):
        """Post daily recap at 6:30 AM UTC (yesterday's signals)"""
        try:
            now = datetime.utcnow()
            current_date_str = now.date().isoformat()
            
            if now.hour == 6 and 30 <= now.minute < 35:
                db = self.runtime.db
                last_posted = db.get_last_recap_date('daily', tenant_id=self.tenant_id)
                
                if last_posted != current_date_str:
                    logger.info("Generating daily recap...")
                    
                    ai_recap = generate_daily_recap()
                    bot = self.runtime.get_telegram_bot()
                    await bot.post_daily_recap(ai_recap)
                    
                    db.set_last_recap_date('daily', current_date_str, tenant_id=self.tenant_id)
                    logger.info("✅ Daily recap posted")
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
                    
                    ai_recap = generate_weekly_recap()
                    bot = self.runtime.get_telegram_bot()
                    await bot.post_weekly_recap(ai_recap)
                    
                    db.set_last_recap_date('weekly', week_number, tenant_id=self.tenant_id)
                    logger.info("✅ Weekly recap posted")
                else:
                    logger.info("Weekly recap already posted this week, skipping")
        
        except Exception as e:
            logger.error(f"❌ Error posting weekly recap: {e}")
    
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
        logger.info("🔍 Price monitoring: Every 1 minute")
        logger.info("💡 Signal guidance: Every 1 minute (with 10min cooldown)")
        logger.info("🔄 Stagnant re-validation: First at 90min, then every 30min")
        logger.info("⏰ Hard timeout: 3 hours")
        logger.info("☀️ Morning briefing: 6:20 AM UTC")
        logger.info("📅 Daily recap: 6:30 AM UTC")
        logger.info("📅 Weekly recap: Sunday 6:30 AM UTC")
        logger.info("⏰ Trading hours: 8AM-10PM GMT")
        logger.info("=" * 60)
        
        signal_check_counter = 0
        
        while True:
            try:
                with self.runtime.request_context():
                    # Signal generation check (every 15 minutes)
                    if signal_check_counter % (self.signal_check_interval // self.monitor_interval) == 0:
                        await self.generator.run_signal_check()
                    
                    # Signal monitoring (every minute)
                    await self.monitor.run_signal_monitoring()
                    
                    # Milestone guidance (every minute)
                    await self.monitor.run_signal_guidance()
                    
                    # Stagnant signal checks
                    await self.monitor.run_stagnant_signal_checks()
                    
                    # Scheduled messages
                    await self.check_morning_briefing()
                    await self.check_daily_recap()
                    await self.check_weekly_recap()
                
                signal_check_counter += 1
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
    parser.add_argument('--tenant', type=str, help='Tenant ID (required)')
    return parser.parse_args()


async def main():
    """Async entry point"""
    args = parse_args()
    
    # Create tenant runtime (will exit if tenant not provided)
    runtime = require_tenant_runtime(args.tenant)
    
    # Set tenant on signal engine
    signal_engine = runtime.get_signal_engine()
    signal_engine.set_tenant_id(runtime.tenant_id)
    
    # Create and run scheduler
    scheduler = ForexSchedulerRunner(runtime)
    
    if args.once:
        await scheduler.run_once()
    else:
        await scheduler.run_forever()


def start_forex_scheduler(tenant_id: str = None):
    """
    Start the forex scheduler - backwards compatibility wrapper.
    
    This function is kept for compatibility with workers/scheduler.py.
    It wraps the async main() function.
    
    Args:
        tenant_id: Optional tenant ID (can also be set via TENANT_ID env var)
    """
    if tenant_id:
        os.environ['TENANT_ID'] = tenant_id
    asyncio.run(main())


if __name__ == '__main__':
    asyncio.run(main())
