"""File: app/db/sqlalchemy_types.py.

Cross-dialect UTC datetime type and audit-column factories.

MySQL and Microsoft SQL Server datetime columns commonly return timezone-naive
values. To provide predictable behavior across MySQL, SQL Server, PostgreSQL,
and SQLite-based tests, this module uses the following policy:

- application values must be timezone-aware,
- values are converted to UTC before persistence,
- timezone information is removed at the database boundary,
- values read from the database are restored as timezone-aware UTC.

Application layers may convert UTC values to the configured presentation
timezone when formatting responses, reports, or notifications.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.engine.interfaces import Dialect  # noqa: TC002
from sqlalchemy.orm import (
    MappedColumn,
    mapped_column,
)
from sqlalchemy.types import (
    TypeDecorator,
    TypeEngine,
)

from app.utils.datetime_utils import (
    UTC,
    to_utc,
    utc_now,
)


class UTCDateTime(TypeDecorator[datetime]):
    """Persist timezone-aware datetimes as naive UTC.

    Values returned by database drivers are restored as timezone-aware UTC
    datetimes.
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(
        self,
        dialect: Dialect,
    ) -> TypeEngine[datetime]:
        """Return the datetime type used for the active SQL dialect.

        A timezone-naive database type is used deliberately so all supported
        relational databases follow the same persistence contract.

        Args:
            dialect: Active SQLAlchemy database dialect.

        Returns:
            Dialect-specific SQLAlchemy datetime type.
        """
        return dialect.type_descriptor(
            DateTime(timezone=False),
        )

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: Dialect,
    ) -> datetime | None:
        """Normalize a timezone-aware value to naive UTC for persistence.

        Args:
            value: Optional timezone-aware datetime.
            dialect: Active SQLAlchemy database dialect.

        Returns:
            Naive UTC datetime or ``None``.

        Raises:
            ValueError: If the datetime is timezone-naive.
        """
        _ = dialect

        if value is None:
            return None

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "UTCDateTime requires a timezone-aware datetime",
            )

        return to_utc(value).replace(
            tzinfo=None,
        )

    def process_result_value(
        self,
        value: datetime | None,
        dialect: Dialect,
    ) -> datetime | None:
        """Restore a database datetime as timezone-aware UTC.

        Args:
            value: Optional datetime returned by the database driver.
            dialect: Active SQLAlchemy database dialect.

        Returns:
            Timezone-aware UTC datetime or ``None``.
        """
        _ = dialect

        if value is None:
            return None

        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(
                tzinfo=UTC,
            )

        return to_utc(value)

    @property
    def python_type(self) -> type[datetime]:
        """Return the Python type represented by this SQLAlchemy type."""
        return datetime


def created_at_column(
    db_column_name: str | None = None,
) -> MappedColumn[datetime]:
    """Create a non-null creation timestamp column.

    The default is generated in timezone-aware UTC and normalized by
    ``UTCDateTime`` before persistence.

    Args:
        db_column_name: Optional physical database column name.

    Returns:
        Configured SQLAlchemy mapped column.
    """
    return mapped_column(
        db_column_name,
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )


def updated_at_column(
    db_column_name: str | None = None,
) -> MappedColumn[datetime]:
    """Create a non-null last-updated timestamp column.

    The value is generated during inserts and ORM-managed updates.

    Args:
        db_column_name: Optional physical database column name.

    Returns:
        Configured SQLAlchemy mapped column.
    """
    return mapped_column(
        db_column_name,
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


__all__ = [
    "UTCDateTime",
    "created_at_column",
    "updated_at_column",
]
