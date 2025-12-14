"""
Bot Manager - handles active bot switching and strategy selection
Only one bot can be active at any time
"""
from typing import Optional, Dict, Any
from db import get_active_bot, set_active_bot, get_open_signal
from core.logging import get_logger

logger = get_logger(__name__)


class BotManager:
    """
    Manages which bot is active and provides the correct strategy
    Only one bot can generate signals at any time
    """
    
    def __init__(self, tenant_id: str = None):
        self._strategies = {}
        self.tenant_id = tenant_id
        self._load_strategies()
    
    def _load_strategies(self):
        """Load all available strategies"""
        from bots.strategies.aggressive import aggressive_strategy
        from bots.strategies.conservative import conservative_strategy
        from bots.strategies.custom import custom_strategy
        
        self._strategies = {
            'aggressive': aggressive_strategy,
            'conservative': conservative_strategy,
            'custom': custom_strategy
        }
    
    def get_active_strategy(self):
        """Get the currently active strategy"""
        active_bot = get_active_bot(tenant_id=self.tenant_id)
        if active_bot and active_bot in self._strategies:
            return self._strategies[active_bot]
        return self._strategies['aggressive']
    
    def get_active_bot_name(self) -> str:
        """Get the name of the currently active bot"""
        return get_active_bot(tenant_id=self.tenant_id) or 'aggressive'
    
    def set_active_bot(self, bot_type: str) -> bool:
        """
        Set the active bot type
        
        Args:
            bot_type: 'aggressive', 'conservative', or 'custom'
        
        Returns:
            True if successful
        """
        if bot_type not in self._strategies:
            logger.warning(f"Invalid bot type: {bot_type}")
            return False
        
        return set_active_bot(bot_type)
    
    def get_available_bots(self) -> list:
        """Get list of available bot types"""
        return list(self._strategies.keys())
    
    def can_generate_signal(self) -> bool:
        """
        Check if a new signal can be generated
        Returns False if there's already an open signal
        """
        open_signal = get_open_signal()
        if open_signal:
            logger.info(f"Cannot generate new signal - Signal #{open_signal['id']} is still open")
            return False
        return True
    
    def get_open_signal(self) -> Optional[Dict[str, Any]]:
        """Get the currently open signal if any"""
        return get_open_signal()
    
    def reload_all_configs(self):
        """Reload configuration for all strategies"""
        for strategy in self._strategies.values():
            strategy.reload_config()
        logger.info("All strategy configs reloaded")


bot_manager = BotManager()
