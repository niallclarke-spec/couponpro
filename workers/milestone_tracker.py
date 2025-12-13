"""
Milestone Tracker Worker Wrapper

Thin wrapper that re-exports the milestone tracker singleton.
No internal logic is modified - just provides a clean import path.
"""

from bots.core.milestone_tracker import milestone_tracker, MilestoneTracker

__all__ = ['milestone_tracker', 'MilestoneTracker']
