"""
File: app/db/base.py

Shared SQLAlchemy declarative metadata root.

All relational ORM models in this service must inherit from ``Base`` so they
share one consistent SQLAlchemy metadata registry.

Database migrations are managed by the dedicated database migration project.
This service maps existing tables and must not create or modify schemas during
application startup.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Base class for all relational SQLAlchemy ORM mappings.

    This class intentionally contains no automatic table creation, migration,
    or database-specific behavior.
    """


__all__ = [
    "Base",
]