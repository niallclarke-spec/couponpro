"""
Signal Bot Scheduler
Manages signal generation, monitoring, and Telegram posting
Uses the active bot strategy and enforces one-signal-at-a-time rule

NOTE: This module is deprecated. Use forex_scheduler.py instead.
"""
import os
import asyncio
from datetime import datetime
from typing import Optional
from telegram import Bot
from telegram.error import TelegramError

from bots.core.bot_manager import BotManager, create_bot_manager
from bots.core.signal_generator import SignalGenerator, create_signal_generator
from db import (
    update_forex_signal_status,
    get_forex_signals_by_period,
    get_forex_stats_by_period
)


class SignalBotScheduler:
    """
    Main scheduler for the signal bot system
    
    NOTE: This class is deprecated. Use ForexSchedulerRunner from forex_scheduler.py instead.
    
    Intervals:
    - Signal check: Every 15 minutes (during trading hours)
    - Price monitoring: Every 5 minutes
    - Daily recap: 11:59 PM GMT
    - Weekly recap: Sunday 11:59 PM GMT
    """
    
    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id
        self.signal_check_interval = 900
        self.monitor_interval = 300
        self.last_daily_recap = None
        self.last_weekly_recap = None
        
        self.bot_manager = create_bot_manager(tenant_id=tenant_id)
        self.signal_generator = create_signal_generator(
            bot_manager=self.bot_manager,
            tenant_id=tenant_id
        )
        
        self.bot = None
        self.channel_id = None
        
        from core.bot_credentials import get_bot_credentials, BotNotConfiguredError
        try:
            creds = get_bot_credentials(tenant_id or 'entrylab', 'signal_bot')
            self.channel_id = creds['channel_id']
            token = creds['bot_token']
            if token:
                self.bot = Bot(token=token)
            else:
                print("[SCHEDULER] Forex bot token missing in credentials")
        except BotNotConfiguredError as e:
            print(f"[SCHEDULER] Forex bot not configured: {e}")
    
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
            strategy = self.bot_manager.get_active_strategy()
            
            if not strategy or not strategy.is_trading_hours():
                print(f"[SCHEDULER] Outside trading hours, skipping signal check")
                return
            
            signal_data = await self.signal_generator.generate_signal()
            
            if signal_data:
                message = strategy.format_signal_message(signal_data)
                message_id = await self.post_to_telegram(message)
                
                if message_id:
                    self.signal_generator.update_telegram_message_id(
                        signal_data['id'],
                        message_id
                    )
                    print(f"[SCHEDULER] Signal posted to Telegram: {message_id}")
        
        except Exception as e:
            print(f"[SCHEDULER] Error in signal check: {e}")


def create_scheduler(tenant_id: Optional[str] = None) -> SignalBotScheduler:
    """Factory function to create a SignalBotScheduler instance"""
    return SignalBotScheduler(tenant_id=tenant_id)
