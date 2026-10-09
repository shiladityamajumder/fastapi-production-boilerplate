"""Create user identity and authentication state tables.

Revision ID: 20261009_01
Revises:
Create Date: 2026-10-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261009_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create normalized user, credential, challenge, and throttle tables."""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("username", sa.String(length=32), nullable=True),
        sa.Column("mobile_number", sa.String(length=16), nullable=True),
        sa.Column("password_hash", sa.String(length=512), nullable=True),
        sa.Column("role", sa.String(length=16), server_default="USER", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("profile_image_reference", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "email IS NOT NULL OR username IS NOT NULL OR mobile_number IS NOT NULL",
            name="ck_users_has_identifier",
        ),
        sa.CheckConstraint(
            "password_hash IS NULL OR length(password_hash) > 0",
            name="ck_users_password_hash_nonempty",
        ),
        sa.CheckConstraint("role IN ('USER', 'ADMIN')", name="ck_users_role"),
        sa.CheckConstraint("email IS NULL OR email = lower(email)", name="ck_users_email_normalized"),
        sa.CheckConstraint("username IS NULL OR username = lower(username)", name="ck_users_username_normalized"),
        sa.CheckConstraint(
            "mobile_number IS NULL OR mobile_number ~ '^\\+[1-9][0-9]{7,14}$'",
            name="ck_users_mobile_e164",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("mobile_number", name="uq_users_mobile_number"),
    )
    op.create_table(
        "auth_refresh_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["replaced_by_id"], ["auth_refresh_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_auth_refresh_sessions_token_hash"),
    )
    op.create_index("ix_auth_refresh_user_active", "auth_refresh_sessions", ["user_id", "revoked_at"])
    op.create_index("ix_auth_refresh_family", "auth_refresh_sessions", ["family_id"])
    op.create_table(
        "auth_one_time_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_auth_one_time_tokens_token_hash"),
    )
    op.create_index("ix_auth_action_user_kind", "auth_one_time_tokens", ["user_id", "purpose", "expires_at"])
    op.create_table(
        "auth_otp_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mobile_number", sa.String(length=16), nullable=False),
        sa.Column("purpose", sa.String(length=24), server_default="login", nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_otp_mobile_created", "auth_otp_challenges", ["mobile_number", "created_at"])
    op.create_table(
        "auth_rate_limits",
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key_hash"),
    )
    op.create_index("ix_auth_rate_limits_window", "auth_rate_limits", ["window_started_at"])


def downgrade() -> None:
    """Drop auth tables in reverse dependency order."""
    op.drop_index("ix_auth_rate_limits_window", table_name="auth_rate_limits")
    op.drop_table("auth_rate_limits")
    op.drop_index("ix_auth_otp_mobile_created", table_name="auth_otp_challenges")
    op.drop_table("auth_otp_challenges")
    op.drop_index("ix_auth_action_user_kind", table_name="auth_one_time_tokens")
    op.drop_table("auth_one_time_tokens")
    op.drop_index("ix_auth_refresh_family", table_name="auth_refresh_sessions")
    op.drop_index("ix_auth_refresh_user_active", table_name="auth_refresh_sessions")
    op.drop_table("auth_refresh_sessions")
    op.drop_table("users")
