"""
Scheduler Generator Module

Responsible for signal generation:
- Checking for new signals on 15min and 1h timeframes
- Hot-reloading config when bot_config/forex_config changes
- Enforcing one-signal-at-a-time rule
"""
from datetime import datetime
from typing import Optional, Dict, Any
from core.logging import get_logger
from core.runtime import TenantRuntime
from scheduler.messenger import Messenger

logger = get_logger(__name__)


class SignalGenerator:
    """
    Generates new forex signals based on strategy and market conditions.
    
    Responsibilities:
    - Check for new signals on 15min/1h timeframes
    - Hot-reload config when database settings change
    - Enforce one active signal at a time
    - Post new signals via messenger
    """
    
    def __init__(self, runtime: TenantRuntime, messenger: Messenger):
        self.runtime = runtime
        self.messenger = messenger
        self.tenant_id = runtime.tenant_id
    
    @property
    def signal_engine(self):
        """Get the signal engine from runtime."""
        return self.runtime.get_signal_engine()
    
    def check_config_update(self) -> bool:
        """
        Check if bot_config or forex_config has been updated and trigger hot-reload.
        
        Returns:
            True if config was reloaded
        """
        try:
            from db import tenant_conn
            
            db = self.runtime.db
            if not db.db_pool.connection_pool:
                return False
            
            with tenant_conn(self.tenant_id) as (conn, cursor):
                cursor.execute("""
                    SELECT updated_at FROM bot_config WHERE setting_key = 'active_bot' AND tenant_id = %s
                """, (self.tenant_id,))
                bot_row = cursor.fetchone()
                current_bot_updated_at = bot_row[0] if bot_row and bot_row[0] else None
                
                cursor.execute("""
                    SELECT MAX(updated_at) FROM forex_config WHERE tenant_id = %s
                """, (self.tenant_id,))
                forex_row = cursor.fetchone()
                current_forex_updated_at = forex_row[0] if forex_row and forex_row[0] else None
                
                should_reload = False
                state = self.runtime.state
                
                if state.last_bot_config_updated_at is None:
                    state.last_bot_config_updated_at = current_bot_updated_at
                elif current_bot_updated_at and current_bot_updated_at != state.last_bot_config_updated_at:
                    logger.info("🔄 bot_config change detected")
                    should_reload = True
                    state.last_bot_config_updated_at = current_bot_updated_at
                
                if state.last_forex_config_updated_at is None:
                    state.last_forex_config_updated_at = current_forex_updated_at
                elif current_forex_updated_at and current_forex_updated_at != state.last_forex_config_updated_at:
                    logger.info("🔄 forex_config change detected (guardrails/indicators)")
                    should_reload = True
                    state.last_forex_config_updated_at = current_forex_updated_at
                
                if should_reload:
                    logger.info("🔄 Reloading config...")
                    self.runtime.reload_config()
                    logger.info("✅ Config hot-reloaded successfully")
                    return True
                    
        except Exception as e:
            logger.warning(f"⚠️ Error checking config update: {e}")
        
        return False
    
    async def run_signal_check(self) -> Optional[int]:
        """
        Check for new signals on both 15min and 1h timeframes.
        
        Returns:
            Signal ID if a new signal was posted, None otherwise
        """
        try:
            with self.runtime.request_context():
                self.check_config_update()
                
                if not self.signal_engine.is_trading_hours():
                    logger.info("Outside trading hours (8AM-10PM GMT), skipping signal check")
                    return None
                
                pending_signals = self.runtime.get_forex_signals(status='pending')
                if pending_signals and len(pending_signals) > 0:
                    signal = pending_signals[0]
                    logger.info(f"⏸️ Active signal #{signal['id']} still pending - skipping new signal check")
                    logger.info(f"Entry: ${signal['entry_price']}, TP: ${signal['take_profit']}, SL: ${signal['stop_loss']}")
                    return None
                
                now = datetime.utcnow()
                state = self.runtime.state
                should_check_1h = False
                
                if state.last_1h_check is None:
                    should_check_1h = True
                else:
                    minutes_since_1h = (now - state.last_1h_check).total_seconds() / 60
                    if minutes_since_1h >= 30:
                        should_check_1h = True
                
                signal_data = await self.signal_engine.check_for_signals(timeframe='15min')
                
                if signal_data:
                    signal_id = await self.messenger.post_signal(signal_data)
                    if signal_id:
                        logger.info(f"✅ New 15min signal #{signal_id} posted successfully")
                        if should_check_1h:
                            state.last_1h_check = now
                            logger.info("⏭️ Skipped 1h check (signal already active)")
                        return signal_id
                
                if should_check_1h:
                    logger.info("📊 Checking 1-hour timeframe...")
                    signal_data_1h = await self.signal_engine.check_for_signals(timeframe='1h')
                    state.last_1h_check = now
                    
                    if signal_data_1h:
                        signal_id = await self.messenger.post_signal(signal_data_1h)
                        if signal_id:
                            logger.info(f"✅ New 1h signal #{signal_id} posted successfully")
                            return signal_id
                        else:
                            logger.error("❌ Failed to post 1h signal to Telegram")
                
                return None
                
        except Exception as e:
            logger.exception("❌ Error in signal check")
            return None
