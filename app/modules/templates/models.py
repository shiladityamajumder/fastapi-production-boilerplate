# File: app/modules/templates/models.py
"""
===============================================================================
TEMPLATE ORM MODEL
===============================================================================

Defines the SQLAlchemy ORM model for the Template entity.

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

This module belongs to the **persistence layer**.

Responsibilities:

    • define database table structure
    • map database rows to Python objects
    • define indexes and constraints

This module MUST NOT:

    ✘ contain business logic
    ✘ access repositories
    ✘ call services
    ✘ depend on FastAPI

Business logic belongs in:

    service.py

Database queries belong in:

    repository.py

-------------------------------------------------------------------------------
DESIGN PRINCIPLES
-------------------------------------------------------------------------------

Models should remain:

    • thin
    • declarative
    • persistence-focused

-------------------------------------------------------------------------------
SQLALCHEMY VERSION
-------------------------------------------------------------------------------

Uses SQLAlchemy 2.0 style with:

    Mapped[]
    mapped_column()

This provides:

    • type safety
    • IDE support
    • modern SQLAlchemy compatibility
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

from .constants import (
    TemplateTable,
    TemplateStatus,
    NAME_MAX_LENGTH,
    DESCRIPTION_MAX_LENGTH,
)


# =============================================================================
# TEMPLATE MODEL
# =============================================================================


class Template(Base):
    """
    Template ORM model.

    Represents reusable content templates within the system.

    Examples:

        • email templates
        • notification templates
        • message templates

    Each template has:

        - unique identifier
        - name
        - optional description
        - lifecycle status
        - timestamps
    """

    __tablename__ = TemplateTable.NAME

    # -------------------------------------------------------------------------
    # PRIMARY KEY
    # -------------------------------------------------------------------------

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
        autoincrement=True,
        comment="Primary key identifier",
    )

    # -------------------------------------------------------------------------
    # CORE FIELDS
    # -------------------------------------------------------------------------

    name: Mapped[str] = mapped_column(
        String(NAME_MAX_LENGTH),
        nullable=False,
        index=True,
        comment="Human-readable template name",
    )

    description: Mapped[str | None] = mapped_column(
        String(DESCRIPTION_MAX_LENGTH),
        nullable=True,
        comment="Optional description of the template",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TemplateStatus.ACTIVE.value,
        index=True,
        comment="Lifecycle status of the template",
    )

    # -------------------------------------------------------------------------
    # AUDIT FIELDS
    # -------------------------------------------------------------------------

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        comment="Timestamp when template was created",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Timestamp when template was last updated",
    )

    # -------------------------------------------------------------------------
    # TABLE INDEXES
    # -------------------------------------------------------------------------

    __table_args__ = (
        Index(
            "idx_template_name_status",
            "name",
            "status",
        ),
    )

    # -------------------------------------------------------------------------
    # REPRESENTATION
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<Template(id={self.id}, "
            f"name='{self.name}', "
            f"status='{self.status}')>"
        )


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "Template",
]
