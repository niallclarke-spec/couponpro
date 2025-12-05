"""
Signal Bot System
Three strategy modes: Aggressive, Conservative, Custom
Only one bot can be active at any time
"""
from bots.core.bot_manager import BotManager
from bots.core.signal_generator import SignalGenerator

__all__ = ['BotManager', 'SignalGenerator']
