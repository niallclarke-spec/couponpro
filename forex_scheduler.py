"""
Forex signals scheduler
Runs signal checks every 15 minutes and monitors active signals
Handles daily/weekly recaps at scheduled times
Includes real-time guidance updates for active signals
"""
import asyncio
from datetime import datetime, time
from forex_signals import forex_signal_engine
from forex_bot import forex_telegram_bot
from forex_ai import generate_tp_celebration, generate_daily_recap, generate_weekly_recap, generate_signal_guidance, generate_revalidation_message, generate_timeout_message
from db import update_forex_signal_status, get_forex_signals, update_signal_breakeven, update_signal_guidance, update_signal_revalidation, update_signal_timeout_notified, get_last_recap_date, set_last_recap_date
from forex_api import twelve_data_client

# Scheduler timing constants (in seconds)
SIGNAL_CHECK_INTERVAL = 900      # 15 minutes - check for new signals
MONITOR_INTERVAL = 60            # 1 minute - monitor active signals for TP/SL
GUIDANCE_INTERVAL = 60           # 1 minute - check for guidance updates
STAGNANT_CHECK_INTERVAL = 300    # 5 minutes - check stagnant signals for revalidation

class ForexScheduler:
    def __init__(self):
        self.signal_check_interval = SIGNAL_CHECK_INTERVAL
        self.monitor_interval = MONITOR_INTERVAL
        self.last_daily_recap = None
        self.last_weekly_recap = None
        self.last_1h_check = None  # Track when we last checked 1h timeframe
    
    async def run_signal_check(self):
        """Check for new signals on both 15min and 1h timeframes"""
        try:
            if not forex_signal_engine.is_trading_hours():
                print("[SCHEDULER] Outside trading hours (8AM-10PM GMT), skipping signal check")
                return
            
            # CRITICAL: Only allow ONE active signal at a time
            pending_signals = get_forex_signals(status='pending')
            if pending_signals and len(pending_signals) > 0:
                signal = pending_signals[0]
                print(f"[SCHEDULER] ⏸️ Active signal #{signal['id']} still pending - skipping new signal check")
                print(f"[SCHEDULER] Entry: ${signal['entry_price']}, TP: ${signal['take_profit']}, SL: ${signal['stop_loss']}")
                return
            
            # Determine if it's time to check 1h timeframe (every hour)
            now = datetime.utcnow()
            should_check_1h = False
            
            if self.last_1h_check is None:
                should_check_1h = True
            else:
                minutes_since_1h = (now - self.last_1h_check).total_seconds() / 60
                if minutes_since_1h >= 60:
                    should_check_1h = True
            
            # Check 15-minute timeframe (every signal check)
            signal_data = await forex_signal_engine.check_for_signals(timeframe='15min')
            
            if signal_data:
                signal_id = await forex_telegram_bot.post_signal(signal_data)
                if signal_id:
                    print(f"[SCHEDULER] ✅ New 15min signal #{signal_id} posted successfully")
                    # Update 1h timestamp even if we posted a 15min signal (prevent starvation)
                    if should_check_1h:
                        self.last_1h_check = now
                        print("[SCHEDULER] ⏭️ Skipped 1h check (signal already active)")
                    return
            
            # Check 1-hour timeframe if due
            if should_check_1h:
                print("[SCHEDULER] 📊 Checking 1-hour timeframe...")
                signal_data_1h = await forex_signal_engine.check_for_signals(timeframe='1h')
                self.last_1h_check = now
                
                if signal_data_1h:
                    signal_id = await forex_telegram_bot.post_signal(signal_data_1h)
                    if signal_id:
                        print(f"[SCHEDULER] ✅ New 1h signal #{signal_id} posted successfully")
                    else:
                        print("[SCHEDULER] ❌ Failed to post 1h signal to Telegram")
            
        except Exception as e:
            print(f"[SCHEDULER] ❌ Error in signal check: {e}")
    
    async def run_signal_monitoring(self):
        """Monitor active signals for multi-TP hits, SL hits, and breakeven alerts"""
        try:
            updates = await forex_signal_engine.monitor_active_signals()
            
            for update in updates:
                signal_id = update['id']
                event = update.get('event')
                status = update.get('status')
                pips = update.get('pips', 0)
                
                signals_data = get_forex_signals(status=None, limit=10)
                matching_signal = next((s for s in signals_data if s['id'] == signal_id), None)
                signal_type = matching_signal.get('signal_type', 'BUY') if matching_signal else 'BUY'
                
                if event == 'breakeven_alert':
                    entry_price = update.get('entry_price')
                    current_price = update.get('current_price')
                    await forex_telegram_bot.post_breakeven_alert(signal_id, entry_price, current_price)
                    print(f"[SCHEDULER] ✅ Posted breakeven alert for signal #{signal_id}")
                
                elif event == 'tp1_hit':
                    percentage = update.get('percentage', 50)
                    remaining = update.get('remaining', 50)
                    await forex_telegram_bot.post_tp_hit(signal_id, 1, pips, percentage, remaining)
                    print(f"[SCHEDULER] ✅ Posted TP1 notification for signal #{signal_id}")
                
                elif event == 'tp2_hit':
                    percentage = update.get('percentage', 30)
                    remaining = update.get('remaining', 20)
                    await forex_telegram_bot.post_tp_hit(signal_id, 2, pips, percentage, remaining)
                    print(f"[SCHEDULER] ✅ Posted TP2 notification for signal #{signal_id}")
                
                elif event == 'tp3_hit':
                    percentage = update.get('percentage', 20)
                    await forex_telegram_bot.post_tp_hit(signal_id, 3, pips, percentage, 0)
                    if status == 'won':
                        update_forex_signal_status(signal_id, 'won', pips)
                        print(f"[SCHEDULER] ✅ Signal #{signal_id} completed - all TPs hit!")
                
                elif status == 'won':
                    update_forex_signal_status(signal_id, status, pips)
                    ai_message = generate_tp_celebration(signal_id, pips, signal_type)
                    await forex_telegram_bot.post_tp_celebration(signal_id, pips, ai_message)
                    print(f"[SCHEDULER] ✅ Posted TP celebration for signal #{signal_id}")
                    
                elif status == 'lost':
                    update_forex_signal_status(signal_id, status, pips)
                    await forex_telegram_bot.post_sl_hit(signal_id, pips, signal_type)
                    print(f"[SCHEDULER] ✅ Posted SL notification for signal #{signal_id}")
                    
                elif status == 'expired':
                    update_forex_signal_status(signal_id, 'expired', pips)
                    await forex_telegram_bot.post_signal_expired(signal_id, pips, signal_type)
                    print(f"[SCHEDULER] ✅ Posted expiry notification for signal #{signal_id}")
                
                if status in ('won', 'lost', 'expired'):
                    forex_signal_engine.load_active_strategy()
                    print(f"[SCHEDULER] Strategy reloaded after signal #{signal_id} closed")
                
        except Exception as e:
            print(f"[SCHEDULER] ❌ Error in signal monitoring: {e}")
            import traceback
            traceback.print_exc()
    
    async def run_signal_guidance(self):
        """Check for and post guidance updates on active signals"""
        try:
            guidance_events = await forex_signal_engine.check_signal_guidance()
            
            for event in guidance_events:
                signal_id = event['signal_id']
                guidance_type = event['guidance_type']
                signal_type = event['signal_type']
                progress = event['progress_percent']
                current_price = event['current_price']
                entry = event['entry_price']
                tp = event['take_profit']
                sl = event['stop_loss']
                
                ai_message = generate_signal_guidance(
                    signal_id=signal_id,
                    signal_type=signal_type,
                    progress_percent=progress,
                    guidance_type=guidance_type,
                    current_price=current_price,
                    entry_price=entry,
                    tp_price=tp,
                    sl_price=sl
                )
                
                signal_data = {
                    'signal_type': signal_type,
                    'entry_price': entry,
                    'take_profit': tp,
                    'stop_loss': sl,
                    'current_price': current_price
                }
                
                success = await forex_telegram_bot.post_signal_guidance(
                    signal_id=signal_id,
                    guidance_type=guidance_type,
                    message=ai_message,
                    signal_data=signal_data
                )
                
                if success:
                    zone_value = event.get('zone_value')
                    progress_toward = event.get('progress_toward', 'tp')
                    
                    if progress_toward == 'tp':
                        update_signal_guidance(signal_id, f"{guidance_type}: {ai_message[:100]}", progress_zone=zone_value)
                    else:
                        update_signal_guidance(signal_id, f"{guidance_type}: {ai_message[:100]}", caution_zone=zone_value)
                    
                    if guidance_type == 'breakeven':
                        update_signal_breakeven(signal_id, entry)
                    
                    print(f"[SCHEDULER] ✅ Posted {guidance_type} guidance for signal #{signal_id} (zone {zone_value})")
                
        except Exception as e:
            print(f"[SCHEDULER] ❌ Error in signal guidance: {e}")
            import traceback
            traceback.print_exc()
    
    async def run_stagnant_signal_checks(self):
        """Check stagnant signals for re-validation and timeout"""
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
                    print(f"[SCHEDULER] ⚠️ Could not fetch price for revalidation of signal #{signal_id}")
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
                        print(f"[SCHEDULER] Could not fetch current indicators for timeout: {e}")
                    
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
                        update_signal_timeout_notified(signal_id)
                        # Close the signal as expired
                        if signal_type == 'BUY':
                            pips = round(current_price - entry, 2)
                        else:
                            pips = round(entry - current_price, 2)
                        update_forex_signal_status(signal_id, 'expired', pips)
                        forex_signal_engine.load_active_strategy()
                        print(f"[SCHEDULER] ✅ Posted close advisory for signal #{signal_id} after {minutes_elapsed/60:.1f}h")
                    
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
                            print(f"[SCHEDULER] Thesis status changed: {previous_status} -> {thesis_status}")
                        elif thesis_status == 'intact':
                            # Back to healthy - no need to spam
                            should_post = False
                            print(f"[SCHEDULER] Signal #{signal_id} thesis still intact - no update needed")
                        else:
                            # Still weakening/broken - don't repeat the same message
                            should_post = False
                            print(f"[SCHEDULER] Signal #{signal_id} thesis still {thesis_status} - skipping duplicate message")
                        
                        # Always update the database timestamp (for tracking), but only post if status changed
                        update_signal_revalidation(signal_id, thesis_status, f"Check: {thesis_status}")
                        
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
                                update_signal_revalidation(signal_id, thesis_status, f"Revalidation: {ai_message[:100]}")
                                print(f"[SCHEDULER] ✅ Posted revalidation ({thesis_status}) for signal #{signal_id}")
                                
                                # If thesis is broken, recommend closing
                                if thesis_status == 'broken':
                                    # Close the signal as expired with current P/L
                                    if signal_type == 'BUY':
                                        pips = round(current_price - entry, 2)
                                    else:
                                        pips = round(entry - current_price, 2)
                                    update_forex_signal_status(signal_id, 'expired', pips)
                                    forex_signal_engine.load_active_strategy()
                                    print(f"[SCHEDULER] 🚨 Signal #{signal_id} closed due to broken thesis")
                
        except Exception as e:
            print(f"[SCHEDULER] ❌ Error in stagnant signal checks: {e}")
            import traceback
            traceback.print_exc()
    
    async def check_daily_recap(self):
        """Post daily recap at 11:59 PM GMT"""
        try:
            now = datetime.utcnow()
            current_date_str = now.date().isoformat()
            
            if now.hour == 23 and now.minute >= 55:
                # Check database for last posted date (survives server restarts)
                last_posted = get_last_recap_date('daily')
                
                if last_posted != current_date_str:
                    print("[SCHEDULER] Generating daily recap...")
                    
                    ai_recap = generate_daily_recap()
                    await forex_telegram_bot.post_daily_recap(ai_recap)
                    
                    # Persist to database
                    set_last_recap_date('daily', current_date_str)
                    self.last_daily_recap = current_date_str
                    print("[SCHEDULER] ✅ Daily recap posted")
                else:
                    print("[SCHEDULER] Daily recap already posted today, skipping")
        
        except Exception as e:
            print(f"[SCHEDULER] ❌ Error posting daily recap: {e}")
    
    async def check_weekly_recap(self):
        """Post weekly recap on Sunday"""
        try:
            now = datetime.utcnow()
            
            if now.weekday() == 6 and now.hour == 23 and now.minute >= 55:
                week_number = str(now.isocalendar()[1])
                
                # Check database for last posted week (survives server restarts)
                last_posted = get_last_recap_date('weekly')
                
                if last_posted != week_number:
                    print("[SCHEDULER] Generating weekly recap...")
                    
                    ai_recap = generate_weekly_recap()
                    await forex_telegram_bot.post_weekly_recap(ai_recap)
                    
                    # Persist to database
                    set_last_recap_date('weekly', week_number)
                    self.last_weekly_recap = week_number
                    print("[SCHEDULER] ✅ Weekly recap posted")
                else:
                    print("[SCHEDULER] Weekly recap already posted this week, skipping")
        
        except Exception as e:
            print(f"[SCHEDULER] ❌ Error posting weekly recap: {e}")
    
    async def run_forever(self):
        """Main scheduler loop"""
        print("\n" + "="*60)
        print("🚀 FOREX SIGNALS SCHEDULER STARTED")
        print("="*60)
        print(f"📊 Signal checks: 15min timeframe every 15 minutes")
        print(f"📊 Signal checks: 1h timeframe every hour")
        print(f"🔍 Price monitoring: Every 1 minute")
        print(f"💡 Signal guidance: Every 1 minute (with 10min cooldown)")
        print(f"🔄 Stagnant re-validation: First at 90min, then every 30min")
        print(f"⏰ Hard timeout: 3 hours")
        print(f"📅 Daily recap: 11:59 PM GMT")
        print(f"📅 Weekly recap: Sunday 11:59 PM GMT")
        print(f"⏰ Trading hours: 8AM-10PM GMT")
        print("="*60 + "\n")
        
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
                
                await self.check_daily_recap()
                await self.check_weekly_recap()
                
                signal_check_counter += 1
                monitor_counter += 1
                
                await asyncio.sleep(self.monitor_interval)
                
            except KeyboardInterrupt:
                print("\n[SCHEDULER] Shutting down...")
                break
            except Exception as e:
                print(f"[SCHEDULER] ❌ Unexpected error: {e}")
                await asyncio.sleep(60)

forex_scheduler = ForexScheduler()

async def start_forex_scheduler():
    """Entry point to start the scheduler"""
    await forex_scheduler.run_forever()
