"""Track owner-scoped S3 upload metadata.

Revision ID: 20261009_02
Revises: 20261009_01
Create Date: 2026-10-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261009_02"
down_revision = "20261009_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add upload records so objects are visible only after verification."""
    op.create_table(
        "stored_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("expected_size", sa.Integer(), nullable=False),
        sa.Column("actual_size", sa.Integer(), nullable=True),
        sa.Column("etag", sa.String(length=128), nullable=True),
        sa.Column(
            "is_complete", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key", name="uq_stored_files_object_key"),
    )
    op.create_index(
        "ix_stored_files_owner_status",
        "stored_files",
        ["owner_user_id", "is_complete"],
    )


def downgrade() -> None:
    """Remove stored file tracking."""
    op.drop_index("ix_stored_files_owner_status", table_name="stored_files")
    op.drop_table("stored_files")
