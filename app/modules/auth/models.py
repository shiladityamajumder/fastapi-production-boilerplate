"""Persistent account and authentication state."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum
from uuid import UUID, uuid4  # noqa: TC003

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(StrEnum):
    """Authorization roles available to accounts."""

    USER = "USER"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


class User(Base):
    """Application identity with normalized unique login identifiers."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "email IS NOT NULL OR username IS NOT NULL OR mobile_number IS NOT NULL",
            name="ck_users_has_identifier",
        ),
        CheckConstraint(
            "password_hash IS NULL OR length(password_hash) > 0",
            name="ck_users_password_hash_nonempty",
        ),
        CheckConstraint(
            "role IN ('USER', 'ADMIN', 'SUPER_ADMIN')", name="ck_users_role"
        ),
        CheckConstraint(
            "email IS NULL OR email = lower(email)",
            name="ck_users_email_normalized",
        ),
        CheckConstraint(
            "username IS NULL OR username = lower(username)",
            name="ck_users_username_normalized",
        ),
        CheckConstraint(
            "mobile_number IS NULL OR mobile_number ~ '^\\+[1-9][0-9]{7,14}$'",
            name="ck_users_mobile_e164",
        ),
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("mobile_number", name="uq_users_mobile_number"),
        Index(
            "ix_users_role_active_created",
            "role",
            "is_active",
            "created_at",
            "id",
        ),
        Index(
            "ix_users_email_prefix",
            "email",
            postgresql_ops={"email": "text_pattern_ops"},
        ),
        Index(
            "ix_users_username_prefix",
            "username",
            postgresql_ops={"username": "text_pattern_ops"},
        ),
        Index(
            "ix_users_mobile_prefix",
            "mobile_number",
            postgresql_ops={"mobile_number": "text_pattern_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str | None] = mapped_column(String(254))
    username: Mapped[str | None] = mapped_column(String(32))
    mobile_number: Mapped[str | None] = mapped_column(
        String(16)
    )
    password_hash: Mapped[str | None] = mapped_column(String(512))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=16),
        default=UserRole.USER,
        server_default=UserRole.USER.value,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    token_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    profile_image_reference: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class RefreshSession(Base):
    """Hashed, rotating refresh token family state."""

    __tablename__ = "auth_refresh_sessions"
    __table_args__ = (
        Index("ix_auth_refresh_user_active", "user_id", "revoked_at"),
        Index("ix_auth_refresh_family", "family_id"),
        Index("ix_auth_refresh_expiry", "expires_at"),
        UniqueConstraint("token_hash", name="uq_auth_refresh_sessions_token_hash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    family_id: Mapped[UUID] = mapped_column(Uuid, default=uuid4, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("auth_refresh_sessions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OneTimeToken(Base):
    """Hashed email verification and password reset token state."""

    __tablename__ = "auth_one_time_tokens"
    __table_args__ = (
        Index("ix_auth_action_user_kind", "user_id", "purpose", "expires_at"),
        Index("ix_auth_action_expiry", "expires_at"),
        UniqueConstraint("token_hash", name="uq_auth_one_time_tokens_token_hash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OTPChallenge(Base):
    """Hashed, one-time mobile login challenges with bounded attempts."""

    __tablename__ = "auth_otp_challenges"
    __table_args__ = (
        Index("ix_auth_otp_mobile_created", "mobile_number", "created_at"),
        Index("ix_auth_otp_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    mobile_number: Mapped[str] = mapped_column(String(16), nullable=False)
    purpose: Mapped[str] = mapped_column(
        String(24), default="login", server_default="login", nullable=False
    )
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuthRateLimit(Base):
    """PostgreSQL-backed fixed-window counters shared across API processes."""

    __tablename__ = "auth_rate_limits"
    __table_args__ = (Index("ix_auth_rate_limits_window", "window_started_at"),)

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    hits: Mapped[int] = mapped_column(Integer, nullable=False)


class StoredFile(Base):
    """Owner-scoped S3 object metadata and upload completion state."""

    __tablename__ = "stored_files"
    __table_args__ = (
        UniqueConstraint("object_key", name="uq_stored_files_object_key"),
        Index("ix_stored_files_owner_status", "owner_user_id", "is_complete"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    expected_size: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_size: Mapped[int | None] = mapped_column(Integer)
    etag: Mapped[str | None] = mapped_column(String(128))
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    """Append-only record of security-sensitive actions and outcomes."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('success', 'failure')", name="ck_audit_logs_outcome"
        ),
        Index("ix_audit_actor_time", "actor_user_id", "created_at", "id"),
        Index("ix_audit_target_time", "target_type", "target_id", "created_at", "id"),
        Index("ix_audit_action_time", "action", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(128))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    safe_metadata: Mapped[dict[str, str | int | bool | None]] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NotificationOutbox(Base):
    """Encrypted transactional notification jobs awaiting delivery."""

    __tablename__ = "notification_outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_notification_outbox_status",
        ),
        Index("ix_notification_outbox_due", "status", "available_at", "created_at"),
        Index("ix_notification_outbox_lease", "status", "locked_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    payload_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending", nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, server_default="5", nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_id: Mapped[str | None] = mapped_column(String(128))
    last_error: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = [
    "AuditLog",
    "NotificationOutbox",
    "AuthRateLimit",
    "OTPChallenge",
    "OneTimeToken",
    "RefreshSession",
    "StoredFile",
    "User",
    "UserRole",
]
