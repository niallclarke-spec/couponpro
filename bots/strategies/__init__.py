"""
Trading strategies for signal generation
"""
from bots.strategies.base import BaseStrategy
from bots.strategies.aggressive import AggressiveStrategy
from bots.strategies.conservative import ConservativeStrategy
from bots.strategies.custom import CustomStrategy

__all__ = ['BaseStrategy', 'AggressiveStrategy', 'ConservativeStrategy', 'CustomStrategy']
