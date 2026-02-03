"""
Scheduler Messenger Module

Handles all Telegram messaging and notifications for the forex scheduler.
Centralizes TP celebrations, recap generation, milestone notifications, etc.

All sends go through core/telegram_sender.py - no direct Bot instantiation.
"""
import asyncio
from datetime import datetime
from typing import Optional, Any, Dict, List, Tuple
from core.logging import get_logger
from core.runtime import TenantRuntime
from core.telegram_sender import send_to_channel, send_photo_to_channel, SendResult
from core.bot_credentials import SIGNAL_BOT
from showcase.trade_win_generator import generate_trade_win_image, TradeWinData
from showcase.profit_calculator import calculate_trade_profit, COMMISSION_PER_LOT

logger = get_logger(__name__)


class Messenger:
    """
    Handles Telegram messaging for forex signals.
    
    Centralizes all messaging operations:
    - Signal posting (delegates to ForexTelegramBot)
    - TP/SL hit notifications (uses send_to_channel directly)
    - Milestone celebrations
    - Daily/weekly recaps
    - Revalidation updates
    
    All direct sends use core/telegram_sender.send_to_channel() for consistency
    with production-grade credential resolution and error handling.
    """
    
    def __init__(self, runtime: TenantRuntime):
        self.runtime = runtime
        self.tenant_id = runtime.tenant_id
    
    @property
    def bot(self):
        """Get the ForexTelegramBot instance for high-level operations."""
        return self.runtime.get_telegram_bot()
    
    @property
    def milestone_tracker(self):
        """Get the milestone tracker for message generation."""
        return self.runtime.get_milestone_tracker()
    
    async def _send_channel_message(
        self, 
        text: str, 
        channel_type: str = 'vip'
    ) -> SendResult:
        """
        Internal helper to send a message to the signal channel.
        
        Uses core/telegram_sender.send_to_channel() for all sends.
        No direct Bot instantiation.
        
        Args:
            text: Message text
            channel_type: 'vip', 'free', or 'default'
            
        Returns:
            SendResult with success status and message_id or error
        """
        return await send_to_channel(
            tenant_id=self.tenant_id,
            bot_role=SIGNAL_BOT,
            text=text,
            parse_mode='HTML',
            channel_type=channel_type
        )
    
    def _build_trades_for_showcase(
        self,
        signal_data: Dict[str, Any],
        tp_level: int
    ) -> List[TradeWinData]:
        """
        Build trade data rows for showcase image.
        
        Returns list of TradeWinData objects for the given TP level.
        """
        entry_price = float(signal_data.get('entry_price', 0))
        direction = signal_data.get('signal_type', 'BUY')
        pair = signal_data.get('pair', 'XAU/USD')
        
        tp_prices = [
            signal_data.get('take_profit'),
            signal_data.get('take_profit_2'),
            signal_data.get('take_profit_3')
        ]
        
        trades: List[TradeWinData] = []
        now = datetime.utcnow()
        
        for i in range(tp_level):
            tp_price = tp_prices[i]
            if tp_price is None:
                continue
                
            tp_price = float(tp_price)
            profit_calc = calculate_trade_profit(
                entry_price=entry_price,
                exit_price=tp_price,
                direction=direction,
                lot_size=1.0,
                include_commission=True
            )
            
            trade = TradeWinData(
                pair=pair,
                direction=direction,
                lot_size=1.0,
                entry_price=entry_price,
                exit_price=tp_price,
                profit=profit_calc.net_profit,
                timestamp=now
            )
            trades.append(trade)
        
        return trades
    
    async def _generate_image_with_retry(
        self,
        signal_data: Dict[str, Any],
        tp_level: int,
        max_attempts: int = 3,
        delay_ms: int = 200
    ) -> Optional[bytes]:
        """
        Generate showcase image with retry logic.
        
        Tries up to max_attempts times with delay_ms between attempts.
        Returns image bytes on success, None after all attempts fail.
        
        Args:
            signal_data: Signal dict with entry_price, TP prices, etc.
            tp_level: Current TP level (1, 2, or 3)
            max_attempts: Number of attempts before giving up (default 3)
            delay_ms: Delay between retries in milliseconds (default 200)
            
        Returns:
            Image bytes if successful, None if all attempts fail
        """
        trades = self._build_trades_for_showcase(signal_data, tp_level)
        
        if not trades:
            logger.warning("No trades to display in showcase image")
            return None
        
        for attempt in range(1, max_attempts + 1):
            try:
                img_bytes = generate_trade_win_image(trades)
                if img_bytes:
                    logger.debug(f"Generated showcase image on attempt {attempt}")
                    return img_bytes
            except Exception as e:
                logger.warning(f"Image generation attempt {attempt}/{max_attempts} failed: {e}")
            
            if attempt < max_attempts:
                await asyncio.sleep(delay_ms / 1000.0)
        
        logger.error(f"All {max_attempts} image generation attempts failed")
        return None
    
    async def _send_photo_with_caption(
        self,
        photo: bytes,
        caption: str,
        channel_type: str = 'vip'
    ) -> SendResult:
        """
        Send a photo with caption to the channel.
        
        Args:
            photo: Image bytes
            caption: Caption text (HTML formatted)
            channel_type: 'vip' or 'free'
            
        Returns:
            SendResult with message_id if successful
        """
        return await send_photo_to_channel(
            tenant_id=self.tenant_id,
            bot_role=SIGNAL_BOT,
            photo=photo,
            caption=caption,
            channel_type=channel_type
        )
    
    async def _send_tp_celebration_combined(
        self,
        message: str,
        signal_data: Optional[Dict[str, Any]],
        tp_level: int,
        channel_type: str = 'vip'
    ) -> Tuple[bool, Optional[int]]:
        """
        Send TP celebration as combined photo+caption or text-only fallback.
        
        Strategy:
        1. If signal_data provided, try to generate showcase image (3 retries)
        2. If image generated, send as photo+caption
        3. If image fails after retries, send text-only message
        
        Args:
            message: Celebration message text
            signal_data: Optional signal dict for showcase image
            tp_level: TP level (1, 2, or 3)
            channel_type: 'vip' or 'free'
            
        Returns:
            Tuple of (success, message_id or None)
        """
        if signal_data:
            img_bytes = await self._generate_image_with_retry(signal_data, tp_level)
            
            if img_bytes:
                result = await self._send_photo_with_caption(
                    photo=img_bytes,
                    caption=message,
                    channel_type=channel_type
                )
                if result.success:
                    logger.info(f"Sent TP{tp_level} photo+caption to {channel_type}, msg_id={result.message_id}")
                    return True, result.message_id
                else:
                    logger.warning(f"Photo+caption send failed, falling back to text: {result.error}")
            else:
                logger.warning(f"Image generation failed after retries, sending text-only")
        
        result = await self._send_channel_message(message, channel_type)
        if result.success:
            logger.info(f"Sent TP{tp_level} text message to {channel_type}, msg_id={result.message_id}")
        return result.success, result.message_id if result.success else None
    
    async def post_signal(self, signal_data: Dict[str, Any]) -> Optional[int]:
        """Post a new signal to Telegram."""
        try:
            signal_id = await self.bot.post_signal(signal_data)
            if signal_id:
                logger.info(f"Signal #{signal_id} posted to Telegram")
            return signal_id
        except Exception as e:
            logger.exception("Failed to post signal to Telegram")
            return None
    
    async def send_tp1_celebration(
        self, 
        signal_type: str, 
        pips: float, 
        remaining: float, 
        posted_at: Optional[str] = None,
        signal_data: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """
        Send TP1 hit celebration as combined photo+caption (with text-only fallback).
        
        Args:
            signal_type: BUY or SELL
            pips: Pips secured at TP1
            remaining: Percentage still riding to TP2
            posted_at: ISO timestamp of original signal for elapsed time display
            signal_data: Optional signal dict with entry_price, take_profit, pair for showcase
        
        Returns:
            Telegram message_id if successful, None otherwise
        """
        try:
            message = self.milestone_tracker.generate_tp1_celebration(signal_type, pips, remaining, posted_at)
            success, message_id = await self._send_tp_celebration_combined(
                message=message,
                signal_data=signal_data,
                tp_level=1
            )
            
            if success:
                logger.info(f"Posted TP1 celebration (+{pips} pips), message_id={message_id}")
                return message_id
            else:
                logger.error("Failed to send TP1 celebration")
                return None
        except Exception as e:
            logger.exception("Failed to send TP1 celebration")
            return None
    
    async def send_tp2_celebration(
        self, 
        signal_type: str, 
        pips: float, 
        tp1_price: float, 
        remaining: float, 
        posted_at: Optional[str] = None,
        signal_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send TP2 hit celebration as combined photo+caption (with text-only fallback).
        
        Args:
            signal_type: BUY or SELL
            pips: Pips secured at TP2
            tp1_price: TP1 price for SL adjustment advice
            remaining: Percentage still riding to TP3
            posted_at: ISO timestamp of original signal for elapsed time display
            signal_data: Optional signal dict with entry_price, take_profit_2, pair for showcase
        """
        try:
            message = self.milestone_tracker.generate_tp2_celebration(signal_type, pips, tp1_price, remaining, posted_at)
            success, message_id = await self._send_tp_celebration_combined(
                message=message,
                signal_data=signal_data,
                tp_level=2
            )
            
            if success:
                logger.info(f"Posted TP2 celebration (+{pips} pips), message_id={message_id}")
                return True
            else:
                logger.error("Failed to send TP2 celebration")
                return False
        except Exception as e:
            logger.exception("Failed to send TP2 celebration")
            return False
    
    async def send_tp3_celebration(
        self, 
        signal_type: str, 
        pips: float, 
        posted_at: Optional[str] = None,
        signal_data: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """
        Send TP3 hit celebration as combined photo+caption (with text-only fallback).
        
        Args:
            signal_type: BUY or SELL
            pips: Total pips secured
            posted_at: ISO timestamp of original signal for elapsed time display
            signal_data: Optional signal dict with entry_price, take_profit_3, pair for showcase
        
        Returns:
            Telegram message_id if successful, None otherwise
        """
        try:
            message = self.milestone_tracker.generate_tp3_celebration(signal_type, pips, posted_at)
            success, message_id = await self._send_tp_celebration_combined(
                message=message,
                signal_data=signal_data,
                tp_level=3
            )
            
            if success:
                logger.info(f"Posted TP3 celebration - full exit (+{pips} pips), message_id={message_id}")
                return message_id
            else:
                logger.error("Failed to send TP3 celebration")
                return None
        except Exception as e:
            logger.exception("Failed to send TP3 celebration")
            return None
    
    async def send_sl_hit_message(self, pips: float) -> bool:
        """Send SL hit message."""
        try:
            message = self.milestone_tracker.generate_sl_hit_message(abs(pips))
            result = await self._send_channel_message(message)
            
            if result.success:
                logger.info(f"Posted SL hit notification ({pips} pips)")
                return True
            else:
                logger.error(f"Failed to send SL hit message: {result.error}")
                return False
        except Exception as e:
            logger.exception("Failed to send SL hit message")
            return False
    
    async def send_profit_locked_message(self, pips: float) -> bool:
        """Send profit-locked SL hit message."""
        try:
            message = self.milestone_tracker.generate_profit_locked_message(pips)
            result = await self._send_channel_message(message)
            
            if result.success:
                logger.info(f"Posted profit-locked notification (+{pips} pips)")
                return True
            else:
                logger.error(f"Failed to send profit locked message: {result.error}")
                return False
        except Exception as e:
            logger.exception("Failed to send profit locked message")
            return False
    
    async def send_breakeven_exit_message(self) -> bool:
        """Send breakeven exit message."""
        try:
            message = self.milestone_tracker.generate_breakeven_exit_message()
            result = await self._send_channel_message(message)
            
            if result.success:
                logger.info("Posted breakeven exit notification")
                return True
            else:
                logger.error(f"Failed to send breakeven exit message: {result.error}")
                return False
        except Exception as e:
            logger.exception("Failed to send breakeven exit message")
            return False
    
    async def send_milestone_message(self, milestone_event: Dict[str, Any]) -> bool:
        """Send a milestone progress message."""
        try:
            message = self.milestone_tracker.generate_milestone_message(milestone_event)
            if not message:
                return False
                
            result = await self._send_channel_message(message)
            
            if result.success:
                logger.info(f"Posted milestone: {milestone_event.get('milestone')}")
                return True
            else:
                logger.error(f"Failed to send milestone message: {result.error}")
                return False
        except Exception as e:
            logger.exception("Failed to send milestone message")
            return False
    
    async def post_signal_expired(self, signal_id: int, pips: float, signal_type: str) -> bool:
        """Post signal expiry notification."""
        try:
            await self.bot.post_signal_expired(signal_id, pips, signal_type)
            logger.info(f"Posted expiry notification for signal #{signal_id}")
            return True
        except Exception as e:
            logger.exception(f"Failed to post expiry for signal #{signal_id}")
            return False
    
    async def post_revalidation_update(
        self,
        signal_id: int,
        thesis_status: str,
        message: str,
        current_price: float,
        entry_price: float
    ) -> bool:
        """Post a revalidation update."""
        try:
            success = await self.bot.post_revalidation_update(
                signal_id=signal_id,
                thesis_status=thesis_status,
                message=message,
                current_price=current_price,
                entry_price=entry_price
            )
            if success:
                logger.info(f"Posted revalidation ({thesis_status}) for signal #{signal_id}")
            return success
        except Exception as e:
            logger.exception(f"Failed to post revalidation for signal #{signal_id}")
            return False
    
    async def post_signal_timeout(
        self,
        signal_id: int,
        message: str,
        current_price: float,
        entry_price: float,
        signal_type: str = 'BUY'
    ) -> bool:
        """Post signal timeout notification."""
        try:
            success = await self.bot.post_signal_timeout(
                signal_id=signal_id,
                message=message,
                current_price=current_price,
                entry_price=entry_price,
                signal_type=signal_type
            )
            if success:
                logger.info(f"Posted timeout notification for signal #{signal_id}")
            return success
        except Exception as e:
            logger.exception(f"Failed to post timeout for signal #{signal_id}")
            return False
