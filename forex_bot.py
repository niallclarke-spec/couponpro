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

⏰ Posted: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
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
            ai_message: Optional AI-generated motivational message
        """
        if not self.bot or not self.channel_id:
            return
        
        try:
            if ai_message:
                message = f"""🎉 <b>TAKE PROFIT HIT!</b> 🎉

✅ Signal #{signal_id} closed with <b>+{pips_profit:.2f} pips</b> profit!

{ai_message}
"""
            else:
                message = f"""🎉 <b>TAKE PROFIT HIT!</b> 🎉

✅ Signal #{signal_id} closed with <b>+{pips_profit:.2f} pips</b> profit!

Great trade! 🚀
"""
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='HTML'
            )
            
            print(f"✅ Posted TP celebration for signal #{signal_id}")
            
        except Exception as e:
            print(f"❌ Failed to post TP celebration: {e}")
    
    async def post_daily_recap(self, ai_recap=None):
        """
        Post daily performance recap at 11:59 PM GMT
        
        Args:
            ai_recap: Optional AI-generated recap message with signal list
        """
        if not self.bot or not self.channel_id:
            return
        
        try:
            stats = get_forex_stats_by_period(period='today')
            
            if not stats:
                print("No stats available for daily recap")
                return
            
            total_signals = stats.get('total_signals', 0)
            won_signals = stats.get('won_signals', 0)
            lost_signals = stats.get('lost_signals', 0)
            expired_signals = stats.get('expired_signals', 0)
            total_pips = stats.get('total_pips', 0)
            
            if total_signals == 0:
                message = "📊 <b>Daily Recap</b>\n\nNo signals posted today. Market conditions didn't align."
            else:
                message = f"""📊 <b>Daily Recap - {datetime.utcnow().strftime('%Y-%m-%d')}</b>

<b>Performance:</b>
✅ Won: {won_signals}
❌ Lost: {lost_signals}
⏱️ Expired: {expired_signals}
📈 Total Pips: {total_pips:+.2f}

<b>Total Signals:</b> {total_signals}
"""
                
                if ai_recap:
                    message += f"\n{ai_recap}"
            
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
            ai_recap: Optional AI-generated recap with weekly insights
        """
        if not self.bot or not self.channel_id:
            return
        
        try:
            stats = get_forex_stats_by_period(period='week')
            
            if not stats:
                print("No stats available for weekly recap")
                return
            
            total_signals = stats.get('total_signals', 0)
            won_signals = stats.get('won_signals', 0)
            lost_signals = stats.get('lost_signals', 0)
            total_pips = stats.get('total_pips', 0)
            
            if total_signals == 0:
                message = "📊 <b>Weekly Recap</b>\n\nNo signals this week."
            else:
                win_rate = (won_signals / total_signals * 100) if total_signals > 0 else 0
                
                message = f"""📊 <b>Weekly Recap</b>

<b>This Week's Performance:</b>
✅ Won: {won_signals}
❌ Lost: {lost_signals}
📊 Win Rate: {win_rate:.1f}%
📈 Total Pips: {total_pips:+.2f}

<b>Total Signals:</b> {total_signals}
"""
                
                if ai_recap:
                    message += f"\n{ai_recap}"
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='HTML'
            )
            
            print(f"✅ Posted weekly recap")
            
        except Exception as e:
            print(f"❌ Failed to post weekly recap: {e}")

forex_telegram_bot = ForexTelegramBot()
