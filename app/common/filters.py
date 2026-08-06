"""
File: app/common/filters.py

Allow-listed SQLAlchemy filtering and search helpers.

These functions support MySQL, Microsoft SQL Server, PostgreSQL, and compatible
SQLAlchemy test databases. They only operate on explicitly supplied columns and
never convert arbitrary client field names into SQL expressions.

Repositories remain responsible for defining their public filter-to-column
allow-lists.
"""

from __future__ import annotations

from collections.abc import (
    Mapping,
    Sequence,
)
from datetime import (
    date,
    datetime,
)
from typing import Any

from sqlalchemy import (
    Select,
    and_,
    false,
    or_,
    true,
)
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.common.exceptions import ValidationError


type SQLFilterColumn = (
    ColumnElement[Any]
    | InstrumentedAttribute[Any]
)

type SQLSelect = Select[Any]


_TRUE_STRINGS = frozenset(
    {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }
)

_FALSE_STRINGS = frozenset(
    {
        "0",
        "false",
        "no",
        "n",
        "off",
    }
)


def normalize_boolean(
    value: Any,
) -> bool | None:
    """
    Convert explicit boolean representations without using truthiness.

    Args:
        value: Raw boolean-like value.

    Returns:
        Normalized boolean or ``None`` when the input is ``None``.

    Raises:
        ValidationError: If the value cannot be safely interpreted.
    """

    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, int) and value in {0, 1}:
        return bool(value)

    if isinstance(value, bytes):
        if value == b"\x01":
            return True

        if value == b"\x00":
            return False

    if isinstance(value, str):
        normalized = value.strip().casefold()

        if normalized in _TRUE_STRINGS:
            return True

        if normalized in _FALSE_STRINGS:
            return False

    raise ValidationError(
        message="Invalid boolean value.",
        details={
            "valueType": type(value).__name__,
        },
    )


def build_true_condition(
    column: SQLFilterColumn,
) -> ColumnElement[bool]:
    """
    Build a cross-dialect true comparison.

    Args:
        column: Boolean-compatible SQLAlchemy column.

    Returns:
        SQLAlchemy boolean expression.
    """

    return column == true()


def build_false_condition(
    column: SQLFilterColumn,
    *,
    include_null: bool = False,
) -> ColumnElement[bool]:
    """
    Build a false comparison, optionally treating SQL NULL as false.

    Args:
        column: Boolean-compatible SQLAlchemy column.
        include_null: Whether NULL values should also match.

    Returns:
        SQLAlchemy boolean expression.
    """

    condition = column == false()

    if include_null:
        return or_(
            condition,
            column.is_(None),
        )

    return condition


def apply_text_search(
    statement: SQLSelect,
    *,
    search: str | None,
    columns: Sequence[SQLFilterColumn],
    min_length: int = 2,
    max_length: int = 128,
) -> SQLSelect:
    """
    Apply an escaped, case-insensitive contains search.

    Args:
        statement: Base SQLAlchemy select statement.
        search: Optional user-provided search term.
        columns: Explicitly allow-listed searchable columns.
        min_length: Minimum accepted normalized search length.
        max_length: Maximum accepted normalized search length.

    Returns:
        Updated or unchanged statement.

    Raises:
        ValueError: If length configuration is invalid.
        ValidationError: If the search length is outside the allowed range.
    """

    _validate_length_bounds(
        min_length=min_length,
        max_length=max_length,
    )

    normalized = _normalize_search_value(search)

    if normalized is None:
        return statement

    _validate_search_length(
        value=normalized,
        min_length=min_length,
        max_length=max_length,
    )

    escaped = _escape_like(normalized)

    conditions = [
        column.ilike(
            f"%{escaped}%",
            escape="\\",
        )
        for column in columns
    ]

    if not conditions:
        return statement

    return statement.where(
        or_(*conditions)
    )


def apply_prefix_search(
    statement: SQLSelect,
    *,
    search: str | None,
    columns: Sequence[SQLFilterColumn],
    min_length: int = 1,
    max_length: int = 128,
) -> SQLSelect:
    """
    Apply an escaped, case-insensitive prefix search.

    Prefix search is generally more index-friendly than contains search and is
    appropriate for autosuggest-style endpoints.

    Args:
        statement: Base SQLAlchemy select statement.
        search: Optional user-provided prefix.
        columns: Explicitly allow-listed searchable columns.
        min_length: Minimum accepted normalized search length.
        max_length: Maximum accepted normalized search length.

    Returns:
        Updated or unchanged statement.

    Raises:
        ValueError: If length configuration is invalid.
        ValidationError: If the search length is outside the allowed range.
    """

    _validate_length_bounds(
        min_length=min_length,
        max_length=max_length,
    )

    normalized = _normalize_search_value(search)

    if normalized is None:
        return statement

    _validate_search_length(
        value=normalized,
        min_length=min_length,
        max_length=max_length,
    )

    escaped = _escape_like(normalized)

    conditions = [
        column.ilike(
            f"{escaped}%",
            escape="\\",
        )
        for column in columns
    ]

    if not conditions:
        return statement

    return statement.where(
        or_(*conditions)
    )


def apply_exact_filter(
    statement: SQLSelect,
    *,
    column: SQLFilterColumn,
    value: Any,
) -> SQLSelect:
    """
    Apply equality filtering when a value is present.

    Args:
        statement: Base SQLAlchemy select statement.
        column: Explicitly selected database column.
        value: Value to compare.

    Returns:
        Updated or unchanged statement.
    """

    if value is None:
        return statement

    return statement.where(
        column == value
    )


def apply_boolean_filter(
    statement: SQLSelect,
    *,
    column: SQLFilterColumn,
    value: Any,
    include_null_as_false: bool = False,
) -> SQLSelect:
    """
    Normalize and apply a boolean filter.

    Args:
        statement: Base SQLAlchemy select statement.
        column: Boolean-compatible database column.
        value: Raw boolean-like value.
        include_null_as_false: Whether NULL should match a false filter.

    Returns:
        Updated or unchanged statement.

    Raises:
        ValidationError: If the value is not a supported boolean.
    """

    normalized = normalize_boolean(value)

    if normalized is None:
        return statement

    condition = (
        build_true_condition(column)
        if normalized
        else build_false_condition(
            column,
            include_null=include_null_as_false,
        )
    )

    return statement.where(condition)


def apply_in_filter(
    statement: SQLSelect,
    *,
    column: SQLFilterColumn,
    values: Sequence[Any] | None,
    max_values: int = 100,
) -> SQLSelect:
    """
    Apply a bounded SQL IN predicate.

    Args:
        statement: Base SQLAlchemy select statement.
        column: Explicitly selected database column.
        values: Values accepted by the filter.
        max_values: Maximum number of accepted values.

    Returns:
        Updated or unchanged statement.

    Raises:
        ValueError: If ``max_values`` is invalid.
        ValidationError: If too many values are supplied.
    """

    if max_values < 1:
        raise ValueError(
            "max_values must be greater than zero"
        )

    if not values:
        return statement

    if len(values) > max_values:
        raise ValidationError(
            message=(
                "Too many values were supplied for a filter."
            ),
            details={
                "maxValues": max_values,
            },
        )

    return statement.where(
        column.in_(list(values))
    )


def apply_date_range_filter(
    statement: SQLSelect,
    *,
    column: SQLFilterColumn,
    start_date: date | datetime | None = None,
    end_date: date | datetime | None = None,
) -> SQLSelect:
    """
    Apply inclusive date or datetime bounds.

    Args:
        statement: Base SQLAlchemy select statement.
        column: Date or datetime database column.
        start_date: Optional inclusive lower bound.
        end_date: Optional inclusive upper bound.

    Returns:
        Updated statement.

    Raises:
        ValidationError: If the lower bound is after the upper bound.
    """

    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        raise ValidationError(
            message=(
                "The start date must not be after the end date."
            )
        )

    if start_date is not None:
        statement = statement.where(
            column >= start_date
        )

    if end_date is not None:
        statement = statement.where(
            column <= end_date
        )

    return statement


def apply_dynamic_filters(
    statement: SQLSelect,
    *,
    filters: Mapping[str, Any] | None,
    allowed_filters: Mapping[
        str,
        SQLFilterColumn,
    ],
    boolean_fields: set[str] | None = None,
    max_in_values: int = 100,
    strict: bool = True,
) -> SQLSelect:
    """
    Apply allow-listed exact, boolean, and bounded-list filters.

    Args:
        statement: Base SQLAlchemy select statement.
        filters: Public filter-field mapping.
        allowed_filters: Public field-to-column allow-list.
        boolean_fields: Fields requiring boolean normalization.
        max_in_values: Maximum accepted values for list filters.
        strict: Reject unsupported fields when ``True``.

    Returns:
        Updated or unchanged statement.

    Raises:
        ValueError: If ``max_in_values`` is invalid.
        ValidationError: If a field or value is unsupported.
    """

    if max_in_values < 1:
        raise ValueError(
            "max_in_values must be greater than zero"
        )

    if not filters:
        return statement

    normalized_boolean_fields = (
        boolean_fields
        or set()
    )

    conditions: list[ColumnElement[bool]] = []

    for field, value in filters.items():
        column = allowed_filters.get(field)

        if column is None:
            if strict:
                raise ValidationError(
                    message="Unsupported filter field.",
                    details={
                        "field": field,
                        "allowedFields": sorted(
                            allowed_filters
                        ),
                    },
                )

            continue

        if value is None:
            continue

        if field in normalized_boolean_fields:
            normalized_boolean = normalize_boolean(
                value
            )

            if normalized_boolean is None:
                continue

            conditions.append(
                build_true_condition(column)
                if normalized_boolean
                else build_false_condition(column)
            )

            continue

        if isinstance(value, Sequence) and not isinstance(
            value,
            (
                str,
                bytes,
                bytearray,
            ),
        ):
            if not value:
                continue

            if len(value) > max_in_values:
                raise ValidationError(
                    message=(
                        "Too many values were supplied for a filter."
                    ),
                    details={
                        "field": field,
                        "maxValues": max_in_values,
                    },
                )

            conditions.append(
                column.in_(list(value))
            )

            continue

        conditions.append(
            column == value
        )

    if not conditions:
        return statement

    return statement.where(
        and_(*conditions)
    )


def _normalize_search_value(
    value: str | None,
) -> str | None:
    """Normalize an optional search value."""

    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def _validate_length_bounds(
    *,
    min_length: int,
    max_length: int,
) -> None:
    """Validate reusable search-length configuration."""

    if min_length < 1:
        raise ValueError(
            "min_length must be greater than zero"
        )

    if max_length < min_length:
        raise ValueError(
            "max_length must be greater than or equal to min_length"
        )


def _validate_search_length(
    *,
    value: str,
    min_length: int,
    max_length: int,
) -> None:
    """Validate a normalized search term."""

    if not min_length <= len(value) <= max_length:
        raise ValidationError(
            message=(
                "Search length is outside the allowed range."
            ),
            details={
                "minLength": min_length,
                "maxLength": max_length,
            },
        )


def _escape_like(
    value: str,
) -> str:
    """
    Escape SQL LIKE wildcard characters.

    Args:
        value: User-provided search value.

    Returns:
        Escaped SQL LIKE value.
    """

    return (
        value
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


__all__ = [
    "SQLFilterColumn",
    "SQLSelect",
    "apply_boolean_filter",
    "apply_date_range_filter",
    "apply_dynamic_filters",
    "apply_exact_filter",
    "apply_in_filter",
    "apply_prefix_search",
    "apply_text_search",
    "build_false_condition",
    "build_true_condition",
    "normalize_boolean",
]
