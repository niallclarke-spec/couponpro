"""
Centralized Alerting / Error Notification Hook

Provides a single entry point for error notifications across the application.
Default implementation logs warnings, but can be extended to send alerts via
email, Slack, PagerDuty, etc.

Usage:
    from core.alerts import notify_error
    
    try:
        do_work()
    except Exception as e:
        notify_error(f"Work failed: {e}", tenant_id="entrylab", context={"signal_id": 123})
"""
from typing import Optional, Dict, Any
from core.logging import get_logger

logger = get_logger(__name__)


def notify_error(
    message: str,
    tenant_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Notify about an error condition.
    
    Default implementation logs at WARNING level. Override or extend this
    function to integrate with external alerting systems.
    
    Args:
        message: Human-readable error description
        tenant_id: Optional tenant identifier for multi-tenant context
        context: Optional dict with additional context (signal_id, error type, etc.)
    
    Example:
        notify_error(
            "Signal generation failed",
            tenant_id="entrylab",
            context={"error_type": "timeout", "duration_s": 120}
        )
    """
    ctx_str = ""
    if context:
        ctx_str = f" context={context}"
    
    if tenant_id:
        logger.warning(f"[ALERT] tenant={tenant_id}: {message}{ctx_str}")
    else:
        logger.warning(f"[ALERT] {message}{ctx_str}")


def notify_tenant_failure(
    tenant_id: str,
    error: str,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Convenience function for tenant-level failures in the scheduler.
    
    Args:
        tenant_id: The failing tenant's identifier
        error: Error message or description
        context: Optional additional context
    """
    notify_error(
        f"Tenant processing failed: {error}",
        tenant_id=tenant_id,
        context=context
    )
