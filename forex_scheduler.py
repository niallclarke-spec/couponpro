"""
Forex signals scheduler
Runs signal checks every 15 minutes and monitors active signals
Handles daily/weekly recaps at scheduled times
"""
import asyncio
from datetime import datetime, time
from forex_signals import forex_signal_engine
from forex_bot import forex_telegram_bot
from forex_ai import generate_tp_celebration, generate_daily_recap, generate_weekly_recap
from db import update_forex_signal_status, get_forex_signals

class ForexScheduler:
    def __init__(self):
        self.signal_check_interval = 900
        self.monitor_interval = 300
        self.last_daily_recap = None
        self.last_weekly_recap = None
    
    async def run_signal_check(self):
        """Check for new signals and post to Telegram if found"""
        try:
            if not forex_signal_engine.is_trading_hours():
                print("[SCHEDULER] Outside trading hours (8AM-10PM GMT), skipping signal check")
                return
            
            # CRITICAL: Only allow ONE active signal at a time
            # Check for any pending signals before generating new ones
            pending_signals = get_forex_signals(status='pending')
            if pending_signals and len(pending_signals) > 0:
                signal = pending_signals[0]
                print(f"[SCHEDULER] ⏸️ Active signal #{signal['id']} still pending - skipping new signal check")
                print(f"[SCHEDULER] Entry: ${signal['entry_price']}, TP: ${signal['take_profit']}, SL: ${signal['stop_loss']}")
                return
            
            signal_data = await forex_signal_engine.check_for_signals(timeframe='15min')
            
            if signal_data:
                signal_id = await forex_telegram_bot.post_signal(signal_data)
                
                if signal_id:
                    print(f"[SCHEDULER] ✅ New signal #{signal_id} posted successfully")
                else:
                    print("[SCHEDULER] ❌ Failed to post signal to Telegram")
            
        except Exception as e:
            print(f"[SCHEDULER] ❌ Error in signal check: {e}")
    
    async def run_signal_monitoring(self):
        """Monitor active signals for TP/SL hits"""
        try:
            updates = await forex_signal_engine.monitor_active_signals()
            
            for update in updates:
                signal_id = update['id']
                status = update['status']
                pips = update['pips']
                
                update_forex_signal_status(signal_id, status, pips)
                
                signals_data = get_forex_signals(status=None, limit=10)
                matching_signal = next((s for s in signals_data if s['id'] == signal_id), None)
                signal_type = matching_signal.get('signal_type', 'BUY') if matching_signal else 'BUY'
                
                if status == 'won':
                    ai_message = generate_tp_celebration(signal_id, pips, signal_type)
                    await forex_telegram_bot.post_tp_celebration(signal_id, pips, ai_message)
                    print(f"[SCHEDULER] ✅ Posted TP celebration for signal #{signal_id}")
                    
                elif status == 'lost':
                    await forex_telegram_bot.post_sl_hit(signal_id, pips, signal_type)
                    print(f"[SCHEDULER] ✅ Posted SL notification for signal #{signal_id}")
                    
                elif status == 'expired':
                    await forex_telegram_bot.post_signal_expired(signal_id, pips, signal_type)
                    print(f"[SCHEDULER] ✅ Posted expiry notification for signal #{signal_id}")
                
        except Exception as e:
            print(f"[SCHEDULER] ❌ Error in signal monitoring: {e}")
            import traceback
            traceback.print_exc()
    
    async def check_daily_recap(self):
        """Post daily recap at 11:59 PM GMT"""
        try:
            now = datetime.utcnow()
            current_date = now.date()
            
            if now.hour == 23 and now.minute >= 55:
                if self.last_daily_recap != current_date:
                    print("[SCHEDULER] Generating daily recap...")
                    
                    ai_recap = generate_daily_recap()
                    await forex_telegram_bot.post_daily_recap(ai_recap)
                    
                    self.last_daily_recap = current_date
                    print("[SCHEDULER] ✅ Daily recap posted")
        
        except Exception as e:
            print(f"[SCHEDULER] ❌ Error posting daily recap: {e}")
    
    async def check_weekly_recap(self):
        """Post weekly recap on Sunday"""
        try:
            now = datetime.utcnow()
            
            if now.weekday() == 6 and now.hour == 23 and now.minute >= 55:
                week_number = now.isocalendar()[1]
                
                if self.last_weekly_recap != week_number:
                    print("[SCHEDULER] Generating weekly recap...")
                    
                    ai_recap = generate_weekly_recap()
                    await forex_telegram_bot.post_weekly_recap(ai_recap)
                    
                    self.last_weekly_recap = week_number
                    print("[SCHEDULER] ✅ Weekly recap posted")
        
        except Exception as e:
            print(f"[SCHEDULER] ❌ Error posting weekly recap: {e}")
    
    async def run_forever(self):
        """Main scheduler loop"""
        print("\n" + "="*60)
        print("🚀 FOREX SIGNALS SCHEDULER STARTED")
        print("="*60)
        print(f"📊 Signal checks: Every 15 minutes (during 8AM-10PM GMT)")
        print(f"🔍 Price monitoring: Every 5 minutes")
        print(f"📅 Daily recap: 11:59 PM GMT")
        print(f"📅 Weekly recap: Sunday 11:59 PM GMT")
        print("="*60 + "\n")
        
        signal_check_counter = 0
        monitor_counter = 0
        
        while True:
            try:
                if signal_check_counter % (self.signal_check_interval // self.monitor_interval) == 0:
                    await self.run_signal_check()
                
                await self.run_signal_monitoring()
                
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
