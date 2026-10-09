"""Validated request and public response schemas for authentication."""

from __future__ import annotations

import re
from datetime import datetime  # noqa: TC003
from typing import Literal, Self  # noqa: TC003
from uuid import UUID  # noqa: TC003

from pydantic import EmailStr, Field, field_validator, model_validator

from app.common.response import APIModel
from app.modules.auth.models import UserRole  # noqa: TC001

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
_E164_RE = re.compile(r"^\+[1-9][0-9]{7,14}$")


class RegisterRequest(APIModel):
    """Public registration input; role is intentionally not accepted."""

    email: EmailStr
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        """Normalize email identifiers for consistent uniqueness checks."""
        return str(value).strip().lower()

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        """Normalize and constrain public usernames."""
        normalized = value.strip().lower()
        if not _USERNAME_RE.fullmatch(normalized):
            raise ValueError("Username must contain 3-32 letters, numbers, dots, dashes, or underscores")
        return normalized


class LoginRequest(APIModel):
    """Password login by normalized email or username."""

    identifier: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        """Normalize password login identifiers."""
        return value.strip().lower()


class OTPRequest(APIModel):
    """Request an OTP for phone login."""

    mobile_number: str

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile_number(cls, value: str) -> str:
        """Require canonical E.164 formatting."""
        normalized = value.strip()
        if not _E164_RE.fullmatch(normalized):
            raise ValueError("Mobile number must use E.164 format")
        return normalized


class OTPVerifyRequest(OTPRequest):
    """Verify a one-time phone challenge."""

    challenge_id: UUID
    code: str = Field(pattern=r"^[0-9]{6}$")


class RefreshRequest(APIModel):
    """Rotating refresh-token input."""

    refresh_token: str = Field(min_length=32, max_length=512)


class TokenPair(APIModel):
    """Access and rotating refresh credentials."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserPublic(APIModel):
    """Safe user representation; excludes password and token state."""

    id: UUID
    email: EmailStr | None
    username: str | None
    mobile_number: str | None
    role: str
    is_active: bool
    is_verified: bool
    profile_image_reference: str | None


class AuthResult(APIModel):
    """Authentication credentials and safe account profile."""

    tokens: TokenPair
    user: UserPublic


class EmailRequest(APIModel):
    """Email address input for verification and recovery requests."""

    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        """Normalize email identifiers for account lookup."""
        return str(value).strip().lower()


class TokenRequest(APIModel):
    """Opaque one-time action token submitted by email link."""

    token: str = Field(min_length=32, max_length=256)


class ResetPasswordRequest(TokenRequest):
    """Password reset token and replacement password."""

    new_password: str = Field(min_length=12, max_length=128)


class ChangePasswordRequest(APIModel):
    """Authenticated password change input."""

    current_password: str | None = Field(default=None, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class ProfileUpdateRequest(APIModel):
    """Self-service editable profile fields."""

    username: str | None = Field(default=None, min_length=3, max_length=32)
    mobile_number: str | None = None

    @model_validator(mode="after")
    def require_update(self) -> Self:
        """Reject empty profile patches."""
        if self.username is None and self.mobile_number is None:
            raise ValueError("At least one profile field is required")
        return self

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str | None) -> str | None:
        """Normalize a changed username."""
        if value is None:
            return None
        normalized = value.strip().lower()
        if not _USERNAME_RE.fullmatch(normalized):
            raise ValueError("Username must contain 3-32 letters, numbers, dots, dashes, or underscores")
        return normalized

    @field_validator("mobile_number")
    @classmethod
    def validate_mobile_number(cls, value: str | None) -> str | None:
        """Validate a changed phone number when present."""
        if value is None:
            return None
        normalized = value.strip()
        if not _E164_RE.fullmatch(normalized):
            raise ValueError("Mobile number must use E.164 format")
        return normalized


class MessageResult(APIModel):
    """Non-sensitive operation acknowledgement."""

    accepted: bool = True


class OTPChallengeResult(MessageResult):
    """Non-secret challenge reference while OTP delivery is pending."""

    challenge_id: UUID
    delivery_status: Literal["pending"] = "pending"


class DeliveryQueuedResult(MessageResult):
    """Non-sensitive acknowledgement for work staged in the outbox."""

    delivery_status: Literal["pending"] = "pending"


class FileUploadRequest(APIModel):
    """Metadata used to create a constrained, owner-scoped S3 upload."""

    category: Literal["profile_image", "file"]
    content_type: str = Field(min_length=3, max_length=128)
    size: int = Field(gt=0, le=52_428_800)


class FileUploadResult(APIModel):
    """Presigned browser upload form and its opaque database identifier."""

    upload_id: UUID
    url: str
    fields: dict[str, str]
    expires_in: int


class FileResult(APIModel):
    """Safe metadata for an owned stored object."""

    id: UUID
    category: str
    content_type: str
    size: int


class FileDownloadResult(APIModel):
    """Short-lived private object download URL."""

    url: str
    expires_in: int


class AdminUserCreateRequest(APIModel):
    """Administrator-created account; elevated roles need super-admin policy."""

    email: EmailStr
    username: str = Field(min_length=3, max_length=32)
    mobile_number: str | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)
    role: UserRole = UserRole.USER

    @field_validator("email")
    @classmethod
    def normalize_admin_email(cls, value: EmailStr) -> str:
        """Normalize admin-created account email."""
        return str(value).strip().lower()

    @field_validator("username")
    @classmethod
    def normalize_admin_username(cls, value: str) -> str:
        """Normalize admin-created account username."""
        normalized = value.strip().lower()
        if not _USERNAME_RE.fullmatch(normalized):
            raise ValueError("Username must contain 3-32 letters, numbers, dots, dashes, or underscores")
        return normalized

    @field_validator("mobile_number")
    @classmethod
    def validate_admin_mobile(cls, value: str | None) -> str | None:
        """Validate an optional E.164 mobile number."""
        if value is None:
            return None
        normalized = value.strip()
        if not _E164_RE.fullmatch(normalized):
            raise ValueError("Mobile number must use E.164 format")
        return normalized


class AdminUserUpdateRequest(APIModel):
    """Editable administrator account fields; role/status use dedicated routes."""

    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=3, max_length=32)
    mobile_number: str | None = None

    @model_validator(mode="after")
    def require_admin_update(self) -> Self:
        """Reject empty administration patches."""
        if self.email is None and self.username is None and self.mobile_number is None:
            raise ValueError("At least one account field is required")
        return self

    @field_validator("email")
    @classmethod
    def normalize_optional_admin_email(cls, value: EmailStr | None) -> str | None:
        """Normalize a replacement email address."""
        return str(value).strip().lower() if value is not None else None

    @field_validator("username")
    @classmethod
    def normalize_optional_admin_username(cls, value: str | None) -> str | None:
        """Normalize a replacement username."""
        if value is None:
            return None
        normalized = value.strip().lower()
        if not _USERNAME_RE.fullmatch(normalized):
            raise ValueError("Username must contain 3-32 letters, numbers, dots, dashes, or underscores")
        return normalized

    @field_validator("mobile_number")
    @classmethod
    def validate_optional_admin_mobile(cls, value: str | None) -> str | None:
        """Validate a replacement E.164 mobile number."""
        if value is None:
            return None
        normalized = value.strip()
        if not _E164_RE.fullmatch(normalized):
            raise ValueError("Mobile number must use E.164 format")
        return normalized


class AdminRoleUpdateRequest(APIModel):
    """Role assignment request, separately permissioned from profile edits."""

    role: UserRole


class AdminUserDetail(APIModel):
    """Administrative user representation without credential fields."""

    id: UUID
    email: EmailStr | None
    username: str | None
    mobile_number: str | None
    role: UserRole
    is_active: bool
    is_verified: bool
    profile_image_reference: str | None
    created_at: datetime
    updated_at: datetime


class AdminUserPage(APIModel):
    """Paginated user results."""

    items: list[AdminUserDetail]
    total: int
    limit: int
    offset: int


class AuditLogPublic(APIModel):
    """Safe audit information with curated metadata only."""

    id: UUID
    actor_user_id: UUID | None
    action: str
    target_type: str
    target_id: str | None
    request_id: str | None
    ip_address: str | None
    outcome: str
    metadata: dict[str, str | int | bool | None]
    created_at: datetime


class AuditLogPage(APIModel):
    """Paginated audit results."""

    items: list[AuditLogPublic]
    total: int
    limit: int
    offset: int


__all__ = [
    "AdminRoleUpdateRequest",
    "AdminUserCreateRequest",
    "AdminUserDetail",
    "AdminUserPage",
    "AdminUserUpdateRequest",
    "AuditLogPage",
    "AuditLogPublic",
    "AuthResult",
    "ChangePasswordRequest",
    "DeliveryQueuedResult",
    "EmailRequest",
    "FileDownloadResult",
    "FileResult",
    "FileUploadRequest",
    "FileUploadResult",
    "LoginRequest",
    "MessageResult",
    "OTPRequest",
    "OTPChallengeResult",
    "OTPVerifyRequest",
    "ProfileUpdateRequest",
    "RefreshRequest",
    "RegisterRequest",
    "ResetPasswordRequest",
    "TokenPair",
    "TokenRequest",
    "UserPublic",
]
