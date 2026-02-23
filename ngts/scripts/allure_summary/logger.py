"""
Logging Configuration for Allure Summary Tool.

This module provides a centralized logging setup with debug support.
"""

import logging
import sys
from typing import Optional

from ngts.scripts.allure_summary.config import LOG_FORMAT, LOG_DATE_FORMAT, LOG_LEVEL_DEFAULT


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colored output for terminal."""

    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'

    def format(self, record):
        # Add color to level name
        color = self.COLORS.get(record.levelname, '')
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logger(
    name: str = "allure_summary",
    level: str = LOG_LEVEL_DEFAULT,
    verbose: bool = False
) -> logging.Logger:
    """
    Setup and return a configured logger.

    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        verbose: If True, sets level to DEBUG

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Don't add handlers if already configured
    if logger.handlers:
        return logger

    # Set level
    log_level = logging.DEBUG if verbose else getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Use colored formatter for terminal
    if sys.stdout.isatty():
        formatter = ColoredFormatter(LOG_FORMAT, LOG_DATE_FORMAT)
    else:
        formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)

    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str = "allure_summary") -> logging.Logger:
    """Get an existing logger or create a new one."""
    return logging.getLogger(name)


class DebugContext:
    """
    Context manager for debug logging with additional context.

    Usage:
        with DebugContext(logger, "Fetching report"):
            # ... do work ...
    """

    def __init__(self, logger: logging.Logger, operation: str, **context):
        self.logger = logger
        self.operation = operation
        self.context = context

    def __enter__(self):
        ctx_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
        self.logger.debug(f"[START] {self.operation} | {ctx_str}" if ctx_str else f"[START] {self.operation}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.logger.error(f"[FAILED] {self.operation} | Error: {exc_val}")
        else:
            self.logger.debug(f"[DONE] {self.operation}")
        return False


def log_function_call(logger: logging.Logger):
    """
    Decorator to log function entry and exit.

    Usage:
        @log_function_call(logger)
        def my_function(arg1, arg2):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            logger.debug(f"[CALL] {func_name}(args={len(args)}, kwargs={list(kwargs.keys())})")
            try:
                result = func(*args, **kwargs)
                logger.debug(f"[RETURN] {func_name} -> success")
                return result
            except Exception as e:
                logger.error(f"[EXCEPTION] {func_name} raised {type(e).__name__}: {e}")
                raise
        return wrapper
    return decorator
