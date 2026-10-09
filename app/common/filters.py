"""File: app/common/filters.py.

Allow-listed SQLAlchemy filtering and search helpers.

These functions support PostgreSQL, Microsoft SQL Server, and compatible
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
from datetime import (  # noqa: TC003
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

_BOOLEAN_BYTES = {
    b"\x00": False,
    b"\x01": True,
}


def normalize_boolean(
    value: Any,
) -> bool | None:
    """Convert explicit boolean representations without using truthiness.

    Args:
        value: Raw boolean-like value.

    Returns:
        Normalized boolean or ``None`` when the input is ``None``.

    Raises:
        ValidationError: If the value cannot be safely interpreted.
    """
    if value is None:
        return None

    normalized: bool | None = None

    if isinstance(value, bool):
        normalized = value

    elif isinstance(value, int) and value in {0, 1}:
        normalized = bool(value)

    elif isinstance(value, bytes):
        normalized = _BOOLEAN_BYTES.get(value)

    elif isinstance(value, str):
        normalized_text = value.strip().casefold()

        if normalized_text in _TRUE_STRINGS:
            normalized = True

        elif normalized_text in _FALSE_STRINGS:
            normalized = False

    if normalized is None:
        raise ValidationError(
            message="Invalid boolean value.",
            details={
                "valueType": type(value).__name__,
            },
        )

    return normalized


def build_true_condition(
    column: SQLFilterColumn,
) -> ColumnElement[bool]:
    """Build a cross-dialect true comparison.

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
    """Build a false comparison, optionally treating SQL NULL as false.

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
    """Apply an escaped, case-insensitive contains search.

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

    normalized = _normalize_search_value(
        search,
    )

    if normalized is None:
        return statement

    _validate_search_length(
        value=normalized,
        min_length=min_length,
        max_length=max_length,
    )

    conditions = _build_search_conditions(
        value=normalized,
        columns=columns,
        prefix_only=False,
    )

    if not conditions:
        return statement

    return statement.where(
        or_(*conditions),
    )


def apply_prefix_search(
    statement: SQLSelect,
    *,
    search: str | None,
    columns: Sequence[SQLFilterColumn],
    min_length: int = 1,
    max_length: int = 128,
) -> SQLSelect:
    """Apply an escaped, case-insensitive prefix search.

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

    normalized = _normalize_search_value(
        search,
    )

    if normalized is None:
        return statement

    _validate_search_length(
        value=normalized,
        min_length=min_length,
        max_length=max_length,
    )

    conditions = _build_search_conditions(
        value=normalized,
        columns=columns,
        prefix_only=True,
    )

    if not conditions:
        return statement

    return statement.where(
        or_(*conditions),
    )


def apply_exact_filter(
    statement: SQLSelect,
    *,
    column: SQLFilterColumn,
    value: Any,
) -> SQLSelect:
    """Apply equality filtering when a value is present.

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
        column == value,
    )


def apply_boolean_filter(
    statement: SQLSelect,
    *,
    column: SQLFilterColumn,
    value: Any,
    include_null_as_false: bool = False,
) -> SQLSelect:
    """Normalize and apply a boolean filter.

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
    normalized = normalize_boolean(
        value,
    )

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

    return statement.where(
        condition,
    )


def apply_in_filter(
    statement: SQLSelect,
    *,
    column: SQLFilterColumn,
    values: Sequence[Any] | None,
    max_values: int = 100,
) -> SQLSelect:
    """Apply a bounded SQL IN predicate.

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
    _validate_max_values(
        value=max_values,
        name="max_values",
    )

    if not values:
        return statement

    _validate_value_count(
        values=values,
        max_values=max_values,
    )

    return statement.where(
        column.in_(list(values)),
    )


def apply_date_range_filter(
    statement: SQLSelect,
    *,
    column: SQLFilterColumn,
    start_date: date | datetime | None = None,
    end_date: date | datetime | None = None,
) -> SQLSelect:
    """Apply inclusive date or datetime bounds.

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
            ),
        )

    if start_date is not None:
        statement = statement.where(
            column >= start_date,
        )

    if end_date is not None:
        statement = statement.where(
            column <= end_date,
        )

    return statement


def apply_dynamic_filters(  # noqa: PLR0913
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
    """Apply allow-listed exact, boolean, and bounded-list filters.

    The keyword-only options are intentionally kept separate because each
    controls an independent filtering policy and existing repositories may
    already call this helper using those names.

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
    _validate_max_values(
        value=max_in_values,
        name="max_in_values",
    )

    if not filters:
        return statement

    normalized_boolean_fields = (
        boolean_fields
        if boolean_fields is not None
        else set()
    )

    conditions: list[ColumnElement[bool]] = []

    for field, value in filters.items():
        condition = _build_dynamic_filter_condition(
            field=field,
            value=value,
            allowed_filters=allowed_filters,
            boolean_fields=normalized_boolean_fields,
            max_in_values=max_in_values,
            strict=strict,
        )

        if condition is not None:
            conditions.append(condition)

    if not conditions:
        return statement

    return statement.where(
        and_(*conditions),
    )


def _build_dynamic_filter_condition(  # noqa: PLR0913
    *,
    field: str,
    value: Any,
    allowed_filters: Mapping[
        str,
        SQLFilterColumn,
    ],
    boolean_fields: set[str],
    max_in_values: int,
    strict: bool,
) -> ColumnElement[bool] | None:
    """Build one validated dynamic filter condition.

    Args:
        field: Public filter field.
        value: Filter value.
        allowed_filters: Public field-to-column allow-list.
        boolean_fields: Fields requiring boolean normalization.
        max_in_values: Maximum accepted values for list filters.
        strict: Whether unsupported fields should be rejected.

    Returns:
        SQL expression or ``None`` when the filter should be skipped.

    Raises:
        ValidationError: If the field or value is unsupported.
    """
    column = allowed_filters.get(field)

    if column is None:
        if strict:
            raise ValidationError(
                message="Unsupported filter field.",
                details={
                    "field": field,
                    "allowedFields": sorted(
                        allowed_filters,
                    ),
                },
            )

        return None

    if value is None:
        return None

    if field in boolean_fields:
        return _build_dynamic_boolean_condition(
            column=column,
            value=value,
        )

    if _is_non_text_sequence(value):
        return _build_dynamic_in_condition(
            field=field,
            column=column,
            values=value,
            max_in_values=max_in_values,
        )

    return column == value


def _build_dynamic_boolean_condition(
    *,
    column: SQLFilterColumn,
    value: Any,
) -> ColumnElement[bool] | None:
    """Build one normalized dynamic boolean condition.

    Args:
        column: Boolean-compatible database column.
        value: Raw boolean-like value.

    Returns:
        Boolean expression or ``None``.
    """
    normalized = normalize_boolean(
        value,
    )

    if normalized is None:
        return None

    if normalized:
        return build_true_condition(
            column,
        )

    return build_false_condition(
        column,
    )


def _build_dynamic_in_condition(
    *,
    field: str,
    column: SQLFilterColumn,
    values: Sequence[Any],
    max_in_values: int,
) -> ColumnElement[bool] | None:
    """Build one bounded dynamic IN condition.

    Args:
        field: Public filter field.
        column: Database column.
        values: Filter values.
        max_in_values: Maximum accepted values.

    Returns:
        SQL IN expression or ``None`` for an empty sequence.

    Raises:
        ValidationError: If too many values are supplied.
    """
    if not values:
        return None

    _validate_value_count(
        values=values,
        max_values=max_in_values,
        field=field,
    )

    return column.in_(
        list(values),
    )


def _build_search_conditions(
    *,
    value: str,
    columns: Sequence[SQLFilterColumn],
    prefix_only: bool,
) -> list[ColumnElement[bool]]:
    """Build escaped SQL LIKE conditions for allow-listed columns.

    Args:
        value: Normalized search value.
        columns: Explicitly allow-listed searchable columns.
        prefix_only: Use prefix matching instead of contains matching.

    Returns:
        SQLAlchemy boolean expressions.
    """
    escaped = _escape_like(
        value,
    )

    pattern = (
        f"{escaped}%"
        if prefix_only
        else f"%{escaped}%"
    )

    return [
        column.ilike(
            pattern,
            escape="\\",
        )
        for column in columns
    ]


def _normalize_search_value(
    value: str | None,
) -> str | None:
    """Normalize an optional search value.

    Args:
        value: Optional raw search value.

    Returns:
        Stripped value or ``None``.
    """
    if value is None:
        return None

    normalized = value.strip()

    return normalized or None


def _validate_length_bounds(
    *,
    min_length: int,
    max_length: int,
) -> None:
    """Validate reusable search-length configuration.

    Args:
        min_length: Minimum permitted search length.
        max_length: Maximum permitted search length.

    Raises:
        ValueError: If the bounds are invalid.
    """
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
    """Validate a normalized search term.

    Args:
        value: Normalized search value.
        min_length: Minimum permitted length.
        max_length: Maximum permitted length.

    Raises:
        ValidationError: If the length is outside the allowed range.
    """
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


def _validate_max_values(
    *,
    value: int,
    name: str,
) -> None:
    """Validate a configured maximum list size.

    Args:
        value: Configured maximum.
        name: Configuration argument name.

    Raises:
        ValueError: If the maximum is not positive.
    """
    if value < 1:
        raise ValueError(
            f"{name} must be greater than zero"
        )


def _validate_value_count(
    *,
    values: Sequence[Any],
    max_values: int,
    field: str | None = None,
) -> None:
    """Validate the size of a sequence filter.

    Args:
        values: Values supplied for filtering.
        max_values: Maximum permitted number of values.
        field: Optional public filter field.

    Raises:
        ValidationError: If the sequence exceeds the permitted size.
    """
    if len(values) <= max_values:
        return

    details: dict[str, Any] = {
        "maxValues": max_values,
    }

    if field is not None:
        details["field"] = field

    raise ValidationError(
        message=(
            "Too many values were supplied for a filter."
        ),
        details=details,
    )


def _is_non_text_sequence(
    value: Any,
) -> bool:
    """Return whether a value is a non-text sequence.

    Args:
        value: Value being inspected.

    Returns:
        ``True`` for supported list-like filter values.
    """
    return isinstance(
        value,
        Sequence,
    ) and not isinstance(
        value,
        (
            str,
            bytes,
            bytearray,
        ),
    )


def _escape_like(
    value: str,
) -> str:
    """Escape SQL LIKE wildcard characters.

    Args:
        value: User-provided search value.

    Returns:
        Escaped SQL LIKE value.
    """
    return (
        value.replace(
            "\\",
            "\\\\",
        )
        .replace(
            "%",
            "\\%",
        )
        .replace(
            "_",
            "\\_",
        )
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
