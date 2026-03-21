# File: app/db/base.py
"""
===============================================================================
SQLALCHEMY DECLARATIVE BASE
===============================================================================

Defines the shared SQLAlchemy Declarative Base for all ORM models.

This is the foundational class for the relational data layer.

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

This module belongs strictly to the Infrastructure Layer.

It provides:

    - Centralized SQLAlchemy metadata registry
    - Declarative mapping foundation
    - Single source of truth for ORM model inheritance

It does NOT:

    - Contain business logic
    - Define implicit columns
    - Enforce domain rules
    - Manage database connections
    - Implement repository behavior

-------------------------------------------------------------------------------
BOUNDARY CONTRACT
-------------------------------------------------------------------------------

All SQLAlchemy ORM models MUST inherit from this Base.

Violation of this rule may result in:

    - Missing metadata registration
    - Migration tool inconsistencies
    - Broken schema generation
    - Undetected model definitions

-------------------------------------------------------------------------------
MIGRATION TOOLING IMPLICATION
-------------------------------------------------------------------------------

Because all models share a single DeclarativeBase:

    - Alembic can introspect unified metadata
    - Schema generation remains deterministic
    - Cross-model relationships resolve correctly

-------------------------------------------------------------------------------
DESIGN PRINCIPLES
-------------------------------------------------------------------------------

- Keep base minimal
- Avoid premature abstraction
- Avoid implicit columns
- Avoid automatic timestamps
- Avoid automatic primary keys
- Avoid business-layer coupling

This base should remain intentionally simple.

If cross-cutting model behavior is required,
implement explicit abstract mixins instead.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Root declarative base class for all relational database models.

    ---------------------------------------------------------------------------
    USAGE EXAMPLE
    ---------------------------------------------------------------------------

        from sqlalchemy.orm import Mapped, mapped_column
        from sqlalchemy import String

        class User(Base):
            __tablename__ = "users"

            id: Mapped[int] = mapped_column(primary_key=True)
            email: Mapped[str] = mapped_column(String(255), unique=True)

    ---------------------------------------------------------------------------
    INHERITANCE CONTRACT
    ---------------------------------------------------------------------------

    - Must be the direct or indirect parent of all ORM models.
    - __tablename__ must be explicitly defined in each concrete model.
    - Primary keys must be explicitly defined.

    ---------------------------------------------------------------------------
    EXTENSION GUIDELINES
    ---------------------------------------------------------------------------

    If common fields are required across models:

        - Create abstract mixin classes
        - Mark them with __abstract__ = True
        - Inherit alongside Base

    Example:

        class TimestampMixin:
            __abstract__ = True
            created_at = mapped_column(...)
            updated_at = mapped_column(...)

        class User(Base, TimestampMixin):
            ...

    Avoid modifying Base directly unless absolutely necessary.
    """

    pass


# * =============================================================================
# * FUTURE EXTENSION IDEAS (INTENTIONALLY DISABLED)
# * =============================================================================
# *
# * The following patterns are intentionally NOT enabled by default.
# *
# * Rationale:
# *     Implicit behavior creates hidden coupling and migration complexity.
# *
# * Example pattern (not active):
# *
# * from sqlalchemy import Column
# * from sqlalchemy.types import BigInteger, DateTime
# * from datetime import datetime
# *
# * class BaseWithTimestamps(Base):
# *     __abstract__ = True
# *     id = Column(BigInteger, primary_key=True, autoincrement=True)
# *     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
# *     updated_at = Column(
# *         DateTime,
# *         default=datetime.utcnow,
# *         onupdate=datetime.utcnow,
# *         nullable=False,
# *     )
# *
# * If enabling such patterns:
# *     - Evaluate migration implications
# *     - Ensure explicit opt-in
# *     - Avoid automatic schema mutation