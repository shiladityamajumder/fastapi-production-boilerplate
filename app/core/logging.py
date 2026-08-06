"""File: app/core/logging.py.

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
from collections.abc import (
    Callable,
    Mapping,
    Sequence,
)
from contextlib import suppress
from dataclasses import (
    dataclass,
    field,
)
from datetime import datetime
from queue import (
    Full,
    Queue,
)
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

# Internal sentinel returned when a value is not a supported primitive.
_UNHANDLED = object()

# =============================================================================
# TEXT REDACTION PATTERNS
# =============================================================================

# Redact authorization values embedded in plain text.
_AUTH_PATTERN = re.compile(
    r"(?i)\b(?:authorization|proxy-authorization|bearer)"
    r"\b\s*[:=]?\s*[^\s,;]+"
)

# Redact credentials embedded in URLs, for example:
#
#     protocol://username:password@hostname
_URI_PASSWORD_PATTERN = re.compile(
    r"(://[^:/\s]+:)([^@/\s]+)(@)"
)

# Redact common key-value assignments, for example:
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


@dataclass(slots=True)
class _LoggingState:
    """Hold mutable logging resources owned by the current process."""

    log_queue: Queue[logging.LogRecord] | None = None
    queue_handler: NonBlockingQueueHandler | None = None
    listener: logging.handlers.QueueListener | None = None
    sink_handlers: tuple[logging.Handler, ...] = ()

    setup_lock: Lock = field(
        default_factory=Lock,
    )

    configured_pid: int | None = None
    dropped_records: int = 0
    redaction_enabled: bool = True

    def clear_resources(self) -> None:
        """Clear process-owned queue and handler references."""
        self.log_queue = None
        self.queue_handler = None
        self.listener = None
        self.sink_handlers = ()
        self.configured_pid = None


_STATE = _LoggingState()

# =============================================================================
# REDACTION HELPERS
# =============================================================================


def _normalize_sensitive_key(
    value: str,
) -> str:
    """Normalize a metadata key for sensitivity comparison.

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
    """Return whether a metadata key represents sensitive information.

    Args:
        key: Optional metadata key.

    Returns:
        ``True`` when the key should be redacted.
    """
    return bool(
        key
        and _normalize_sensitive_key(key) in _SENSITIVE_KEYS
    )


def _redact_text(
    value: str,
) -> str:
    """Redact common credential patterns embedded in text.

    Args:
        value: Plain text value.

    Returns:
        Redacted text.
    """
    if not _STATE.redaction_enabled:
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
        lambda match: f"{match.group(1)}=[REDACTED]",
        redacted,
    )


def sanitize_log_value(
    value: Any,
    *,
    key: str | None = None,
) -> Any:
    """Recursively sanitize a structured logging value.

    This function is a defense-in-depth safeguard. Callers should still avoid
    logging request bodies, complete external responses, ORM objects, files,
    credentials, or other confidential information.

    Args:
        value: Structured metadata value.
        key: Optional field name associated with the value.

    Returns:
        Redacted JSON-compatible representation.
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
    """Return a sanitized representation of one structured value.

    Args:
        value: Value being sanitized.
        key: Associated metadata key.
        depth: Current recursive depth.
        seen: Object identifiers currently being traversed.

    Returns:
        Sanitized representation.
    """
    if _STATE.redaction_enabled and _is_sensitive_key(key):
        return "[REDACTED]"

    primitive = _sanitize_primitive(value)

    if primitive is not _UNHANDLED:
        return primitive

    if depth >= _MAX_SANITIZE_DEPTH:
        return "<maximum-depth-reached>"

    if isinstance(value, Mapping):
        return _sanitize_mapping(
            value=value,
            depth=depth,
            seen=seen,
        )

    if _is_collection_value(value):
        return _sanitize_collection(
            value=value,
            depth=depth,
            seen=seen,
        )

    return _redact_text(
        repr(value),
    )


def _sanitize_primitive(
    value: Any,
) -> Any:
    """Return a sanitized primitive or an unhandled marker.

    Args:
        value: Value being inspected.

    Returns:
        Sanitized primitive or the internal ``_UNHANDLED`` marker.
    """
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

    return _UNHANDLED


def _is_collection_value(
    value: Any,
) -> bool:
    """Return whether a value is a supported non-text collection.

    Args:
        value: Value being inspected.

    Returns:
        ``True`` for sequences, sets, and frozen sets.
    """
    if isinstance(
        value,
        (
            str,
            bytes,
            bytearray,
        ),
    ):
        return False

    return isinstance(
        value,
        (
            Sequence,
            set,
            frozenset,
        ),
    )


def _sanitize_mapping(
    *,
    value: Mapping[Any, Any],
    depth: int,
    seen: set[int],
) -> Any:
    """Sanitize a mapping while detecting circular references.

    Args:
        value: Mapping being sanitized.
        depth: Current recursive depth.
        seen: Object identifiers currently being traversed.

    Returns:
        Sanitized dictionary or a circular-reference marker.
    """
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
            for item_key, item_value in value.items()
        }
    finally:
        seen.remove(object_id)


def _sanitize_collection(
    *,
    value: Sequence[Any] | set[Any] | frozenset[Any],
    depth: int,
    seen: set[int],
) -> Any:
    """Sanitize a collection while detecting circular references.

    Args:
        value: Sequence, set, or frozen set being sanitized.
        depth: Current recursive depth.
        seen: Object identifiers currently being traversed.

    Returns:
        Sanitized list or a circular-reference marker.
    """
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


# =============================================================================
# LOGGING FILTER
# =============================================================================


class ContextFilter(logging.Filter):
    """Attach execution context to every log record.

    The filter runs before the record is placed into the queue. Context-variable
    values are therefore captured on the request or task execution thread rather
    than the queue-listener thread.
    """

    def filter(
        self,
        record: logging.LogRecord,
    ) -> bool:
        """Add request, correlation, trace, and task identifiers.

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
    """Place records into a bounded queue without blocking application work.

    When the queue is full, records are dropped rather than blocking request,
    task, or event-loop execution. Controlled warnings are written directly to
    stderr so queue saturation remains visible.
    """

    def prepare(
        self,
        record: logging.LogRecord,
    ) -> logging.LogRecord:
        """Copy a log record while preserving exception information.

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
        """Add a record without waiting for queue capacity.

        Args:
            record: Prepared log record.
        """
        try:
            self.queue.put_nowait(record)
        except Full:
            _STATE.dropped_records += 1
            _write_queue_saturation_warning()


def _write_queue_saturation_warning() -> None:
    """Write bounded warnings when logging records are dropped."""
    dropped = _STATE.dropped_records

    should_report = (
        dropped in {
            1,
            10,
            100,
        }
        or dropped % 1_000 == 0
    )

    if not should_report:
        return

    sys.stderr.write(
        "Logging queue is full; records are being dropped. "
        f"dropped={dropped}\n"
    )
    sys.stderr.flush()


# =============================================================================
# LOG FORMATTER
# =============================================================================


class StructuredFormatter(logging.Formatter):
    """Format records as JSON or readable console log lines."""

    def __init__(
        self,
        *,
        json_mode: bool,
        timezone_name: str,
    ) -> None:
        """Initialize the formatter.

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
        """Render one structured log record.

        Args:
            record: Log record to serialize.

        Returns:
            Formatted log line.
        """
        payload = self._build_payload(record)

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

    def _build_payload(
        self,
        record: logging.LogRecord,
    ) -> dict[str, Any]:
        """Build one sanitized structured logging payload.

        Args:
            record: Log record being formatted.

        Returns:
            Sanitized structured payload.
        """
        timestamp = datetime.fromtimestamp(
            record.created,
            tz=self._timezone,
        ).isoformat()

        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_text(record.getMessage()),
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

        self._add_custom_context(
            payload=payload,
            record=record,
        )

        if record.exc_info:
            payload["exception"] = _redact_text(
                self.formatException(
                    record.exc_info,
                )
            )

        if record.stack_info:
            payload["stack"] = _redact_text(
                self.formatStack(
                    record.stack_info,
                )
            )

        return payload

    @staticmethod
    def _add_custom_context(
        *,
        payload: dict[str, Any],
        record: logging.LogRecord,
    ) -> None:
        """Add sanitized custom ``extra`` values to a payload.

        Args:
            payload: Structured payload being assembled.
            record: Original log record.
        """
        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_BUILTINS or key in payload:
                continue

            payload[key] = sanitize_log_value(
                value,
                key=key,
            )

    @staticmethod
    def _format_readable(
        *,
        payload: dict[str, Any],
    ) -> str:
        """Format a structured payload for local console output.

        Args:
            payload: Sanitized structured log payload.

        Returns:
            Readable log line.
        """
        identity_context = _identity_context(payload)
        custom_context = _custom_context(payload)

        identity_suffix = _json_suffix(
            label="execution",
            value=identity_context,
        )

        context_suffix = _json_suffix(
            label="context",
            value=custom_context,
        )

        source_suffix = (
            f" | source={payload['module']}."
            f"{payload['function']}:{payload['line']}"
        )

        process_suffix = (
            f" | process={payload['process_id']}:"
            f"{payload['thread_name']}"
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


def _identity_context(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Return non-empty request and task identity metadata.

    Args:
        payload: Structured logging payload.

    Returns:
        Non-empty execution identity fields.
    """
    values = {
        "request_id": payload.get("request_id"),
        "correlation_id": payload.get("correlation_id"),
        "trace_id": payload.get("trace_id"),
        "task_id": payload.get("task_id"),
    }

    return {
        key: value
        for key, value in values.items()
        if value is not None
    }


def _custom_context(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Return non-reserved custom structured metadata.

    Args:
        payload: Structured logging payload.

    Returns:
        Non-empty custom metadata.
    """
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

    return {
        key: value
        for key, value in payload.items()
        if key not in reserved_keys and value is not None
    }


def _json_suffix(
    *,
    label: str,
    value: Mapping[str, Any],
) -> str:
    """Return a readable JSON suffix when a mapping is non-empty.

    Args:
        label: Context label.
        value: Structured context values.

    Returns:
        Serialized suffix or an empty string.
    """
    if not value:
        return ""

    return f" | {label}=" + json.dumps(
        value,
        ensure_ascii=False,
        default=str,
        sort_keys=True,
    )


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass(frozen=True, slots=True)
class _LoggingResources:
    """Contain successfully initialized queue logging resources."""

    log_queue: Queue[logging.LogRecord]
    queue_handler: NonBlockingQueueHandler
    listener: logging.handlers.QueueListener
    sinks: tuple[logging.Handler, ...]


def setup_logging(
    settings: AppSettings | None = None,
    *,
    force: bool = False,
) -> None:
    """Configure process-local application logging.

    Configuration is performed once per operating-system process. If a worker
    process is forked, the child process creates a fresh queue, listener thread,
    and output handlers instead of reusing inherited logging resources.

    Args:
        settings: Optional validated settings override.
        force: Reconfigure logging in the current process.

    Raises:
        Exception: Propagates logging initialization failures.
    """
    current_pid = os.getpid()

    with _STATE.setup_lock:
        if _already_configured(
            current_pid=current_pid,
            force=force,
        ):
            return

        _prepare_existing_state(
            current_pid=current_pid,
        )

        resolved = settings or get_settings()

        _configure_process_options(resolved)

        formatter = _build_formatter(resolved)

        sinks = _build_sink_handlers(
            settings=resolved,
            formatter=formatter,
        )

        try:
            resources = _start_queue_pipeline(
                settings=resolved,
                sinks=sinks,
            )
        except Exception:
            _close_handlers(sinks)
            raise

        _install_logging_resources(
            current_pid=current_pid,
            resources=resources,
        )

        logging.captureWarnings(True)


def _already_configured(
    *,
    current_pid: int,
    force: bool,
) -> bool:
    """Return whether logging setup can be skipped.

    Args:
        current_pid: Current operating-system process identifier.
        force: Whether forced reconfiguration was requested.

    Returns:
        ``True`` when logging is already configured.
    """
    return (
        _STATE.configured_pid == current_pid
        and not force
    )


def _prepare_existing_state(
    *,
    current_pid: int,
) -> None:
    """Dispose or clear logging state from an earlier setup.

    Args:
        current_pid: Current operating-system process identifier.
    """
    if _STATE.configured_pid == current_pid:
        _shutdown_logging_unlocked()
        return

    if _STATE.configured_pid is not None:
        _clear_logging_state_unlocked()


def _configure_process_options(
    settings: AppSettings,
) -> None:
    """Configure process-level options and the root logger.

    Args:
        settings: Validated application settings.
    """
    _STATE.dropped_records = 0
    _STATE.redaction_enabled = (
        settings.SENSITIVE_DATA_REDACTION_ENABLED
    )

    logging.raiseExceptions = (
        settings.ENVIRONMENT != Environment.PRODUCTION
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        _close_handler(handler)


def _build_formatter(
    settings: AppSettings,
) -> StructuredFormatter:
    """Build the configured structured formatter.

    Args:
        settings: Validated application settings.

    Returns:
        Configured formatter.
    """
    json_mode = (
        settings.LOG_JSON
        or settings.ENVIRONMENT == Environment.PRODUCTION
    )

    return StructuredFormatter(
        json_mode=json_mode,
        timezone_name=settings.TIMEZONE,
    )


def _build_sink_handlers(
    *,
    settings: AppSettings,
    formatter: logging.Formatter,
) -> list[logging.Handler]:
    """Build console and optional file handlers.

    Args:
        settings: Validated application settings.
        formatter: Configured log formatter.

    Returns:
        Output handlers.
    """
    sinks: list[logging.Handler] = []

    console_handler = logging.StreamHandler(
        sys.stdout,
    )

    console_handler.setLevel(
        settings.LOG_LEVEL,
    )

    console_handler.setFormatter(
        formatter,
    )

    sinks.append(
        console_handler,
    )

    if settings.LOG_TO_FILE:
        sinks.append(
            _build_file_handler(
                settings=settings,
                formatter=formatter,
            )
        )

    return sinks


def _build_file_handler(
    *,
    settings: AppSettings,
    formatter: logging.Formatter,
) -> logging.Handler:
    """Build the configured rotating file handler.

    Args:
        settings: Validated application settings.
        formatter: Configured log formatter.

    Returns:
        Rotating file handler.
    """
    settings.log_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    handler = logging.handlers.RotatingFileHandler(
        filename=(
            settings.log_directory
            / settings.LOG_FILE
        ),
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )

    handler.setLevel(
        settings.LOG_LEVEL,
    )

    handler.setFormatter(
        formatter,
    )

    return handler


def _start_queue_pipeline(
    *,
    settings: AppSettings,
    sinks: list[logging.Handler],
) -> _LoggingResources:
    """Create and start the bounded queue logging pipeline.

    Args:
        settings: Validated application settings.
        sinks: Output handlers receiving queued records.

    Returns:
        Initialized logging resources.

    Raises:
        Exception: If listener startup or root-handler registration fails.
    """
    log_queue: Queue[logging.LogRecord] = Queue(
        maxsize=settings.LOG_QUEUE_SIZE,
    )

    queue_handler = NonBlockingQueueHandler(
        log_queue,
    )

    queue_handler.setLevel(
        settings.LOG_LEVEL,
    )

    queue_handler.addFilter(
        ContextFilter(),
    )

    listener = logging.handlers.QueueListener(
        log_queue,
        *sinks,
        respect_handler_level=True,
    )

    try:
        listener.start()

        logging.getLogger().addHandler(
            queue_handler,
        )
    except Exception:
        with suppress(Exception):
            listener.stop()

        _close_handler(
            queue_handler,
        )

        raise

    return _LoggingResources(
        log_queue=log_queue,
        queue_handler=queue_handler,
        listener=listener,
        sinks=tuple(sinks),
    )


def _install_logging_resources(
    *,
    current_pid: int,
    resources: _LoggingResources,
) -> None:
    """Store initialized resources in process-local state.

    Args:
        current_pid: Current operating-system process identifier.
        resources: Initialized queue logging resources.
    """
    _STATE.log_queue = resources.log_queue
    _STATE.queue_handler = resources.queue_handler
    _STATE.listener = resources.listener
    _STATE.sink_handlers = resources.sinks
    _STATE.configured_pid = current_pid


def shutdown_logging() -> None:
    """Drain queued records and close process-local logging resources.

    The operation is idempotent and safe to call from application shutdown,
    tests, background-worker shutdown, and interpreter exit.
    """
    with _STATE.setup_lock:
        _shutdown_logging_unlocked()


def _shutdown_logging_unlocked() -> None:
    """Stop and clear logging resources while holding the setup lock."""
    current_pid = os.getpid()
    root_logger = logging.getLogger()

    queue_handler = _STATE.queue_handler
    listener = _STATE.listener
    sinks = _STATE.sink_handlers

    if queue_handler is not None:
        root_logger.removeHandler(
            queue_handler,
        )

    # Only stop resources created by the current process. Inherited parent
    # resources must never be closed by a forked child process.
    if _STATE.configured_pid == current_pid:
        _stop_listener(
            listener,
        )

        if queue_handler is not None:
            _close_handler(
                queue_handler,
            )

        _close_handlers(
            sinks,
        )

    _STATE.clear_resources()


def _stop_listener(
    listener: logging.handlers.QueueListener | None,
) -> None:
    """Stop a queue listener without allowing shutdown to fail.

    Args:
        listener: Optional active queue listener.
    """
    if listener is None:
        return

    try:
        listener.stop()
    except Exception:
        sys.stderr.write(
            "Failed to stop logging queue listener cleanly.\n"
        )
        sys.stderr.flush()


def _close_handlers(
    handlers: Sequence[logging.Handler],
) -> None:
    """Close multiple logging handlers without raising.

    Args:
        handlers: Logging handlers to close.
    """
    for handler in handlers:
        _close_handler(
            handler,
        )


def _close_handler(
    handler: logging.Handler,
) -> None:
    """Flush and close one logging handler without raising.

    Args:
        handler: Logging handler to close.
    """
    with suppress(Exception):
        handler.flush()

    with suppress(Exception):
        handler.close()


def _clear_logging_state_unlocked() -> None:
    """Clear inherited state without closing parent-owned resources."""
    _STATE.clear_resources()


def _reset_logging_after_fork() -> None:
    """Reset inherited logging state inside a forked child process.

    Listener threads do not survive process forking. The child must therefore
    create a new lock, queue, listener, and handlers when ``setup_logging`` is
    called.
    """
    _STATE.clear_resources()
    _STATE.dropped_records = 0

    # A lock inherited while held by another thread can remain permanently
    # locked inside a child process.
    _STATE.setup_lock = Lock()


def _register_fork_handler() -> None:
    """Register child-process logging reset where supported."""
    register_at_fork: Callable[..., None] | None = getattr(
        os,
        "register_at_fork",
        None,
    )

    if register_at_fork is not None:
        register_at_fork(
            after_in_child=_reset_logging_after_fork,
        )


_register_fork_handler()

# =============================================================================
# LOGGER FACTORY
# =============================================================================


def get_logger(
    name: str,
) -> logging.Logger:
    """Return a standard-library logger.

    Args:
        name: Logger name, normally ``__name__``.

    Returns:
        Logger instance.

    Raises:
        ValueError: If the logger name is blank.
    """
    normalized_name = name.strip()

    if not normalized_name:
        raise ValueError(
            "Logger name must not be blank"
        )

    return logging.getLogger(
        normalized_name,
    )


atexit.register(
    shutdown_logging,
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
