"""
Scheduler Runner - backwards compatibility wrapper.

Provides a thin SchedulerRunner class that wraps ForexSchedulerRunner
for backwards compatibility without triggering DB connections on import.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.runtime import TenantRuntime


class SchedulerRunner:
    """
    Generic scheduler runner wrapper for backwards compatibility.
    
    This class provides a stable import path (scheduler.runner.SchedulerRunner)
    that delegates to the actual ForexSchedulerRunner implementation.
    """
    
    def __init__(self, tenant_id: str):
        """
        Initialize the scheduler runner.
        
        Args:
            tenant_id: The tenant identifier to run the scheduler for.
        """
        self.tenant_id = tenant_id
        self._runner = None
    
    def _get_runner(self):
        """Lazy-load the actual runner to avoid DB init on import."""
        if self._runner is None:
            from forex_scheduler import ForexSchedulerRunner
            from core.runtime import TenantRuntime
            
            runtime = TenantRuntime(tenant_id=self.tenant_id)
            self._runner = ForexSchedulerRunner(runtime)
        return self._runner
    
    def run_once(self) -> None:
        """
        Run one iteration of the scheduler.
        
        Internally delegates to ForexSchedulerRunner.run_once().
        """
        runner = self._get_runner()
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(runner.run_once())
        else:
            loop.run_until_complete(runner.run_once())
