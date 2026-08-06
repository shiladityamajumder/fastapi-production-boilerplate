"""File: app/common/exceptions.py.

Framework-independent application exception hierarchy.

Exceptions defined here represent expected business, application, and
infrastructure failures. They contain only client-safe information and must
never expose:

- SQL statements,
- database connection details,
- access tokens or credentials,
- stack traces,
- patient or prescription data,
- raw third-party service responses.

HTTP status-code translation belongs to ``app/api/exception_handlers.py`` so
services, repositories, and domain code remain independent of FastAPI.
"""

from __future__ import annotations

from typing import Any, ClassVar


class AppError(Exception):
    """Base class for expected application failures.

    Attributes:
        message: Human-readable and client-safe error message.
        details: Optional client-safe structured error context.
        code: Stable machine-readable error identifier.
    """

    default_code: ClassVar[str] = "APPLICATION_ERROR"
    default_message: ClassVar[str] = "The operation could not be completed."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Any | None = None,
        code: str | None = None,
    ) -> None:
        """Initialize an expected application error.

        Args:
            message: Optional client-safe message override.
            details: Optional client-safe structured context.
            code: Optional stable error-code override.
        """
        normalized_message = (
            message.strip() if message and message.strip() else self.default_message
        )

        normalized_code = code.strip() if code and code.strip() else self.default_code

        super().__init__(normalized_message)

        self.message = normalized_message
        self.details = details
        self.code = normalized_code


class DomainError(AppError):
    """Base class for domain invariant or business-rule violations."""

    default_code = "DOMAIN_ERROR"
    default_message = "A business rule was violated."


class ApplicationError(AppError):
    """Base class for expected application use-case failures."""

    default_code = "APPLICATION_ERROR"


class ValidationError(ApplicationError):
    """Input is structurally valid but unacceptable to the use case.

    FastAPI and Pydantic request-shape failures use
    ``RequestValidationError`` and are translated separately by the API layer.
    """

    default_code = "VALIDATION_ERROR"
    default_message = "The supplied input is invalid."


class AuthenticationError(ApplicationError):
    """Authentication credentials are missing, expired, or invalid."""

    default_code = "AUTHENTICATION_REQUIRED"
    default_message = "Authentication is required."


class AuthorizationError(ApplicationError):
    """The authenticated principal lacks permission for the operation."""

    default_code = "PERMISSION_DENIED"
    default_message = "You do not have permission to perform this operation."


class NotFoundError(ApplicationError):
    """A requested resource does not exist or is not visible to the caller."""

    default_code = "RESOURCE_NOT_FOUND"
    default_message = "The requested resource was not found."


class ConflictError(ApplicationError):
    """The requested operation conflicts with the current resource state."""

    default_code = "RESOURCE_CONFLICT"
    default_message = "The request conflicts with the current resource state."


class OperationTimeoutError(ApplicationError):
    """An internal bounded operation exceeded its configured deadline."""

    default_code = "OPERATION_TIMEOUT"
    default_message = "The operation timed out."


class ExternalServiceError(ApplicationError):
    """A required external service failed without exposing provider details."""

    default_code = "EXTERNAL_SERVICE_ERROR"
    default_message = "A required external service is unavailable."


class ExternalServiceTimeoutError(ExternalServiceError):
    """A required external service exceeded its configured timeout."""

    default_code = "EXTERNAL_SERVICE_TIMEOUT"
    default_message = "A required external service timed out."


class DatabaseError(ApplicationError):
    """A database operation failed without exposing driver or SQL details."""

    default_code = "DATABASE_ERROR"
    default_message = "A persistence operation failed."


class InfrastructureError(AppError):
    """Base class for runtime infrastructure failures."""

    default_code = "INFRASTRUCTURE_ERROR"
    default_message = "A required infrastructure component failed."


class InfrastructureUnavailableError(InfrastructureError):
    """A required infrastructure dependency is temporarily unavailable."""

    default_code = "INFRASTRUCTURE_UNAVAILABLE"
    default_message = "A required service is temporarily unavailable."


__all__ = [
    "AppError",
    "ApplicationError",
    "AuthenticationError",
    "AuthorizationError",
    "ConflictError",
    "DatabaseError",
    "DomainError",
    "ExternalServiceError",
    "ExternalServiceTimeoutError",
    "InfrastructureError",
    "InfrastructureUnavailableError",
    "NotFoundError",
    "OperationTimeoutError",
    "ValidationError",
]
