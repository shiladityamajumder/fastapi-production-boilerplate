"""File: app/common/sorting.py.

Allow-listed SQLAlchemy sorting helpers.

Client-provided sort fields are resolved only through explicit repository
allow-lists. Raw field names, SQL fragments, and arbitrary column expressions
must never be passed directly from request input.
"""

from __future__ import annotations

from collections.abc import (  # noqa: TC003
    Mapping,
    Sequence,
)
from enum import StrEnum
from typing import Any

from sqlalchemy import Select
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import (
    ColumnElement,
    UnaryExpression,
)

from app.common.exceptions import ValidationError

type SQLColumn = (
    ColumnElement[Any]
    | InstrumentedAttribute[Any]
)

type SQLOrderExpression = UnaryExpression[Any]
type SQLSelect = Select[Any]


class SortOrder(StrEnum):
    """Supported client-visible sorting directions."""

    ASC = "asc"
    DESC = "desc"


def normalize_sort_order(
    value: str | SortOrder | None,
) -> SortOrder:
    """Normalize and validate a sorting direction.

    Args:
        value: Raw direction or an existing ``SortOrder``.

    Returns:
        Normalized sort direction. Missing values default to ascending.

    Raises:
        ValidationError: If the direction is unsupported.
    """
    if value is None:
        return SortOrder.ASC

    if isinstance(value, SortOrder):
        return value

    normalized = value.strip().casefold()

    try:
        return SortOrder(normalized)
    except ValueError as exc:
        raise ValidationError(
            message="Unsupported sort direction.",
            details={
                "value": value,
                "allowedValues": [
                    item.value
                    for item in SortOrder
                ],
            },
        ) from exc


def build_order_expression(
    *,
    column: SQLColumn,
    sort_order: str | SortOrder = SortOrder.ASC,
) -> SQLOrderExpression:
    """Build an ascending or descending SQLAlchemy expression.

    Args:
        column: Allow-listed SQLAlchemy column or expression.
        sort_order: Requested direction.

    Returns:
        SQLAlchemy order expression.
    """
    normalized_order = normalize_sort_order(
        sort_order
    )

    if normalized_order is SortOrder.DESC:
        return column.desc()

    return column.asc()


def apply_sorting(
    statement: SQLSelect,
    *,
    sort_by: str | None,
    sort_order: str | SortOrder = SortOrder.ASC,
    allowed_fields: Mapping[str, SQLColumn],
    strict: bool = True,
) -> SQLSelect:
    """Apply one allow-listed sorting field.

    Args:
        statement: Base SQLAlchemy select statement.
        sort_by: Public client-visible field name.
        sort_order: Requested sorting direction.
        allowed_fields: Public field-to-column allow-list.
        strict: Reject unsupported fields when ``True``.

    Returns:
        Updated or unchanged SQLAlchemy statement.

    Raises:
        ValidationError: If the field or direction is unsupported.
    """
    normalized_field = _normalize_sort_field(
        sort_by
    )

    if normalized_field is None:
        return statement

    column = allowed_fields.get(
        normalized_field
    )

    if column is None:
        if strict:
            raise ValidationError(
                message="Unsupported sort field.",
                details={
                    "field": normalized_field,
                    "allowedFields": sorted(
                        allowed_fields
                    ),
                },
            )

        return statement

    return statement.order_by(
        build_order_expression(
            column=column,
            sort_order=sort_order,
        )
    )


def apply_multi_sorting(
    statement: SQLSelect,
    *,
    sorting: Sequence[
        tuple[str, str | SortOrder]
    ]
    | None,
    allowed_fields: Mapping[str, SQLColumn],
    strict: bool = True,
) -> SQLSelect:
    """Apply ordered, allow-listed multi-column sorting.

    Duplicate public fields are ignored after their first occurrence to avoid
    conflicting order expressions.

    Args:
        statement: Base SQLAlchemy select statement.
        sorting: Ordered field and direction pairs.
        allowed_fields: Public field-to-column allow-list.
        strict: Reject unsupported fields when ``True``.

    Returns:
        Updated or unchanged SQLAlchemy statement.

    Raises:
        ValidationError: If a field or direction is unsupported.
    """
    if not sorting:
        return statement

    clauses: list[SQLOrderExpression] = []
    seen_fields: set[str] = set()

    for raw_field, direction in sorting:
        field = _normalize_sort_field(
            raw_field
        )

        if (
            field is None
            or field in seen_fields
        ):
            continue

        seen_fields.add(field)

        column = allowed_fields.get(field)

        if column is None:
            if strict:
                raise ValidationError(
                    message="Unsupported sort field.",
                    details={
                        "field": field,
                        "allowedFields": sorted(
                            allowed_fields
                        ),
                    },
                )

            continue

        clauses.append(
            build_order_expression(
                column=column,
                sort_order=direction,
            )
        )

    if not clauses:
        return statement

    return statement.order_by(
        *clauses
    )


def apply_default_sort(
    statement: SQLSelect,
    *,
    default_column: SQLColumn,
    default_order: str | SortOrder = SortOrder.DESC,
) -> SQLSelect:
    """Apply a deterministic default order.

    When the default column is not unique, repositories should add a unique
    secondary sort column to guarantee stable offset pagination.

    Args:
        statement: Base SQLAlchemy select statement.
        default_column: Default SQLAlchemy sorting column.
        default_order: Default direction.

    Returns:
        Statement with the default order applied.
    """
    return statement.order_by(
        build_order_expression(
            column=default_column,
            sort_order=default_order,
        )
    )


def _normalize_sort_field(
    value: str | None,
) -> str | None:
    """Normalize an optional public sorting field.

    Args:
        value: Raw public sorting field.

    Returns:
        Stripped field name or ``None``.
    """
    if value is None:
        return None

    normalized = value.strip()

    return normalized or None


__all__ = [
    "SQLColumn",
    "SQLOrderExpression",
    "SQLSelect",
    "SortOrder",
    "apply_default_sort",
    "apply_multi_sorting",
    "apply_sorting",
    "build_order_expression",
    "normalize_sort_order",
]
