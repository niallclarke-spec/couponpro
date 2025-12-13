"""
Application Context - Centralized container for all application-level singletons and state.

This module provides an AppContext class that wraps all global state, availability flags,
and service references used throughout the application.
"""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AppContext:
    """
    Centralized application context holding all singletons and availability flags.
    
    Usage:
        from core.app_context import get_app_context
        ctx = get_app_context()
        if ctx.database_available:
            # use ctx.db_pool
    """
    object_storage_available: bool = False
    telegram_bot_available: bool = False
    database_available: bool = False
    coupon_validator_available: bool = False
    forex_scheduler_available: bool = False
    stripe_available: bool = False
    
    db_pool: Optional[Any] = None
    telegram_bot_module: Optional[Any] = None
    object_storage_service: Optional[Any] = None
    coupon_validator_module: Optional[Any] = None
    forex_scheduler_module: Optional[Any] = None
    stripe_client: Optional[Any] = None
    
    def is_ready(self) -> bool:
        """Check if the application context has been initialized."""
        return True


_app_context: Optional[AppContext] = None


def get_app_context() -> AppContext:
    """
    Get the global application context singleton.
    
    Returns:
        AppContext: The initialized application context.
        
    Raises:
        RuntimeError: If the context has not been initialized via bootstrap.
    """
    global _app_context
    if _app_context is None:
        raise RuntimeError(
            "AppContext not initialized. Call core.bootstrap.initialize_app() first."
        )
    return _app_context


def set_app_context(ctx: AppContext) -> None:
    """
    Set the global application context. Called by bootstrap.initialize_app().
    
    Args:
        ctx: The AppContext instance to set as global.
    """
    global _app_context
    _app_context = ctx


def reset_app_context() -> None:
    """Reset the global application context. Primarily for testing."""
    global _app_context
    _app_context = None
