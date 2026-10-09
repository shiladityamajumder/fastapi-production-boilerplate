"""AWS-backed delivery and private object storage adapters."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.common.exceptions import ExternalServiceError, ValidationError
from app.core.config import AppSettings

_IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_GENERIC_TYPES = {**_IMAGE_TYPES, "application/pdf": "pdf", "text/plain": "txt"}


def _matches_signature(content_type: str, header: bytes) -> bool:
    """Check the file signature for the supported, non-executable formats."""
    if content_type == "image/jpeg":
        return header.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return (
            len(header) >= 12
            and header[:4] == b"RIFF"
            and header[8:12] == b"WEBP"
        )
    if content_type == "application/pdf":
        return header.startswith(b"%PDF-")
    if content_type == "text/plain":
        return b"\x00" not in header and bool(header.decode("utf-8", errors="ignore"))
    return False


@lru_cache(maxsize=8)
def _client(
    service: str, region: str, connect_timeout: int, read_timeout: int
) -> Any:
    """Create reusable boto clients using the standard credential chain."""
    try:
        return boto3.client(
            service,
            region_name=region,
            config=Config(
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
                retries={"mode": "standard", "max_attempts": 3},
            ),
        )
    except (BotoCoreError, ClientError, OSError) as exc:
        raise ExternalServiceError("AWS service is not available.") from exc


def _aws_client(settings: AppSettings, service: str) -> Any:
    region = settings.AWS_REGION
    if not region:
        raise ExternalServiceError("AWS integration is not configured.")
    return _client(
        service,
        region,
        settings.AWS_CONNECT_TIMEOUT_SECONDS,
        settings.AWS_READ_TIMEOUT_SECONDS,
    )


class SESEmailDelivery:
    """Send account action links through Amazon SES v2."""

    available = True

    def __init__(self, settings: AppSettings, client: Any | None = None) -> None:
        """Bind this adapter to validated settings and a reusable SES client."""
        self.settings = settings
        self.client = client or _aws_client(settings, "sesv2")

    async def send_action_link(self, email: str, purpose: str, token: str) -> None:
        """Send an expiring action URL using text and HTML alternatives."""
        label = (
            "reset your password"
            if purpose == "password_reset"
            else "verify your email"
        )
        base_url = self.settings.AUTH_PUBLIC_BASE_URL or ""
        link = (
            f"{base_url.rstrip('/')}/#auth_action={quote(purpose)}"
            f"&token={quote(token)}"
        )
        text = (
            f"Use this link to {label}: {link}\n"
            "This link expires soon and can be used once."
        )
        html = (
            f'<p>Use the link below to {label}:</p>'
            f'<p><a href="{link}">Continue</a></p>'
            "<p>This link expires soon and can be used once.</p>"
        )
        try:
            await asyncio.to_thread(
                self.client.send_email,
                FromEmailAddress=self.settings.AWS_SES_FROM_EMAIL,
                Destination={"ToAddresses": [email]},
                Content={
                    "Simple": {
                        "Subject": {"Data": "Account security"},
                        "Body": {
                            "Text": {"Data": text},
                            "Html": {"Data": html},
                        },
                    }
                },
            )
        except (BotoCoreError, ClientError, OSError) as exc:
            raise ExternalServiceError("Email delivery failed.") from exc

    async def send_notification(
        self,
        email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> None:
        """Submit a general text/HTML notification through SES v2."""
        body: dict[str, dict[str, str]] = {"Text": {"Data": text_body}}
        if html_body is not None:
            body["Html"] = {"Data": html_body}
        try:
            await asyncio.to_thread(
                self.client.send_email,
                FromEmailAddress=self.settings.AWS_SES_FROM_EMAIL,
                Destination={"ToAddresses": [email]},
                Content={
                    "Simple": {
                        "Subject": {"Data": subject},
                        "Body": body,
                    }
                },
            )
        except (BotoCoreError, ClientError, OSError) as exc:
            raise ExternalServiceError("Email delivery failed.") from exc


class AWSSMSDelivery:
    """Send transactional OTP messages through AWS End User Messaging SMS."""

    available = True

    def __init__(self, settings: AppSettings, client: Any | None = None) -> None:
        """Bind this adapter to validated settings and an SMS client."""
        self.settings = settings
        self.client = client or _aws_client(settings, "pinpoint-sms-voice-v2")

    async def send_code(self, mobile_number: str, code: str) -> None:
        """Send one transactional OTP to a canonical E.164 destination."""
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", mobile_number):
            raise ValidationError("Mobile number must use E.164 format.")
        try:
            await asyncio.to_thread(
                self.client.send_text_message,
                DestinationPhoneNumber=mobile_number,
                OriginationIdentity=self.settings.AWS_SMS_ORIGINATION_IDENTITY,
                MessageBody=f"Your verification code is {code}. It expires soon.",
                MessageType="TRANSACTIONAL",
            )
        except (BotoCoreError, ClientError, OSError) as exc:
            raise ExternalServiceError("SMS delivery failed.") from exc


@dataclass(frozen=True)
class UploadForm:
    """Short-lived presigned POST data for one server-owned key."""

    key: str
    url: str
    fields: dict[str, str]
    expires_in: int


@dataclass(frozen=True)
class VerifiedObject:
    """S3 object facts confirmed during upload completion."""

    size: int
    content_type: str
    etag: str | None


class S3FileStorage:
    """Private S3 storage adapter with constrained uploads and ownership metadata."""

    available = True

    def __init__(self, settings: AppSettings, client: Any | None = None) -> None:
        """Bind this adapter to validated settings and a private S3 client."""
        self.settings = settings
        self.client = client or _aws_client(settings, "s3")
        self.bucket = settings.AWS_S3_BUCKET

    @staticmethod
    def content_type_supported(content_type: str, *, profile_image: bool) -> bool:
        """Return whether the media type is allowed for this category."""
        return content_type in (_IMAGE_TYPES if profile_image else _GENERIC_TYPES)

    async def create_upload(
        self,
        *,
        owner_id: UUID,
        upload_id: UUID,
        category: str,
        content_type: str,
        size: int,
    ) -> UploadForm:
        """Create a signed POST policy bound to owner metadata and exact size."""
        profile_image = category == "profile_image"
        allowed = _IMAGE_TYPES if profile_image else _GENERIC_TYPES
        if (
            content_type not in allowed
            or size < 1
            or size > self.settings.AWS_S3_MAX_UPLOAD_BYTES
        ):
            raise ValidationError("The file type or size is not supported.")
        key = f"users/{owner_id}/{category}/{uuid4()}.{allowed[content_type]}"
        fields = {
            "Content-Type": content_type,
            "x-amz-meta-owner-id": str(owner_id),
            "x-amz-meta-upload-id": str(upload_id),
            "x-amz-meta-category": category,
        }
        conditions: list[Any] = [
            {"Content-Type": content_type},
            {"x-amz-meta-owner-id": str(owner_id)},
            {"x-amz-meta-upload-id": str(upload_id)},
            {"x-amz-meta-category": category},
            ["content-length-range", 1, size],
        ]
        try:
            response = await asyncio.to_thread(
                self.client.generate_presigned_post,
                Bucket=self.bucket,
                Key=key,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=self.settings.AWS_S3_UPLOAD_URL_TTL_SECONDS,
            )
        except (BotoCoreError, ClientError, OSError) as exc:
            raise ExternalServiceError("File upload could not be initialized.") from exc
        return UploadForm(
            key=key,
            url=response["url"],
            fields=response["fields"],
            expires_in=self.settings.AWS_S3_UPLOAD_URL_TTL_SECONDS,
        )

    async def verify_upload(
        self,
        *,
        key: str,
        owner_id: UUID,
        upload_id: UUID,
        expected_type: str,
        expected_size: int,
        category: str,
    ) -> VerifiedObject:
        """Check object metadata, size, and its content signature."""
        try:
            head = await asyncio.to_thread(
                self.client.head_object,
                Bucket=self.bucket,
                Key=key,
            )
            metadata = {
                name.lower(): value
                for name, value in head.get("Metadata", {}).items()
            }
            size = int(head["ContentLength"])
            actual_type = head.get("ContentType", "")
            if (
                metadata.get("owner-id") != str(owner_id)
                or metadata.get("upload-id") != str(upload_id)
                or metadata.get("category") != category
                or actual_type != expected_type
                or size != expected_size
                or size > self.settings.AWS_S3_MAX_UPLOAD_BYTES
            ):
                raise ValidationError(
                    "Uploaded file metadata did not match the request."
                )
            response = await asyncio.to_thread(
                self.client.get_object,
                Bucket=self.bucket,
                Key=key,
                Range="bytes=0-31",
            )
            body = response["Body"]
            try:
                header = await asyncio.to_thread(body.read, 32)
            finally:
                await asyncio.to_thread(body.close)
            if not _matches_signature(expected_type, header):
                raise ValidationError(
                    "Uploaded file content does not match its declared type."
                )
            return VerifiedObject(
                size=size,
                content_type=actual_type,
                etag=head.get("ETag"),
            )
        except ValidationError:
            raise
        except (BotoCoreError, ClientError, OSError, KeyError, ValueError) as exc:
            raise ExternalServiceError("Uploaded file could not be verified.") from exc

    async def delete(self, key: str) -> None:
        """Delete one object at a server-owned key."""
        try:
            await asyncio.to_thread(
                self.client.delete_object,
                Bucket=self.bucket,
                Key=key,
            )
        except (BotoCoreError, ClientError, OSError) as exc:
            raise ExternalServiceError("File could not be deleted.") from exc

    async def exists(self, key: str) -> bool:
        """Check object existence and distinguish missing from failed checks."""
        try:
            await asyncio.to_thread(
                self.client.head_object,
                Bucket=self.bucket,
                Key=key,
            )
            return True
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return False
            raise ExternalServiceError(
                "File availability could not be checked."
            ) from exc
        except (BotoCoreError, OSError) as exc:
            raise ExternalServiceError(
                "File availability could not be checked."
            ) from exc

    async def temporary_download_url(self, key: str) -> str:
        """Create a short-lived signed GET URL for a private object."""
        try:
            return await asyncio.to_thread(
                self.client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=self.settings.AWS_S3_DOWNLOAD_URL_TTL_SECONDS,
            )
        except (BotoCoreError, ClientError, OSError) as exc:
            raise ExternalServiceError(
                "File download could not be initialized."
            ) from exc


__all__ = [
    "AWSSMSDelivery",
    "SESEmailDelivery",
    "S3FileStorage",
    "UploadForm",
    "VerifiedObject",
]
