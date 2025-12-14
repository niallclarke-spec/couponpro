"""
Error Boundary / Guarded Execution

Provides a standardized way to wrap functions with error handling that:
1. Logs the error with full context
2. Calls notify_error() for alerting
3. Handles re-raise vs exit behavior based on mode

Usage:
    from core.error_boundary import run_guarded
    
    def my_function():
        do_risky_work()
    
    run_guarded(my_function, tenant_id="entrylab", context={"signal_id": 123})
"""
import os
import sys
import traceback
from typing import Callable, Optional, Dict, Any, TypeVar

from core.logging import get_logger
from core.alerts import notify_error

logger = get_logger(__name__)

T = TypeVar('T')


def is_dev_mode() -> bool:
    """Check if we're running in development mode."""
    return os.environ.get('REPLIT_DEV_DOMAIN') is not None or \
           os.environ.get('DEV_MODE', '').lower() in ('1', 'true', 'yes')


def run_guarded(
    fn: Callable[[], T],
    *,
    tenant_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    reraise_in_dev: bool = True,
    exit_on_error: bool = True,
    exit_code: int = 1
) -> Optional[T]:
    """
    Execute a function with error boundary protection.
    
    On exception:
    - Logs the full stack trace
    - Calls notify_error() with context
    - In dev mode: re-raises if reraise_in_dev=True
    - In production: exits with exit_code if exit_on_error=True
    
    Args:
        fn: Function to execute (no arguments)
        tenant_id: Tenant identifier for context
        context: Additional context dict for error reporting
        reraise_in_dev: Whether to re-raise in dev mode (default True)
        exit_on_error: Whether to sys.exit in production (default True)
        exit_code: Exit code to use on error (default 1)
    
    Returns:
        The return value of fn(), or None if an error occurred
    
    Example:
        run_guarded(
            lambda: scheduler.run_once(),
            tenant_id="entrylab",
            context={"operation": "signal_check"}
        )
    """
    try:
        return fn()
    except Exception as exc:
        stack_trace = traceback.format_exc()
        
        error_context = {
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "module": getattr(fn, '__module__', 'unknown'),
            "function": getattr(fn, '__name__', 'anonymous'),
        }
        
        if context:
            error_context.update(context)
        
        logger.error(
            f"Unhandled exception in guarded execution: {exc}",
            extra={
                "tenant_id": tenant_id,
                "stack_trace": stack_trace,
                **error_context
            }
        )
        
        notify_error(
            f"Unhandled exception: {type(exc).__name__}: {exc}",
            tenant_id=tenant_id,
            context=error_context
        )
        
        if is_dev_mode() and reraise_in_dev:
            raise
        
        if exit_on_error:
            logger.error(f"Exiting with code {exit_code} due to unhandled exception")
            sys.exit(exit_code)
        
        return None


async def run_guarded_async(
    fn: Callable[[], T],
    *,
    tenant_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    reraise_in_dev: bool = True,
    exit_on_error: bool = True,
    exit_code: int = 1
) -> Optional[T]:
    """
    Async version of run_guarded.
    
    Same behavior as run_guarded but awaits the function.
    
    Args:
        fn: Async function to execute (no arguments)
        tenant_id: Tenant identifier for context  
        context: Additional context dict for error reporting
        reraise_in_dev: Whether to re-raise in dev mode (default True)
        exit_on_error: Whether to sys.exit in production (default True)
        exit_code: Exit code to use on error (default 1)
    
    Returns:
        The return value of fn(), or None if an error occurred
    """
    try:
        return await fn()
    except Exception as exc:
        stack_trace = traceback.format_exc()
        
        error_context = {
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "module": getattr(fn, '__module__', 'unknown'),
            "function": getattr(fn, '__name__', 'anonymous'),
        }
        
        if context:
            error_context.update(context)
        
        logger.error(
            f"Unhandled exception in guarded async execution: {exc}",
            extra={
                "tenant_id": tenant_id,
                "stack_trace": stack_trace,
                **error_context
            }
        )
        
        notify_error(
            f"Unhandled exception: {type(exc).__name__}: {exc}",
            tenant_id=tenant_id,
            context=error_context
        )
        
        if is_dev_mode() and reraise_in_dev:
            raise
        
        if exit_on_error:
            logger.error(f"Exiting with code {exit_code} due to unhandled exception")
            sys.exit(exit_code)
        
        return None
