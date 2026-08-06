"""File: app/api/exception_handlers.py.

Central HTTP translation for application and framework exceptions.

Expected domain, application, and infrastructure exceptions are converted into
the canonical API response envelope. Unexpected failures are logged with their
stack trace and returned to clients without leaking internal implementation
details.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import (
    FastAPI,
    Request,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import (
    HTTPException as StarletteHTTPException,
)

from app.common.exceptions import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DatabaseError,
    ExternalServiceError,
    ExternalServiceTimeoutError,
    InfrastructureError,
    InfrastructureUnavailableError,
    NotFoundError,
    OperationTimeoutError,
    ValidationError,
)
from app.common.response import APIResponse
from app.core.logging import get_logger

logger = get_logger(__name__)


ExceptionHandler = Callable[
    [Request, Exception],
    Awaitable[JSONResponse],
]


_HTTP_SERVER_ERROR_MIN = status.HTTP_500_INTERNAL_SERVER_ERROR


# More-specific exception classes must appear before their parent classes.
_ERROR_STATUS: tuple[
    tuple[type[AppError], int],
    ...,
] = (
    (
        AuthenticationError,
        status.HTTP_401_UNAUTHORIZED,
    ),
    (
        AuthorizationError,
        status.HTTP_403_FORBIDDEN,
    ),
    (
        NotFoundError,
        status.HTTP_404_NOT_FOUND,
    ),
    (
        ConflictError,
        status.HTTP_409_CONFLICT,
    ),
    (
        ValidationError,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    ),
    (
        ExternalServiceTimeoutError,
        status.HTTP_504_GATEWAY_TIMEOUT,
    ),
    (
        OperationTimeoutError,
        status.HTTP_504_GATEWAY_TIMEOUT,
    ),
    (
        InfrastructureUnavailableError,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
    (
        ExternalServiceError,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
    (
        DatabaseError,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
    (
        InfrastructureError,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
)


_HTTP_ERROR_CODES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "AUTHENTICATION_REQUIRED",
    status.HTTP_403_FORBIDDEN: "PERMISSION_DENIED",
    status.HTTP_404_NOT_FOUND: "ROUTE_NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    status.HTTP_406_NOT_ACCEPTABLE: "NOT_ACCEPTABLE",
    status.HTTP_408_REQUEST_TIMEOUT: "REQUEST_TIMEOUT",
    status.HTTP_409_CONFLICT: "RESOURCE_CONFLICT",
    status.HTTP_410_GONE: "RESOURCE_GONE",
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: "PAYLOAD_TOO_LARGE",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "UNSUPPORTED_MEDIA_TYPE",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "UNPROCESSABLE_CONTENT",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
    status.HTTP_504_GATEWAY_TIMEOUT: "GATEWAY_TIMEOUT",
}


def _route_template(
    request: Request,
) -> str:
    """Return the matched route template without exposing raw path parameters.

    Args:
        request: Current FastAPI request.

    Returns:
        Matched route template or ``"unmatched"``.
    """
    route = request.scope.get("route")
    path = getattr(
        route,
        "path",
        None,
    )

    if isinstance(path, str) and path:
        return path

    return "unmatched"


def _status_for(
    error: AppError,
) -> int:
    """Resolve the public HTTP status for an application exception.

    Args:
        error: Expected application exception.

    Returns:
        HTTP status code.
    """
    for error_type, status_code in _ERROR_STATUS:
        if isinstance(
            error,
            error_type,
        ):
            return status_code

    # Unmapped expected application or domain errors represent client-side
    # request failures unless a more specific mapping is introduced.
    return status.HTTP_400_BAD_REQUEST


def _log_expected_error(
    *,
    request: Request,
    error: AppError,
    status_code: int,
) -> None:
    """Log an expected application failure at an appropriate severity.

    Validation and missing-resource cases are routine client outcomes and use
    INFO. Conflicts and permission failures use WARNING. Infrastructure failures
    use ERROR because they generally require operational attention.

    Args:
        request: Current FastAPI request.
        error: Expected application exception.
        status_code: Resolved public HTTP status code.
    """
    context = {
        "error_code": error.code,
        "http_status_code": status_code,
        "http_method": request.method,
        "http_route": _route_template(request),
        "exception_type": type(error).__name__,
    }

    if status_code >= _HTTP_SERVER_ERROR_MIN:
        logger.error(
            "Expected infrastructure or dependency failure",
            extra=context,
        )

    elif status_code in {
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_409_CONFLICT,
    }:
        logger.warning(
            "Expected application request rejected",
            extra=context,
        )

    else:
        logger.info(
            "Expected application request rejected",
            extra=context,
        )


async def app_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Translate an expected application error into a safe HTTP response.

    Args:
        request: Current FastAPI request.
        exc: Application exception raised by downstream code.

    Returns:
        Canonical JSON error response.
    """
    error = cast(
        "AppError",
        exc,
    )

    status_code = _status_for(
        error,
    )

    _log_expected_error(
        request=request,
        error=error,
        status_code=status_code,
    )

    return APIResponse.error(
        error_code=error.code,
        message=error.message,
        status_code=status_code,
        details=error.details,
    )


async def validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Sanitize FastAPI and Pydantic request-validation failures.

    Only field location, validation type, and a safe validation message are
    exposed. Rejected values and Pydantic context are intentionally omitted
    because they may contain credentials or healthcare information.

    Args:
        request: Current FastAPI request.
        exc: FastAPI request-validation exception.

    Returns:
        Canonical HTTP 422 response.
    """
    validation_error = cast(
        "RequestValidationError",
        exc,
    )

    details: list[dict[str, str]] = []

    for item in validation_error.errors():
        location = [
            str(part)
            for part in item.get(
                "loc",
                (),
            )
            if str(part)
            not in {
                "body",
                "query",
                "path",
                "header",
            }
        ]

        field = ".".join(location) or "request"

        details.append(
            {
                "field": field,
                "message": str(
                    item.get(
                        "msg",
                        "Invalid value",
                    )
                ),
                "type": str(
                    item.get(
                        "type",
                        "validation_error",
                    )
                ),
            }
        )

    logger.info(
        "HTTP request validation failed",
        extra={
            "validation_error_count": len(details),
            "http_method": request.method,
            "http_route": _route_template(request),
        },
    )

    return APIResponse.error(
        error_code="REQUEST_VALIDATION_ERROR",
        message="The request contains invalid input.",
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        details=details,
    )


async def http_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Normalize framework-generated HTTP exceptions.

    Args:
        request: Current FastAPI request.
        exc: Starlette HTTP exception.

    Returns:
        Canonical JSON error response.
    """
    http_error = cast(
        "StarletteHTTPException",
        exc,
    )

    error_code = _HTTP_ERROR_CODES.get(
        http_error.status_code,
        "HTTP_ERROR",
    )

    if http_error.status_code >= _HTTP_SERVER_ERROR_MIN:
        message = "An unexpected server error occurred."

        logger.error(
            "Framework HTTP server error",
            extra={
                "error_code": error_code,
                "http_status_code": http_error.status_code,
                "http_method": request.method,
                "http_route": _route_template(request),
            },
        )

    elif isinstance(
        http_error.detail,
        str,
    ):
        normalized_detail = http_error.detail.strip()

        message = (
            normalized_detail
            if normalized_detail
            else "The request could not be processed."
        )

    else:
        message = "The request could not be processed."

    return APIResponse.error(
        error_code=error_code,
        message=message,
        status_code=http_error.status_code,
        headers=dict(
            http_error.headers or {}
        ),
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Log an unexpected failure and return a non-leaking HTTP 500 response.

    Args:
        request: Current FastAPI request.
        exc: Unexpected exception.

    Returns:
        Canonical internal-server-error response.
    """
    logger.error(
        "Unhandled application exception",
        extra={
            "http_method": request.method,
            "http_route": _route_template(request),
            "exception_type": type(exc).__name__,
        },
        exc_info=(
            type(exc),
            exc,
            exc.__traceback__,
        ),
    )

    return APIResponse.error(
        error_code="INTERNAL_SERVER_ERROR",
        message="An unexpected server error occurred.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def register_exception_handlers(
    app: FastAPI,
) -> None:
    """Register centralized exception handlers on a FastAPI application.

    Args:
        app: Application instance receiving the handlers.
    """
    handlers: tuple[
        tuple[type[Exception], ExceptionHandler],
        ...,
    ] = (
        (
            AppError,
            app_error_handler,
        ),
        (
            RequestValidationError,
            validation_exception_handler,
        ),
        (
            StarletteHTTPException,
            http_exception_handler,
        ),
        (
            Exception,
            unhandled_exception_handler,
        ),
    )

    for exception_type, handler in handlers:
        app.add_exception_handler(
            exception_type,
            handler,
        )


__all__ = [
    "app_error_handler",
    "http_exception_handler",
    "register_exception_handlers",
    "unhandled_exception_handler",
    "validation_exception_handler",
]
