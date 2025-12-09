"""
Telegram bot for posting forex signals to channel
Uses python-telegram-bot library
"""
import os
import asyncio
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError
from db import create_forex_signal, get_forex_signals, get_forex_stats_by_period, update_signal_original_indicators, add_signal_narrative

def get_forex_bot_token():
    """
    Get the appropriate forex bot token based on environment.
    - Dev (Replit): Uses ENTRYLAB_TEST_BOT for testing
    - Prod: Uses FOREX_BOT_TOKEN for live signals
    """
    # Check if running in Replit (dev environment)
    is_replit = os.environ.get('REPL_ID') or os.environ.get('REPLIT')
    
    if is_replit:
        # Dev: Use test bot
        test_token = os.environ.get('ENTRYLAB_TEST_BOT')
        if test_token:
            print("[FOREX BOT] 🧪 Using ENTRYLAB_TEST_BOT (dev mode)")
            return test_token
        else:
            print("[FOREX BOT] ⚠️ ENTRYLAB_TEST_BOT not set, falling back to FOREX_BOT_TOKEN")
    
    # Prod: Use real bot
    return os.environ.get('FOREX_BOT_TOKEN')

def get_forex_channel_id():
    """
    Get the appropriate channel ID based on environment.
    - Dev (Replit): Uses test channel
    - Prod: Uses real forex channel
    """
    # Check if running in Replit (dev environment)
    is_replit = os.environ.get('REPL_ID') or os.environ.get('REPLIT')
    
    if is_replit:
        # Dev: Use test channel
        test_channel = "-1003343226469"  # EntryLab test channel
        print(f"[FOREX BOT] 🧪 Using test channel (dev mode)")
        return test_channel
    
    # Prod: Use real channel
    return os.environ.get('FOREX_CHANNEL_ID')

class ForexTelegramBot:
    def __init__(self):
        self.token = get_forex_bot_token()
        self.channel_id = get_forex_channel_id()
        self.bot = None
        
        if self.token:
            self.bot = Bot(token=self.token)
        else:
            print("⚠️  Forex bot token not set - forex bot will not work")
        
        if not self.channel_id:
            print("⚠️  Forex channel ID not set - forex bot will not work")
    
    async def post_signal(self, signal_data):
        """
        Post a trading signal to the Telegram channel with multi-TP support
        
        Args:
            signal_data: dict with signal_type, pair, entry_price, take_profit, stop_loss, etc.
                        Supports take_profit_2, take_profit_3 for multi-TP
        
        Returns:
            int: Signal ID from database or None if failed
        """
        if not self.bot or not self.channel_id:
            print("❌ Forex bot not configured properly")
            return None
        
        try:
            pending_signals = get_forex_signals(status='pending')
            if pending_signals and len(pending_signals) > 0:
                existing = pending_signals[0]
                print(f"❌ Cannot post new signal - signal #{existing['id']} is still pending")
                print(f"   Entry: ${existing['entry_price']}, created at: {existing.get('posted_at')}")
                return None
            
            signal_type = signal_data['signal_type']
            pair = signal_data['pair']
            entry = signal_data['entry_price']
            tp1 = signal_data['take_profit']
            tp2 = signal_data.get('take_profit_2')
            tp3 = signal_data.get('take_profit_3')
            sl = signal_data['stop_loss']
            rsi = signal_data['rsi_value']
            macd = signal_data['macd_value']
            atr = signal_data['atr_value']
            timeframe = signal_data.get('timeframe', '15min')
            
            tp1_pct = signal_data.get('tp1_percentage', 50)
            tp2_pct = signal_data.get('tp2_percentage', 30)
            tp3_pct = signal_data.get('tp3_percentage', 20)
            
            emoji = '🟢' if signal_type == 'BUY' else '🔴'
            
            tp_section = f"🎯 <b>TP1:</b> ${tp1:.2f} ({tp1_pct}%)"
            if tp2:
                tp_section += f"\n🎯 <b>TP2:</b> ${tp2:.2f} ({tp2_pct}%)"
            if tp3:
                tp_section += f"\n🎯 <b>TP3:</b> ${tp3:.2f} ({tp3_pct}%)"
            
            message = f"""{emoji} <b>{signal_type} SIGNAL</b> {emoji}

<b>Pair:</b> {pair}
<b>Timeframe:</b> {timeframe}

💰 <b>Entry:</b> ${entry:.2f}

{tp_section}

🛡️ <b>Stop Loss:</b> ${sl:.2f}

📊 RSI: {rsi:.2f} | MACD: {macd:.4f}
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
                take_profit=tp1,
                stop_loss=sl,
                rsi_value=rsi,
                macd_value=macd,
                atr_value=atr,
                take_profit_2=tp2,
                take_profit_3=tp3,
                tp1_percentage=tp1_pct,
                tp2_percentage=tp2_pct,
                tp3_percentage=tp3_pct
            )
            
            # Store original indicator values for re-validation using config-driven approach
            # Use the all_indicators dict from signal_data if available
            indicators_dict = signal_data.get('all_indicators', {})
            if not indicators_dict:
                # Fallback to building from individual values
                indicators_dict = {
                    'rsi': rsi,
                    'macd': macd,
                    'adx': signal_data.get('adx_value'),
                    'stochastic': signal_data.get('stoch_k_value'),
                    'atr': atr
                }
            # Remove None values
            indicators_dict = {k: v for k, v in indicators_dict.items() if v is not None}
            
            if signal_id and indicators_dict:
                update_signal_original_indicators(signal_id, indicators_dict=indicators_dict)
                print(f"✅ Stored original indicators for signal #{signal_id}: {list(indicators_dict.keys())}")
                
                # Record entry narrative event
                add_signal_narrative(
                    signal_id=signal_id,
                    event_type='entry',
                    current_price=entry,
                    progress_percent=0,
                    indicators=indicators_dict,
                    notes=f"{signal_type} signal entry at ${entry:.2f}"
                )
            
            print(f"✅ Posted {signal_type} signal to Telegram (ID: {signal_id})")
            return signal_id
            
        except TelegramError as e:
            print(f"❌ Failed to post signal to Telegram: {e}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error posting signal: {e}")
            return None
    
    async def post_tp_hit(self, signal_id, tp_number, pips_profit, position_percentage, remaining_percentage=None):
        """
        Post notification when an individual TP is hit (multi-TP system)
        
        Args:
            signal_id: Database signal ID
            tp_number: 1, 2, or 3
            pips_profit: Profit in pips for this TP
            position_percentage: Percentage of position closed at this TP
            remaining_percentage: Percentage of position still open (optional)
        """
        if not self.bot or not self.channel_id:
            return
        
        try:
            if tp_number == 1:
                emoji = "✅"
                status_msg = f"🔄 Remaining: {remaining_percentage}% still in play" if remaining_percentage else ""
            elif tp_number == 2:
                emoji = "✅✅"
                status_msg = f"🔄 Remaining: {remaining_percentage}% riding to TP3" if remaining_percentage else ""
            else:
                emoji = "🎯🎉"
                status_msg = "Full position closed!"
            
            message = f"""{emoji} <b>TP{tp_number} HIT!</b>

<b>+${pips_profit:.2f}</b> ({position_percentage}% closed)

{status_msg}"""
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='HTML'
            )
            
            add_signal_narrative(
                signal_id=signal_id,
                event_type=f'tp{tp_number}_hit',
                notes=f"TP{tp_number} hit: +${pips_profit:.2f} ({position_percentage}% closed)"
            )
            
            print(f"✅ Posted TP{tp_number} notification for signal #{signal_id}")
            
        except Exception as e:
            print(f"❌ Failed to post TP{tp_number} notification: {e}")
    
    async def post_breakeven_alert(self, signal_id, entry_price, current_price):
        """
        Post breakeven alert when price reaches 70% toward TP1
        
        Args:
            signal_id: Database signal ID
            entry_price: Original entry price
            current_price: Current price
        """
        if not self.bot or not self.channel_id:
            return
        
        try:
            pips_profit = abs(current_price - entry_price)
            
            message = f"""⚡ <b>BREAKEVEN ALERT</b>

📈 Price at 70% toward TP1!

💰 Current: <b>+{pips_profit:.1f} pips</b>

🔒 Move SL to entry @ ${entry_price:.2f}"""
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='HTML'
            )
            
            add_signal_narrative(
                signal_id=signal_id,
                event_type='breakeven_alert',
                current_price=current_price,
                notes=f"Breakeven alert at ${current_price:.2f}, +${dollar_profit:.2f}"
            )
            
            print(f"✅ Posted breakeven alert for signal #{signal_id}")
            
        except Exception as e:
            print(f"❌ Failed to post breakeven alert: {e}")
    
    async def post_tp_celebration(self, signal_id, pips_profit, ai_message=None):
        """
        Post a celebration message when all Take Profits are hit (legacy support)
        
        Args:
            signal_id: Database signal ID
            pips_profit: Total profit in pips
            ai_message: Optional AI-generated motivational message (ignored)
        """
        if not self.bot or not self.channel_id:
            return
        
        try:
            message = f"""🎉 <b>TRADE COMPLETE!</b> 🎉

Total profit: <b>+${pips_profit:.2f}</b>"""
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='HTML'
            )
            
            add_signal_narrative(
                signal_id=signal_id,
                event_type='tp_hit',
                progress_percent=100,
                notes=f"Trade complete: +${pips_profit:.2f}"
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

<b>${abs(pips_loss):.2f} loss</b>

Risk was managed. Onwards to the next opportunity."""
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='HTML'
            )
            
            # Record SL hit narrative event
            add_signal_narrative(
                signal_id=signal_id,
                event_type='sl_hit',
                progress_percent=-100,
                notes=f"Stop loss hit: -${abs(pips_loss):.2f}"
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
            dollar_display = f"+${pips:.2f}" if pips > 0 else f"-${abs(pips):.2f}" if pips < 0 else "$0.00"
            message = f"""Trade Closed (Timeout)

<b>{dollar_display}</b> {result_text}

Signal closed after maximum hold time."""
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode='HTML'
            )
            
            print(f"✅ Posted expiry notification for signal #{signal_id}")
            
        except Exception as e:
            print(f"❌ Failed to post expiry notification: {e}")
    
    async def post_signal_guidance(self, signal_id, guidance_type, message, signal_data):
        """
        Post a guidance update for an active signal.
        
        Args:
            signal_id: Database signal ID
            guidance_type: 'progress', 'breakeven', 'caution', 'decision'
            message: AI-generated or fallback guidance message
            signal_data: Dict with current signal info (entry, tp, sl, current_price)
        """
        if not self.bot or not self.channel_id:
            return False
        
        try:
            entry = signal_data.get('entry_price', 0)
            current = signal_data.get('current_price', 0)
            tp = signal_data.get('take_profit', 0)
            sl = signal_data.get('stop_loss', 0)
            signal_type = signal_data.get('signal_type', 'BUY')
            
            type_headers = {
                'progress': '📊 <b>Signal Update</b>',
                'breakeven': '🔒 <b>Breakeven Advisory</b>',
                'caution': '⚠️ <b>Position Alert</b>',
                'decision': '📉 <b>Decision Point</b>'
            }
            
            header = type_headers.get(guidance_type, '📊 <b>Signal Update</b>')
            
            full_message = f"""{header}
<b>Signal #{signal_id}</b> | {signal_type}

{message}

<b>Current:</b> ${current:.2f}
<b>Entry:</b> ${entry:.2f} | <b>TP:</b> ${tp:.2f} | <b>SL:</b> ${sl:.2f}"""
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=full_message,
                parse_mode='HTML'
            )
            
            # Calculate progress toward TP for narrative
            progress = signal_data.get('progress_percent', 0)
            current_indicators = signal_data.get('current_indicators', {})
            indicator_deltas = signal_data.get('indicator_deltas', {})
            
            # Record guidance narrative event
            add_signal_narrative(
                signal_id=signal_id,
                event_type='guidance_sent',
                current_price=current,
                progress_percent=progress,
                indicators=current_indicators if current_indicators else None,
                indicator_deltas=indicator_deltas if indicator_deltas else None,
                guidance_type=guidance_type,
                message_sent=message[:500] if message else None,
                notes=f"{guidance_type.title()} guidance at {progress:.1f}% progress"
            )
            
            print(f"✅ Posted {guidance_type} guidance for signal #{signal_id}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to post signal guidance: {e}")
            return False
    
    async def post_revalidation_update(self, signal_id, thesis_status, message, current_price, entry_price):
        """
        Post a thesis re-validation update for a stagnant signal.
        
        Args:
            signal_id: Database signal ID
            thesis_status: 'intact', 'weakening', or 'broken'
            message: AI-generated revalidation message
            current_price: Current market price
            entry_price: Signal entry price
        """
        if not self.bot or not self.channel_id:
            return False
        
        try:
            status_headers = {
                'intact': '📊 <b>Trade Status - Thesis Intact</b>',
                'weakening': '⚠️ <b>Trade Status - Momentum Weakening</b>',
                'broken': '🚨 <b>Trade Alert - Thesis Invalidated</b>'
            }
            
            header = status_headers.get(thesis_status, '📊 <b>Trade Status</b>')
            
            full_message = f"""{header}
<b>Signal #{signal_id}</b>

{message}

<b>Current:</b> ${current_price:.2f} | <b>Entry:</b> ${entry_price:.2f}"""
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=full_message,
                parse_mode='HTML'
            )
            
            # Record thesis check narrative event
            add_signal_narrative(
                signal_id=signal_id,
                event_type='thesis_check',
                current_price=current_price,
                guidance_type=thesis_status,
                message_sent=message[:500] if message else None,
                notes=f"Thesis re-validation: {thesis_status}"
            )
            
            print(f"✅ Posted revalidation ({thesis_status}) for signal #{signal_id}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to post revalidation update: {e}")
            return False
    
    async def post_signal_timeout(self, signal_id, message, current_price, entry_price):
        """
        Post a timeout notification when signal reaches 3-hour limit.
        
        Args:
            signal_id: Database signal ID
            message: AI-generated timeout message
            current_price: Current market price
            entry_price: Signal entry price
        """
        if not self.bot or not self.channel_id:
            return False
        
        try:
            full_message = f"""⏰ <b>Trade Timeout</b>
<b>Signal #{signal_id}</b>

{message}

<b>Current:</b> ${current_price:.2f} | <b>Entry:</b> ${entry_price:.2f}"""
            
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=full_message,
                parse_mode='HTML'
            )
            
            # Record close advisory narrative event
            add_signal_narrative(
                signal_id=signal_id,
                event_type='close_advisory',
                current_price=current_price,
                message_sent=message[:500] if message else None,
                notes="Signal closed due to timeout"
            )
            
            print(f"✅ Posted timeout notification for signal #{signal_id}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to post timeout notification: {e}")
            return False
    
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
                stats = get_forex_stats_by_period(period='today') or {}
                total_dollars = stats.get('total_pips', 0)
                
                # Build signal list
                signal_lines = []
                for signal in signals_today:
                    entry = signal.get('entry_price', 0)
                    posted_at = datetime.fromisoformat(signal['posted_at'])
                    time_str = posted_at.strftime('%H:%M')
                    
                    if signal['status'] == 'won':
                        dollars = signal.get('result_pips', 0)
                        signal_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ✅ +${dollars:.2f}")
                    elif signal['status'] == 'lost':
                        dollars = signal.get('result_pips', 0)
                        signal_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ❌ -${abs(dollars):.2f}")
                    elif signal['status'] == 'pending':
                        signal_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ⏳")
                    elif signal['status'] == 'expired':
                        signal_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ⏱️")
                
                signal_list = "\n".join(signal_lines)
                
                total_display = f"+${total_dollars:.2f}" if total_dollars >= 0 else f"-${abs(total_dollars):.2f}"
                message = f"""📊 <b>Daily Recap - {datetime.utcnow().strftime('%b %d')}</b>

{signal_list}

<b>Total: {total_display}</b>"""
            
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
                stats = get_forex_stats_by_period(period='week') or {}
                total_dollars = stats.get('total_pips', 0)
                
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
                            dollars = signal.get('result_pips', 0)
                            message_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ✅ +${dollars:.2f}")
                        elif signal['status'] == 'lost':
                            dollars = signal.get('result_pips', 0)
                            message_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ❌ -${abs(dollars):.2f}")
                        elif signal['status'] == 'pending':
                            message_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ⏳")
                        elif signal['status'] == 'expired':
                            message_lines.append(f"{signal['signal_type']}@{entry:.2f} | {time_str} ⏱️")
                    
                    message_lines.append("")  # Blank line between days
                
                total_display = f"+${total_dollars:.2f}" if total_dollars >= 0 else f"-${abs(total_dollars):.2f}"
                message_lines.append(f"<b>Weekly Total: {total_display}</b>")
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
