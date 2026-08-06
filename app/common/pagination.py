"""File: app/common/pagination.py.

Typed offset-pagination primitives for SQLAlchemy repositories.

Offset pagination is appropriate for bounded administrative and operational
lists. Endpoints expected to traverse very large datasets should implement
module-specific cursor pagination instead of increasing ``MAX_OFFSET``.

Repositories must apply deterministic ordering before pagination.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)
from sqlalchemy import Select  # noqa: TC002
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.common.response import PaginationMeta

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_OFFSET = 100_000


class PaginationParams(BaseModel):
    """Validated public offset-pagination request parameters.

    Attributes:
        limit: Maximum number of records returned.
        offset: Number of matching records skipped.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    limit: int = Field(
        default=DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
    )

    offset: int = Field(
        default=0,
        ge=0,
        le=MAX_OFFSET,
    )


@dataclass(
    frozen=True,
    slots=True,
)
class PaginationResult[T]:
    """Materialized records and their pagination metadata.

    Attributes:
        items: Records returned for the current page.
        pagination: Metadata included in the API response.
    """

    items: list[T]
    pagination: PaginationMeta


def apply_pagination[T](
    statement: Select[tuple[T]],
    *,
    params: PaginationParams,
) -> Select[tuple[T]]:
    """Apply validated limit and offset values to a query.

    The caller must apply deterministic sorting before pagination.

    Args:
        statement: SQLAlchemy scalar select statement.
        params: Validated pagination parameters.

    Returns:
        Paginated SQLAlchemy statement.
    """
    return statement.limit(
        params.limit,
    ).offset(
        params.offset,
    )


def build_pagination_meta(
    *,
    total_count: int,
    params: PaginationParams,
) -> PaginationMeta:
    """Build public pagination metadata.

    Args:
        total_count: Total number of matching records.
        params: Parameters used by the data query.

    Returns:
        Canonical pagination metadata.

    Raises:
        ValueError: If ``total_count`` is negative.
    """
    if total_count < 0:
        raise ValueError(
            "total_count cannot be negative"
        )

    return PaginationMeta(
        total_count=total_count,
        limit=params.limit,
        offset=params.offset,
        has_next=(
            params.offset + params.limit
        )
        < total_count,
    )


async def paginate_scalars[T](
    *,
    session: AsyncSession,
    data_statement: Select[tuple[T]],
    count_statement: Select[tuple[int]],
    params: PaginationParams,
    unique: bool = False,
) -> PaginationResult[T]:
    """Execute a count query and paginated scalar data query.

    Requiring a caller-supplied count statement avoids incorrect totals caused
    by joins and prevents this helper from generating unexpectedly expensive
    subqueries.

    Args:
        session: Active asynchronous SQLAlchemy session.
        data_statement: Statement selecting one scalar entity or value.
        count_statement: Statement selecting the total matching row count.
        params: Validated pagination parameters.
        unique: Deduplicate scalar ORM results when joined eager loading
            produces repeated entities.

    Returns:
        Materialized page and canonical pagination metadata.
    """
    total_value = await session.scalar(
        count_statement,
    )

    total_count = int(
        total_value or 0
    )

    scalar_result = await session.scalars(
        apply_pagination(
            data_statement,
            params=params,
        )
    )

    if unique:
        scalar_result = scalar_result.unique()

    items: list[T] = list(
        scalar_result.all()
    )

    return PaginationResult(
        items=items,
        pagination=build_pagination_meta(
            total_count=total_count,
            params=params,
        ),
    )


__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "MAX_OFFSET",
    "PaginationParams",
    "PaginationResult",
    "apply_pagination",
    "build_pagination_meta",
    "paginate_scalars",
]
