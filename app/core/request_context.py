# File: app/core/request_context.py
"""
===============================================================================
REQUEST CONTEXT MANAGEMENT (ASYNC + THREAD SAFE)
===============================================================================

Provides request-scoped execution context using Python `contextvars`.

Primary responsibility:

    - Store and retrieve request_id safely across async boundaries
    - Guarantee isolation across concurrent requests
    - Prevent cross-request contamination

-------------------------------------------------------------------------------
ARCHITECTURAL BOUNDARY
-------------------------------------------------------------------------------

This module:

    - Has NO FastAPI dependency
    - Has NO middleware dependency
    - Owns NO infrastructure resources
    - Contains NO business logic
    - Is framework-agnostic

It provides pure execution-context state management.

-------------------------------------------------------------------------------
WHY CONTEXTVARS
-------------------------------------------------------------------------------

`contextvars` provides:

    - Async safety (coroutine isolation)
    - Thread safety
    - Per-task logical context separation
    - Compatibility with async/await execution model

Unlike global variables:

    - Values do NOT leak across coroutines
    - Each request runs in its own logical execution context

-------------------------------------------------------------------------------
IMPORTANT EXECUTION RULE
-------------------------------------------------------------------------------

Middleware MUST:

    1. Capture the token from set_request_id()
    2. Reset it in a finally block

Example:

    token = set_request_id("req_123")
    try:
        await next_layer()
    finally:
        reset_request_id(token)

This guarantees:

    - No cross-request leakage
    - No context bleed in background tasks
    - Deterministic lifecycle

-------------------------------------------------------------------------------
FAILURE SEMANTICS
-------------------------------------------------------------------------------

- get_request_id() always returns a string
- If not set → returns provided default
- set_request_id() rejects empty values
- reset_request_id() must be passed valid Token
"""

from __future__ import annotations

import contextvars
from contextvars import Token
from typing import Optional


# =============================================================================
# CONTEXT VARIABLE
# =============================================================================

_request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id",
    default=None,
)


# =============================================================================
# PUBLIC API
# =============================================================================


def set_request_id(request_id: str) -> Token:
    """
    Set request ID in current execution context.

    Args:
        request_id:
            Non-empty correlation identifier.

    Returns:
        Token required for safe reset.

    Raises:
        ValueError if request_id is empty.

    Production invariant:
        Always reset using the returned token.
    """

    if not request_id:
        raise ValueError("request_id must be non-empty")

    return _request_id_ctx.set(request_id)


def get_request_id(default: str = "N/A") -> str:
    """
    Retrieve request ID from current execution context.

    Args:
        default:
            Value returned if no request_id has been set.

    Returns:
        Current request_id or default.

    Guarantees:
        - Never raises
        - Always returns string
    """

    value = _request_id_ctx.get()
    return value if value is not None else default


def reset_request_id(token: Token) -> None:
    """
    Reset request ID to previous state using token.

    Required for:

        - Middleware cleanup
        - Manual context overrides
        - Background task simulations
        - Unit tests

    Raises:
        RuntimeError if invalid token is provided
        (standard contextvars behavior).
    """

    _request_id_ctx.reset(token)
