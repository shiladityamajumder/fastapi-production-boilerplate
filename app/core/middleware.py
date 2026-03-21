# File: app/core/middleware.py
"""
===============================================================================
APPLICATION MIDDLEWARE STACK (PRODUCTION-HARDENED)
===============================================================================

Defines the complete HTTP middleware stack for the application.

Cross-cutting concerns implemented here:

    • Request ID generation
    • Request lifecycle logging
    • Redis-backed rate limiting
    • Response header enrichment

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

Middleware layer sits between:

    Client
        ↓
    Middleware
        ↓
    Routes / Services

Responsibilities:

    - cross-cutting concerns
    - observability
    - infrastructure enforcement

This layer MUST NOT:

    - contain business logic
    - mutate response bodies
    - own infrastructure resources

Infrastructure is accessed via:

    request.app.state

-------------------------------------------------------------------------------
EXECUTION ORDER (CRITICAL)
-------------------------------------------------------------------------------

Outer → Inner:

    1. RequestContextMiddleware
    2. RequestLoggingMiddleware
    3. RateLimitMiddleware
    4. Route Handler

-------------------------------------------------------------------------------
FAILURE POLICY
-------------------------------------------------------------------------------

Redis failures → Fail OPEN

Availability is prioritized over strict enforcement.
"""

from __future__ import annotations

import time
import uuid
from typing import Callable, Optional

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp, Receive, Scope, Send

from app.common.response import APIResponse
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.rate_limit import RateLimitConfig
from app.core.request_context import set_request_id, reset_request_id


logger = get_logger("middleware")


# =============================================================================
# REQUEST CONTEXT MIDDLEWARE
# =============================================================================


class RequestContextMiddleware:
    """
    ASGI-level middleware responsible for request context propagation.

    Responsibilities:

        - generate request_id
        - propagate request_id via contextvars
        - inject response headers safely

    Why ASGI-level?

        Header injection must happen during the ASGI
        "http.response.start" event.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()

        request = Request(scope)

        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

        token = set_request_id(request_id)

        async def send_wrapper(message):

            if message["type"] == "http.response.start":

                headers = list(message.get("headers", []))

                headers = [
                    (k, v)
                    for (k, v) in headers
                    if k.lower() not in (b"x-request-id", b"x-api-version")
                ]

                headers.append(
                    (b"x-request-id", request_id.encode("utf-8"))
                )

                headers.append(
                    (
                        b"x-api-version",
                        settings.API_V1_STR.encode("utf-8"),
                    )
                )

                message["headers"] = headers

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)

        finally:
            reset_request_id(token)


# =============================================================================
# REQUEST LOGGING MIDDLEWARE
# =============================================================================


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Structured request lifecycle logging.

    Logs:

        - request start
        - request completion
        - execution duration
        - unhandled exceptions
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:

        start = time.perf_counter()

        client_ip = request.client.host if request.client else None

        logger.info(
            "Incoming request",
            extra={
                "path": request.url.path,
                "method": request.method,
                "client_ip": client_ip,
            },
        )

        try:
            response = await call_next(request)

        except Exception:
            logger.exception("Unhandled exception during request")
            raise

        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "Request completed",
            extra={
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )

        return response


# =============================================================================
# RATE LIMITING MIDDLEWARE
# =============================================================================


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-backed distributed rate limiter.

    Features:

        - shared Redis coordination
        - per-endpoint configuration
        - explicit opt-out support
        - standards-compliant headers

    Failure strategy:

        Fail OPEN (allow request).
    """

    def _get_endpoint_config(
        self,
        request: Request,
    ) -> Optional[RateLimitConfig]:

        endpoint: Optional[Callable] = request.scope.get("endpoint")

        if endpoint is None:
            return None

        if getattr(endpoint, "__no_rate_limit__", False):
            return None

        return getattr(endpoint, "__rate_limit__", None)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:

        settings = get_settings()

        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        limiter = getattr(request.app.state, "rate_limiter", None)

        if limiter is None:
            return await call_next(request)

        cfg = self._get_endpoint_config(request)

        effective_cfg = cfg or limiter.default_config

        try:

            key = limiter.build_key(request)

            allowed, remaining, reset_at = await limiter.check(
                key=key,
                config=effective_cfg,
            )

        except Exception:
            logger.exception("Rate limiter internal error")
            return await call_next(request)

        if not allowed:

            logger.warning(
                "Rate limit exceeded",
                extra={"rate_limit_key": key},
            )

            response = APIResponse.error(
                message="Rate limit exceeded",
                code=429,
                errors=[
                    {
                        "field": None,
                        "message": f"Retry after {reset_at}",
                    }
                ],
            )

            response.headers["X-RateLimit-Limit"] = str(
                effective_cfg.limit
            )

            response.headers["X-RateLimit-Remaining"] = "0"

            response.headers["X-RateLimit-Reset"] = str(reset_at)

            response.headers["Retry-After"] = str(reset_at)

            return response

        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(
            effective_cfg.limit
        )

        response.headers["X-RateLimit-Remaining"] = str(remaining)

        response.headers["X-RateLimit-Reset"] = str(reset_at)

        return response


# =============================================================================
# REGISTRATION
# =============================================================================


def register_middleware(app: FastAPI) -> None:
    """
    Register middleware in deterministic order.

    Order MUST NOT be changed.
    """

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
