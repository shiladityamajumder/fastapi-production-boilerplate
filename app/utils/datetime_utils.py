"""File: app/utils/datetime_utils.py.

Timezone-aware date and time utilities.

UTC is the canonical timezone for:

- database persistence,
- audit timestamps,
- events,
- Celery task payloads,
- cache expiration,
- communication between microservices.

The configured application timezone is intended for:

- user-facing responses,
- reports,
- email content,
- operational displays,
- business-day calculations.

All conversion helpers reject timezone-naive datetime values because a naive
datetime cannot be converted reliably without knowing its original timezone.
"""

from __future__ import annotations

from datetime import (
    UTC,
    date,
    datetime,
    time,
)
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.core.config import get_settings


@lru_cache(maxsize=1)
def application_timezone() -> ZoneInfo:
    """Return the configured application timezone.

    The validated timezone is cached once per process. Tests that replace
    application settings must call ``clear_timezone_cache``.

    Returns:
        Configured IANA timezone.
    """
    return ZoneInfo(get_settings().TIMEZONE)


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime.

    Returns:
        Current UTC datetime.
    """
    return datetime.now(UTC)


def current_datetime() -> datetime:
    """Return the current datetime in the configured application timezone.

    This helper is intended for user-facing or business-local calculations.
    Persistence and distributed-system timestamps should normally use
    ``utc_now``.

    Returns:
        Current application-local datetime.
    """
    return utc_now().astimezone(application_timezone())


def current_date() -> date:
    """Return the current date in the configured application timezone.

    Returns:
        Current application-local date.
    """
    return current_datetime().date()


def require_aware(
    value: datetime,
) -> datetime:
    """Validate that a datetime contains effective timezone information.

    Args:
        value: Datetime to validate.

    Returns:
        Original timezone-aware datetime.

    Raises:
        TypeError: If ``value`` is not a datetime.
        ValueError: If ``value`` is timezone-naive.
    """
    if not isinstance(value, datetime):
        raise TypeError("value must be a datetime")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-naive datetimes are not allowed")

    return value


def to_utc(
    value: datetime,
) -> datetime:
    """Convert a timezone-aware datetime to UTC.

    Args:
        value: Timezone-aware datetime.

    Returns:
        Equivalent timezone-aware UTC datetime.

    Raises:
        TypeError: If ``value`` is not a datetime.
        ValueError: If ``value`` is timezone-naive.
    """
    return require_aware(value).astimezone(UTC)


def to_application_timezone(
    value: datetime,
) -> datetime:
    """Convert a timezone-aware datetime to the application timezone.

    Args:
        value: Timezone-aware datetime.

    Returns:
        Equivalent application-local datetime.

    Raises:
        TypeError: If ``value`` is not a datetime.
        ValueError: If ``value`` is timezone-naive.
    """
    return require_aware(value).astimezone(application_timezone())


def datetime_to_iso(
    value: datetime,
    *,
    use_application_timezone: bool = False,
    use_utc: bool = False,
) -> str:
    """Serialize a timezone-aware datetime as ISO 8601.

    Only one conversion option may be enabled.

    Args:
        value: Timezone-aware datetime.
        use_application_timezone: Convert to the configured application
            timezone before serialization.
        use_utc: Convert to UTC before serialization.

    Returns:
        ISO 8601 datetime string.

    Raises:
        ValueError: If both conversion options are enabled or the datetime is
            timezone-naive.
    """
    if use_application_timezone and use_utc:
        raise ValueError("Only one timezone conversion option may be enabled")

    normalized = require_aware(value)

    if use_application_timezone:
        normalized = to_application_timezone(normalized)
    elif use_utc:
        normalized = to_utc(normalized)

    return normalized.isoformat()


def datetime_to_utc_iso(
    value: datetime,
) -> str:
    """Serialize a timezone-aware datetime as an ISO 8601 UTC value.

    The conventional ``Z`` suffix is used instead of ``+00:00``.

    Args:
        value: Timezone-aware datetime.

    Returns:
        UTC ISO 8601 datetime string.
    """
    return (
        to_utc(value)
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


def parse_iso_datetime(
    value: str,
    *,
    convert_to_utc: bool = False,
    convert_to_application_timezone: bool = False,
) -> datetime:
    """Parse an ISO 8601 datetime containing timezone information.

    Both explicit offsets and the UTC ``Z`` suffix are accepted.

    Args:
        value: ISO 8601 datetime string.
        convert_to_utc: Convert the parsed datetime to UTC.
        convert_to_application_timezone: Convert the parsed datetime to the
            configured application timezone.

    Returns:
        Parsed timezone-aware datetime.

    Raises:
        TypeError: If ``value`` is not a string.
        ValueError: If the value is blank, malformed, timezone-naive, or both
            conversion options are enabled.
    """
    if convert_to_utc and convert_to_application_timezone:
        raise ValueError("Only one timezone conversion option may be enabled")

    if not isinstance(value, str):
        raise TypeError("value must be a string")

    normalized = value.strip()

    if not normalized:
        raise ValueError("Datetime value must not be blank")

    if normalized.endswith(("Z", "z")):
        normalized = f"{normalized[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("Datetime value must use a valid ISO 8601 format") from exc

    parsed = require_aware(parsed)

    if convert_to_utc:
        return to_utc(parsed)

    if convert_to_application_timezone:
        return to_application_timezone(parsed)

    return parsed


def is_expired(
    expiry: datetime,
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether a datetime has expired.

    Both values are normalized to UTC before comparison.

    Args:
        expiry: Timezone-aware expiration datetime.
        now: Optional timezone-aware comparison datetime.

    Returns:
        ``True`` when ``expiry`` is at or before the comparison time.

    Raises:
        TypeError: If either supplied value is not a datetime.
        ValueError: If either supplied value is timezone-naive.
    """
    comparison_time = utc_now() if now is None else require_aware(now)

    return to_utc(expiry) <= to_utc(comparison_time)


def current_date_string() -> str:
    """Return the current application-local date as ISO 8601.

    Returns:
        Date string in ``YYYY-MM-DD`` format.
    """
    return current_date().isoformat()


def current_time_string() -> str:
    """Return the current application-local time with its UTC offset.

    Returns:
        ISO 8601 time string.
    """
    return current_datetime().timetz().isoformat()


def start_of_application_day(
    value: datetime | None = None,
) -> datetime:
    """Return the beginning of an application-local calendar day.

    Args:
        value: Optional timezone-aware datetime. When omitted, the current
            application-local datetime is used.

    Returns:
        Application-local datetime at 00:00:00.

    Raises:
        TypeError: If ``value`` is not a datetime.
        ValueError: If ``value`` is timezone-naive.
    """
    local_value = (
        current_datetime() if value is None else to_application_timezone(value)
    )

    return local_value.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def end_of_application_day(
    value: datetime | None = None,
) -> datetime:
    """Return the end of an application-local calendar day.

    Args:
        value: Optional timezone-aware datetime. When omitted, the current
            application-local datetime is used.

    Returns:
        Application-local datetime at 23:59:59.999999.
    """
    local_value = (
        current_datetime() if value is None else to_application_timezone(value)
    )

    return local_value.replace(
        hour=23,
        minute=59,
        second=59,
        microsecond=999_999,
    )


def combine_application_datetime(
    date_value: date,
    time_value: time,
) -> datetime:
    """Combine a date and time in the configured application timezone.

    A timezone attached to ``time_value`` is ignored deliberately. The result
    always uses the configured application timezone.

    Args:
        date_value: Calendar date.
        time_value: Local wall-clock time.

    Returns:
        Timezone-aware application-local datetime.

    Raises:
        TypeError: If the supplied values have incorrect types.
    """
    if not isinstance(date_value, date):
        raise TypeError("date_value must be a date")

    if not isinstance(time_value, time):
        raise TypeError("time_value must be a time")

    return datetime.combine(
        date_value,
        time_value.replace(tzinfo=None),
        tzinfo=application_timezone(),
    )


def clear_timezone_cache() -> None:
    """Clear the cached application timezone.

    This helper is intended for tests that replace configuration between test
    cases.
    """
    application_timezone.cache_clear()


__all__ = [
    "UTC",
    "application_timezone",
    "clear_timezone_cache",
    "combine_application_datetime",
    "current_date",
    "current_date_string",
    "current_datetime",
    "current_time_string",
    "datetime_to_iso",
    "datetime_to_utc_iso",
    "end_of_application_day",
    "is_expired",
    "parse_iso_datetime",
    "require_aware",
    "start_of_application_day",
    "to_application_timezone",
    "to_utc",
    "utc_now",
]
