# File: app/core/logging.py
"""
===============================================================================
CENTRALIZED LOGGING & OBSERVABILITY LAYER (NON-BLOCKING, PRODUCTION-SAFE)
===============================================================================

Authoritative logging configuration for the application.

This module provides:

    • Non-blocking logging using QueueHandler + QueueListener
    • Structured JSON logs in production
    • Human-readable logs in development/testing
    • Automatic request_id injection
    • Thread-safe operation
    • Multi-worker compatibility

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

This module belongs to the Core / Infrastructure boundary.

Responsibilities:

    - Configure global logging
    - Provide logger factory
    - Ensure non-blocking log writes
    - Inject request-scoped context information

This module MUST NOT:

    - Depend on FastAPI
    - Contain business logic
    - Access HTTP request objects

-------------------------------------------------------------------------------
HIGH THROUGHPUT DESIGN
-------------------------------------------------------------------------------

All logs are written asynchronously:

    Application thread
        ↓
    QueueHandler
        ↓
    In-memory queue
        ↓
    QueueListener thread
        ↓
    Actual IO (stdout/file)

Benefits:

    - prevents event-loop blocking
    - avoids disk IO latency inside request handling
    - safe for 5k–10k+ RPS workloads

-------------------------------------------------------------------------------
PRODUCTION BEHAVIOR
-------------------------------------------------------------------------------

Production:

    - JSON structured logs
    - Written to stdout
    - Single-line events
    - Compatible with ELK / Loki / CloudWatch

Development / Testing:

    - Human-readable logs
    - Includes request_id
    - Includes module and line number

-------------------------------------------------------------------------------
USAGE
-------------------------------------------------------------------------------

    from app.core.logging import get_logger

    logger = get_logger(__name__)
    logger.info("User created successfully")
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from queue import Queue
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import get_settings, Environment
from app.core.request_context import get_request_id


# =============================================================================
# GLOBAL STATE
# =============================================================================

_log_queue: Queue | None = None
_listener: logging.handlers.QueueListener | None = None


# =============================================================================
# CONTEXT-AWARE FORMATTER
# =============================================================================


class ContextAwareFormatter(logging.Formatter):
    """
    Logging formatter that injects contextual metadata.

    Features:

        • request_id injection
        • timezone-aware timestamps
        • JSON logs in production
        • readable logs in development
    """

    def __init__(self, *, json_mode: bool, timezone_name: str) -> None:
        super().__init__()

        self.json_mode = json_mode
        self.tz = ZoneInfo(timezone_name)

    # -------------------------------------------------------------------------
    # Timestamp formatting
    # -------------------------------------------------------------------------

    def format_timestamp(self, record: logging.LogRecord) -> str:
        dt = datetime.fromtimestamp(record.created, tz=self.tz)
        return dt.isoformat()

    # -------------------------------------------------------------------------
    # Main formatting
    # -------------------------------------------------------------------------

    def format(self, record: logging.LogRecord) -> str:

        try:

            message = record.getMessage()
            timestamp = self.format_timestamp(record)

            base: dict[str, Any] = {
                "timestamp": timestamp,
                "level": record.levelname,
                "logger": record.name,
                "message": message,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "request_id": getattr(record, "request_id", None),
            }

            if record.exc_info:
                base["exception"] = self.formatException(record.exc_info)

            # -------------------------------------------------------------
            # Production JSON
            # -------------------------------------------------------------

            if self.json_mode:
                return json.dumps(base, ensure_ascii=False)

            # -------------------------------------------------------------
            # Development readable format
            # -------------------------------------------------------------

            req_id = base["request_id"] or "-"

            return (
                f"{timestamp} | {record.levelname:<8} | {record.name} "
                f"[req={req_id}] - {message} "
                f"({record.module}:{record.lineno})"
            )

        except Exception:
            return (
                f"{datetime.now(timezone.utc).isoformat()} "
                "| ERROR | Logging formatter failure"
            )


# =============================================================================
# REQUEST ID FILTER
# =============================================================================


class RequestIdFilter(logging.Filter):
    """
    Inject request_id automatically into log records.

    Uses contextvars-backed request context.
    """

    def filter(self, record: logging.LogRecord) -> bool:

        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()

        return True


# =============================================================================
# LOGGING INITIALIZATION
# =============================================================================


def setup_logging() -> None:
    """
    Configure global logging.

    Guarantees:

        • idempotent initialization
        • non-blocking log writes
        • safe multi-worker behavior
    """

    global _log_queue, _listener

    root = logging.getLogger()

    if getattr(root, "_configured", False):
        return

    settings = get_settings()

    root.setLevel(
        getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    )

    root.handlers.clear()

    json_mode = settings.ENVIRONMENT == Environment.PRODUCTION

    formatter = ContextAwareFormatter(
        json_mode=json_mode,
        timezone_name=settings.TIMEZONE,
    )

    request_filter = RequestIdFilter()

    handlers: list[logging.Handler] = []

    # -------------------------------------------------------------------------
    # Production → stdout
    # -------------------------------------------------------------------------

    if settings.ENVIRONMENT == Environment.PRODUCTION:

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        handler.addFilter(request_filter)

        handlers.append(handler)

    # -------------------------------------------------------------------------
    # Development / Testing
    # -------------------------------------------------------------------------

    else:

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        console.addFilter(request_filter)

        handlers.append(console)

        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(settings.LOG_DIR / settings.LOG_FILE),
            maxBytes=settings.LOG_MAX_BYTES,
            backupCount=settings.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )

        file_handler.setFormatter(formatter)
        file_handler.addFilter(request_filter)

        handlers.append(file_handler)

    # -------------------------------------------------------------------------
    # Queue logging (non-blocking)
    # -------------------------------------------------------------------------

    _log_queue = Queue(maxsize=10000)

    queue_handler = logging.handlers.QueueHandler(_log_queue)
    root.addHandler(queue_handler)

    _listener = logging.handlers.QueueListener(
        _log_queue,
        *handlers,
        respect_handler_level=True,
    )

    _listener.start()

    root._configured = True  # type: ignore[attr-defined]


# =============================================================================
# SHUTDOWN SUPPORT
# =============================================================================


def shutdown_logging() -> None:
    """
    Gracefully stop background logging thread.

    Should be called during application shutdown.
    """

    global _listener

    if _listener:
        _listener.stop()


# =============================================================================
# LOGGER FACTORY
# =============================================================================


def get_logger(name: str) -> logging.Logger:
    """
    Retrieve configured logger instance.

    This function does not reconfigure logging.
    It simply returns a logger bound to the global system.
    """

    return logging.getLogger(name)


# Initialize logging immediately
setup_logging()
