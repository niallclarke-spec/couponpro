"""
Tenant-scoped Runtime Container

Provides a TenantRuntime class that holds tenant-scoped dependencies for the scheduler
and bot systems. Eliminates global singletons and ensures explicit tenant context.

Usage:
    runtime = TenantRuntime(tenant_id="entrylab")
    
    # Access tenant-scoped services
    signal_engine = runtime.get_signal_engine()
    telegram_bot = runtime.get_telegram_bot()
    
    # Context management
    with runtime.request_context():
        # All operations have tenant context
        signals = runtime.db.get_forex_signals(status='pending')
"""
import os
from dataclasses import dataclass, field
from typing import Optional, Any, Dict
from contextlib import contextmanager

from core.logging import get_logger, set_request_context, clear_request_context

logger = get_logger(__name__)


class TenantContextError(RuntimeError):
    """Raised when tenant context is missing or invalid."""
    pass


@dataclass
class SchedulerState:
    """Shared state for scheduler modules within a tenant runtime."""
    last_daily_recap: Optional[Any] = None
    last_weekly_recap: Optional[Any] = None
    last_1h_check: Optional[Any] = None
    last_bot_config_updated_at: Optional[Any] = None
    last_forex_config_updated_at: Optional[Any] = None


class TenantRuntime:
    """
    Tenant-scoped runtime container for scheduler and bot operations.
    
    Holds and lazily initializes tenant-specific dependencies:
    - Signal engine (forex signal generation)
    - Telegram bot (messaging)
    - Strategy registry
    - Config loaders
    
    All DB operations go through this runtime to ensure tenant_id is always passed.
    """
    
    def __init__(self, tenant_id: str, request_id: Optional[str] = None):
        if not tenant_id:
            raise TenantContextError("tenant_id is required for TenantRuntime")
        
        self.tenant_id = tenant_id
        self.request_id = request_id
        self.state = SchedulerState()
        
        self._signal_engine: Optional[Any] = None
        self._telegram_bot: Optional[Any] = None
        self._milestone_tracker: Optional[Any] = None
        self._twelve_data_client: Optional[Any] = None
        self._db_module: Optional[Any] = None
        
        logger.debug(f"TenantRuntime initialized for tenant: {tenant_id}")
    
    @classmethod
    def from_env(cls) -> 'TenantRuntime':
        """
        Create TenantRuntime from environment variables.
        
        Requires TENANT_ID env var to be set.
        
        Raises:
            TenantContextError: If TENANT_ID is not set
        """
        tenant_id = os.environ.get('TENANT_ID')
        if not tenant_id:
            raise TenantContextError(
                "TENANT_ID environment variable is required. "
                "Set via --tenant CLI flag or TENANT_ID env var."
            )
        return cls(tenant_id=tenant_id)
    
    @contextmanager
    def request_context(self, request_id: Optional[str] = None):
        """
        Context manager that sets logging context for the current operation.
        
        Usage:
            with runtime.request_context():
                # All logs include tenant_id
                do_work()
        """
        set_request_context(tenant_id=self.tenant_id, request_id=request_id or self.request_id)
        try:
            yield
        finally:
            clear_request_context()
    
    @property
    def db(self):
        """Get the database module with tenant context."""
        if self._db_module is None:
            import db as db_module
            self._db_module = db_module
        return self._db_module
    
    def get_signal_engine(self):
        """
        Get or create the forex signal engine for this tenant.
        
        Returns a tenant-scoped ForexSignalEngine instance.
        """
        if self._signal_engine is None:
            from forex_signals import ForexSignalEngine
            self._signal_engine = ForexSignalEngine(tenant_id=self.tenant_id)
            logger.debug(f"Created ForexSignalEngine for tenant: {self.tenant_id}")
        return self._signal_engine
    
    def get_telegram_bot(self):
        """
        Get or create the forex telegram bot for this tenant.
        
        Returns a tenant-scoped ForexTelegramBot instance.
        """
        if self._telegram_bot is None:
            from forex_bot import ForexTelegramBot
            self._telegram_bot = ForexTelegramBot(tenant_id=self.tenant_id)
            logger.debug(f"Created ForexTelegramBot for tenant: {self.tenant_id}")
        return self._telegram_bot
    
    def get_milestone_tracker(self):
        """Get the milestone tracker (shared across tenants for now)."""
        if self._milestone_tracker is None:
            from bots.core.milestone_tracker import MilestoneTracker
            self._milestone_tracker = MilestoneTracker()
        return self._milestone_tracker
    
    def get_price_client(self):
        """Get the Twelve Data price client."""
        if self._twelve_data_client is None:
            from forex_api import twelve_data_client
            self._twelve_data_client = twelve_data_client
        return self._twelve_data_client
    
    def get_forex_signals(self, status: Optional[str] = None, limit: int = 10) -> list:
        """
        Get forex signals for this tenant.
        
        Ensures tenant_id is always passed.
        """
        return self.db.get_forex_signals(
            status=status,
            limit=limit,
            tenant_id=self.tenant_id
        )
    
    def update_forex_signal_status(self, signal_id: int, status: str, pips: float, exit_price: float):
        """Update forex signal status for this tenant."""
        return self.db.update_forex_signal_status(
            signal_id=signal_id,
            status=status,
            result_pips=pips,
            close_price=exit_price,
            tenant_id=self.tenant_id
        )
    
    def get_forex_config(self) -> Dict[str, Any]:
        """Get forex config for this tenant."""
        return self.db.get_forex_config(tenant_id=self.tenant_id) or {}
    
    def get_active_bot(self) -> str:
        """Get the active bot type for this tenant."""
        return self.db.get_active_bot(tenant_id=self.tenant_id) or 'aggressive'
    
    def get_last_recap_date(self, recap_type: str):
        """Get last recap date for this tenant."""
        return self.db.get_last_recap_date(recap_type=recap_type, tenant_id=self.tenant_id)
    
    def set_last_recap_date(self, recap_type: str, value: str):
        """Set last recap date for this tenant."""
        return self.db.set_last_recap_date(recap_type=recap_type, value=value, tenant_id=self.tenant_id)
    
    def reload_config(self):
        """Reload configuration for signal engine."""
        if self._signal_engine:
            self._signal_engine.reload_config()
            logger.info("Config hot-reloaded for signal engine")
    
    def refresh_bot_credentials(self) -> bool:
        """
        Hot-reload Telegram bot credentials from the database.
        
        Allows the scheduler to pick up token updates without restart.
        Forces bot instantiation if not yet created to detect late configuration.
        
        Returns:
            True if credentials were updated, False if unchanged or failed
        """
        try:
            if self._telegram_bot is None:
                from forex_bot import ForexTelegramBot
                self._telegram_bot = ForexTelegramBot(tenant_id=self.tenant_id)
                if self._telegram_bot._configured:
                    logger.info(f"Late bot initialization succeeded for tenant: {self.tenant_id}")
                    return True
                logger.debug(f"Bot not configured for tenant: {self.tenant_id}")
                return False
            return self._telegram_bot.refresh_credentials()
        except Exception as e:
            logger.error(f"Bot credential refresh failed for tenant {self.tenant_id}: {e}")
            self._telegram_bot = None
            return False


def create_tenant_runtime(tenant_id: Optional[str] = None) -> TenantRuntime:
    """
    Factory function to create TenantRuntime.
    
    Args:
        tenant_id: Tenant identifier. If None, reads from TENANT_ID env var.
    
    Returns:
        TenantRuntime instance
    
    Raises:
        TenantContextError: If tenant_id is not provided and env var not set
    """
    if tenant_id:
        return TenantRuntime(tenant_id=tenant_id)
    return TenantRuntime.from_env()


def require_tenant_runtime(tenant_id: Optional[str] = None) -> TenantRuntime:
    """
    Require a TenantRuntime, exiting with error if tenant not provided.
    
    Used by CLI entrypoints to enforce tenant context.
    
    Args:
        tenant_id: Tenant identifier from CLI arg
    
    Returns:
        TenantRuntime instance
    
    Exits:
        sys.exit(2) if tenant_id is not provided
    """
    import sys
    
    resolved_tenant = tenant_id or os.environ.get('TENANT_ID')
    
    if not resolved_tenant:
        logger.error("❌ tenant_id is required. Use --tenant <tenant_id> or set TENANT_ID env var.")
        sys.exit(2)
    
    return TenantRuntime(tenant_id=resolved_tenant)


def get_runtime(tenant_id: str) -> TenantRuntime:
    """
    Get a new TenantRuntime instance for the given tenant.
    
    IMPORTANT: This always returns a NEW instance - no caching.
    Each call creates a fresh runtime to ensure tenant isolation.
    
    Args:
        tenant_id: Tenant identifier (required)
    
    Returns:
        New TenantRuntime instance
    
    Example:
        runtime = get_runtime("entrylab")
    """
    return TenantRuntime(tenant_id=tenant_id)
