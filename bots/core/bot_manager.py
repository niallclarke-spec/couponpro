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
    
    def __init__(self, tenant_id: Optional[str] = None):
        self._strategies: Dict[str, Any] = {}
        self.tenant_id = tenant_id
        self._load_strategies()
    
    def _load_strategies(self):
        """Load all available strategies from the canonical strategies/ module"""
        from strategies.strategy_loader import STRATEGY_REGISTRY
        from strategies.aggressive import AggressiveStrategy
        from strategies.conservative import ConservativeStrategy
        from strategies.raja_banks import RajaBanksStrategy
        
        self._strategies = {
            'aggressive': AggressiveStrategy(tenant_id=self.tenant_id),
            'conservative': ConservativeStrategy(tenant_id=self.tenant_id),
            'raja_banks': RajaBanksStrategy(tenant_id=self.tenant_id)
        }
    
    def get_active_strategy(self):
        """Get the currently active strategy"""
        active_bot = get_active_bot(tenant_id=self.tenant_id)
        if active_bot and active_bot in self._strategies:
            return self._strategies[active_bot]
        return self._strategies.get('aggressive')
    
    def get_active_bot_name(self) -> str:
        """Get the name of the currently active bot"""
        return get_active_bot(tenant_id=self.tenant_id) or 'aggressive'
    
    def set_active_bot(self, bot_type: str) -> bool:
        """
        Set the active bot type
        
        Args:
            bot_type: 'aggressive', 'conservative', or 'raja_banks'
        
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
        open_signal = get_open_signal(tenant_id=self.tenant_id)
        if open_signal:
            logger.info(f"Cannot generate new signal - Signal #{open_signal['id']} is still open")
            return False
        return True
    
    def get_open_signal(self) -> Optional[Dict[str, Any]]:
        """Get the currently open signal if any"""
        return get_open_signal(tenant_id=self.tenant_id)
    
    def reload_all_configs(self):
        """Reload configuration for all strategies"""
        for strategy in self._strategies.values():
            if hasattr(strategy, 'reload_config'):
                strategy.reload_config()
        logger.info("All strategy configs reloaded")


def create_bot_manager(tenant_id: Optional[str] = None) -> BotManager:
    """Factory function to create a BotManager instance"""
    return BotManager(tenant_id=tenant_id)
