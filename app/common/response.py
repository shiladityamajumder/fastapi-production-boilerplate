"""File: app/common/response.py.

Canonical external API response envelope.

All successful and failed JSON responses use one stable structure:

    {
        "success": true,
        "message": "Operation completed successfully",
        "data": {},
        "error": null,
        "meta": {
            "requestId": "...",
            "correlationId": "...",
            "apiVersion": "v1",
            "timestamp": "..."
        }
    }

Python fields use snake_case while serialized API fields use camelCase.

This module belongs to the API transport boundary. Domain services and
repositories should return typed results or raise application exceptions rather
than constructing HTTP responses directly.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Any

from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)
from pydantic.alias_generators import to_camel

from app.core.request_context import (
    get_api_version,
    get_correlation_id,
    get_request_id,
)
from app.utils.datetime_utils import utc_now

_HTTP_SUCCESS_MIN = status.HTTP_200_OK
_HTTP_SUCCESS_MAX_EXCLUSIVE = status.HTTP_400_BAD_REQUEST
_HTTP_ERROR_MIN = status.HTTP_400_BAD_REQUEST
_HTTP_ERROR_MAX = 599


class APIModel(BaseModel):
    """Base model for externally serialized API payloads.

    Internal Python code uses snake_case. JSON responses use camelCase aliases.
    Unknown fields are rejected to keep the public contract predictable.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class PaginationMeta(APIModel):
    """Offset-based pagination metadata.

    Attributes:
        total_count: Total number of matching records.
        limit: Maximum number of records requested.
        offset: Number of records skipped.
        has_next: Whether another result page is available.
    """

    total_count: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    has_next: bool


class ErrorBody(APIModel):
    """Machine-readable and client-safe error information.

    Attributes:
        code: Stable application error identifier.
        details: Optional structured error context.
    """

    code: str
    details: Any | None = None

    @field_validator("code")
    @classmethod
    def validate_code(
        cls,
        value: str,
    ) -> str:
        """Normalize and reject a blank error code.

        Args:
            value: Raw error code.

        Returns:
            Normalized error code.

        Raises:
            ValueError: If the code is blank.
        """
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Error code must not be blank"
            )

        return normalized


class ResponseMeta(APIModel):
    """Operational metadata included in every JSON response.

    Attributes:
        request_id: Identifier for the current HTTP request.
        correlation_id: Identifier propagated across related services.
        api_version: Public API version associated with the request.
        timestamp: UTC response creation timestamp.
        pagination: Optional pagination metadata for collection responses.
    """

    request_id: str | None = None
    correlation_id: str | None = None
    api_version: str
    timestamp: datetime = Field(
        default_factory=utc_now
    )
    pagination: PaginationMeta | None = None

    @field_validator("api_version")
    @classmethod
    def validate_api_version(
        cls,
        value: str,
    ) -> str:
        """Normalize and reject a blank API version.

        Args:
            value: API version obtained from request context.

        Returns:
            Normalized API version.

        Raises:
            ValueError: If the version is blank.
        """
        normalized = value.strip().strip("/")

        if not normalized:
            raise ValueError(
                "API version must not be blank"
            )

        return normalized


class APIResponseModel[DataT](APIModel):
    """Stable response contract for successful and failed requests.

    Type Parameters:
        DataT: Type of the successful response payload.
    """

    success: bool
    message: str
    data: DataT | None
    error: ErrorBody | None
    meta: ResponseMeta

    @field_validator("message")
    @classmethod
    def validate_message(
        cls,
        value: str,
    ) -> str:
        """Normalize and reject a blank response message.

        Args:
            value: Response message.

        Returns:
            Normalized response message.

        Raises:
            ValueError: If the message is blank.
        """
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Response message must not be blank"
            )

        return normalized


class APIResponse:
    """Build JSON responses using the canonical public API envelope.

    This class contains transport-level response construction only. Application
    and domain layers must not depend on it.
    """

    @staticmethod
    def success(
        *,
        message: str = "Operation completed successfully.",
        data: Any = None,
        status_code: int = status.HTTP_200_OK,
        pagination: PaginationMeta | None = None,
        headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        """Create a successful JSON response.

        Args:
            message: Human-readable success message.
            data: Successful response payload.
            status_code: HTTP success or redirect status.
            pagination: Optional pagination metadata.
            headers: Optional additional HTTP headers.

        Returns:
            Serialized JSON response.

        Raises:
            ValueError: If the status code cannot contain this response body.
        """
        if status_code == status.HTTP_204_NO_CONTENT:
            raise ValueError(
                "Use an empty Response for HTTP 204"
            )

        if not (
            _HTTP_SUCCESS_MIN
            <= status_code
            < _HTTP_SUCCESS_MAX_EXCLUSIVE
        ):
            raise ValueError(
                "Success status_code must be between 200 and 399"
            )

        body = APIResponseModel[Any](
            success=True,
            message=message,
            data=data,
            error=None,
            meta=APIResponse._build_meta(
                pagination=pagination,
            ),
        )

        response = JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(
                body,
                by_alias=True,
                exclude_none=False,
            ),
            headers=headers,
        )

        APIResponse._attach_context_headers(
            response
        )

        return response

    @staticmethod
    def error(
        *,
        error_code: str,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        """Create a standardized client-safe error response.

        Args:
            error_code: Stable machine-readable error identifier.
            message: Human-readable client-safe explanation.
            status_code: HTTP client or server error status.
            details: Optional structured error details.
            headers: Optional additional HTTP headers.

        Returns:
            Serialized JSON error response.

        Raises:
            ValueError: If the status code is outside the HTTP error range.
        """
        if not (
            _HTTP_ERROR_MIN
            <= status_code
            <= _HTTP_ERROR_MAX
        ):
            raise ValueError(
                "Error status_code must be between 400 and 599"
            )

        body = APIResponseModel[Any](
            success=False,
            message=message,
            data=None,
            error=ErrorBody(
                code=error_code,
                details=details,
            ),
            meta=APIResponse._build_meta(),
        )

        response = JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(
                body,
                by_alias=True,
                exclude_none=False,
            ),
            headers=headers,
        )

        response.headers.setdefault(
            "Cache-Control",
            "no-store",
        )

        APIResponse._attach_context_headers(
            response
        )

        return response

    @staticmethod
    def _build_meta(
        *,
        pagination: PaginationMeta | None = None,
    ) -> ResponseMeta:
        """Build response metadata from the current execution context.

        Args:
            pagination: Optional pagination metadata.

        Returns:
            Response metadata populated from context variables.
        """
        return ResponseMeta(
            request_id=get_request_id(),
            correlation_id=get_correlation_id(),
            api_version=get_api_version(),
            pagination=pagination,
        )

    @staticmethod
    def _attach_context_headers(
        response: JSONResponse,
    ) -> None:
        """Attach request and correlation identifiers to response headers.

        The request-context middleware also performs this operation. Keeping it
        here ensures responses constructed outside the normal middleware path,
        including tests and internal calls, remain consistent.

        Args:
            response: Response receiving context headers.
        """
        request_id = get_request_id()
        correlation_id = get_correlation_id()

        if request_id:
            response.headers.setdefault(
                "X-Request-ID",
                request_id,
            )

        if correlation_id:
            response.headers.setdefault(
                "X-Correlation-ID",
                correlation_id,
            )


__all__ = [
    "APIModel",
    "APIResponse",
    "APIResponseModel",
    "ErrorBody",
    "PaginationMeta",
    "ResponseMeta",
]
