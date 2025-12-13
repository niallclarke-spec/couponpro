"""
Price Monitor Worker Wrapper

Thin wrapper that re-exports the price monitor singleton.
No internal logic is modified - just provides a clean import path.
"""

from bots.core.price_monitor import price_monitor, PriceMonitor

__all__ = ['price_monitor', 'PriceMonitor']
