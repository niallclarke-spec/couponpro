"""
Scheduler Messenger Module

Handles all Telegram messaging and notifications for the forex scheduler.
Centralizes TP celebrations, recap generation, milestone notifications, etc.

All sends go through core/telegram_sender.py - no direct Bot instantiation.
"""
from datetime import datetime
from typing import Optional, Any, Dict
from core.logging import get_logger
from core.runtime import TenantRuntime
from core.telegram_sender import send_to_channel, send_photo_to_channel, SendResult
from core.bot_credentials import SIGNAL_BOT
from showcase.trade_win_generator import generate_single_trade_image

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
    
    async def _send_showcase_image(
        self,
        pair: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        pips: float,
        channel_type: str = 'vip'
    ) -> SendResult:
        """
        Send a trade win showcase image to the channel.
        
        Args:
            pair: Trading pair (e.g., "XAU/USD")
            direction: "BUY" or "SELL"
            entry_price: Entry price
            exit_price: Exit/TP price
            pips: Pips gained
            channel_type: 'vip' or 'free'
            
        Returns:
            SendResult
        """
        try:
            img_bytes = generate_single_trade_image(
                pair=pair,
                direction=direction,
                entry_price=entry_price,
                exit_price=exit_price,
                pips=pips,
                lot_size=1.0,
                timestamp=datetime.utcnow()
            )
            
            result = await send_photo_to_channel(
                tenant_id=self.tenant_id,
                bot_role=SIGNAL_BOT,
                photo=img_bytes,
                caption=None,
                channel_type=channel_type
            )
            
            if result.success:
                logger.info(f"Sent showcase image to {channel_type} channel")
            else:
                logger.error(f"Failed to send showcase image: {result.error}")
            
            return result
            
        except Exception as e:
            logger.exception(f"Error generating/sending showcase image: {e}")
            return SendResult(success=False, error=str(e))
    
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
        Send TP1 hit celebration message and showcase image.
        
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
            result = await self._send_channel_message(message)
            
            if result.success:
                logger.info(f"Posted TP1 celebration (+{pips} pips), message_id={result.message_id}")
                
                if signal_data:
                    await self._send_showcase_image(
                        pair=signal_data.get('pair', 'XAU/USD'),
                        direction=signal_type,
                        entry_price=float(signal_data.get('entry_price', 0)),
                        exit_price=float(signal_data.get('take_profit', 0)),
                        pips=pips
                    )
                
                return result.message_id
            else:
                logger.error(f"Failed to send TP1 celebration: {result.error}")
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
        """Send TP2 hit celebration message and showcase image.
        
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
            result = await self._send_channel_message(message)
            
            if result.success:
                logger.info(f"Posted TP2 celebration (+{pips} pips)")
                
                if signal_data:
                    await self._send_showcase_image(
                        pair=signal_data.get('pair', 'XAU/USD'),
                        direction=signal_type,
                        entry_price=float(signal_data.get('entry_price', 0)),
                        exit_price=float(signal_data.get('take_profit_2', 0)),
                        pips=pips
                    )
                
                return True
            else:
                logger.error(f"Failed to send TP2 celebration: {result.error}")
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
        Send TP3 hit (full exit) celebration message and showcase image.
        
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
            result = await self._send_channel_message(message)
            
            if result.success:
                logger.info(f"Posted TP3 celebration - full exit (+{pips} pips), message_id={result.message_id}")
                
                if signal_data:
                    await self._send_showcase_image(
                        pair=signal_data.get('pair', 'XAU/USD'),
                        direction=signal_type,
                        entry_price=float(signal_data.get('entry_price', 0)),
                        exit_price=float(signal_data.get('take_profit_3', 0)),
                        pips=pips
                    )
                
                return result.message_id
            else:
                logger.error(f"Failed to send TP3 celebration: {result.error}")
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
        entry_price: float
    ) -> bool:
        """Post signal timeout notification."""
        try:
            success = await self.bot.post_signal_timeout(
                signal_id=signal_id,
                message=message,
                current_price=current_price,
                entry_price=entry_price
            )
            if success:
                logger.info(f"Posted timeout notification for signal #{signal_id}")
            return success
        except Exception as e:
            logger.exception(f"Failed to post timeout for signal #{signal_id}")
            return False
