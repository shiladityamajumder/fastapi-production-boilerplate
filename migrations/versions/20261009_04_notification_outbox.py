"""Add encrypted notification outbox for background delivery.

Revision ID: 20261009_04
Revises: 20261009_03
Create Date: 2026-10-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261009_04"
down_revision = "20261009_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create indexed, encrypted notification job storage."""
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="pending", nullable=False
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_notification_outbox_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_notification_outbox_idempotency_key"),
    )
    op.create_index(
        "ix_notification_outbox_due",
        "notification_outbox",
        ["status", "available_at", "created_at"],
    )
    op.create_index(
        "ix_notification_outbox_lease",
        "notification_outbox",
        ["status", "locked_at"],
    )
    op.create_index("ix_auth_otp_expiry", "auth_otp_challenges", ["expires_at"])
    op.create_index("ix_auth_action_expiry", "auth_one_time_tokens", ["expires_at"])
    op.create_index("ix_auth_refresh_expiry", "auth_refresh_sessions", ["expires_at"])


def downgrade() -> None:
    """Drop notification jobs after background dispatch has been stopped."""
    op.drop_index("ix_auth_refresh_expiry", table_name="auth_refresh_sessions")
    op.drop_index("ix_auth_action_expiry", table_name="auth_one_time_tokens")
    op.drop_index("ix_auth_otp_expiry", table_name="auth_otp_challenges")
    op.drop_index("ix_notification_outbox_lease", table_name="notification_outbox")
    op.drop_index("ix_notification_outbox_due", table_name="notification_outbox")
    op.drop_table("notification_outbox")
