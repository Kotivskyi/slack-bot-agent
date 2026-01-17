"""Structured logging configuration.

Provides logging formatters and setup for both development (readable)
and production (JSON) environments, with optional file-based logging
for debugging and AI assistant access.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, ClassVar

from app.core.config import settings

# Log file configuration
LOG_DIR = Path(__file__).parent.parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"
LOG_FILE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_FILE_BACKUP_COUNT = 5


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


def setup_logging(enable_file_logging: bool = True) -> None:
    """Set up logging configuration based on environment.

    In production environments, uses JSON formatting.
    In development/local environments, uses readable formatting.

    Args:
        enable_file_logging: Whether to enable file-based logging.
            Defaults to True. File logs are written to logs/app.log
            with rotation (10MB max, 5 backups).
    """
    # Determine the formatter based on environment
    is_production = settings.ENVIRONMENT == "production"

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # Set log level
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    root_logger.setLevel(log_level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    if is_production:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(ReadableFormatter())
    root_logger.addHandler(console_handler)

    # File handler (always uses JSON for easy parsing)
    if enable_file_logging:
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                LOG_FILE,
                maxBytes=LOG_FILE_MAX_BYTES,
                backupCount=LOG_FILE_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(JSONFormatter())
            file_handler.setLevel(logging.DEBUG)  # Capture all levels in file
            root_logger.addHandler(file_handler)
            logging.info(f"File logging enabled: {LOG_FILE}")
        except Exception as e:
            logging.warning(f"Could not enable file logging: {e}")

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
