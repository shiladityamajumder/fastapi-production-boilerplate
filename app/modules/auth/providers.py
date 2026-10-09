"""Provider ports and fail-closed implementations for account integrations."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.common.exceptions import ExternalServiceError


class EmailDelivery(Protocol):
    """Deliver an account email without logging its secret content."""

    async def send_action_link(self, email: str, purpose: str, token: str) -> None:
        """Send a password-reset or verification action link."""
        ...

    async def send_notification(
        self, email: str, subject: str, text_body: str, html_body: str | None = None
    ) -> None:
        """Send a general notification using text and optional HTML content."""
        ...


class SMSDelivery(Protocol):
    """Deliver a phone verification code."""

    async def send_code(self, mobile_number: str, code: str) -> None:
        """Deliver an OTP to one E.164 destination."""
        ...


class ProfileImageStorage(Protocol):
    """Manage private owner-scoped objects through short-lived upload forms."""

    async def create_upload(
        self,
        *,
        owner_id: UUID,
        upload_id: UUID,
        category: str,
        content_type: str,
        size: int,
    ) -> object:
        """Create a short-lived upload form for a server-generated object key."""
        ...

    async def verify_upload(
        self,
        *,
        key: str,
        owner_id: UUID,
        upload_id: UUID,
        expected_type: str,
        expected_size: int,
        category: str,
    ) -> object:
        """Confirm S3 metadata, size, existence, and content signature."""
        ...

    async def delete(self, key: str) -> None:
        """Delete an owned object key."""
        ...

    async def exists(self, key: str) -> bool:
        """Check whether the object exists."""
        ...

    async def temporary_download_url(self, key: str) -> str:
        """Generate a short-lived private download URL."""
        ...


class DisabledEmailDelivery:
    """Fail-closed email provider used when delivery is disabled."""

    available = False

    async def send_action_link(self, email: str, purpose: str, token: str) -> None:
        """Fail closed because no email service is configured."""
        raise ExternalServiceError("Email delivery is not configured.")

    async def send_notification(
        self, email: str, subject: str, text_body: str, html_body: str | None = None
    ) -> None:
        """Fail closed because no email service is configured."""
        del email, subject, text_body, html_body
        raise ExternalServiceError("Email delivery is not configured.")


class DisabledSMSDelivery:
    """Fail-closed SMS provider used when delivery is disabled."""

    available = False

    async def send_code(self, mobile_number: str, code: str) -> None:
        """Fail closed because no SMS service is configured."""
        raise ExternalServiceError("SMS delivery is not configured.")


class DisabledProfileImageStorage:
    """Fail-closed object provider used when S3 storage is disabled."""

    available = False

    async def create_upload(self, **kwargs: object) -> object:
        """Fail closed because no object storage provider is configured."""
        del kwargs
        raise ExternalServiceError("Profile image storage is not configured.")

    async def verify_upload(self, **kwargs: object) -> object:
        """Fail closed because no object storage provider is configured."""
        del kwargs
        raise ExternalServiceError("Profile image storage is not configured.")

    async def delete(self, key: str) -> None:
        """Fail closed because no object storage provider is configured."""
        del key
        raise ExternalServiceError("Profile image storage is not configured.")

    async def exists(self, key: str) -> bool:
        """Fail closed because no object storage provider is configured."""
        del key
        raise ExternalServiceError("Profile image storage is not configured.")

    async def temporary_download_url(self, key: str) -> str:
        """Fail closed because no object storage provider is configured."""
        del key
        raise ExternalServiceError("Profile image storage is not configured.")


__all__ = [
    "DisabledEmailDelivery",
    "DisabledProfileImageStorage",
    "DisabledSMSDelivery",
    "EmailDelivery",
    "ProfileImageStorage",
    "SMSDelivery",
]
