"""
Telegram bot for posting forex signals to channel
Uses python-telegram-bot library
"""
import os
import asyncio
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError
from db import create_forex_signal, get_forex_signals, get_forex_stats_by_period

class ForexTelegramBot:
    def __init__(self):
        self.token = os.environ.get('FOREX_BOT_TOKEN')
        self.channel_id = os.environ.get('FOREX_CHANNEL_ID')
        self.bot = None
        
        if self.token:
            self.bot = Bot(token=self.token)
        else:
            print("⚠️  FOREX_BOT_TOKEN not set - forex bot will not work")
        
        if not self.channel_id:
            print("⚠️  FOREX_CHANNEL_ID not set - forex bot will not work")
    
    async def post_signal(self, signal_data):
        """
        Post a trading signal to the Telegram channel
        
        Args:
            signal_data: dict with signal_type, pair, entry_price, take_profit, stop_loss, etc.
        
        Returns:
            int: Signal ID from database or None if failed
        """
        if not self.bot or not self.channel_id:
            print("❌ Forex bot not configured properly")
            return None
        
        try:
            signal_type = signal_data['signal_type']
            pair = signal_data['pair']
            entry = signal_data['entry_price']
            tp = signal_data['take_profit']
            sl = signal_data['stop_loss']
            rsi = signal_data['rsi_value']
            macd = signal_data['macd_value']
            atr = signal_data['atr_value']
            timeframe = signal_data.get('timeframe', '15min')
            
            emoji = '🟢' if signal_type == 'BUY' else '🔴'
            
            message = f"""{emoji} <b>{signal_type} SIGNAL</b> {emoji}

<b>Pair:</b> {pair}
<b>Timeframe:</b> {timeframe}

💰 <b>Entry:</b> ${entry:.2f}
🎯 <b>Take Profit:</b> ${tp:.2f}
🛡️ <b>Stop Loss:</b> ${sl:.2f}

<b>Technical Analysis:</b>
📊 RSI: {rsi:.2f}
📈 MACD: {macd:.4f}
📉 ATR: {atr:.2f}
"""
            
            sent_message = await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='HTML'
            )
            
            signal_id = create_forex_signal(
                signal_type=signal_type,
                pair=pair,
                timeframe=timeframe,
                entry_price=entry,
                take_profit=tp,
                stop_loss=sl,
                rsi_value=rsi,
                macd_value=macd,
                atr_value=atr
            )
            
            print(f"✅ Posted {signal_type} signal to Telegram (ID: {signal_id})")
            return signal_id
            
        except TelegramError as e:
            print(f"❌ Failed to post signal to Telegram: {e}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error posting signal: {e}")
            return None
    
    async def post_tp_celebration(self, signal_id, pips_profit, ai_message=None):
        """
        Post a celebration message when Take Profit is hit
        
        Args:
            signal_id: Database signal ID
            pips_profit: Profit in pips
            ai_message: Optional AI-generated motivational message (ignored)
        """
        if not self.bot or not self.channel_id:
            return
        
        try:
            message = f"""Take Profit Hit 🎉

<b>+{pips_profit:.2f} pips</b>"""
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='HTML'
            )
            
            print(f"✅ Posted TP celebration for signal #{signal_id}")
            
        except Exception as e:
            print(f"❌ Failed to post TP celebration: {e}")
    
    async def post_sl_hit(self, signal_id, pips_loss, signal_type='BUY'):
        """
        Post a message when Stop Loss is hit
        
        Args:
            signal_id: Database signal ID
            pips_loss: Loss in pips (should be negative)
            signal_type: 'BUY' or 'SELL'
        """
        if not self.bot or not self.channel_id:
            return
        
        try:
            message = f"""Stop Loss Hit

<b>{pips_loss:.2f} pips</b>

Risk was managed. Onwards to the next opportunity."""
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='HTML'
            )
            
            print(f"✅ Posted SL notification for signal #{signal_id}")
            
        except Exception as e:
            print(f"❌ Failed to post SL notification: {e}")
    
    async def post_signal_expired(self, signal_id, pips, signal_type='BUY'):
        """
        Post a message when signal expires (timeout)
        
        Args:
            signal_id: Database signal ID
            pips: Current P/L in pips
            signal_type: 'BUY' or 'SELL'
        """
        if not self.bot or not self.channel_id:
            return
        
        try:
            result_text = "profit" if pips > 0 else "loss" if pips < 0 else "breakeven"
            message = f"""Trade Closed (Timeout)

<b>{pips:+.2f} pips</b> {result_text}

Signal closed after maximum hold time."""
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='HTML'
            )
            
            print(f"✅ Posted expiry notification for signal #{signal_id}")
            
        except Exception as e:
            print(f"❌ Failed to post expiry notification: {e}")
    
    async def post_daily_recap(self, ai_recap=None):
        """
        Post daily performance recap at 11:59 PM GMT
        
        Args:
            ai_recap: Optional AI-generated recap message (ignored)
        """
        if not self.bot or not self.channel_id:
            return
        
        try:
            from db import get_forex_signals_by_period
            
            signals_today = get_forex_signals_by_period(period='today')
            
            if not signals_today or len(signals_today) == 0:
                message = "📊 <b>Daily Recap</b>\n\nNo signals posted today."
            else:
                stats = get_forex_stats_by_period(period='today')
                total_pips = stats.get('total_pips', 0)
                
                # Build signal list
                signal_lines = []
                for signal in signals_today:
                    entry = signal.get('entry_price', 0)
                    posted_at = datetime.fromisoformat(signal['posted_at'])
                    time_str = posted_at.strftime('%H:%M')
                    
                    if signal['status'] == 'won':
                        pips = signal.get('result_pips', 0)
                        signal_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ✅ +{pips:.2f}")
                    elif signal['status'] == 'lost':
                        pips = signal.get('result_pips', 0)
                        signal_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ❌ {pips:.2f}")
                    elif signal['status'] == 'pending':
                        signal_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ⏳")
                    elif signal['status'] == 'expired':
                        signal_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ⏱️")
                
                signal_list = "\n".join(signal_lines)
                
                message = f"""📊 <b>Daily Recap - {datetime.utcnow().strftime('%b %d')}</b>

{signal_list}

<b>Total: {total_pips:+.2f} pips</b>"""
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='HTML'
            )
            
            print(f"✅ Posted daily recap")
            
        except Exception as e:
            print(f"❌ Failed to post daily recap: {e}")
    
    async def post_weekly_recap(self, ai_recap=None):
        """
        Post weekly performance recap on Sunday
        
        Args:
            ai_recap: Optional AI-generated recap (ignored)
        """
        if not self.bot or not self.channel_id:
            return
        
        try:
            from db import get_forex_signals_by_period
            from collections import defaultdict
            
            signals_week = get_forex_signals_by_period(period='week')
            
            if not signals_week or len(signals_week) == 0:
                message = "📊 <b>Weekly Recap</b>\n\nNo signals this week."
            else:
                stats = get_forex_stats_by_period(period='week')
                total_pips = stats.get('total_pips', 0)
                
                # Group signals by day
                signals_by_day = defaultdict(list)
                for signal in signals_week:
                    posted_at = datetime.fromisoformat(signal['posted_at'])
                    day_key = posted_at.strftime('%b %d')
                    signals_by_day[day_key].append(signal)
                
                # Build message with daily breakdown
                message_lines = ["📊 <b>Weekly Recap</b>\n"]
                
                for day in sorted(signals_by_day.keys()):
                    day_signals = signals_by_day[day]
                    message_lines.append(f"<b>{day}</b>")
                    
                    for signal in day_signals:
                        entry = signal.get('entry_price', 0)
                        posted_at = datetime.fromisoformat(signal['posted_at'])
                        time_str = posted_at.strftime('%H:%M')
                        
                        if signal['status'] == 'won':
                            pips = signal.get('result_pips', 0)
                            message_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ✅ +{pips:.2f}")
                        elif signal['status'] == 'lost':
                            pips = signal.get('result_pips', 0)
                            message_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ❌ {pips:.2f}")
                        elif signal['status'] == 'pending':
                            message_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ⏳")
                        elif signal['status'] == 'expired':
                            message_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ⏱️")
                    
                    message_lines.append("")  # Blank line between days
                
                message_lines.append(f"<b>Weekly Total: {total_pips:+.2f} pips</b>")
                message = "\n".join(message_lines)
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='HTML'
            )
            
            print(f"✅ Posted weekly recap")
            
        except Exception as e:
            print(f"❌ Failed to post weekly recap: {e}")

forex_telegram_bot = ForexTelegramBot()
