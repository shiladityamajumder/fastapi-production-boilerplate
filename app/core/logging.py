"""
File: app/core/logging.py

Structured, queue-backed, context-aware application logging.

The logging pipeline provides:

- non-blocking log production,
- structured JSON output for production,
- readable console output for development,
- request, correlation, trace, and task identifiers,
- recursive sensitive-value redaction,
- optional rotating file logging,
- bounded queue protection,
- process-safe reinitialization after worker forking.

Application code should use ``get_logger(__name__)`` and provide structured,
non-sensitive metadata through the standard logging ``extra`` argument.

In containerized environments, ``LOG_TO_FILE`` should normally remain disabled
so logs are written to stdout and collected by the container platform.
"""

from __future__ import annotations

import atexit
import copy
import json
import logging
import logging.handlers
import os
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from queue import Full, Queue
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import (
    AppSettings,
    Environment,
    get_settings,
)
from app.core.request_context import (
    get_correlation_id,
    get_request_id,
    get_task_id,
    get_trace_id,
)


# =============================================================================
# LOG RECORD METADATA
# =============================================================================

# Standard fields created internally by ``logging.LogRecord``. These fields are
# excluded when collecting custom metadata supplied through ``extra``.
_LOG_RECORD_BUILTINS = frozenset(
    logging.LogRecord(
        name="",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__
) | {
    "asctime",
    "message",
}


# Generic credential and secret field names. Keys are normalized before
# matching, so snake_case, camelCase, kebab-case, and similar variants match.
_SENSITIVE_KEYS = frozenset(
    {
        "accesskey",
        "accesstoken",
        "apikey",
        "authorization",
        "bearertoken",
        "clientsecret",
        "connectionstring",
        "cookie",
        "credentials",
        "databasepassword",
        "databaseurl",
        "dsn",
        "emailpassword",
        "idtoken",
        "jwt",
        "password",
        "passwd",
        "privatekey",
        "proxyauthorization",
        "refreshtoken",
        "secret",
        "secretkey",
        "sessioncookie",
        "sessiontoken",
        "setcookie",
        "smtppassword",
        "token",
    }
)


# Maximum recursive depth used while sanitizing structured values.
_MAX_SANITIZE_DEPTH = 8


# =============================================================================
# TEXT REDACTION PATTERNS
# =============================================================================

# Redact authorization values embedded in plain text.
_AUTH_PATTERN = re.compile(
    r"(?i)\b(?:authorization|proxy-authorization|bearer)"
    r"\b\s*[:=]?\s*[^\s,;]+"
)


# Redact credentials embedded in URLs such as:
#
#     protocol://username:password@hostname
_URI_PASSWORD_PATTERN = re.compile(
    r"(://[^:/\s]+:)([^@/\s]+)(@)"
)


# Redact common key-value assignments such as:
#
#     password=secret
#     api_key: abc123
#     "client_secret": "abc123"
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b("
    r"password|passwd|pwd|secret|secret[_-]?key|"
    r"api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"id[_-]?token|client[_-]?secret|private[_-]?key|"
    r"session[_-]?token"
    r")\b"
    r"[\"']?\s*[:=]\s*[\"']?"
    r"([^\s,;\"'}]+)"
)


# =============================================================================
# PROCESS-LOCAL LOGGING STATE
# =============================================================================

_log_queue: Queue[logging.LogRecord] | None = None
_queue_handler: NonBlockingQueueHandler | None = None
_listener: logging.handlers.QueueListener | None = None
_sink_handlers: tuple[logging.Handler, ...] = ()

_setup_lock = Lock()

_configured_pid: int | None = None
_dropped_records = 0
_redaction_enabled = True


# =============================================================================
# REDACTION HELPERS
# =============================================================================

def _normalize_sensitive_key(
    value: str,
) -> str:
    """
    Normalize a metadata key for sensitivity comparison.

    Args:
        value: Raw metadata key.

    Returns:
        Lowercase alphanumeric key.
    """

    return re.sub(
        pattern=r"[^a-z0-9]",
        repl="",
        string=value.casefold(),
    )


def _is_sensitive_key(
    key: str | None,
) -> bool:
    """
    Return whether a metadata key represents sensitive information.

    Args:
        key: Optional metadata key.

    Returns:
        ``True`` when the key should be redacted.
    """

    if not key:
        return False

    return (
        _normalize_sensitive_key(key)
        in _SENSITIVE_KEYS
    )


def _redact_text(
    value: str,
) -> str:
    """
    Redact common credential patterns embedded in text.

    Args:
        value: Plain text value.

    Returns:
        Redacted text.
    """

    if not _redaction_enabled:
        return value

    redacted = _AUTH_PATTERN.sub(
        "authorization=[REDACTED]",
        value,
    )

    redacted = _URI_PASSWORD_PATTERN.sub(
        r"\1[REDACTED]\3",
        redacted,
    )

    return _SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: (
            f"{match.group(1)}=[REDACTED]"
        ),
        redacted,
    )


def sanitize_log_value(
    value: Any,
    *,
    key: str | None = None,
) -> Any:
    """
    Recursively sanitize a structured logging value.

    This function is a defense-in-depth safeguard. Callers should still avoid
    logging request bodies, complete external responses, ORM objects, files,
    credentials, or other confidential information.

    Args:
        value: Structured metadata value.
        key: Optional field name associated with the value.

    Returns:
        Redacted, JSON-compatible representation.
    """

    return _sanitize_log_value(
        value=value,
        key=key,
        depth=0,
        seen=set(),
    )


def _sanitize_log_value(
    *,
    value: Any,
    key: str | None,
    depth: int,
    seen: set[int],
) -> Any:
    """
    Internal recursive sanitization implementation.

    Args:
        value: Value being sanitized.
        key: Associated metadata key.
        depth: Current recursion depth.
        seen: Object identifiers currently being traversed.

    Returns:
        Sanitized representation.
    """

    if (
        _redaction_enabled
        and _is_sensitive_key(key)
    ):
        return "[REDACTED]"

    if value is None or isinstance(
        value,
        (
            bool,
            int,
            float,
        ),
    ):
        return value

    if isinstance(value, str):
        return _redact_text(value)

    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"

    if isinstance(value, bytearray):
        return f"<bytearray:{len(value)}>"

    if depth >= _MAX_SANITIZE_DEPTH:
        return "<maximum-depth-reached>"

    if isinstance(value, Mapping):
        object_id = id(value)

        if object_id in seen:
            return "<circular-reference>"

        seen.add(object_id)

        try:
            return {
                str(item_key): _sanitize_log_value(
                    value=item_value,
                    key=str(item_key),
                    depth=depth + 1,
                    seen=seen,
                )
                for item_key, item_value
                in value.items()
            }
        finally:
            seen.remove(object_id)

    if isinstance(value, Sequence) and not isinstance(
        value,
        (
            str,
            bytes,
            bytearray,
        ),
    ):
        object_id = id(value)

        if object_id in seen:
            return "<circular-reference>"

        seen.add(object_id)

        try:
            return [
                _sanitize_log_value(
                    value=item,
                    key=None,
                    depth=depth + 1,
                    seen=seen,
                )
                for item in value
            ]
        finally:
            seen.remove(object_id)

    if isinstance(
        value,
        (
            set,
            frozenset,
        ),
    ):
        object_id = id(value)

        if object_id in seen:
            return "<circular-reference>"

        seen.add(object_id)

        try:
            return [
                _sanitize_log_value(
                    value=item,
                    key=None,
                    depth=depth + 1,
                    seen=seen,
                )
                for item in value
            ]
        finally:
            seen.remove(object_id)

    return _redact_text(
        repr(value)
    )


# =============================================================================
# LOGGING FILTER
# =============================================================================

class ContextFilter(logging.Filter):
    """
    Attach execution context to every log record.

    The filter runs before the record is placed into the queue. Context-variable
    values are therefore captured on the request or task execution thread rather
    than the queue-listener thread.
    """

    def filter(
        self,
        record: logging.LogRecord,
    ) -> bool:
        """
        Add request, correlation, trace, and task identifiers.

        Explicit values already supplied through ``extra`` are preserved.

        Args:
            record: Log record being processed.

        Returns:
            Always ``True``.
        """

        record.request_id = (
            getattr(
                record,
                "request_id",
                None,
            )
            or get_request_id()
        )

        record.correlation_id = (
            getattr(
                record,
                "correlation_id",
                None,
            )
            or get_correlation_id()
        )

        record.trace_id = (
            getattr(
                record,
                "trace_id",
                None,
            )
            or get_trace_id()
        )

        record.task_id = (
            getattr(
                record,
                "task_id",
                None,
            )
            or get_task_id()
        )

        return True


# =============================================================================
# QUEUE HANDLER
# =============================================================================

class NonBlockingQueueHandler(
    logging.handlers.QueueHandler
):
    """
    Place log records into a bounded queue without blocking application work.

    When the queue is full, records are dropped rather than blocking request,
    task, or event-loop execution. Controlled warnings are written directly to
    stderr so queue saturation remains visible.
    """

    def prepare(
        self,
        record: logging.LogRecord,
    ) -> logging.LogRecord:
        """
        Copy a log record while preserving exception information.

        The standard ``QueueHandler.prepare`` removes exception information for
        process-safe pickling. This implementation uses an in-process queue, so
        the traceback can safely remain attached for structured formatting.

        Args:
            record: Original log record.

        Returns:
            Prepared record copied for queue processing.
        """

        prepared = copy.copy(record)

        prepared.msg = record.getMessage()
        prepared.args = None
        prepared.exc_text = None
        prepared.stack_info = record.stack_info

        return prepared

    def enqueue(
        self,
        record: logging.LogRecord,
    ) -> None:
        """
        Add a record without waiting for queue capacity.

        Args:
            record: Prepared log record.
        """

        global _dropped_records

        try:
            self.queue.put_nowait(record)
        except Full:
            _dropped_records += 1

            if (
                _dropped_records in {
                    1,
                    10,
                    100,
                }
                or _dropped_records % 1_000 == 0
            ):
                sys.stderr.write(
                    "Logging queue is full; records are being dropped. "
                    f"dropped={_dropped_records}\n"
                )
                sys.stderr.flush()


# =============================================================================
# LOG FORMATTER
# =============================================================================

class StructuredFormatter(logging.Formatter):
    """
    Format records as JSON or readable console log lines.
    """

    def __init__(
        self,
        *,
        json_mode: bool,
        timezone_name: str,
    ) -> None:
        """
        Initialize the formatter.

        Args:
            json_mode: Emit compact JSON when ``True``.
            timezone_name: IANA timezone used for log timestamps.
        """

        super().__init__()

        self._json_mode = json_mode
        self._timezone = ZoneInfo(timezone_name)

    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        """
        Render one structured log record.

        Args:
            record: Log record to serialize.

        Returns:
            Formatted log line.
        """

        timestamp = datetime.fromtimestamp(
            record.created,
            tz=self._timezone,
        ).isoformat()

        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_text(
                record.getMessage()
            ),
            "request_id": getattr(
                record,
                "request_id",
                None,
            ),
            "correlation_id": getattr(
                record,
                "correlation_id",
                None,
            ),
            "trace_id": getattr(
                record,
                "trace_id",
                None,
            ),
            "task_id": getattr(
                record,
                "task_id",
                None,
            ),
            "process_id": record.process,
            "process_name": record.processName,
            "thread_id": record.thread,
            "thread_name": record.threadName,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        for key, value in record.__dict__.items():
            if (
                key in _LOG_RECORD_BUILTINS
                or key in payload
            ):
                continue

            payload[key] = sanitize_log_value(
                value,
                key=key,
            )

        if record.exc_info:
            payload["exception"] = _redact_text(
                self.formatException(
                    record.exc_info
                )
            )

        if record.stack_info:
            payload["stack"] = _redact_text(
                self.formatStack(
                    record.stack_info
                )
            )

        if self._json_mode:
            return json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )

        return self._format_readable(
            payload=payload,
        )

    @staticmethod
    def _format_readable(
        *,
        payload: dict[str, Any],
    ) -> str:
        """
        Format a structured payload for local console output.

        Args:
            payload: Sanitized structured log payload.

        Returns:
            Readable log line.
        """

        identity_values = {
            "request_id": payload.get(
                "request_id"
            ),
            "correlation_id": payload.get(
                "correlation_id"
            ),
            "trace_id": payload.get(
                "trace_id"
            ),
            "task_id": payload.get(
                "task_id"
            ),
        }

        identity_context = {
            key: value
            for key, value in identity_values.items()
            if value is not None
        }

        reserved_keys = {
            "timestamp",
            "level",
            "logger",
            "message",
            "request_id",
            "correlation_id",
            "trace_id",
            "task_id",
            "process_id",
            "process_name",
            "thread_id",
            "thread_name",
            "module",
            "function",
            "line",
            "exception",
            "stack",
        }

        custom_context = {
            key: value
            for key, value in payload.items()
            if (
                key not in reserved_keys
                and value is not None
            )
        }

        identity_suffix = ""

        if identity_context:
            identity_suffix = (
                " | execution="
                + json.dumps(
                    identity_context,
                    ensure_ascii=False,
                    default=str,
                    sort_keys=True,
                )
            )

        context_suffix = ""

        if custom_context:
            context_suffix = (
                " | context="
                + json.dumps(
                    custom_context,
                    ensure_ascii=False,
                    default=str,
                    sort_keys=True,
                )
            )

        source_suffix = (
            " | source="
            f"{payload['module']}."
            f"{payload['function']}:"
            f"{payload['line']}"
        )

        process_suffix = (
            " | process="
            f"{payload['process_id']}"
            f":{payload['thread_name']}"
        )

        exception_suffix = (
            f"\n{payload['exception']}"
            if "exception" in payload
            else ""
        )

        stack_suffix = (
            f"\n{payload['stack']}"
            if "stack" in payload
            else ""
        )

        return (
            f"{payload['timestamp']} | "
            f"{payload['level']:<8} | "
            f"{payload['logger']} | "
            f"{payload['message']}"
            f"{identity_suffix}"
            f"{context_suffix}"
            f"{source_suffix}"
            f"{process_suffix}"
            f"{exception_suffix}"
            f"{stack_suffix}"
        )


# =============================================================================
# CONFIGURATION
# =============================================================================

def setup_logging(
    settings: AppSettings | None = None,
    *,
    force: bool = False,
) -> None:
    """
    Configure process-local application logging.

    Configuration is performed once per operating-system process. If a worker
    process is forked, the child process creates a fresh queue, listener thread,
    and output handlers instead of reusing inherited logging resources.

    Args:
        settings: Optional validated settings override.
        force: Reconfigure logging even when already configured in the current
            process.

    Raises:
        Exception: Propagates logging initialization failures.
    """

    global _configured_pid
    global _dropped_records
    global _listener
    global _log_queue
    global _queue_handler
    global _redaction_enabled
    global _sink_handlers

    current_pid = os.getpid()

    with _setup_lock:
        if (
            _configured_pid == current_pid
            and not force
        ):
            return

        if _configured_pid == current_pid:
            _shutdown_logging_unlocked()

        elif _configured_pid is not None:
            # State belonging to another process must not be stopped or closed
            # from the current process.
            _clear_logging_state_unlocked()

        resolved = settings or get_settings()

        _dropped_records = 0
        _redaction_enabled = (
            resolved.SENSITIVE_DATA_REDACTION_ENABLED
        )

        logging.raiseExceptions = (
            resolved.ENVIRONMENT
            != Environment.PRODUCTION
        )

        root_logger = logging.getLogger()
        root_logger.setLevel(
            resolved.LOG_LEVEL
        )

        # Replace inherited or framework-installed root handlers with one
        # predictable application-owned logging pipeline.
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(
                handler
            )

            _close_handler(
                handler
            )

        json_mode = (
            resolved.LOG_JSON
            or resolved.ENVIRONMENT
            == Environment.PRODUCTION
        )

        formatter = StructuredFormatter(
            json_mode=json_mode,
            timezone_name=resolved.TIMEZONE,
        )

        sinks: list[logging.Handler] = []
        listener: logging.handlers.QueueListener | None = None
        queue_handler: NonBlockingQueueHandler | None = None

        try:
            console_handler = logging.StreamHandler(
                sys.stdout
            )

            console_handler.setLevel(
                resolved.LOG_LEVEL
            )

            console_handler.setFormatter(
                formatter
            )

            sinks.append(
                console_handler
            )

            if resolved.LOG_TO_FILE:
                resolved.log_directory.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                file_handler = (
                    logging.handlers.RotatingFileHandler(
                        filename=(
                            resolved.log_directory
                            / resolved.LOG_FILE
                        ),
                        maxBytes=resolved.LOG_MAX_BYTES,
                        backupCount=(
                            resolved.LOG_BACKUP_COUNT
                        ),
                        encoding="utf-8",
                    )
                )

                file_handler.setLevel(
                    resolved.LOG_LEVEL
                )

                file_handler.setFormatter(
                    formatter
                )

                sinks.append(
                    file_handler
                )

            log_queue: Queue[logging.LogRecord] = Queue(
                maxsize=resolved.LOG_QUEUE_SIZE
            )

            queue_handler = NonBlockingQueueHandler(
                log_queue
            )

            queue_handler.setLevel(
                resolved.LOG_LEVEL
            )

            queue_handler.addFilter(
                ContextFilter()
            )

            listener = logging.handlers.QueueListener(
                log_queue,
                *sinks,
                respect_handler_level=True,
            )

            listener.start()
            root_logger.addHandler(
                queue_handler
            )

        except Exception:
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass

            if queue_handler is not None:
                _close_handler(
                    queue_handler
                )

            for sink in sinks:
                _close_handler(
                    sink
                )

            raise

        _log_queue = log_queue
        _queue_handler = queue_handler
        _listener = listener
        _sink_handlers = tuple(sinks)
        _configured_pid = current_pid

        # Route warnings emitted through Python's ``warnings`` module into the
        # configured logging pipeline.
        logging.captureWarnings(True)


def shutdown_logging() -> None:
    """
    Drain queued records and close process-local logging resources.

    The operation is idempotent and safe to call from application shutdown,
    tests, background-worker shutdown, and interpreter exit.
    """

    with _setup_lock:
        _shutdown_logging_unlocked()


def _shutdown_logging_unlocked() -> None:
    """
    Stop and clear logging resources while the setup lock is held.
    """

    global _configured_pid
    global _listener
    global _log_queue
    global _queue_handler
    global _sink_handlers

    current_pid = os.getpid()
    root_logger = logging.getLogger()

    queue_handler = _queue_handler
    listener = _listener
    sinks = _sink_handlers

    if queue_handler is not None:
        root_logger.removeHandler(
            queue_handler
        )

    # Only stop threads and handlers created by the current process.
    if _configured_pid == current_pid:
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                sys.stderr.write(
                    "Failed to stop logging queue listener cleanly.\n"
                )
                sys.stderr.flush()

        if queue_handler is not None:
            _close_handler(
                queue_handler
            )

        for sink in sinks:
            _close_handler(
                sink
            )

    _log_queue = None
    _queue_handler = None
    _listener = None
    _sink_handlers = ()
    _configured_pid = None


def _close_handler(
    handler: logging.Handler,
) -> None:
    """
    Flush and close a logging handler without raising.

    Args:
        handler: Logging handler to close.
    """

    try:
        handler.flush()
    except Exception:
        pass

    try:
        handler.close()
    except Exception:
        pass


def _clear_logging_state_unlocked() -> None:
    """
    Clear inherited process state without closing parent-owned resources.

    This is used when the current process detects logging objects created by a
    different operating-system process.
    """

    global _configured_pid
    global _listener
    global _log_queue
    global _queue_handler
    global _sink_handlers

    _log_queue = None
    _queue_handler = None
    _listener = None
    _sink_handlers = ()
    _configured_pid = None


def _reset_logging_after_fork() -> None:
    """
    Reset inherited logging state inside a forked child process.

    Listener threads do not survive process forking. The child must therefore
    create a new lock, queue, listener, and handlers when ``setup_logging`` is
    called.
    """

    global _configured_pid
    global _dropped_records
    global _listener
    global _log_queue
    global _queue_handler
    global _setup_lock
    global _sink_handlers

    _log_queue = None
    _queue_handler = None
    _listener = None
    _sink_handlers = ()

    _configured_pid = None
    _dropped_records = 0

    # A lock inherited while held by another thread can remain permanently
    # locked in a child process, so replace it after forking.
    _setup_lock = Lock()


# Register process-fork cleanup where supported. This is particularly important
# for prefork background workers.
if hasattr(os, "register_at_fork"):
    os.register_at_fork(
        after_in_child=_reset_logging_after_fork
    )


# =============================================================================
# LOGGER FACTORY
# =============================================================================

def get_logger(
    name: str,
) -> logging.Logger:
    """
    Return a standard-library logger.

    Args:
        name: Logger name, normally ``__name__``.

    Returns:
        Logger instance.
    """

    normalized_name = name.strip()

    if not normalized_name:
        raise ValueError(
            "Logger name must not be blank"
        )

    return logging.getLogger(
        normalized_name
    )


atexit.register(
    shutdown_logging
)


__all__ = [
    "ContextFilter",
    "NonBlockingQueueHandler",
    "StructuredFormatter",
    "get_logger",
    "sanitize_log_value",
    "setup_logging",
    "shutdown_logging",
]
