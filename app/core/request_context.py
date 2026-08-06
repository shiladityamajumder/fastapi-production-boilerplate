"""File: app/core/request_context.py.

Request- and task-scoped observability context based on ``contextvars``.

The same context implementation can be used by:

- FastAPI request middleware,
- Celery task lifecycle hooks,
- internal asynchronous jobs,
- integration clients,
- repositories and services.

Context values are isolated across asynchronous execution flows and must always
be reset using the tokens returned by the corresponding setter.
"""

from __future__ import annotations

from contextvars import (
    ContextVar,
    Token,
)
from dataclasses import dataclass

_request_id: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)

_correlation_id: ContextVar[str | None] = ContextVar(
    "correlation_id",
    default=None,
)

_trace_id: ContextVar[str | None] = ContextVar(
    "trace_id",
    default=None,
)

_task_id: ContextVar[str | None] = ContextVar(
    "task_id",
    default=None,
)

_api_version: ContextVar[str] = ContextVar(
    "api_version",
    default="v1",
)


@dataclass(
    frozen=True,
    slots=True,
)
class RequestContextTokens:
    """Tokens required to restore the previous execution context.

    Context variables must be reset in reverse assignment order to safely
    restore any parent request or task context.
    """

    request_id: Token[str | None]
    correlation_id: Token[str | None]
    trace_id: Token[str | None]
    task_id: Token[str | None]
    api_version: Token[str]


def _normalize_required_identifier(
    value: str,
    name: str,
) -> str:
    """Normalize and validate a required context identifier.

    Args:
        value: Raw identifier value.
        name: Setting name used in validation errors.

    Returns:
        Normalized identifier.

    Raises:
        ValueError: If the identifier is blank.
    """
    normalized = value.strip()

    if not normalized:
        raise ValueError(f"{name} must be non-empty")

    return normalized


def _normalize_optional_identifier(
    value: str | None,
) -> str | None:
    """Normalize an optional context identifier."""
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def set_request_context(
    *,
    request_id: str,
    correlation_id: str,
    trace_id: str | None,
    api_version: str,
    task_id: str | None = None,
) -> RequestContextTokens:
    """Bind request or task metadata to the current asynchronous context.

    Args:
        request_id: Identifier for the current HTTP request or task execution.
        correlation_id: Identifier propagated across service boundaries.
        trace_id: Optional distributed-tracing identifier.
        api_version: API version associated with the execution.
        task_id: Optional Celery task identifier.

    Returns:
        Tokens required to restore the previous context.
    """
    normalized_request_id = _normalize_required_identifier(
        request_id,
        "request_id",
    )

    normalized_correlation_id = _normalize_required_identifier(
        correlation_id,
        "correlation_id",
    )

    normalized_api_version = api_version.strip().strip("/") or "v1"

    return RequestContextTokens(
        request_id=_request_id.set(
            normalized_request_id,
        ),
        correlation_id=_correlation_id.set(
            normalized_correlation_id,
        ),
        trace_id=_trace_id.set(
            _normalize_optional_identifier(trace_id),
        ),
        task_id=_task_id.set(
            _normalize_optional_identifier(task_id),
        ),
        api_version=_api_version.set(
            normalized_api_version,
        ),
    )


def reset_request_context(
    tokens: RequestContextTokens,
) -> None:
    """Restore every context variable to its previous value.

    Args:
        tokens: Tokens returned by ``set_request_context``.
    """
    _api_version.reset(tokens.api_version)
    _task_id.reset(tokens.task_id)
    _trace_id.reset(tokens.trace_id)
    _correlation_id.reset(tokens.correlation_id)
    _request_id.reset(tokens.request_id)


def set_request_id(
    request_id: str,
) -> Token[str | None]:
    """Set only the request identifier.

    This helper is retained for narrow compatibility cases. New request or
    Celery lifecycle code should normally use ``set_request_context``.
    """
    normalized = _normalize_required_identifier(
        request_id,
        "request_id",
    )

    return _request_id.set(normalized)


def reset_request_id(
    token: Token[str | None],
) -> None:
    """Reset a token returned by ``set_request_id``."""
    _request_id.reset(token)


def set_correlation_id(
    correlation_id: str,
) -> Token[str | None]:
    """Set only the cross-service correlation identifier."""
    normalized = _normalize_required_identifier(
        correlation_id,
        "correlation_id",
    )

    return _correlation_id.set(normalized)


def reset_correlation_id(
    token: Token[str | None],
) -> None:
    """Reset a token returned by ``set_correlation_id``."""
    _correlation_id.reset(token)


def set_task_id(
    task_id: str,
) -> Token[str | None]:
    """Set the current Celery or background-task identifier."""
    normalized = _normalize_required_identifier(
        task_id,
        "task_id",
    )

    return _task_id.set(normalized)


def reset_task_id(
    token: Token[str | None],
) -> None:
    """Reset a token returned by ``set_task_id``."""
    _task_id.reset(token)


def get_request_id(
    default: str | None = None,
) -> str | None:
    """Return the current request identifier."""
    return _request_id.get() or default


def get_correlation_id(
    default: str | None = None,
) -> str | None:
    """Return the current cross-service correlation identifier."""
    return _correlation_id.get() or default


def get_trace_id(
    default: str | None = None,
) -> str | None:
    """Return the current distributed-tracing identifier."""
    return _trace_id.get() or default


def get_task_id(
    default: str | None = None,
) -> str | None:
    """Return the current Celery or background-task identifier."""
    return _task_id.get() or default


def get_api_version() -> str:
    """Return the API version associated with the current execution."""
    return _api_version.get()


__all__ = [
    "RequestContextTokens",
    "get_api_version",
    "get_correlation_id",
    "get_request_id",
    "get_task_id",
    "get_trace_id",
    "reset_correlation_id",
    "reset_request_context",
    "reset_request_id",
    "reset_task_id",
    "set_correlation_id",
    "set_request_context",
    "set_request_id",
    "set_task_id",
]
