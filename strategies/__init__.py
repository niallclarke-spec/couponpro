"""
Strategy Module
Modular trading strategy system for forex signals bot
"""
from strategies.base_strategy import BaseStrategy
from strategies.strategy_loader import get_active_strategy, get_available_strategies, STRATEGY_REGISTRY

__all__ = ['BaseStrategy', 'get_active_strategy', 'get_available_strategies', 'STRATEGY_REGISTRY']
