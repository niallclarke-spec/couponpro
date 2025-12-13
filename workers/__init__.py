"""
Workers Package - Clean namespace for background worker modules.

This package provides thin wrappers around existing worker implementations
without modifying their internal logic. All workers are started via bootstrap.

Exports:
- start_forex_scheduler: Start the forex signals scheduler
- price_monitor: PriceMonitor singleton instance
- milestone_tracker: MilestoneTracker singleton instance
"""

from workers.scheduler import start_forex_scheduler
from workers.price_monitor import price_monitor
from workers.milestone_tracker import milestone_tracker

__all__ = [
    'start_forex_scheduler',
    'price_monitor',
    'milestone_tracker',
]
