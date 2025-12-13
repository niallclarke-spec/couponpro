"""
Scheduler Worker Wrapper

Thin wrapper that re-exports the forex scheduler start function.
No internal logic is modified - just provides a clean import path.
"""

from forex_scheduler import start_forex_scheduler

__all__ = ['start_forex_scheduler']
