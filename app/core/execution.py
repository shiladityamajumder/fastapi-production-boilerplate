# File: app/core/execution.py
"""
===============================================================================
SERVICE-LAYER EXECUTION GUARD (ERROR NORMALIZATION LAYER)
===============================================================================

Provides a reusable execution wrapper for service-layer operations.

Purpose:

    - Normalize error handling across service methods
    - Avoid repetitive try/except blocks
    - Ensure consistent logging
    - Prevent leakage of internal exceptions

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

This module belongs to the application core layer.

It:

    - Is used exclusively inside service classes
    - Does NOT perform HTTP logic
    - Does NOT construct responses
    - Does NOT depend on FastAPI routing
    - Preserves clean architecture boundaries

-------------------------------------------------------------------------------
ERROR HANDLING POLICY
-------------------------------------------------------------------------------

1. APIException
    - Controlled domain failure
    - Re-raised unchanged

2. Unexpected Exception
    - Logged with operation context
    - Wrapped into APIException(500)
    - Original exception preserved via chaining

-------------------------------------------------------------------------------
WHY THIS EXISTS
-------------------------------------------------------------------------------

Without this utility:

    Service methods must repeat try/except blocks.

With this utility:

    - services remain clean
    - error handling is centralized
    - unexpected failures are normalized

-------------------------------------------------------------------------------
USAGE EXAMPLE
-------------------------------------------------------------------------------

    async def create_user(self, payload: CreateUserDTO):

        return await execute_service_operation(
            operation="user creation",
            func=lambda: self._create_user(payload),
            error_message="Unable to create user",
        )
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar
import inspect

from app.common.exceptions import APIException
from app.core.logging import get_logger


logger = get_logger(__name__)

T = TypeVar("T")

HTTP_INTERNAL_SERVER_ERROR = 500


# =============================================================================
# EXECUTION WRAPPER
# =============================================================================


async def execute_service_operation(
    *,
    operation: str,
    func: Callable[[], Awaitable[T]],
    error_message: str | None = None,
) -> T:
    """
    Execute service-layer logic with standardized error handling.

    Parameters
    ----------
    operation:
        Human-readable name of the operation being executed.

    func:
        Zero-argument async callable containing the service logic.

    error_message:
        Optional client-safe fallback message.

    Returns
    -------
    T
        Result returned by the callable.

    Raises
    ------
    APIException
        - Re-raised unchanged if thrown by func()
        - Raised with HTTP 500 if unexpected error occurs
    """

    if not operation or not operation.strip():
        raise ValueError("operation name must be provided")

    try:

        result = func()

        if not inspect.isawaitable(result):
            raise TypeError(
                "execute_service_operation requires an async callable"
            )

        return await result

    # -------------------------------------------------------------------------
    # Controlled domain failures
    # -------------------------------------------------------------------------

    except APIException:
        raise

    # -------------------------------------------------------------------------
    # Unexpected failures
    # -------------------------------------------------------------------------

    except Exception as exc:

        logger.exception(
            "Unexpected service failure",
            extra={
                "operation": operation,
                "exception_type": type(exc).__name__,
            },
        )

        raise APIException(
            message=error_message or "Internal service error",
            code=HTTP_INTERNAL_SERVER_ERROR,
        ) from exc
