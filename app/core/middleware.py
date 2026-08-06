"""File: app/core/middleware.py.

Pure-ASGI middleware for request context, security, request limits, CORS, and
HTTP observability.

The service runs inside a controlled VPC, so this module intentionally contains:

- no application-level Host allow-list validation,
- no rate-limiting middleware,
- no rate-limit response headers.

Middleware is implemented directly against ASGI to avoid request-body buffering
and the execution behavior associated with ``BaseHTTPMiddleware``.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid

from fastapi import FastAPI  # noqa: TC002
from starlette.datastructures import (
    Headers,
    MutableHeaders,
)
from starlette.middleware.cors import CORSMiddleware
from starlette.types import (
    ASGIApp,  # noqa: TC002
    Message,  # noqa: TC002
    Receive,  # noqa: TC002
    Scope,  # noqa: TC002
    Send,  # noqa: TC002
)

from app.common.response import APIResponse
from app.core.config import AppSettings  # noqa: TC001
from app.core.logging import get_logger
from app.core.request_context import (
    reset_request_context,
    set_request_context,
)

logger = get_logger(__name__)


_IDENTIFIER_PATTERN = re.compile(
    r"^[A-Za-z0-9._:/-]{1,128}$",
)

_TRACEPARENT_PATTERN = re.compile(
    r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$",
)

_HTTP_SERVER_ERROR_STATUS_MIN = 500


def _accepted_identifier(
    value: str | None,
) -> str | None:
    """Normalize and validate an incoming request identifier.

    Args:
        value: Raw header value.

    Returns:
        Validated identifier or ``None`` when the value is missing or invalid.
    """
    if value is None:
        return None

    normalized = value.strip()

    if _IDENTIFIER_PATTERN.fullmatch(normalized):
        return normalized

    return None


def _extract_trace_id(
    traceparent: str | None,
) -> str | None:
    """Extract a valid trace identifier from a W3C traceparent header.

    Args:
        traceparent: Raw ``traceparent`` header.

    Returns:
        A 32-character lowercase trace identifier or ``None``.
    """
    if not traceparent:
        return None

    match = _TRACEPARENT_PATTERN.fullmatch(
        traceparent.strip().lower(),
    )

    if not match:
        return None

    trace_id = match.group(1)
    parent_id = match.group(2)

    if trace_id == "0" * 32 or parent_id == "0" * 16:
        return None

    return trace_id


def _hash_client_ip(
    scope: Scope,
) -> str | None:
    """Return a privacy-reduced hash of the direct ASGI client address.

    The raw address is never logged. Forwarded client headers are intentionally
    ignored here because they must only be trusted through explicit gateway or
    server configuration.

    Args:
        scope: Current ASGI request scope.

    Returns:
        Short hexadecimal hash or ``None``.
    """
    client = scope.get("client")

    if not client:
        return None

    return hashlib.blake2b(
        str(client[0]).encode("utf-8"),
        digest_size=12,
    ).hexdigest()


def _resolved_route_template(
    scope: Scope,
) -> str:
    """Return the matched route template without raw URL parameters.

    Route templates produce bounded-cardinality metrics such as
    ``/products/{product_id}`` instead of recording every product identifier.

    Args:
        scope: Current ASGI request scope.

    Returns:
        Matched route template or ``unmatched``.
    """
    route = scope.get("route")
    route_path = getattr(
        route,
        "path",
        None,
    )

    if isinstance(route_path, str) and route_path:
        return route_path

    return "unmatched"


class RequestContextMiddleware:
    """Bind request, correlation, trace, and API-version context.

    Valid incoming identifiers are propagated. Invalid identifiers are ignored
    and replaced with generated values.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        api_version: str,
    ) -> None:
        """Initialize request-context middleware.

        Args:
            app: Downstream ASGI application.
            api_version: Configured API prefix or version.
        """
        self.app = app

        normalized_version = api_version.strip().strip("/")

        if "/" in normalized_version:
            normalized_version = normalized_version.rsplit(
                "/",
                maxsplit=1,
            )[-1]

        self.api_version = normalized_version or "v1"

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Bind context for one HTTP request."""
        if scope["type"] != "http":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        headers = Headers(
            scope=scope,
        )

        request_id = (
            _accepted_identifier(
                headers.get("x-request-id"),
            )
            or str(uuid.uuid4())
        )

        correlation_id = (
            _accepted_identifier(
                headers.get("x-correlation-id"),
            )
            or request_id
        )

        trace_id = _extract_trace_id(
            headers.get("traceparent"),
        )

        tokens = set_request_context(
            request_id=request_id,
            correlation_id=correlation_id,
            trace_id=trace_id,
            api_version=self.api_version,
        )

        async def send_wrapper(
            message: Message,
        ) -> None:
            """Attach correlation metadata to the response."""
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(
                    scope=message,
                )

                response_headers["X-Request-ID"] = request_id
                response_headers["X-Correlation-ID"] = correlation_id
                response_headers["X-API-Version"] = self.api_version

            await send(message)

        try:
            await self.app(
                scope,
                receive,
                send_wrapper,
            )
        finally:
            reset_request_context(tokens)


class RequestLoggingMiddleware:
    """Emit one structured completion record for every HTTP request.

    Query strings and request bodies are deliberately excluded to avoid logging
    sensitive data and creating unbounded log cardinality.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        slow_threshold_ms: int,
    ) -> None:
        """Initialize request logging.

        Args:
            app: Downstream ASGI application.
            slow_threshold_ms: Duration at which a request is logged as slow.
        """
        self.app = app
        self.slow_threshold_ms = slow_threshold_ms

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Process and log one HTTP request."""
        if scope["type"] != "http":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        started = time.perf_counter()

        status_code = _HTTP_SERVER_ERROR_STATUS_MIN
        escaped_exception = False

        async def send_wrapper(
            message: Message,
        ) -> None:
            """Capture the final HTTP status code."""
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = int(message["status"])

            await send(message)

        try:
            await self.app(
                scope,
                receive,
                send_wrapper,
            )
        except Exception:
            escaped_exception = True
            raise
        finally:
            duration_ms = round(
                (time.perf_counter() - started) * 1_000,
                2,
            )

            log_context = {
                "http_method": scope.get("method"),
                "http_route": _resolved_route_template(scope),
                "http_status_code": status_code,
                "duration_ms": duration_ms,
                "client_ip_hash": _hash_client_ip(scope),
                "exception_escaped": escaped_exception,
            }

            if (
                escaped_exception
                or status_code >= _HTTP_SERVER_ERROR_STATUS_MIN
            ):
                logger.error(
                    "HTTP request failed",
                    extra=log_context,
                )
            elif duration_ms >= self.slow_threshold_ms:
                logger.warning(
                    "Slow HTTP request completed",
                    extra=log_context,
                )
            else:
                logger.info(
                    "HTTP request completed",
                    extra=log_context,
                )


class RequestSizeLimitMiddleware:
    """Reject request bodies larger than the configured byte limit.

    Both fixed-length and chunked request bodies are supported without buffering
    the complete payload in memory.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
    ) -> None:
        """Initialize request-size enforcement.

        Args:
            app: Downstream ASGI application.
            max_body_bytes: Maximum accepted request-body size.
        """
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Enforce the request-body limit for one HTTP request."""
        if scope["type"] != "http":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        content_length = Headers(
            scope=scope,
        ).get("content-length")

        if content_length is not None:
            declared_length = self._parse_content_length(
                content_length,
            )

            if declared_length is None:
                await self._send_invalid_content_length(
                    scope=scope,
                    receive=receive,
                    send=send,
                )
                return

            if declared_length > self.max_body_bytes:
                await self._send_too_large(
                    scope=scope,
                    receive=receive,
                    send=send,
                )
                return

        received_bytes = 0
        response_started = False

        async def limited_receive() -> Message:
            """Track streamed body bytes without buffering the body."""
            nonlocal received_bytes

            message = await receive()

            if message["type"] == "http.request":
                received_bytes += len(
                    message.get(
                        "body",
                        b"",
                    ),
                )

                if received_bytes > self.max_body_bytes:
                    raise _RequestBodyTooLargeError

            return message

        async def send_wrapper(
            message: Message,
        ) -> None:
            """Track whether the downstream response has already started."""
            nonlocal response_started

            if message["type"] == "http.response.start":
                response_started = True

            await send(message)

        try:
            await self.app(
                scope,
                limited_receive,
                send_wrapper,
            )
        except _RequestBodyTooLargeError:
            # A second response cannot be emitted after headers have already
            # been sent. In that unusual case, propagate the exception so the
            # server terminates the incomplete response safely.
            if response_started:
                raise

            await self._send_too_large(
                scope=scope,
                receive=receive,
                send=send,
            )

    @staticmethod
    def _parse_content_length(
        value: str,
    ) -> int | None:
        """Parse a non-negative Content-Length value.

        Args:
            value: Raw Content-Length header value.

        Returns:
            Parsed non-negative length or ``None``.
        """
        try:
            parsed = int(value)
        except ValueError:
            return None

        if parsed < 0:
            return None

        return parsed

    async def _send_invalid_content_length(
        self,
        *,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Return a standardized invalid Content-Length response."""
        response = APIResponse.error(
            error_code="INVALID_CONTENT_LENGTH",
            message="The Content-Length header is invalid.",
            status_code=400,
        )

        await response(
            scope,
            receive,
            send,
        )

    async def _send_too_large(
        self,
        *,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Return a standardized payload-too-large response."""
        response = APIResponse.error(
            error_code="PAYLOAD_TOO_LARGE",
            message="The request body exceeds the allowed size.",
            status_code=413,
            details={
                "maxBytes": self.max_body_bytes,
            },
        )

        await response(
            scope,
            receive,
            send,
        )


class _RequestBodyTooLargeError(Exception):
    """Signal streamed request-body overflow internally."""


class SecurityHeadersMiddleware:
    """Add conservative security and cache-control headers to API responses."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        enabled: bool,
        hsts_enabled: bool,
    ) -> None:
        """Initialize security-header middleware.

        Args:
            app: Downstream ASGI application.
            enabled: Whether standard security headers are added.
            hsts_enabled: Whether HSTS is added.
        """
        self.app = app
        self.enabled = enabled
        self.hsts_enabled = hsts_enabled

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Attach security headers to one HTTP response."""
        if scope["type"] != "http" or not self.enabled:
            await self.app(
                scope,
                receive,
                send,
            )
            return

        async def send_wrapper(
            message: Message,
        ) -> None:
            """Add headers before the response starts."""
            if message["type"] == "http.response.start":
                headers = MutableHeaders(
                    scope=message,
                )

                headers.setdefault(
                    "Cache-Control",
                    "no-store",
                )

                headers.setdefault(
                    "X-Content-Type-Options",
                    "nosniff",
                )

                headers.setdefault(
                    "X-Frame-Options",
                    "DENY",
                )

                headers.setdefault(
                    "Referrer-Policy",
                    "no-referrer",
                )

                headers.setdefault(
                    "Permissions-Policy",
                    "camera=(), microphone=(), geolocation=()",
                )

                if self.hsts_enabled:
                    headers.setdefault(
                        "Strict-Transport-Security",
                        "max-age=31536000; includeSubDomains",
                    )

            await send(message)

        await self.app(
            scope,
            receive,
            send_wrapper,
        )


def register_middleware(
    app: FastAPI,
    settings: AppSettings,
) -> None:
    """Register global application middleware.

    Starlette applies the last added middleware as the outermost wrapper. The
    registration order therefore ensures:

    1. request context wraps every downstream component,
    2. CORS can decorate application and middleware error responses,
    3. request logging observes rejected and successful requests,
    4. security headers are applied to standardized body-limit responses,
    5. body-size validation occurs before route execution.

    Args:
        app: FastAPI application instance.
        settings: Validated application settings.
    """
    # Innermost middleware: reject oversized bodies before route handlers read
    # or deserialize the complete payload.
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_body_bytes=settings.MAX_REQUEST_BODY_BYTES,
    )

    app.add_middleware(
        SecurityHeadersMiddleware,
        enabled=settings.SECURE_HEADERS_ENABLED,
        hsts_enabled=settings.HSTS_ENABLED,
    )

    app.add_middleware(
        RequestLoggingMiddleware,
        slow_threshold_ms=settings.SLOW_REQUEST_THRESHOLD_MS,
    )

    if settings.CORS_ALLOWED_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ALLOWED_ORIGINS,
            allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
            allow_methods=[
                "GET",
                "POST",
                "PUT",
                "PATCH",
                "DELETE",
                "OPTIONS",
            ],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Idempotency-Key",
                "Traceparent",
                "X-Correlation-ID",
                "X-Request-ID",
                "X-User-ID",
                "X-User-Role",
            ],
            expose_headers=[
                "X-API-Version",
                "X-Correlation-ID",
                "X-Request-ID",
            ],
            max_age=600,
        )

    # Outermost middleware: all responses, including CORS preflight and
    # middleware-generated errors, receive request and correlation identifiers.
    app.add_middleware(
        RequestContextMiddleware,
        api_version=settings.API_V1_STR,
    )


__all__ = [
    "RequestContextMiddleware",
    "RequestLoggingMiddleware",
    "RequestSizeLimitMiddleware",
    "SecurityHeadersMiddleware",
    "register_middleware",
]
