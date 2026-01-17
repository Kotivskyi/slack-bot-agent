"""Structured logging configuration.

Provides logging formatters and setup for both development (readable)
and production (JSON) environments.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, ClassVar

from app.core.config import settings


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging in production.

    Outputs log records as JSON objects with consistent fields
    for easy parsing by log aggregation systems.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a JSON string."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add location info
        if record.pathname:
            log_data["location"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Add extra fields from the record
        for key, value in record.__dict__.items():
            if key not in (
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "taskName",
                "message",
            ):
                log_data[key] = value

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


class ReadableFormatter(logging.Formatter):
    """Human-readable formatter for development.

    Provides colored, easy-to-read log output for local development.
    """

    COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET: ClassVar[str] = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record for readable output."""
        color = self.COLORS.get(record.levelname, self.RESET)
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Build the base message
        message = f"{color}{timestamp} [{record.levelname:8}]{self.RESET} {record.name}: {record.getMessage()}"

        # Add extra fields if present
        extras = []
        for key, value in record.__dict__.items():
            if key not in (
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "taskName",
                "message",
            ):
                extras.append(f"{key}={value}")

        if extras:
            message += f" | {' '.join(extras)}"

        # Add exception info if present
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        return message


def setup_logging() -> None:
    """Set up logging configuration based on environment.

    In production environments, uses JSON formatting.
    In development/local environments, uses readable formatting.
    """
    # Determine the formatter based on environment
    is_production = settings.ENVIRONMENT == "production"

    # Create handler
    handler = logging.StreamHandler(sys.stdout)

    if is_production:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(ReadableFormatter())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Set log level
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    root_logger.setLevel(log_level)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)


class ContextFilter(logging.Filter):
    """Filter that adds context variables to log records.

    Automatically adds request_id and user_id from context variables
    to all log records.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Add context to the log record."""
        from app.core.middleware import get_logging_context

        context = get_logging_context()
        record.request_id = context.get("request_id")
        record.user_id = context.get("user_id")
        return True
