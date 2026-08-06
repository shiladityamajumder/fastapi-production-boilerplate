"""File: app/common/execution.py.

Reusable execution helpers for observable and optionally bounded asynchronous
operations.

This module provides consistent timing, structured logging, and timeout
translation for services, repositories, integration clients, and background
tasks.

Request, correlation, trace, and Celery task identifiers are attached
automatically by the logging context filter.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import (  # noqa: TC003
    Awaitable,
    Callable,
    Mapping,
)
from typing import Any

from app.common.exceptions import (
    AppError,
    OperationTimeoutError,
)
from app.core.logging import (
    get_logger,
    sanitize_log_value,
)

logger = get_logger(__name__)


async def execute_operation[T](
    *,
    operation: str,
    func: Callable[[], Awaitable[T]],
    layer: str = "application",
    timeout_seconds: float | None = None,
    context: Mapping[str, Any] | None = None,
) -> T:
    """Execute an asynchronous operation with timing and structured logging.

    Logging behavior:

    - DEBUG when the operation starts,
    - DEBUG when the operation completes,
    - DEBUG when an expected application error escapes,
    - WARNING when the configured timeout is exceeded,
    - ERROR with a stack trace for unexpected failures.

    Args:
        operation: Stable operation name such as ``product.create``.
        func: Zero-argument asynchronous callable to execute.
        layer: Logical layer such as ``service``, ``repository``, or
            ``integration``.
        timeout_seconds: Optional maximum execution duration.
        context: Optional non-sensitive structured metadata.

    Returns:
        Value returned by ``func``.

    Raises:
        ValueError: If operation, layer, or timeout configuration is invalid.
        OperationTimeoutError: If the operation exceeds its deadline.
        AppError: Any expected application error raised by ``func``.
        Exception: Any unexpected error raised by ``func``.
    """
    normalized_operation = operation.strip()
    normalized_layer = layer.strip()

    if not normalized_operation:
        raise ValueError("operation must not be blank")

    if not normalized_layer:
        raise ValueError("layer must not be blank")

    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError(
            "timeout_seconds must be greater than zero"
        )

    sanitized_context = sanitize_log_value(
        dict(context or {})
    )

    started_at = time.perf_counter()

    logger.debug(
        "Operation started",
        extra={
            "operation": normalized_operation,
            "layer": normalized_layer,
            "operation_context": sanitized_context,
            "timeout_seconds": timeout_seconds,
        },
    )

    try:
        if timeout_seconds is None:
            result = await func()
        else:
            async with asyncio.timeout(
                timeout_seconds
            ):
                result = await func()

    except TimeoutError as exc:
        duration_ms = _elapsed_milliseconds(
            started_at
        )

        logger.warning(
            "Operation timed out",
            extra={
                "operation": normalized_operation,
                "layer": normalized_layer,
                "operation_context": sanitized_context,
                "duration_ms": duration_ms,
                "timeout_seconds": timeout_seconds,
            },
        )

        raise OperationTimeoutError(
            message=(
                f"{normalized_operation} exceeded its "
                "allowed execution time."
            ),
            details={
                "operation": normalized_operation,
            },
        ) from exc

    except AppError as exc:
        # Expected application errors are translated and logged by the API
        # exception layer. Logging them here at DEBUG preserves operation
        # visibility without producing duplicate warning or error records.
        logger.debug(
            "Operation rejected",
            extra={
                "operation": normalized_operation,
                "layer": normalized_layer,
                "operation_context": sanitized_context,
                "duration_ms": _elapsed_milliseconds(
                    started_at
                ),
                "error_code": exc.code,
                "exception_type": type(exc).__name__,
            },
        )

        raise

    except Exception as exc:
        logger.exception(
            "Operation failed",
            extra={
                "operation": normalized_operation,
                "layer": normalized_layer,
                "operation_context": sanitized_context,
                "duration_ms": _elapsed_milliseconds(
                    started_at
                ),
                "exception_type": type(exc).__name__,
            },
        )

        raise

    logger.debug(
        "Operation completed",
        extra={
            "operation": normalized_operation,
            "layer": normalized_layer,
            "operation_context": sanitized_context,
            "duration_ms": _elapsed_milliseconds(
                started_at
            ),
        },
    )

    return result


async def execute_with_timeout[T](
    *,
    operation: str,
    timeout_seconds: float,
    func: Callable[[], Awaitable[T]],
    layer: str = "application",
    context: Mapping[str, Any] | None = None,
) -> T:
    """Execute an asynchronous operation within an explicit deadline.

    This compatibility helper delegates to ``execute_operation``.

    Args:
        operation: Stable operation name.
        timeout_seconds: Maximum execution duration.
        func: Zero-argument asynchronous callable.
        layer: Logical application layer.
        context: Optional non-sensitive structured metadata.

    Returns:
        Value returned by ``func``.
    """
    return await execute_operation(
        operation=operation,
        func=func,
        layer=layer,
        timeout_seconds=timeout_seconds,
        context=context,
    )


def _elapsed_milliseconds(
    started_at: float,
) -> float:
    """Return elapsed monotonic time in milliseconds.

    Args:
        started_at: Value returned by ``time.perf_counter``.

    Returns:
        Elapsed duration rounded to two decimal places.
    """
    return round(
        (time.perf_counter() - started_at) * 1_000,
        2,
    )


# Compatibility aliases preserve existing imports while allowing callers to
# communicate the logical use of the helper.
execute_service_operation = execute_operation
execute_repository_operation = execute_operation


__all__ = [
    "execute_operation",
    "execute_repository_operation",
    "execute_service_operation",
    "execute_with_timeout",
]
