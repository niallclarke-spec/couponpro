"""
Telegram bot for posting forex signals to channel
Uses the new send infrastructure from core/telegram_sender.py

No cached bot instances - each send resolves fresh credentials.
"""
import asyncio
from datetime import datetime
from db import create_forex_signal, get_forex_signals, get_forex_stats_by_period, update_signal_original_indicators, add_signal_narrative, get_active_bot, update_signal_status, update_tp_message_id
from core.logging import get_logger
from core.bot_credentials import BotNotConfiguredError, SIGNAL_BOT
from core.telegram_sender import send_to_channel, get_connection_for_send, SendResult
from core.pip_calculator import PIPS_MULTIPLIER

logger = get_logger(__name__)


class ForexTelegramBot:
    """
    Forex signal posting bot for VIP channel operations.
    
    This class is exclusively for VIP channel sends:
    - Trading signals (post_signal)
    - TP/SL notifications (post_tp_hit, post_stop_loss, post_stagnant_close)
    - Milestone celebrations (post_signal_closed_winner)
    - Recaps (post_daily_recap, post_weekly_recap, post_morning_briefing)
    
    For FREE channel operations (cross-promo), use domains/crosspromo/client.py
    which calls send_to_channel() directly with channel_type='free'.
    
    All sends go through core/telegram_sender.py which:
    - Resolves fresh credentials from DB (with short TTL cache)
    - Constructs short-lived Bot per send
    - Fails fast if credentials missing
    """
    
    def __init__(self, tenant_id: str | None = None):
        if not tenant_id:
            raise ValueError("tenant_id is required - no implicit tenant inference allowed")
        self.tenant_id = tenant_id
    
    def is_configured(self) -> bool:
        """Check if signal bot has VIP channel configured."""
        connection = get_connection_for_send(self.tenant_id, SIGNAL_BOT)
        # Signal bot uses vip_channel_id (not legacy channel_id which is for message_bot)
        is_ready = connection is not None and connection.vip_channel_id is not None
        if not is_ready and connection:
            logger.debug(f"is_configured=False: vip_channel_id={connection.vip_channel_id}")
        return is_ready
    
    async def _send(self, text: str, channel_type: str = 'vip') -> SendResult:
        """Internal send helper - all channel sends go through VIP channel by default."""
        return await send_to_channel(
            tenant_id=self.tenant_id,
            bot_role=SIGNAL_BOT,
            text=text,
            parse_mode='HTML',
            channel_type=channel_type
        )
    
    async def post_signal(self, signal_data):
        """
        Post a trading signal to the Telegram channel with multi-TP support
        
        Args:
            signal_data: dict with signal_type, pair, entry_price, take_profit, stop_loss, etc.
                        Supports take_profit_2, take_profit_3 for multi-TP
        
        Returns:
            int: Signal ID from database or None if failed
        """
        if not self.is_configured():
            logger.error(f"SEND BLOCKED: Signal bot not configured for tenant '{self.tenant_id}'")
            return None
        
        try:
            pending_signals = get_forex_signals(tenant_id=self.tenant_id, status='pending')
            if pending_signals and len(pending_signals) > 0:
                existing = pending_signals[0]
                logger.error(f"Cannot post new signal - signal #{existing['id']} is still pending")
                logger.error(f"   Entry: ${existing['entry_price']}, created at: {existing.get('posted_at')}")
                return None
            
            signal_type = signal_data['signal_type']
            pair = signal_data['pair']
            entry = signal_data['entry_price']
            tp1 = signal_data['take_profit']
            tp2 = signal_data.get('take_profit_2')
            tp3 = signal_data.get('take_profit_3')
            sl = signal_data['stop_loss']
            rsi = signal_data.get('rsi_value')
            macd = signal_data.get('macd_value')
            atr = signal_data.get('atr_value')
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
            
            indicator_parts = []
            if rsi is not None:
                indicator_parts.append(f"RSI: {rsi:.2f}")
            if macd is not None:
                indicator_parts.append(f"MACD: {macd:.4f}")
            if atr is not None:
                indicator_parts.append(f"ATR: {atr:.2f}")
            indicator_line = f"\n📊 {' | '.join(indicator_parts)}" if indicator_parts else ""
            
            # Capture signal time for transparency
            signal_time = datetime.utcnow().strftime('%H:%M')
            
            message = f"""{emoji} <b>{signal_type} SIGNAL</b> {emoji}

⏰ <b>LIVE ENTRY NOW @ {signal_time} UTC</b>

<b>Pair:</b> {pair}
<b>Timeframe:</b> {timeframe}

💰 <b>Entry:</b> ${entry:.2f}

{tp_section}

🛡️ <b>Stop Loss:</b> ${sl:.2f}
{indicator_line}
"""
            
            signal_id = create_forex_signal(
                signal_type=signal_type,
                pair=pair,
                timeframe=timeframe,
                entry_price=entry,
                tenant_id=self.tenant_id,
                take_profit=tp1,
                stop_loss=sl,
                rsi_value=rsi,
                macd_value=macd,
                atr_value=atr,
                bot_type=get_active_bot(tenant_id=self.tenant_id),
                take_profit_2=tp2,
                take_profit_3=tp3,
                tp1_percentage=tp1_pct,
                tp2_percentage=tp2_pct,
                tp3_percentage=tp3_pct,
                status='draft'
            )
            
            if not signal_id:
                logger.error("Failed to create draft signal in database")
                return None
            
            logger.info(f"Created draft signal #{signal_id}, posting to Telegram...")
            
            result = await self._send(message)
            
            if result.success:
                if update_signal_status(signal_id, 'pending', tenant_id=self.tenant_id, telegram_message_id=result.message_id):
                    logger.info(f"Signal #{signal_id} status updated to pending (Telegram msg: {result.message_id})")
                else:
                    logger.error(f"Failed to update signal #{signal_id} status to pending after Telegram broadcast")
                    logger.warning(f"Ghost signal detected: Telegram message sent but DB update failed")
                    fallback_success = update_signal_status(signal_id, 'broadcast_failed', tenant_id=self.tenant_id)
                    if fallback_success:
                        logger.info(f"Signal #{signal_id} marked as broadcast_failed (fallback)")
                    else:
                        logger.error(f"CRITICAL: Could not mark signal #{signal_id} as broadcast_failed - manual cleanup required")
                    return None
            else:
                logger.error(f"Failed to post signal to Telegram: {result.error}")
                update_signal_status(signal_id, 'broadcast_failed', tenant_id=self.tenant_id)
                logger.info(f"Signal #{signal_id} marked as broadcast_failed")
                return None
            
            indicators_dict = signal_data.get('all_indicators', {})
            if not indicators_dict:
                indicators_dict = {
                    'rsi': rsi,
                    'macd': macd,
                    'adx': signal_data.get('adx_value'),
                    'stochastic': signal_data.get('stoch_k_value'),
                    'atr': atr
                }
            indicators_dict = {k: v for k, v in indicators_dict.items() if v is not None}
            
            if signal_id and indicators_dict:
                update_signal_original_indicators(signal_id, tenant_id=self.tenant_id, indicators_dict=indicators_dict)
                logger.info(f"Stored original indicators for signal #{signal_id}: {list(indicators_dict.keys())}")
                
                add_signal_narrative(
                    signal_id=signal_id,
                    event_type='entry',
                    current_price=entry,
                    progress_percent=0,
                    indicators=indicators_dict,
                    notes=f"{signal_type} signal entry at ${entry:.2f}"
                )
            
            logger.info(f"Posted {signal_type} signal to Telegram (ID: {signal_id})")
            return signal_id
            
        except Exception as e:
            logger.exception(f"Unexpected error posting signal: {e}")
            return None
    
    async def post_tp_hit(self, signal_id, tp_number, pips_profit, position_percentage, remaining_percentage=None) -> int | None:
        """
        Post notification when an individual TP is hit (multi-TP system)
        
        Args:
            signal_id: Database signal ID
            tp_number: 1, 2, or 3
            pips_profit: Profit in pips for this TP
            position_percentage: Percentage of position closed at this TP
            remaining_percentage: Percentage of position still open (optional)
        
        Returns:
            int: Telegram message ID if successful (for TP1/TP3 cross-promo), None otherwise
        """
        if not self.is_configured():
            return None
        
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
            
            result = await self._send(message)
            
            if result.success:
                add_signal_narrative(
                    signal_id=signal_id,
                    event_type=f'tp{tp_number}_hit',
                    notes=f"TP{tp_number} hit: +${pips_profit:.2f} ({position_percentage}% closed)"
                )
                logger.info(f"Posted TP{tp_number} notification for signal #{signal_id} (msg_id: {result.message_id})")
                
                # Store message ID for cross-promo (TP1 and TP3 only)
                if tp_number in [1, 3] and result.message_id:
                    update_tp_message_id(signal_id, tp_number, result.message_id, self.tenant_id)
                    logger.debug(f"Stored TP{tp_number} message ID {result.message_id} for signal #{signal_id}")
                
                return result.message_id
            else:
                logger.error(f"Failed to post TP{tp_number} notification: {result.error}")
                return None
            
        except Exception as e:
            logger.exception(f"Failed to post TP{tp_number} notification: {e}")
            return None
    
    async def post_breakeven_alert(self, signal_id, entry_price, current_price):
        """
        Post breakeven alert when price reaches 70% toward TP1
        
        Args:
            signal_id: Database signal ID
            entry_price: Original entry price
            current_price: Current price
        """
        if not self.is_configured():
            return
        
        try:
            pips_profit = abs(current_price - entry_price) * PIPS_MULTIPLIER
            
            message = f"""⚡ <b>BREAKEVEN ALERT</b>

📈 Price at 70% toward TP1!

💰 Current: <b>+{pips_profit:.0f} pips</b>

🔒 Move SL to entry @ ${entry_price:.2f}"""
            
            result = await self._send(message)
            
            if result.success:
                dollar_profit = abs(current_price - entry_price)
                add_signal_narrative(
                    signal_id=signal_id,
                    event_type='breakeven_alert',
                    current_price=current_price,
                    notes=f"Breakeven alert at ${current_price:.2f}, +{pips_profit:.0f} pips (${dollar_profit:.2f})"
                )
                logger.info(f"Posted breakeven alert for signal #{signal_id}")
            else:
                logger.error(f"Failed to post breakeven alert: {result.error}")
            
        except Exception as e:
            logger.exception(f"Failed to post breakeven alert: {e}")
    
    async def post_tp_celebration(self, signal_id, pips_profit, ai_message=None):
        """
        Post a celebration message when all Take Profits are hit (legacy support)
        
        Args:
            signal_id: Database signal ID
            pips_profit: Total profit in pips
            ai_message: Optional AI-generated motivational message (ignored)
        """
        if not self.is_configured():
            return
        
        try:
            message = f"""🎉 <b>TRADE COMPLETE!</b> 🎉

Total profit: <b>+${pips_profit:.2f}</b>"""
            
            result = await self._send(message)
            
            if result.success:
                add_signal_narrative(
                    signal_id=signal_id,
                    event_type='tp_hit',
                    progress_percent=100,
                    notes=f"Trade complete: +${pips_profit:.2f}"
                )
                logger.info(f"Posted TP celebration for signal #{signal_id}")
            else:
                logger.error(f"Failed to post TP celebration: {result.error}")
            
        except Exception as e:
            logger.exception(f"Failed to post TP celebration: {e}")
    
    async def post_sl_hit(self, signal_id, pips_loss, signal_type='BUY'):
        """
        Post a message when Stop Loss is hit
        
        Args:
            signal_id: Database signal ID
            pips_loss: Loss in pips (should be negative)
            signal_type: 'BUY' or 'SELL'
        """
        if not self.is_configured():
            return
        
        try:
            message = f"""Stop Loss Hit

<b>${abs(pips_loss):.2f} loss</b>

Risk was managed. Onwards to the next opportunity."""
            
            result = await self._send(message)
            
            if result.success:
                add_signal_narrative(
                    signal_id=signal_id,
                    event_type='sl_hit',
                    progress_percent=-100,
                    notes=f"Stop loss hit: -${abs(pips_loss):.2f}"
                )
                logger.info(f"Posted SL notification for signal #{signal_id}")
            else:
                logger.error(f"Failed to post SL notification: {result.error}")
            
        except Exception as e:
            logger.exception(f"Failed to post SL notification: {e}")
    
    async def post_signal_expired(self, signal_id, pips, signal_type='BUY'):
        """
        Post a message when signal expires (timeout)
        
        Args:
            signal_id: Database signal ID
            pips: Current P/L in pips
            signal_type: 'BUY' or 'SELL'
        """
        if not self.is_configured():
            return
        
        try:
            result_text = "profit" if pips > 0 else "loss" if pips < 0 else "breakeven"
            dollar_display = f"+${pips:.2f}" if pips > 0 else f"-${abs(pips):.2f}" if pips < 0 else "$0.00"
            message = f"""Trade Closed (Timeout)

<b>{dollar_display}</b> {result_text}

Signal closed after maximum hold time."""
            
            result = await self._send(message)
            
            if result.success:
                logger.info(f"Posted expiry notification for signal #{signal_id}")
            else:
                logger.error(f"Failed to post expiry notification: {result.error}")
            
        except Exception as e:
            logger.exception(f"Failed to post expiry notification: {e}")
    
    async def post_signal_guidance(self, signal_id, guidance_type, message, signal_data):
        """
        Post a guidance update for an active signal.
        
        Args:
            signal_id: Database signal ID
            guidance_type: 'progress', 'breakeven', 'caution', 'decision'
            message: AI-generated or fallback guidance message
            signal_data: Dict with current signal info (entry, tp, sl, current_price)
        """
        if not self.is_configured():
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
            
            result = await self._send(full_message)
            
            if result.success:
                progress = signal_data.get('progress_percent', 0)
                current_indicators = signal_data.get('current_indicators', {})
                indicator_deltas = signal_data.get('indicator_deltas', {})
                
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
                
                logger.info(f"Posted {guidance_type} guidance for signal #{signal_id}")
                return True
            else:
                logger.error(f"Failed to post signal guidance: {result.error}")
                return False
            
        except Exception as e:
            logger.exception(f"Failed to post signal guidance: {e}")
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
        if not self.is_configured():
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
            
            result = await self._send(full_message)
            
            if result.success:
                add_signal_narrative(
                    signal_id=signal_id,
                    event_type='thesis_check',
                    current_price=current_price,
                    guidance_type=thesis_status,
                    message_sent=message[:500] if message else None,
                    notes=f"Thesis re-validation: {thesis_status}"
                )
                
                logger.info(f"Posted revalidation ({thesis_status}) for signal #{signal_id}")
                return True
            else:
                logger.error(f"Failed to post revalidation update: {result.error}")
                return False
            
        except Exception as e:
            logger.exception(f"Failed to post revalidation update: {e}")
            return False
    
    async def post_signal_timeout(self, signal_id, message, current_price, entry_price):
        """
        Post a timeout notification when signal reaches maximum hold time.
        
        Args:
            signal_id: Database signal ID
            message: AI-generated timeout message
            current_price: Current market price
            entry_price: Signal entry price
        """
        if not self.is_configured():
            return False
        
        try:
            pnl = current_price - entry_price
            pnl_display = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            
            full_message = f"""⏰ <b>Signal Timeout</b>
<b>Signal #{signal_id}</b>

{message}

<b>Exit:</b> ${current_price:.2f} | <b>Entry:</b> ${entry_price:.2f}
<b>Result:</b> {pnl_display}"""
            
            result = await self._send(full_message)
            
            if result.success:
                add_signal_narrative(
                    signal_id=signal_id,
                    event_type='timeout',
                    current_price=current_price,
                    message_sent=message[:500] if message else None,
                    notes=f"Signal timeout at ${current_price:.2f}, P/L: {pnl_display}"
                )
                
                logger.info(f"Posted timeout notification for signal #{signal_id}")
                return True
            else:
                logger.error(f"Failed to post timeout notification: {result.error}")
                return False
            
        except Exception as e:
            logger.exception(f"Failed to post timeout notification: {e}")
            return False
    
    async def post_thesis_broken(self, signal_id, message, current_price, entry_price):
        """
        Post a thesis broken notification when signal is invalidated.
        
        Args:
            signal_id: Database signal ID
            message: AI-generated thesis broken message
            current_price: Current market price
            entry_price: Signal entry price
        """
        if not self.is_configured():
            return False
        
        try:
            pnl = current_price - entry_price
            pnl_display = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            
            full_message = f"""🚨 <b>Trade Alert - Thesis Invalidated</b>
<b>Signal #{signal_id}</b>

{message}

<b>Exit:</b> ${current_price:.2f} | <b>Entry:</b> ${entry_price:.2f}
<b>Result:</b> {pnl_display}"""
            
            result = await self._send(full_message)
            
            if result.success:
                add_signal_narrative(
                    signal_id=signal_id,
                    event_type='thesis_broken',
                    current_price=current_price,
                    message_sent=message[:500] if message else None,
                    notes=f"Thesis broken at ${current_price:.2f}, P/L: {pnl_display}"
                )
                
                logger.info(f"Posted thesis broken notification for signal #{signal_id}")
                return True
            else:
                logger.error(f"Failed to post thesis broken notification: {result.error}")
                return False
            
        except Exception as e:
            logger.exception(f"Failed to post thesis broken notification: {e}")
            return False
    
    async def post_daily_recap(self, recap_data, date_str=None, ai_message=None):
        """
        Post daily performance recap to channel.
        
        Args:
            recap_data: Dict with total_signals, wins, losses, total_pnl
            date_str: Date string for the recap
            ai_message: Optional AI-generated summary
        """
        if not self.is_configured():
            return False
        
        try:
            total = recap_data.get('total_signals', 0)
            wins = recap_data.get('wins', 0)
            losses = recap_data.get('losses', 0)
            pnl = recap_data.get('total_pnl', 0)
            
            if total == 0:
                message = f"""📊 <b>Daily Recap</b> - {date_str or 'Today'}

No signals posted today. Markets were quiet."""
            else:
                win_rate = (wins / total * 100) if total > 0 else 0
                pnl_emoji = "📈" if pnl >= 0 else "📉"
                pnl_display = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
                
                message = f"""📊 <b>Daily Recap</b> - {date_str or 'Today'}

<b>Signals:</b> {total}
<b>Wins:</b> {wins} | <b>Losses:</b> {losses}
<b>Win Rate:</b> {win_rate:.1f}%

{pnl_emoji} <b>P/L:</b> {pnl_display}"""
                
                if ai_message:
                    message += f"\n\n{ai_message}"
            
            result = await self._send(message)
            
            if result.success:
                logger.info(f"Posted daily recap for {date_str or 'today'}")
                return True
            else:
                logger.error(f"Failed to post daily recap: {result.error}")
                return False
            
        except Exception as e:
            logger.exception(f"Failed to post daily recap: {e}")
            return False
    
    async def post_detailed_recap(self, message: str) -> bool:
        """
        Post a pre-formatted detailed recap message to the VIP channel.
        
        Args:
            message: Pre-formatted HTML message from generate_detailed_daily_recap()
        
        Returns:
            bool: True if posted successfully
        """
        if not self.is_configured():
            return False
        
        try:
            result = await self._send(message)
            
            if result.success:
                logger.info("Posted detailed daily recap to VIP channel")
                return True
            else:
                logger.error(f"Failed to post detailed recap: {result.error}")
                return False
            
        except Exception as e:
            logger.exception(f"Failed to post detailed recap: {e}")
            return False
    
    async def post_weekly_recap(self, recap_data, week_str=None, ai_message=None):
        """
        Post weekly performance recap to channel.
        
        Args:
            recap_data: Dict with total_signals, wins, losses, total_pnl
            week_str: Week string for the recap
            ai_message: Optional AI-generated summary
        """
        if not self.is_configured():
            return False
        
        try:
            total = recap_data.get('total_signals', 0)
            wins = recap_data.get('wins', 0)
            losses = recap_data.get('losses', 0)
            pnl = recap_data.get('total_pnl', 0)
            
            if total == 0:
                message = f"""📅 <b>Weekly Recap</b> - {week_str or 'This Week'}

No signals posted this week."""
            else:
                win_rate = (wins / total * 100) if total > 0 else 0
                pnl_emoji = "📈" if pnl >= 0 else "📉"
                pnl_display = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
                
                message = f"""📅 <b>Weekly Recap</b> - {week_str or 'This Week'}

<b>Total Signals:</b> {total}
<b>Wins:</b> {wins} | <b>Losses:</b> {losses}
<b>Win Rate:</b> {win_rate:.1f}%

{pnl_emoji} <b>Weekly P/L:</b> {pnl_display}"""
                
                if ai_message:
                    message += f"\n\n{ai_message}"
            
            result = await self._send(message)
            
            if result.success:
                logger.info(f"Posted weekly recap for {week_str or 'this week'}")
                return True
            else:
                logger.error(f"Failed to post weekly recap: {result.error}")
                return False
            
        except Exception as e:
            logger.exception(f"Failed to post weekly recap: {e}")
            return False
    
    async def post_morning_briefing(self, briefing_data=None, ai_message=None):
        """
        Post morning market briefing to channel.
        
        Args:
            briefing_data: Dict with market context data (optional, for future use)
            ai_message: AI-generated briefing message
        """
        if not self.is_configured():
            return False
        
        try:
            if not ai_message:
                ai_message = "Good morning! Markets are open. Stay disciplined and follow the signals."
            
            message = f"""☀️ <b>Morning Briefing</b>

{ai_message}"""
            
            result = await self._send(message)
            
            if result.success:
                logger.info("Posted morning briefing")
                return True
            else:
                logger.error(f"Failed to post morning briefing: {result.error}")
                return False
            
        except Exception as e:
            logger.exception(f"Failed to post morning briefing: {e}")
            return False
    
    async def send_custom_message(self, message: str):
        """
        Send a custom message to the channel.
        
        Args:
            message: Message text (HTML format)
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_configured():
            return False
        
        try:
            result = await self._send(message)
            return result.success
        except Exception as e:
            logger.exception(f"Failed to send custom message: {e}")
            return False


def create_forex_bot(tenant_id: str) -> ForexTelegramBot:
    """Factory function to create a ForexTelegramBot instance."""
    return ForexTelegramBot(tenant_id=tenant_id)
