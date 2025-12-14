"""
Forex signals scheduler
Runs signal checks every 15 minutes and monitors active signals
Handles daily/weekly recaps at scheduled times
Includes milestone-based progress notifications for active signals
"""
import argparse
import asyncio
import os
from datetime import datetime, time
from forex_signals import forex_signal_engine
from forex_bot import forex_telegram_bot
from forex_ai import generate_tp_celebration, generate_daily_recap, generate_weekly_recap, generate_signal_guidance, generate_revalidation_message, generate_timeout_message
from db import update_forex_signal_status, get_forex_signals, update_signal_breakeven, update_signal_guidance, update_signal_revalidation, update_signal_timeout_notified, get_last_recap_date, set_last_recap_date, update_milestone_sent, update_effective_sl, db_pool
from forex_api import twelve_data_client
from bots.core.milestone_tracker import milestone_tracker
from core.logging import get_logger, set_request_context, clear_request_context

logger = get_logger(__name__)

# Scheduler timing constants (in seconds)
SIGNAL_CHECK_INTERVAL = 900      # 15 minutes - check for new signals
MONITOR_INTERVAL = 60            # 1 minute - monitor active signals for TP/SL
GUIDANCE_INTERVAL = 60           # 1 minute - check for guidance updates
STAGNANT_CHECK_INTERVAL = 300    # 5 minutes - check stagnant signals for revalidation

class ForexScheduler:
    def __init__(self, tenant_id='entrylab'):
        self.tenant_id = tenant_id  # Default tenant for forex bot
        self.signal_check_interval = SIGNAL_CHECK_INTERVAL
        self.monitor_interval = MONITOR_INTERVAL
        self.last_daily_recap = None
        self.last_weekly_recap = None
        self.last_1h_check = None  # Track when we last checked 1h timeframe
        self.last_bot_config_updated_at = None  # Track bot_config changes for hot-reload
        self.last_forex_config_updated_at = None  # Track forex_config changes for hot-reload
    
    def _check_config_update(self):
        """Check if bot_config or forex_config has been updated and trigger hot-reload if needed"""
        try:
            if not db_pool.connection_pool:
                return
            
            with db_pool.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT updated_at FROM bot_config WHERE setting_key = 'active_bot' AND tenant_id = %s
                """, (self.tenant_id,))
                bot_row = cursor.fetchone()
                current_bot_updated_at = bot_row[0] if bot_row and bot_row[0] else None
                
                cursor.execute("""
                    SELECT MAX(updated_at) FROM forex_config WHERE tenant_id = %s
                """, (self.tenant_id,))
                forex_row = cursor.fetchone()
                current_forex_updated_at = forex_row[0] if forex_row and forex_row[0] else None
                
                should_reload = False
                
                if self.last_bot_config_updated_at is None:
                    self.last_bot_config_updated_at = current_bot_updated_at
                elif current_bot_updated_at and current_bot_updated_at != self.last_bot_config_updated_at:
                    logger.info("🔄 bot_config change detected")
                    should_reload = True
                    self.last_bot_config_updated_at = current_bot_updated_at
                
                if self.last_forex_config_updated_at is None:
                    self.last_forex_config_updated_at = current_forex_updated_at
                elif current_forex_updated_at and current_forex_updated_at != self.last_forex_config_updated_at:
                    logger.info("🔄 forex_config change detected (guardrails/indicators)")
                    should_reload = True
                    self.last_forex_config_updated_at = current_forex_updated_at
                
                if should_reload:
                    logger.info("🔄 Reloading config...")
                    forex_signal_engine.reload_config()
                    logger.info("✅ Config hot-reloaded successfully")
        except Exception as e:
            logger.warning(f"⚠️ Error checking config update: {e}")
    
    async def run_signal_check(self):
        """Check for new signals on both 15min and 1h timeframes"""
        set_request_context(tenant_id=self.tenant_id)
        try:
            self._check_config_update()
            
            if not forex_signal_engine.is_trading_hours():
                logger.info("Outside trading hours (8AM-10PM GMT), skipping signal check")
                return
            
            # CRITICAL: Only allow ONE active signal at a time
            pending_signals = get_forex_signals(status='pending', tenant_id=self.tenant_id)
            if pending_signals and len(pending_signals) > 0:
                signal = pending_signals[0]
                logger.info(f"⏸️ Active signal #{signal['id']} still pending - skipping new signal check")
                logger.info(f"Entry: ${signal['entry_price']}, TP: ${signal['take_profit']}, SL: ${signal['stop_loss']}")
                return
            
            # Determine if it's time to check 1h timeframe (every 30 minutes)
            now = datetime.utcnow()
            should_check_1h = False
            
            if self.last_1h_check is None:
                should_check_1h = True
            else:
                minutes_since_1h = (now - self.last_1h_check).total_seconds() / 60
                if minutes_since_1h >= 30:
                    should_check_1h = True
            
            # Check 15-minute timeframe (every signal check)
            signal_data = await forex_signal_engine.check_for_signals(timeframe='15min')
            
            if signal_data:
                signal_id = await forex_telegram_bot.post_signal(signal_data)
                if signal_id:
                    logger.info(f"✅ New 15min signal #{signal_id} posted successfully")
                    # Update 1h timestamp even if we posted a 15min signal (prevent starvation)
                    if should_check_1h:
                        self.last_1h_check = now
                        logger.info("⏭️ Skipped 1h check (signal already active)")
                    return
            
            # Check 1-hour timeframe if due
            if should_check_1h:
                logger.info("📊 Checking 1-hour timeframe...")
                signal_data_1h = await forex_signal_engine.check_for_signals(timeframe='1h')
                self.last_1h_check = now
                
                if signal_data_1h:
                    signal_id = await forex_telegram_bot.post_signal(signal_data_1h)
                    if signal_id:
                        logger.info(f"✅ New 1h signal #{signal_id} posted successfully")
                    else:
                        logger.error("❌ Failed to post 1h signal to Telegram")
            
        except Exception as e:
            logger.error(f"❌ Error in signal check: {e}")
    
    async def run_signal_monitoring(self):
        """Monitor active signals for multi-TP hits, SL hits, and breakeven alerts"""
        set_request_context(tenant_id=self.tenant_id)
        try:
            updates = await forex_signal_engine.monitor_active_signals()
            
            for update in updates:
                signal_id = update['id']
                event = update.get('event')
                status = update.get('status')
                pips = update.get('pips', 0)
                close_price = update.get('exit_price') or update.get('current_price')
                
                signals_data = get_forex_signals(status=None, limit=10, tenant_id=self.tenant_id)
                matching_signal = next((s for s in signals_data if s['id'] == signal_id), None)
                signal_type = matching_signal.get('signal_type', 'BUY') if matching_signal else 'BUY'
                
                if event == 'breakeven_alert':
                    pass
                
                elif event == 'tp1_hit':
                    remaining = update.get('remaining', 0)
                    message = milestone_tracker.generate_tp1_celebration(signal_type, pips, remaining)
                    await forex_telegram_bot.bot.send_message(
                        chat_id=forex_telegram_bot.channel_id,
                        text=message,
                        parse_mode='HTML'
                    )
                    if remaining > 0 and matching_signal:
                        tp1_price = float(matching_signal.get('take_profit', 0))
                        update_effective_sl(signal_id, tp1_price, tenant_id=self.tenant_id)
                        logger.info(f"🔒 Set effective_sl to TP1 (${tp1_price:.2f}) for signal #{signal_id}")
                    logger.info(f"✅ Posted TP1 celebration for signal #{signal_id}")
                
                elif event == 'tp2_hit':
                    remaining = update.get('remaining', 0)
                    tp1_price = matching_signal.get('take_profit', 0) if matching_signal else 0
                    tp2_price = matching_signal.get('take_profit_2', 0) if matching_signal else 0
                    message = milestone_tracker.generate_tp2_celebration(signal_type, pips, float(tp1_price), remaining)
                    await forex_telegram_bot.bot.send_message(
                        chat_id=forex_telegram_bot.channel_id,
                        text=message,
                        parse_mode='HTML'
                    )
                    if remaining > 0 and tp2_price:
                        update_effective_sl(signal_id, float(tp2_price), tenant_id=self.tenant_id)
                        logger.info(f"🔒 Set effective_sl to TP2 (${float(tp2_price):.2f}) for signal #{signal_id}")
                    logger.info(f"✅ Posted TP2 celebration for signal #{signal_id}")
                
                elif event == 'tp3_hit':
                    message = milestone_tracker.generate_tp3_celebration(signal_type, pips)
                    await forex_telegram_bot.bot.send_message(
                        chat_id=forex_telegram_bot.channel_id,
                        text=message,
                        parse_mode='HTML'
                    )
                    if status == 'won':
                        update_forex_signal_status(signal_id, 'won', pips, close_price, tenant_id=self.tenant_id)
                        logger.info(f"✅ Signal #{signal_id} completed - all TPs hit!")
                
                elif event == 'sl_hit_profit_locked':
                    update_forex_signal_status(signal_id, 'won', pips, close_price, tenant_id=self.tenant_id)
                    message = milestone_tracker.generate_profit_locked_message(pips)
                    await forex_telegram_bot.bot.send_message(
                        chat_id=forex_telegram_bot.channel_id,
                        text=message,
                        parse_mode='HTML'
                    )
                    logger.info(f"🔒 Posted profit-locked SL notification for signal #{signal_id}")
                
                elif event == 'sl_hit_breakeven':
                    update_forex_signal_status(signal_id, 'won', pips, close_price, tenant_id=self.tenant_id)
                    message = milestone_tracker.generate_breakeven_exit_message()
                    await forex_telegram_bot.bot.send_message(
                        chat_id=forex_telegram_bot.channel_id,
                        text=message,
                        parse_mode='HTML'
                    )
                    logger.info(f"🔒 Posted breakeven exit notification for signal #{signal_id}")
                
                elif event == 'sl_hit':
                    update_forex_signal_status(signal_id, status, pips, close_price, tenant_id=self.tenant_id)
                    message = milestone_tracker.generate_sl_hit_message(abs(pips))
                    await forex_telegram_bot.bot.send_message(
                        chat_id=forex_telegram_bot.channel_id,
                        text=message,
                        parse_mode='HTML'
                    )
                    logger.error(f"❌ Posted SL notification for signal #{signal_id}")
                
                elif status == 'won':
                    update_forex_signal_status(signal_id, status, pips, close_price, tenant_id=self.tenant_id)
                    message = milestone_tracker.generate_tp1_celebration(signal_type, pips, 0)
                    await forex_telegram_bot.bot.send_message(
                        chat_id=forex_telegram_bot.channel_id,
                        text=message,
                        parse_mode='HTML'
                    )
                    logger.info(f"✅ Posted TP celebration for signal #{signal_id}")
                    
                elif status == 'lost':
                    update_forex_signal_status(signal_id, status, pips, close_price, tenant_id=self.tenant_id)
                    message = milestone_tracker.generate_sl_hit_message(abs(pips))
                    await forex_telegram_bot.bot.send_message(
                        chat_id=forex_telegram_bot.channel_id,
                        text=message,
                        parse_mode='HTML'
                    )
                    logger.error(f"❌ Posted SL notification for signal #{signal_id}")
                    
                elif status == 'expired':
                    # If signal expires with positive pips, it's still a win
                    final_status = 'won' if pips > 0 else 'expired'
                    update_forex_signal_status(signal_id, final_status, pips, close_price, tenant_id=self.tenant_id)
                    await forex_telegram_bot.post_signal_expired(signal_id, pips, signal_type)
                    logger.info(f"✅ Posted expiry notification for signal #{signal_id} (status: {final_status})")
                
                if status in ('won', 'lost', 'expired'):
                    forex_signal_engine.load_active_strategy()
                    logger.info(f"Strategy reloaded after signal #{signal_id} closed")
                
        except Exception as e:
            logger.exception("❌ Error in signal monitoring")
    
    async def run_signal_guidance(self):
        """
        Check for milestone-based progress updates on active signals.
        
        Milestones:
        - 40% toward TP1: AI motivational message
        - 70% toward TP1: Breakeven alert + Move SL to entry
        - 50% toward TP2: Small celebration (if multi-TP)
        - 60% toward SL: Calm warning (one time)
        
        90-second cooldown between all messages.
        """
        set_request_context(tenant_id=self.tenant_id)
        try:
            active_signals = get_forex_signals(status='pending', tenant_id=self.tenant_id)
            
            if not active_signals:
                return
            
            current_price = twelve_data_client.get_price(forex_signal_engine.symbol)
            if not current_price:
                return
            
            for signal in active_signals:
                signal_id = signal['id']
                
                milestone_event = milestone_tracker.check_milestones(signal, current_price)
                
                if milestone_event:
                    milestone = milestone_event['milestone']
                    milestone_key = milestone_event['milestone_key']
                    
                    # ATOMIC CLAIM: Try to claim this milestone in DB first
                    # update_milestone_sent uses WHERE NOT LIKE to prevent race conditions
                    claimed = update_milestone_sent(signal_id, milestone_key, tenant_id=self.tenant_id)
                    
                    if not claimed:
                        logger.info(f"⏭️ Milestone {milestone_key} already claimed by another worker for signal #{signal_id}")
                        continue
                    
                    message = milestone_tracker.generate_milestone_message(milestone_event)
                    
                    if message:
                        try:
                            await forex_telegram_bot.bot.send_message(
                                chat_id=forex_telegram_bot.channel_id,
                                text=message,
                                parse_mode='HTML'
                            )
                            
                            if milestone == 'tp1_70_breakeven':
                                update_signal_breakeven(signal_id, milestone_event['entry_price'], tenant_id=self.tenant_id)
                                update_effective_sl(signal_id, milestone_event['entry_price'], tenant_id=self.tenant_id)
                                logger.info(f"🔒 Set effective_sl to entry (breakeven) for signal #{signal_id}")
                            
                            logger.info(f"✅ Posted {milestone} milestone for signal #{signal_id}")
                            
                        except Exception as e:
                            logger.error(f"❌ Failed to post milestone message: {e}")
                
        except Exception as e:
            logger.exception("❌ Error in signal guidance")
    
    async def run_stagnant_signal_checks(self):
        """Check stagnant signals for re-validation and timeout"""
        set_request_context(tenant_id=self.tenant_id)
        try:
            revalidation_events = await forex_signal_engine.check_stagnant_signals()
            
            for event in revalidation_events:
                signal_id = event['signal_id']
                event_type = event['event_type']
                signal = event['signal']
                minutes_elapsed = event['minutes_elapsed']
                
                signal_type = signal['signal_type']
                entry = float(signal['entry_price'])
                tp = float(signal['take_profit'])
                sl = float(signal['stop_loss'])
                
                # Fetch current price
                current_price = twelve_data_client.get_price(forex_signal_engine.symbol)
                if not current_price:
                    logger.warning(f"⚠️ Could not fetch price for revalidation of signal #{signal_id}")
                    continue
                
                if event_type == 'timeout':
                    # Fetch current indicators for technical justification
                    current_indicators = None
                    original_indicators = signal.get('original_indicators_json') or {}
                    
                    try:
                        validation = await forex_signal_engine.perform_revalidation(signal)
                        if validation:
                            current_indicators = validation.get('current_indicators', {})
                    except Exception as e:
                        logger.warning(f"Could not fetch current indicators for timeout: {e}")
                    
                    # Generate close recommendation with technical justification
                    ai_message = generate_timeout_message(
                        signal_id=signal_id,
                        signal_type=signal_type,
                        minutes_elapsed=minutes_elapsed,
                        current_price=current_price,
                        entry_price=entry,
                        tp_price=tp,
                        sl_price=sl,
                        current_indicators=current_indicators,
                        original_indicators=original_indicators
                    )
                    
                    success = await forex_telegram_bot.post_signal_timeout(
                        signal_id=signal_id,
                        message=ai_message,
                        current_price=current_price,
                        entry_price=entry
                    )
                    
                    if success:
                        update_signal_timeout_notified(signal_id, tenant_id=self.tenant_id)
                        # Close the signal - mark as won if positive pips, otherwise expired
                        # XAU/USD: 1 pip = $0.01, so multiply by 100
                        if signal_type == 'BUY':
                            pips = round((current_price - entry) * 100, 1)
                        else:
                            pips = round((entry - current_price) * 100, 1)
                        final_status = 'won' if pips > 0 else 'expired'
                        update_forex_signal_status(signal_id, final_status, pips, current_price, tenant_id=self.tenant_id)
                        forex_signal_engine.load_active_strategy()
                        logger.info(f"✅ Posted close advisory for signal #{signal_id} after {minutes_elapsed/60:.1f}h (status: {final_status})")
                    
                elif event_type == 'revalidation':
                    # Perform indicator re-validation
                    validation = await forex_signal_engine.perform_revalidation(signal)
                    
                    if validation:
                        thesis_status = validation['status']
                        reasons = validation['reasons']
                        previous_status = event.get('current_thesis_status', 'intact')
                        
                        # IMPORTANT: Only post if status has actually changed or worsened
                        # Skip if already reported the same status
                        should_post = False
                        if thesis_status != previous_status:
                            # Status changed - always post
                            should_post = True
                            logger.info(f"Thesis status changed: {previous_status} -> {thesis_status}")
                        elif thesis_status == 'intact':
                            # Back to healthy - no need to spam
                            should_post = False
                            logger.info(f"Signal #{signal_id} thesis still intact - no update needed")
                        else:
                            # Still weakening/broken - don't repeat the same message
                            should_post = False
                            logger.info(f"Signal #{signal_id} thesis still {thesis_status} - skipping duplicate message")
                        
                        # Always update the database timestamp (for tracking), but only post if status changed
                        update_signal_revalidation(signal_id, thesis_status, f"Check: {thesis_status}", tenant_id=self.tenant_id)
                        
                        if should_post:
                            ai_message = generate_revalidation_message(
                                signal_id=signal_id,
                                signal_type=signal_type,
                                thesis_status=thesis_status,
                                reasons=reasons,
                                minutes_elapsed=minutes_elapsed,
                                current_price=current_price,
                                entry_price=entry,
                                tp_price=tp,
                                sl_price=sl
                            )
                            
                            success = await forex_telegram_bot.post_revalidation_update(
                                signal_id=signal_id,
                                thesis_status=thesis_status,
                                message=ai_message,
                                current_price=current_price,
                                entry_price=entry
                            )
                            
                            if success:
                                update_signal_revalidation(signal_id, thesis_status, f"Revalidation: {ai_message[:100]}", tenant_id=self.tenant_id)
                                logger.info(f"✅ Posted revalidation ({thesis_status}) for signal #{signal_id}")
                                
                                # If thesis is broken, recommend closing
                                if thesis_status == 'broken':
                                    # Close the signal - mark as won if positive pips, otherwise expired
                                    # XAU/USD: 1 pip = $0.01, so multiply by 100
                                    if signal_type == 'BUY':
                                        pips = round((current_price - entry) * 100, 1)
                                    else:
                                        pips = round((entry - current_price) * 100, 1)
                                    final_status = 'won' if pips > 0 else 'expired'
                                    update_forex_signal_status(signal_id, final_status, pips, current_price, tenant_id=self.tenant_id)
                                    forex_signal_engine.load_active_strategy()
                                    logger.warning(f"🚨 Signal #{signal_id} closed due to broken thesis (status: {final_status})")
                
        except Exception as e:
            logger.exception("❌ Error in stagnant signal checks")
    
    async def check_morning_briefing(self):
        """Post morning briefing at 6:20 AM UTC with news and market levels"""
        try:
            now = datetime.utcnow()
            current_date_str = now.date().isoformat()
            
            if now.hour == 6 and 20 <= now.minute < 25:
                last_posted = get_last_recap_date('morning_briefing', tenant_id=self.tenant_id)
                
                if last_posted != current_date_str:
                    logger.info("Generating morning briefing...")
                    await forex_telegram_bot.post_morning_briefing()
                    set_last_recap_date('morning_briefing', current_date_str, tenant_id=self.tenant_id)
                    logger.info("✅ Morning briefing posted")
        
        except Exception as e:
            logger.error(f"❌ Error posting morning briefing: {e}")
    
    async def check_daily_recap(self):
        """Post daily recap at 6:30 AM UTC (yesterday's signals)"""
        try:
            now = datetime.utcnow()
            current_date_str = now.date().isoformat()
            
            if now.hour == 6 and 30 <= now.minute < 35:
                # Check database for last posted date (survives server restarts)
                last_posted = get_last_recap_date('daily', tenant_id=self.tenant_id)
                
                if last_posted != current_date_str:
                    logger.info("Generating daily recap...")
                    
                    ai_recap = generate_daily_recap()
                    await forex_telegram_bot.post_daily_recap(ai_recap)
                    
                    # Persist to database
                    set_last_recap_date('daily', current_date_str, tenant_id=self.tenant_id)
                    self.last_daily_recap = current_date_str
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
                
                # Check database for last posted week (survives server restarts)
                last_posted = get_last_recap_date('weekly', tenant_id=self.tenant_id)
                
                if last_posted != week_number:
                    logger.info("Generating weekly recap...")
                    
                    ai_recap = generate_weekly_recap()
                    await forex_telegram_bot.post_weekly_recap(ai_recap)
                    
                    # Persist to database
                    set_last_recap_date('weekly', week_number, tenant_id=self.tenant_id)
                    self.last_weekly_recap = week_number
                    logger.info("✅ Weekly recap posted")
                else:
                    logger.info("Weekly recap already posted this week, skipping")
        
        except Exception as e:
            logger.error(f"❌ Error posting weekly recap: {e}")
    
    async def run_forever(self):
        """Main scheduler loop"""
        logger.info("")
        logger.info("=" * 60)
        logger.info("🚀 FOREX SIGNALS SCHEDULER STARTED")
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
        monitor_counter = 0
        
        while True:
            try:
                if signal_check_counter % (self.signal_check_interval // self.monitor_interval) == 0:
                    await self.run_signal_check()
                
                await self.run_signal_monitoring()
                
                await self.run_signal_guidance()
                
                # Check for stagnant signals needing re-validation or timeout
                await self.run_stagnant_signal_checks()
                
                await self.check_morning_briefing()
                await self.check_daily_recap()
                await self.check_weekly_recap()
                
                signal_check_counter += 1
                monitor_counter += 1
                
                await asyncio.sleep(self.monitor_interval)
                
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"❌ Unexpected error: {e}")
                await asyncio.sleep(60)

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Forex Signals Scheduler')
    parser.add_argument('--once', action='store_true', help='Run one signal check cycle and exit')
    parser.add_argument('--tenant', type=str, help='Tenant ID (required)')
    return parser.parse_args()

def get_tenant_id(args):
    """Get tenant_id from args or environment, exit if missing"""
    tenant_id = getattr(args, 'tenant', None) or os.environ.get('TENANT_ID')
    if not tenant_id:
        logger.error("tenant_id is required. Use --tenant <id> or set TENANT_ID env var")
        import sys
        sys.exit(1)
    return tenant_id

forex_scheduler = None

async def start_forex_scheduler(tenant_id=None):
    """Entry point to start the scheduler"""
    global forex_scheduler
    tid = tenant_id or os.environ.get('TENANT_ID', 'entrylab')
    forex_scheduler = ForexScheduler(tenant_id=tid)
    await forex_scheduler.run_forever()

if __name__ == '__main__':
    args = parse_args()
    tenant_id = get_tenant_id(args)
    
    forex_signal_engine.set_tenant_id(tenant_id)
    
    scheduler = ForexScheduler(tenant_id=tenant_id)
    
    if args.once:
        logger.info(f"Running single check with tenant={tenant_id}")
        asyncio.run(scheduler.run_signal_check())
    else:
        asyncio.run(scheduler.run_forever())
