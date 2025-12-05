"""
Signal Bot Scheduler
Manages signal generation, monitoring, and Telegram posting
Uses the active bot strategy and enforces one-signal-at-a-time rule
"""
import os
import asyncio
from datetime import datetime
from typing import Optional
from telegram import Bot
from telegram.error import TelegramError

from bots.core.bot_manager import bot_manager
from bots.core.signal_generator import signal_generator
from bots.core.price_monitor import price_monitor
from bots.core.ai_guidance import ai_guidance
from db import (
    update_forex_signal_status,
    get_forex_signals_by_period,
    get_forex_stats_by_period
)


class SignalBotScheduler:
    """
    Main scheduler for the signal bot system
    
    Intervals:
    - Signal check: Every 15 minutes (during trading hours)
    - Price monitoring: Every 5 minutes
    - Daily recap: 11:59 PM GMT
    - Weekly recap: Sunday 11:59 PM GMT
    """
    
    def __init__(self):
        self.signal_check_interval = 900
        self.monitor_interval = 300
        self.last_daily_recap = None
        self.last_weekly_recap = None
        
        self.bot = None
        self.channel_id = os.environ.get('FOREX_CHANNEL_ID')
        
        token = os.environ.get('FOREX_BOT_TOKEN')
        if token:
            self.bot = Bot(token=token)
        else:
            print("[SCHEDULER] FOREX_BOT_TOKEN not set")
    
    async def post_to_telegram(self, message: str, parse_mode: str = 'HTML') -> Optional[int]:
        """Post message to Telegram channel, return message ID"""
        if not self.bot or not self.channel_id:
            print("[SCHEDULER] Telegram not configured")
            return None
        
        try:
            sent = await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode=parse_mode
            )
            return sent.message_id
        except TelegramError as e:
            print(f"[SCHEDULER] Telegram error: {e}")
            return None
    
    async def run_signal_check(self):
        """Check for new signals using active bot strategy"""
        try:
            strategy = bot_manager.get_active_strategy()
            
            if not strategy.is_trading_hours():
                print(f"[SCHEDULER] Outside trading hours, skipping signal check")
                return
            
            if not bot_manager.can_generate_signal():
                print(f"[SCHEDULER] Signal already open, skipping generation")
                return
            
            signal_data = await signal_generator.generate_signal()
            
            if signal_data:
                message = self._format_signal_message(signal_data)
                message_id = await self.post_to_telegram(message)
                
                if message_id and signal_data.get('id'):
                    signal_generator.update_telegram_message_id(signal_data['id'], message_id)
                    print(f"[SCHEDULER] Signal #{signal_data['id']} posted (msg: {message_id})")
                    
        except Exception as e:
            print(f"[SCHEDULER] Signal check error: {e}")
            import traceback
            traceback.print_exc()
    
    async def run_price_monitoring(self):
        """Monitor open signal for TP/SL hits and provide guidance"""
        try:
            result = await price_monitor.check_signal_status()
            
            if not result:
                return
            
            action = result['action']
            signal_id = result['signal_id']
            
            if action in ['tp_hit', 'sl_hit', 'timeout_close']:
                price_monitor.close_signal(
                    signal_id, 
                    result['status'], 
                    result['pips']
                )
                
                message = ai_guidance.generate_close_message(result)
                await self.post_to_telegram(message)
                
                if action == 'tp_hit':
                    await self._post_celebration(result['pips'])
                    
            elif action == 'breakeven_guidance':
                price_monitor.apply_breakeven(signal_id, result['entry'])
                
                message = ai_guidance.generate_breakeven_guidance(result)
                await self.post_to_telegram(message)
                
                note = f"Breakeven applied at {result['entry']:.2f} after {result['hours_elapsed']:.1f}h"
                price_monitor.add_guidance_note(signal_id, note)
                
            elif action == 'mid_trade_update':
                message = ai_guidance.generate_mid_trade_update(result)
                await self.post_to_telegram(message)
                
                note = f"Mid-trade update at {result['hours_elapsed']:.1f}h"
                price_monitor.add_guidance_note(signal_id, note)
                
        except Exception as e:
            print(f"[SCHEDULER] Monitoring error: {e}")
            import traceback
            traceback.print_exc()
    
    async def _post_celebration(self, pips: float):
        """Post TP hit celebration"""
        message = f"<b>Take Profit Hit!</b>\n\n+{pips:.2f} pips secured."
        await self.post_to_telegram(message)
    
    def _format_signal_message(self, signal_data: dict) -> str:
        """Format signal for Telegram posting"""
        signal_type = signal_data['signal_type']
        pair = signal_data['pair']
        entry = signal_data['entry_price']
        tp = signal_data['take_profit']
        sl = signal_data['stop_loss']
        bot_type = signal_data.get('bot_type', 'aggressive')
        timeframe = signal_data.get('timeframe', '15min')
        
        emoji = '🟢' if signal_type == 'BUY' else '🔴'
        bot_label = bot_type.capitalize()
        
        return f"""{emoji} <b>{signal_type} SIGNAL</b> {emoji}

<b>Pair:</b> {pair}
<b>Strategy:</b> {bot_label}
<b>Timeframe:</b> {timeframe}

<b>Entry:</b> ${entry:.2f}
<b>Take Profit:</b> ${tp:.2f}
<b>Stop Loss:</b> ${sl:.2f}

<i>Signal will be monitored with AI guidance until closed.</i>"""
    
    async def check_daily_recap(self):
        """Post daily recap at 11:59 PM GMT"""
        try:
            now = datetime.utcnow()
            current_date = now.date()
            
            if now.hour == 23 and now.minute >= 55:
                if self.last_daily_recap != current_date:
                    await self._post_daily_recap()
                    self.last_daily_recap = current_date
                    
        except Exception as e:
            print(f"[SCHEDULER] Daily recap error: {e}")
    
    async def _post_daily_recap(self):
        """Generate and post daily recap"""
        try:
            signals = get_forex_signals_by_period(period='today')
            stats = get_forex_stats_by_period(period='today')
            
            if not signals:
                message = "<b>Daily Recap</b>\n\nNo signals posted today."
            else:
                wins = sum(1 for s in signals if s['status'] == 'won')
                losses = sum(1 for s in signals if s['status'] == 'lost')
                total_pips = stats.get('total_pips', 0)
                win_rate = (wins / len(signals) * 100) if signals else 0
                
                recap_stats = {
                    'total_signals': len(signals),
                    'wins': wins,
                    'losses': losses,
                    'net_pips': total_pips,
                    'win_rate': win_rate
                }
                
                ai_recap = ai_guidance.generate_daily_recap(recap_stats)
                
                signal_lines = []
                for s in signals:
                    entry = s.get('entry_price', 0)
                    pips = s.get('result_pips', 0) or 0
                    status_icon = '✅' if s['status'] == 'won' else '❌' if s['status'] == 'lost' else '⏳'
                    signal_lines.append(f"{s['signal_type']} @ ${entry:.2f} {status_icon} {pips:+.2f}")
                
                message = f"""<b>Daily Recap - {datetime.utcnow().strftime('%b %d')}</b>

{chr(10).join(signal_lines)}

<b>Results:</b> {wins}W / {losses}L | {total_pips:+.2f} pips | {win_rate:.0f}% WR

{ai_recap or ''}"""
            
            await self.post_to_telegram(message)
            print("[SCHEDULER] Daily recap posted")
            
        except Exception as e:
            print(f"[SCHEDULER] Daily recap error: {e}")
    
    async def check_weekly_recap(self):
        """Post weekly recap on Sunday at 11:59 PM GMT"""
        try:
            now = datetime.utcnow()
            
            if now.weekday() == 6 and now.hour == 23 and now.minute >= 55:
                week_number = now.isocalendar()[1]
                
                if self.last_weekly_recap != week_number:
                    await self._post_weekly_recap()
                    self.last_weekly_recap = week_number
                    
        except Exception as e:
            print(f"[SCHEDULER] Weekly recap error: {e}")
    
    async def _post_weekly_recap(self):
        """Generate and post weekly recap"""
        try:
            signals = get_forex_signals_by_period(period='week')
            stats = get_forex_stats_by_period(period='week')
            
            if not signals:
                message = "<b>Weekly Recap</b>\n\nNo signals this week."
            else:
                wins = sum(1 for s in signals if s['status'] == 'won')
                losses = sum(1 for s in signals if s['status'] == 'lost')
                total_pips = stats.get('total_pips', 0)
                win_rate = (wins / len(signals) * 100) if signals else 0
                
                recap_stats = {
                    'total_signals': len(signals),
                    'wins': wins,
                    'losses': losses,
                    'net_pips': total_pips,
                    'win_rate': win_rate
                }
                
                ai_recap = ai_guidance.generate_weekly_recap(recap_stats)
                
                message = f"""<b>Weekly Recap</b>

<b>Performance:</b>
Signals: {len(signals)}
Wins: {wins} | Losses: {losses}
Net Pips: {total_pips:+.2f}
Win Rate: {win_rate:.0f}%

{ai_recap or ''}"""
            
            await self.post_to_telegram(message)
            print("[SCHEDULER] Weekly recap posted")
            
        except Exception as e:
            print(f"[SCHEDULER] Weekly recap error: {e}")
    
    async def run_forever(self):
        """Main scheduler loop"""
        print("\n" + "=" * 60)
        print("SIGNAL BOT SCHEDULER STARTED")
        print("=" * 60)
        print(f"Active Bot: {bot_manager.get_active_bot_name().upper()}")
        print(f"Signal checks: Every 15 minutes (trading hours)")
        print(f"Price monitoring: Every 5 minutes")
        print(f"One signal at a time: Enabled")
        print(f"Breakeven: At 4 hours")
        print(f"Auto-close: At 5 hours")
        print("=" * 60 + "\n")
        
        counter = 0
        
        while True:
            try:
                if counter % 3 == 0:
                    await self.run_signal_check()
                
                await self.run_price_monitoring()
                
                await self.check_daily_recap()
                await self.check_weekly_recap()
                
                counter += 1
                await asyncio.sleep(self.monitor_interval)
                
            except KeyboardInterrupt:
                print("\n[SCHEDULER] Shutting down...")
                break
            except Exception as e:
                print(f"[SCHEDULER] Error: {e}")
                await asyncio.sleep(60)


signal_bot_scheduler = SignalBotScheduler()


async def start_signal_bot_scheduler():
    """Entry point to start the scheduler"""
    await signal_bot_scheduler.run_forever()
