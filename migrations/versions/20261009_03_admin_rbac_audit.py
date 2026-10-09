"""Add SUPER_ADMIN, indexed user searches, and immutable audit records.

Revision ID: 20261009_03
Revises: 20261009_02
Create Date: 2026-10-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261009_03"
down_revision = "20261009_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Expand role constraints and add indexed audit storage."""
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('USER', 'ADMIN', 'SUPER_ADMIN')",
    )
    op.create_index(
        "ix_users_role_active_created",
        "users",
        ["role", "is_active", "created_at", "id"],
    )
    op.create_index(
        "ix_users_email_prefix",
        "users",
        ["email"],
        postgresql_ops={"email": "text_pattern_ops"},
    )
    op.create_index(
        "ix_users_username_prefix",
        "users",
        ["username"],
        postgresql_ops={"username": "text_pattern_ops"},
    )
    op.create_index(
        "ix_users_mobile_prefix",
        "users",
        ["mobile_number"],
        postgresql_ops={"mobile_number": "text_pattern_ops"},
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('success', 'failure')", name="ck_audit_logs_outcome"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_actor_time", "audit_logs", ["actor_user_id", "created_at", "id"]
    )
    op.create_index(
        "ix_audit_target_time",
        "audit_logs",
        ["target_type", "target_id", "created_at", "id"],
    )
    op.create_index(
        "ix_audit_action_time", "audit_logs", ["action", "created_at", "id"]
    )


def downgrade() -> None:
    """Remove audit state only if no SUPER_ADMIN assignments remain."""
    bind = op.get_bind()
    count = bind.scalar(
        sa.text("SELECT count(*) FROM users WHERE role = 'SUPER_ADMIN'")
    )
    if count:
        raise RuntimeError(
            "Demote or remove SUPER_ADMIN accounts before downgrading this revision."
        )
    op.drop_index("ix_audit_action_time", table_name="audit_logs")
    op.drop_index("ix_audit_target_time", table_name="audit_logs")
    op.drop_index("ix_audit_actor_time", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_users_mobile_prefix", table_name="users")
    op.drop_index("ix_users_username_prefix", table_name="users")
    op.drop_index("ix_users_email_prefix", table_name="users")
    op.drop_index("ix_users_role_active_created", table_name="users")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role", "users", "role IN ('USER', 'ADMIN')"
    )
