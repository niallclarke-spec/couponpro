"""
Tenant Context Infrastructure

Provides thread-safe tenant context management for multi-tenant operations.
Ensures all database operations have explicit tenant context and logs tenant_id.

Usage:
    from tenant_context import tenant_context, require_tenant, get_current_tenant

    # Context manager for background jobs
    with tenant_context("entrylab", job_id="forex_signal_123"):
        result = db.get_forex_signals(tenant_id=get_current_tenant())

    # Decorator for functions requiring tenant context
    @require_tenant
    def process_signal(signal_id, tenant_id):
        ...
"""

import functools
import logging
import threading
import uuid
from contextlib import contextmanager
from typing import Optional

_tenant_local = threading.local()

logger = logging.getLogger(__name__)


class TenantContextError(Exception):
    """Raised when tenant context is missing or invalid."""
    pass


def get_current_tenant() -> Optional[str]:
    """Get the current tenant_id from thread-local context."""
    return getattr(_tenant_local, 'tenant_id', None)


def get_current_job_id() -> Optional[str]:
    """Get the current job_id from thread-local context."""
    return getattr(_tenant_local, 'job_id', None)


def get_current_request_id() -> Optional[str]:
    """Get the current request_id from thread-local context."""
    return getattr(_tenant_local, 'request_id', None)


@contextmanager
def tenant_context(tenant_id: str, job_id: Optional[str] = None, request_id: Optional[str] = None):
    """
    Context manager that sets tenant context for the current thread.
    
    Args:
        tenant_id: The tenant identifier (required, cannot be None/empty)
        job_id: Optional job identifier for background tasks
        request_id: Optional request identifier for HTTP requests
    
    Raises:
        TenantContextError: If tenant_id is None or empty
    
    Example:
        with tenant_context("entrylab", job_id="recap_daily"):
            signals = db.get_forex_signals(tenant_id=get_current_tenant())
    """
    if not tenant_id:
        raise TenantContextError("tenant_id cannot be None or empty")
    
    old_tenant = getattr(_tenant_local, 'tenant_id', None)
    old_job_id = getattr(_tenant_local, 'job_id', None)
    old_request_id = getattr(_tenant_local, 'request_id', None)
    
    _tenant_local.tenant_id = tenant_id
    _tenant_local.job_id = job_id or str(uuid.uuid4())[:8]
    _tenant_local.request_id = request_id
    
    logger.debug(
        f"[TENANT_CTX] Entered context: tenant={tenant_id}, job={_tenant_local.job_id}"
    )
    
    try:
        yield
    finally:
        _tenant_local.tenant_id = old_tenant
        _tenant_local.job_id = old_job_id
        _tenant_local.request_id = old_request_id
        logger.debug(
            f"[TENANT_CTX] Exited context: tenant={tenant_id}, job={job_id}"
        )


def require_tenant(func):
    """
    Decorator that ensures tenant_id is provided and not None.
    
    The decorated function MUST have tenant_id as a keyword argument.
    Raises TenantContextError if tenant_id is missing or None.
    
    Example:
        @require_tenant
        def get_signals(status=None, tenant_id=None):
            ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        tenant_id = kwargs.get('tenant_id')
        
        if tenant_id is None:
            tenant_id = get_current_tenant()
            if tenant_id:
                kwargs['tenant_id'] = tenant_id
        
        if not kwargs.get('tenant_id'):
            raise TenantContextError(
                f"tenant_id is required for {func.__name__}(). "
                f"Either pass tenant_id explicitly or use tenant_context()."
            )
        
        job_id = get_current_job_id()
        request_id = get_current_request_id()
        
        log_extra = {
            'tenant_id': kwargs['tenant_id'],
            'function': func.__name__,
        }
        if job_id:
            log_extra['job_id'] = job_id
        if request_id:
            log_extra['request_id'] = request_id
        
        logger.debug(f"[TENANT_OP] {func.__name__} called", extra=log_extra)
        
        return func(*args, **kwargs)
    
    return wrapper


def assert_tenant_context(tenant_id: Optional[str], operation: str = "database operation") -> str:
    """
    Assert that tenant_id is provided. Returns the tenant_id if valid.
    
    Args:
        tenant_id: The tenant_id to validate
        operation: Description of operation for error message
    
    Returns:
        The validated tenant_id
    
    Raises:
        TenantContextError: If tenant_id is None or empty
    """
    if not tenant_id:
        thread_tenant = get_current_tenant()
        if thread_tenant:
            return thread_tenant
        raise TenantContextError(
            f"tenant_id is required for {operation}. "
            f"Pass tenant_id explicitly or use tenant_context()."
        )
    return tenant_id


def log_tenant_operation(operation: str, tenant_id: str, **extra):
    """
    Log a tenant-scoped operation with structured context.
    
    Args:
        operation: Name of the operation
        tenant_id: The tenant identifier
        **extra: Additional context to log
    """
    job_id = get_current_job_id()
    request_id = get_current_request_id()
    
    parts = [f"[TENANT:{tenant_id}]"]
    if job_id:
        parts.append(f"[JOB:{job_id}]")
    if request_id:
        parts.append(f"[REQ:{request_id}]")
    parts.append(operation)
    
    if extra:
        extra_str = ", ".join(f"{k}={v}" for k, v in extra.items())
        parts.append(f"({extra_str})")
    
    logger.info(" ".join(parts))
