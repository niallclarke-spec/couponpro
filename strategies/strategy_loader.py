"""
Strategy Loader
Dynamically loads and manages trading strategies
"""
from typing import Dict, Optional, List
from strategies.base_strategy import BaseStrategy

STRATEGY_REGISTRY: Dict[str, type] = {}


def register_strategy(strategy_class: type):
    """Register a strategy class in the global registry"""
    if hasattr(strategy_class, 'bot_type'):
        STRATEGY_REGISTRY[strategy_class.bot_type] = strategy_class
    return strategy_class


def _load_strategies():
    """Load all available strategies into the registry"""
    from strategies.aggressive import AggressiveStrategy
    from strategies.conservative import ConservativeStrategy
    from strategies.raja_banks import RajaBanksStrategy
    
    register_strategy(AggressiveStrategy)
    register_strategy(ConservativeStrategy)
    register_strategy(RajaBanksStrategy)


_load_strategies()


def get_available_strategies(tenant_id: Optional[str] = None) -> List[Dict]:
    """Get list of all available strategies with their display info"""
    strategies = []
    for bot_type, strategy_class in STRATEGY_REGISTRY.items():
        strategy = strategy_class(tenant_id=tenant_id)
        strategies.append(strategy.get_display_info())
    return strategies


def get_active_strategy(bot_type: str = 'aggressive', tenant_id: Optional[str] = None) -> Optional[BaseStrategy]:
    """
    Get the active strategy instance based on bot_type.
    
    Args:
        bot_type: The type of bot/strategy to use
        tenant_id: The tenant ID for multi-tenancy support
    
    Returns:
        Strategy instance or None if not found
    """
    strategy_class = STRATEGY_REGISTRY.get(bot_type)
    if strategy_class:
        return strategy_class(tenant_id=tenant_id)
    
    if 'aggressive' in STRATEGY_REGISTRY:
        print(f"[STRATEGY] Unknown bot_type '{bot_type}', falling back to aggressive")
        return STRATEGY_REGISTRY['aggressive'](tenant_id=tenant_id)
    
    return None


def get_strategy_by_type(bot_type: str, tenant_id: Optional[str] = None) -> Optional[BaseStrategy]:
    """Get a specific strategy by its bot_type"""
    return get_active_strategy(bot_type, tenant_id=tenant_id)
