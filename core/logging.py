"""
Thin logging wrapper for server.py
Preserves existing print() format: [TAG] message
NO side effects at import time.
"""
import logging
import sys


class TagFormatter(logging.Formatter):
    """Formatter that outputs [TAG] message format (no timestamps)"""
    
    def format(self, record):
        # If a tag is provided, use [TAG] format
        tag = getattr(record, 'tag', None)
        if tag:
            return f"[{tag}] {record.getMessage()}"
        # Otherwise just output the message
        return record.getMessage()


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Get a logger instance configured for console output.
    
    Usage:
        logger = get_logger(__name__)
        logger.info("message", extra={'tag': 'AUTH'})
    
    Or use the log() helper for simpler syntax.
    """
    logger = logging.getLogger(name or 'promostack')
    
    # Only configure if not already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(TagFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        # Prevent propagation to root logger
        logger.propagate = False
    
    return logger


# Module-level logger for convenience
_logger = None


def _get_module_logger():
    global _logger
    if _logger is None:
        _logger = get_logger('promostack')
    return _logger


def log(tag: str, message: str, level: str = 'info'):
    """
    Simple logging function that mimics print(f"[TAG] message")
    
    Usage:
        log('AUTH', 'Token expired')
        log('FOREX', f'Error: {e}', level='error')
    
    Equivalent to:
        print(f"[AUTH] Token expired")
        print(f"[FOREX] Error: {e}")
    """
    logger = _get_module_logger()
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message, extra={'tag': tag})


def info(tag: str, message: str):
    """Log info message with tag"""
    log(tag, message, 'info')


def error(tag: str, message: str):
    """Log error message with tag"""
    log(tag, message, 'error')


def warning(tag: str, message: str):
    """Log warning message with tag"""
    log(tag, message, 'warning')


def debug(tag: str, message: str):
    """Log debug message with tag"""
    log(tag, message, 'debug')
