"""
Structured Logging Infrastructure

Provides centralized logging with automatic context injection for:
- tenant_id (from tenant context)
- request_id (from request context)
- module name
- timestamps

Uses contextvars for async-safe context propagation.

Usage:
    from core.logging import get_logger, configure_logging, set_request_context

    configure_logging()  # Call once at startup
    
    logger = get_logger(__name__)
    logger.info("Processing signal")
    
    # With request context
    set_request_context(tenant_id="entrylab", request_id="abc123")
    logger.info("Handling request")  # Automatically includes tenant/request
    clear_request_context()
"""
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from typing import Optional

_tenant_id_var: ContextVar[Optional[str]] = ContextVar('tenant_id', default=None)
_request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
_job_id_var: ContextVar[Optional[str]] = ContextVar('job_id', default=None)

_configured = False


def get_context() -> dict:
    """Get current logging context as a dictionary."""
    return {
        'tenant_id': _tenant_id_var.get(),
        'request_id': _request_id_var.get(),
        'job_id': _job_id_var.get(),
    }


def set_request_context(
    tenant_id: Optional[str] = None,
    request_id: Optional[str] = None,
    job_id: Optional[str] = None
) -> None:
    """
    Set request context for logging.
    
    Args:
        tenant_id: The tenant identifier
        request_id: Request identifier (generated if not provided)
        job_id: Background job identifier
    """
    if tenant_id is not None:
        _tenant_id_var.set(tenant_id)
    if request_id is not None:
        _request_id_var.set(request_id)
    elif _request_id_var.get() is None:
        _request_id_var.set(str(uuid.uuid4())[:8])
    if job_id is not None:
        _job_id_var.set(job_id)


def clear_request_context() -> None:
    """Clear all request context."""
    _tenant_id_var.set(None)
    _request_id_var.set(None)
    _job_id_var.set(None)


def get_tenant_id() -> Optional[str]:
    """Get current tenant_id from context."""
    return _tenant_id_var.get()


def get_request_id() -> Optional[str]:
    """Get current request_id from context."""
    return _request_id_var.get()


def get_job_id() -> Optional[str]:
    """Get current job_id from context."""
    return _job_id_var.get()


class ContextFilter(logging.Filter):
    """
    Logging filter that injects tenant_id and request_id into log records.
    Automatically adds context from contextvars to every log message.
    """
    
    def filter(self, record: logging.LogRecord) -> bool:
        record.tenant_id = _tenant_id_var.get() or '-'
        record.request_id = _request_id_var.get() or '-'
        record.job_id = _job_id_var.get() or '-'
        return True


class StructuredFormatter(logging.Formatter):
    """
    Formatter that outputs structured log messages with context.
    
    Format: [timestamp] [LEVEL] [module] [tenant:X] [req:Y] message
    """
    
    def __init__(self, include_timestamp: bool = True):
        self.include_timestamp = include_timestamp
        super().__init__()
    
    def format(self, record: logging.LogRecord) -> str:
        tenant_id = getattr(record, 'tenant_id', '-')
        request_id = getattr(record, 'request_id', '-')
        
        parts = []
        
        if self.include_timestamp:
            timestamp = self.formatTime(record, '%Y-%m-%d %H:%M:%S')
            parts.append(f"[{timestamp}]")
        
        parts.append(f"[{record.levelname}]")
        
        module_name = record.name.split('.')[-1] if record.name else 'root'
        parts.append(f"[{module_name}]")
        
        if tenant_id and tenant_id != '-':
            parts.append(f"[tenant:{tenant_id}]")
        
        if request_id and request_id != '-':
            parts.append(f"[req:{request_id}]")
        
        parts.append(record.getMessage())
        
        message = ' '.join(parts)
        
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        
        if record.exc_text:
            message = message + '\n' + record.exc_text
        
        return message


class TagFormatter(logging.Formatter):
    """Legacy formatter that outputs [TAG] message format (no timestamps)."""
    
    def format(self, record: logging.LogRecord) -> str:
        tag = getattr(record, 'tag', None)
        if tag:
            return f"[{tag}] {record.getMessage()}"
        return record.getMessage()


def configure_logging(
    level: Optional[str] = None,
    include_timestamp: bool = True,
    use_structured: bool = True
) -> None:
    """
    Configure logging for the application.
    
    Should be called once at application startup.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR). 
               Defaults to LOG_LEVEL env var or INFO.
        include_timestamp: Whether to include timestamps in log output.
        use_structured: Whether to use structured format with context.
    
    Example:
        # In server.py or main entry point
        from core.logging import configure_logging
        configure_logging()
    """
    global _configured
    
    if _configured:
        return
    
    log_level_str = level or os.environ.get('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    
    if use_structured:
        handler.setFormatter(StructuredFormatter(include_timestamp=include_timestamp))
        handler.addFilter(ContextFilter())
    else:
        handler.setFormatter(TagFormatter())
    
    root_logger.addHandler(handler)
    
    for logger_name in ['urllib3', 'asyncio', 'telegram', 'httpx', 'httpcore']:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    _configured = True
    
    logger = logging.getLogger('core.logging')
    logger.debug(f"Logging configured: level={log_level_str}, structured={use_structured}")


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance.
    
    Usage:
        logger = get_logger(__name__)
        logger.info("Processing complete")
        logger.exception("Error occurred")  # Includes stack trace
    
    Args:
        name: Logger name, typically __name__ of the module.
    
    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name or 'promostack')
    return logger


_module_logger: Optional[logging.Logger] = None


def _get_module_logger() -> logging.Logger:
    """Get the module-level logger (lazy initialization)."""
    global _module_logger
    if _module_logger is None:
        _module_logger = get_logger('promostack')
    return _module_logger


def log(tag: str, message: str, level: str = 'info') -> None:
    """
    Simple logging function that mimics print(f"[TAG] message").
    
    DEPRECATED: Use get_logger(__name__) directly instead.
    
    Usage:
        log('AUTH', 'Token expired')
        log('FOREX', f'Error: {e}', level='error')
    """
    logger = _get_module_logger()
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(f"[{tag}] {message}")


def info(tag: str, message: str) -> None:
    """Log info message with tag. DEPRECATED: Use logger.info() instead."""
    log(tag, message, 'info')


def error(tag: str, message: str) -> None:
    """Log error message with tag. DEPRECATED: Use logger.error() instead."""
    log(tag, message, 'error')


def warning(tag: str, message: str) -> None:
    """Log warning message with tag. DEPRECATED: Use logger.warning() instead."""
    log(tag, message, 'warning')


def debug(tag: str, message: str) -> None:
    """Log debug message with tag. DEPRECATED: Use logger.debug() instead."""
    log(tag, message, 'debug')
