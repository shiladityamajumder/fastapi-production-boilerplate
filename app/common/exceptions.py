# File: app/common/exceptions.py
"""
===============================================================================
DOMAIN ERROR MODEL + TRANSPORT ADAPTER
===============================================================================

This module defines the application's error model and its translation layer.

It enforces a strict boundary between:

    1. Domain Layer  (Business rules, use cases, services)
    2. Transport Layer (FastAPI / HTTP)

-------------------------------------------------------------------------------
ARCHITECTURE CONTRACT
-------------------------------------------------------------------------------

Domain Layer:
    - Raises APIException (or subclasses)
    - Must NOT import or raise HTTPException
    - Must NOT return JSONResponse
    - Must NOT depend on FastAPI

Transport Layer:
    - Converts exceptions into HTTP responses
    - Guarantees unified response shape
    - Owns framework-specific concerns

This preserves:

    - Framework independence
    - Testability of business logic
    - Replaceable transport (HTTP → gRPC → CLI, etc.)
    - Predictable error contracts

-------------------------------------------------------------------------------
ERROR FLOW (END-TO-END)
-------------------------------------------------------------------------------

[ Service Layer ]
        |
        | raise NotFoundError("User not found")
        v
[ FastAPI Exception Router ]
        |
        v
[ api_exception_handler ]
        |
        v
[ APIResponse.error(...) ]
        |
        v
[ HTTP JSON Response ]

-------------------------------------------------------------------------------
INVARIANT
-------------------------------------------------------------------------------

Every external error response MUST follow a single response schema.

There are no ad-hoc responses anywhere in the system.

-------------------------------------------------------------------------------
SECURITY RULE
-------------------------------------------------------------------------------

Unhandled exceptions:
    - Never leak internal details in production
    - Expose raw message only when DEBUG=True
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.response import APIResponse
from app.core.config import get_settings

settings = get_settings()


# =============================================================================
# DOMAIN EXCEPTION BASE TYPE
# =============================================================================


class APIException(Exception):
    """
    Root type for all controlled domain failures.

    ---------------------------------------------------------------------------
    ROLE
    ---------------------------------------------------------------------------

    Represents expected business rule violations.

    Examples:
        - Resource not found
        - Duplicate entity
        - Permission denied
        - Invalid state transition

    ---------------------------------------------------------------------------
    DESIGN RULES
    ---------------------------------------------------------------------------

    - Must remain framework-agnostic.
    - Must not depend on FastAPI or HTTPException.
    - May carry structured metadata for client consumption.

    ---------------------------------------------------------------------------
    FAILURE SEMANTICS
    ---------------------------------------------------------------------------

    Raising APIException indicates:
        - The failure is expected
        - The failure is handled
        - The client can safely receive a controlled response

    ---------------------------------------------------------------------------
    PARAMETERS
    ---------------------------------------------------------------------------

    message: str
        Human-readable explanation.

    code: int
        Intended HTTP status code.

    errors: list[dict[str, Any]]
        Optional structured validation or field errors.

    ---------------------------------------------------------------------------
    EXAMPLE (SERVICE LAYER)
    ---------------------------------------------------------------------------

    # def create_user(email: str):
    #     if repository.exists(email):
    #         raise ConflictError("Email already registered")
    #
    #     user = repository.create(email=email)
    #     return user

    ---------------------------------------------------------------------------
    ANTI-PATTERN
    ---------------------------------------------------------------------------

    DO NOT DO THIS IN SERVICE LAYER:

    # from fastapi import HTTPException
    # raise HTTPException(status_code=404, detail="User not found")

    That breaks clean architecture boundaries.
    """

    def __init__(
        self,
        message: str,
        *,
        code: int = status.HTTP_400_BAD_REQUEST,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.errors = errors or []


# =============================================================================
# DOMAIN EXCEPTION SPECIALIZATIONS
# =============================================================================


class ConflictError(APIException):
    """
    Indicates a resource state conflict.

    Maps to HTTP 409.

    Typical triggers:
        - Unique constraint violation
        - Duplicate entity creation
        - Invalid concurrent modification

    Example:

    # if repo.email_exists(email):
    #     raise ConflictError("Email already registered")
    """

    def __init__(self, message: str = "Resource conflict") -> None:
        super().__init__(message=message, code=status.HTTP_409_CONFLICT)


class NotFoundError(APIException):
    """
    Indicates that a requested resource does not exist.

    Maps to HTTP 404.

    Example:

    # user = repo.get(user_id)
    # if not user:
    #     raise NotFoundError("User not found")
    """

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message=message, code=status.HTTP_404_NOT_FOUND)


class ForbiddenError(APIException):
    """
    Indicates insufficient authorization.

    Maps to HTTP 403.

    Example:

    # if not current_user.is_admin:
    #     raise ForbiddenError("Admin privileges required")
    """

    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__(message=message, code=status.HTTP_403_FORBIDDEN)


class UnauthorizedError(APIException):
    """
    Indicates missing or invalid authentication.

    Maps to HTTP 401.

    Example:

    # if not current_user:
    #     raise UnauthorizedError()
    """

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message=message, code=status.HTTP_401_UNAUTHORIZED)


# =============================================================================
# TRANSPORT ADAPTERS (HTTP LAYER)
# =============================================================================


def api_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Adapter: Domain Exception → HTTP Response.

    ---------------------------------------------------------------------------
    CONTRACT
    ---------------------------------------------------------------------------

    Input:
        exc must be APIException (FastAPI enforces type mapping)

    Output:
        JSONResponse formatted via APIResponse.error

    ---------------------------------------------------------------------------
    WHY exc: Exception?
    ---------------------------------------------------------------------------

    FastAPI requires a generic Exception signature.
    We safely cast internally.

    ---------------------------------------------------------------------------
    REGISTRATION EXAMPLE (main.py)
    ---------------------------------------------------------------------------

    # app.add_exception_handler(APIException, api_exception_handler)
    """

    api_exc = cast(APIException, exc)

    return APIResponse.error(
        message=api_exc.message,
        code=api_exc.code,
        errors=api_exc.errors,
    )


def validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Adapter: Pydantic ValidationError → Unified APIResponse.

    ---------------------------------------------------------------------------
    ROLE
    ---------------------------------------------------------------------------

    Normalizes FastAPI validation errors into application-level schema.

    Ensures response consistency across:
        - Domain validation
        - Request body validation
        - Query parameter validation

    ---------------------------------------------------------------------------
    TRANSFORMATION
    ---------------------------------------------------------------------------

    FastAPI error structure → Simplified structured list:
        { field: str, message: str }

    ---------------------------------------------------------------------------
    REGISTRATION EXAMPLE
    ---------------------------------------------------------------------------

    # app.add_exception_handler(RequestValidationError,
    #                           validation_exception_handler)
    """

    validation_exc = cast(RequestValidationError, exc)

    formatted_errors: list[dict[str, str]] = []

    for err in validation_exc.errors():
        field = ".".join(str(loc) for loc in err.get("loc", []))
        formatted_errors.append(
            {
                "field": field,
                "message": err.get("msg", "Invalid value"),
            }
        )

    return APIResponse.error(
        message="Invalid input",
        code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        errors=formatted_errors,
    )


def http_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Adapter: Starlette HTTPException → Unified APIResponse.

    ---------------------------------------------------------------------------
    ROLE
    ---------------------------------------------------------------------------

    Handles framework-level failures:
        - Route not found
        - Method not allowed
        - Middleware-raised errors

    These are NOT domain failures.

    Ensures even framework errors respect our response schema.
    """

    http_exc = cast(StarletteHTTPException, exc)

    return APIResponse.error(
        message=str(http_exc.detail),
        code=http_exc.status_code,
        errors=[{"field": None, "message": str(http_exc.detail)}],
    )


def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Adapter: Unexpected Exception → Safe HTTP 500.

    ---------------------------------------------------------------------------
    FAILURE CLASSIFICATION
    ---------------------------------------------------------------------------

    This captures:
        - Programming errors
        - Unexpected runtime failures
        - Infrastructure issues

    ---------------------------------------------------------------------------
    SECURITY POLICY
    ---------------------------------------------------------------------------

    DEBUG = False:
        - Do NOT expose internal error details

    DEBUG = True:
        - Expose raw message for faster development iteration

    ---------------------------------------------------------------------------
    OPERATIONAL NOTE
    ---------------------------------------------------------------------------

    Logging of the exception should occur elsewhere (middleware or logger).
    This handler is responsible only for client-safe response generation.
    """

    if settings.DEBUG:
        message = str(exc)
    else:
        message = "An unexpected error occurred"

    return APIResponse.error(
        message=message,
        code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
