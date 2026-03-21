# File: app/common/response.py
"""
===============================================================================
UNIFIED API RESPONSE ENVELOPE
===============================================================================

This module defines the single authoritative HTTP response contract.

It is the ONLY location in the system allowed to construct JSONResponse.

-------------------------------------------------------------------------------
ARCHITECTURE BOUNDARY
-------------------------------------------------------------------------------

Domain Layer:
    - Returns domain objects / primitives
    - Raises APIException on failure
    - Does NOT construct HTTP responses

Transport Layer:
    - Converts domain results into APIResponse.success()
    - Converts exceptions into APIResponse.error()

This ensures:
    - Zero framework leakage into business logic
    - Stable external contract
    - Centralized response evolution
    - Cross-service consistency

-------------------------------------------------------------------------------
NON-NEGOTIABLE RULE
-------------------------------------------------------------------------------

Never construct JSONResponse manually outside this file.

Violating this rule leads to:
    - Inconsistent API shape
    - Missing request_id
    - Missing version metadata
    - Broken observability
    - Contract drift

-------------------------------------------------------------------------------
RESPONSE SHAPE (STRICT CONTRACT)
-------------------------------------------------------------------------------

{
    "success": true | false,
    "status": "success" | "error",
    "code": 200,
    "message": "...",
    "data": {...} | null,
    "meta": {
        "request_id": "...",
        "api_version": "v1",
        "timestamp": "ISO8601 UTC",
        "pagination": {...} | null,
        "errors": [...] | null
    }
}

-------------------------------------------------------------------------------
INVARIANTS
-------------------------------------------------------------------------------

1. Every response contains "meta".
2. request_id must be attached when available.
3. Error responses must set data = null.
4. Success responses must set errors = null.
5. The HTTP status code must match body.code.
6. Schema must remain backward compatible.

-------------------------------------------------------------------------------
OBSERVABILITY GUARANTEE
-------------------------------------------------------------------------------

- request_id enables distributed tracing.
- X-Request-ID header mirrors meta.request_id.
- Timestamp always UTC ISO8601.
- API version comes from configuration.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.request_context import get_request_id

settings = get_settings()


# =============================================================================
# PAGINATION CONTRACT
# =============================================================================


class Pagination(BaseModel):
    """
    Offset-based pagination contract.

    ---------------------------------------------------------------------------
    STANDARDIZATION RULE
    ---------------------------------------------------------------------------

    Teams must standardize on offset-based pagination.

    Required fields:
        - total_count
        - limit
        - offset
        - has_next

    Mixing page-based and offset-based pagination is prohibited.

    ---------------------------------------------------------------------------
    EXAMPLE USAGE
    ---------------------------------------------------------------------------

    # pagination = Pagination(
    #     total_count=250,
    #     limit=20,
    #     offset=40,
    #     has_next=True,
    # )
    #
    # return APIResponse.success(
    #     data=users,
    #     pagination=pagination,
    # )
    """

    total_count: int
    limit: int
    offset: int
    has_next: bool


# =============================================================================
# META SECTION
# =============================================================================


class Meta(BaseModel):
    """
    Metadata included in EVERY response.

    ---------------------------------------------------------------------------
    PURPOSE
    ---------------------------------------------------------------------------

    Provides cross-cutting operational context.

    Fields:

    request_id:
        Correlation ID injected by middleware.
        Enables tracing across services.

    api_version:
        Controlled via configuration.
        Allows versioning without route-based coupling.

    timestamp:
        UTC ISO8601.
        Enables debugging and latency analysis.

    pagination:
        Present only for list responses.

    errors:
        Present only for error responses.

    ---------------------------------------------------------------------------
    EXTENSION RULE
    ---------------------------------------------------------------------------

    New metadata fields must:
        - Be backward compatible
        - Not break existing clients
        - Be optional unless universally required
    """

    request_id: str | None
    api_version: str = settings.API_V1_STR.replace("/", "") or "v1"
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )
    pagination: Pagination | None = None
    errors: Sequence[dict[str, Any]] | None = None


# =============================================================================
# UNIFIED RESPONSE MODEL
# =============================================================================


class APIResponseModel(BaseModel):
    """
    Canonical external response schema.

    This model defines the public API contract.

    ---------------------------------------------------------------------------
    FIELD SEMANTICS
    ---------------------------------------------------------------------------

    success:
        Boolean outcome indicator.

    status:
        Redundant but explicit string indicator ("success" | "error").
        Useful for clients that avoid boolean logic.

    code:
        Mirrors HTTP status code.

    message:
        Human-readable explanation.

    data:
        Present only for success responses.

    meta:
        Operational metadata container.

    ---------------------------------------------------------------------------
    STABILITY RULE
    ---------------------------------------------------------------------------

    This schema must remain stable across versions unless explicitly versioned.
    """

    success: bool
    status: str
    code: int
    message: str
    data: Any | None
    meta: Meta


# =============================================================================
# RESPONSE BUILDER (TRANSPORT ADAPTER)
# =============================================================================


class APIResponse:
    """
    The ONLY response builder in the system.

    ---------------------------------------------------------------------------
    RESPONSIBILITY
    ---------------------------------------------------------------------------

    - Construct unified response schema
    - Attach request_id header
    - Serialize via jsonable_encoder
    - Guarantee invariant compliance

    ---------------------------------------------------------------------------
    SUCCESS FLOW
    ---------------------------------------------------------------------------

    Controller Layer:

    # result = service.create_user(payload)
    # return APIResponse.success(
    #     message="User created",
    #     data=result,
    #     code=201,
    # )

    ---------------------------------------------------------------------------
    ERROR FLOW
    ---------------------------------------------------------------------------

    Exceptions are converted centrally by exception handlers:

    # raise NotFoundError("User not found")

    Handler:

    # return APIResponse.error(
    #     message="User not found",
    #     code=404,
    # )

    ---------------------------------------------------------------------------
    ANTI-PATTERN
    ---------------------------------------------------------------------------

    DO NOT:

    # return JSONResponse({"foo": "bar"})

    That breaks contract uniformity.
    """

    @staticmethod
    def success(
        *,
        message: str = "Operation completed successfully",
        data: Any = None,
        code: int = status.HTTP_200_OK,
        pagination: Pagination | None = None,
    ) -> JSONResponse:
        """
        Construct a success response.

        CONTRACT:
            - success=True
            - status="success"
            - errors=None
            - HTTP status must equal body.code
        """

        meta = Meta(
            request_id=get_request_id(),
            pagination=pagination,
        )

        body = APIResponseModel(
            success=True,
            status="success",
            code=code,
            message=message,
            data=data,
            meta=meta,
        )

        response = JSONResponse(
            status_code=code,
            content=jsonable_encoder(body),
        )

        # Distributed tracing header
        if meta.request_id:
            response.headers["X-Request-ID"] = meta.request_id

        return response

    @staticmethod
    def error(
        *,
        message: str,
        code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        errors: list[dict[str, Any]] | None = None,
    ) -> JSONResponse:
        """
        Construct an error response.

        CONTRACT:
            - success=False
            - status="error"
            - data=None
            - errors attached in meta
            - HTTP status must equal body.code

        Used exclusively by exception handlers.
        """

        meta = Meta(
            request_id=get_request_id(),
            errors=errors,
        )

        body = APIResponseModel(
            success=False,
            status="error",
            code=code,
            message=message,
            data=None,
            meta=meta,
        )

        response = JSONResponse(
            status_code=code,
            content=jsonable_encoder(body),
        )

        if meta.request_id:
            response.headers["X-Request-ID"] = meta.request_id

        return response
