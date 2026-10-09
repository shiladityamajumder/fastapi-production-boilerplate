"""Mocked AWS adapter tests; these tests never call AWS."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError

from app.common.exceptions import ExternalServiceError, NotFoundError, ValidationError
from app.core.config import AppSettings
from app.modules.auth.aws import (
    AWSSMSDelivery,
    S3FileStorage,
    SESEmailDelivery,
    VerifiedObject,
)
from app.modules.auth.models import StoredFile, User
from app.modules.auth.providers import DisabledEmailDelivery
from app.modules.auth.service import AuthService


def settings() -> AppSettings:
    """Return valid settings for mocked provider adapters."""
    return AppSettings(
        AWS_REGION="us-east-1",
        AWS_S3_BUCKET="private-test-bucket",
        AWS_SES_FROM_EMAIL="noreply@example.com",
        AUTH_PUBLIC_BASE_URL="https://example.com",
        AWS_SMS_ORIGINATION_IDENTITY=(
            "arn:aws:sms-voice:us-east-1:123456789012:pool/test"
        ),
    )


@pytest.mark.asyncio
async def test_ses_sends_text_and_html_using_mock_client() -> None:
    client = Mock()
    adapter = SESEmailDelivery(settings(), client=client)

    await adapter.send_action_link("person@example.com", "email_verify", "opaque-token")

    call = client.send_email.call_args.kwargs
    assert call["Destination"] == {"ToAddresses": ["person@example.com"]}
    assert "opaque-token" in call["Content"]["Simple"]["Body"]["Text"]["Data"]
    assert "opaque-token" in call["Content"]["Simple"]["Body"]["Html"]["Data"]


@pytest.mark.asyncio
async def test_ses_failure_is_sanitized() -> None:
    client = Mock()
    client.send_email.side_effect = ClientError(
        {"Error": {"Code": "Denied", "Message": "secret"}}, "SendEmail"
    )
    adapter = SESEmailDelivery(settings(), client=client)

    with pytest.raises(ExternalServiceError, match="Email delivery failed") as error:
        await adapter.send_action_link(
            "person@example.com", "password_reset", "never-log-me"
        )

    assert "secret" not in str(error.value)
    assert "never-log-me" not in str(error.value)


@pytest.mark.asyncio
async def test_sms_requires_e164_and_submits_transactional_message() -> None:
    client = Mock()
    adapter = AWSSMSDelivery(settings(), client=client)

    with pytest.raises(ValidationError):
        await adapter.send_code("55512345", "123456")
    await adapter.send_code("+14155552671", "123456")

    call = client.send_text_message.call_args.kwargs
    assert call["DestinationPhoneNumber"] == "+14155552671"
    assert call["MessageType"] == "TRANSACTIONAL"
    assert "123456" in call["MessageBody"]


@pytest.mark.asyncio
async def test_sms_provider_failure_is_sanitized() -> None:
    client = Mock()
    client.send_text_message.side_effect = ClientError(
        {"Error": {"Code": "Denied", "Message": "private provider detail"}},
        "SendTextMessage",
    )
    adapter = AWSSMSDelivery(settings(), client=client)

    with pytest.raises(ExternalServiceError, match="SMS delivery failed") as error:
        await adapter.send_code("+14155552671", "654321")

    assert "private provider detail" not in str(error.value)
    assert "654321" not in str(error.value)


@pytest.mark.asyncio
async def test_s3_upload_policy_has_size_and_owner_constraints() -> None:
    client = Mock()
    client.generate_presigned_post.return_value = {
        "url": "https://s3.test",
        "fields": {"key": "generated"},
    }
    adapter = S3FileStorage(settings(), client=client)
    owner_id, upload_id = uuid4(), uuid4()

    form = await adapter.create_upload(
        owner_id=owner_id,
        upload_id=upload_id,
        category="profile_image",
        content_type="image/png",
        size=1024,
    )

    call = client.generate_presigned_post.call_args.kwargs
    assert call["Key"].startswith(f"users/{owner_id}/profile_image/")
    assert ["content-length-range", 1, 1024] in call["Conditions"]
    assert {"x-amz-meta-owner-id": str(owner_id)} in call["Conditions"]
    assert form.url == "https://s3.test"


@pytest.mark.asyncio
async def test_s3_rejects_unsupported_type_and_provides_private_download_url() -> None:
    client = Mock()
    client.generate_presigned_url.return_value = "https://s3.test/signed"
    adapter = S3FileStorage(settings(), client=client)
    with pytest.raises(ValidationError):
        await adapter.create_upload(
            owner_id=uuid4(), upload_id=uuid4(), category="file",
            content_type="text/html", size=100
        )

    url = await adapter.temporary_download_url("server-generated/key.pdf")
    assert url == "https://s3.test/signed"
    assert client.generate_presigned_url.call_args.kwargs["ExpiresIn"] == 300


@pytest.mark.asyncio
async def test_s3_verification_checks_metadata_and_file_signature() -> None:
    client = Mock()
    client.head_object.return_value = {
        "Metadata": {
            "owner-id": "owner",
            "upload-id": "upload",
            "category": "profile_image",
        },
        "ContentLength": 8,
        "ContentType": "image/png",
        "ETag": '"etag"',
    }
    client.get_object.return_value = {"Body": BytesIO(b"\x89PNG\r\n\x1a\n")}
    adapter = S3FileStorage(settings(), client=client)
    owner_id, upload_id = uuid4(), uuid4()
    client.head_object.return_value["Metadata"] = {
        "owner-id": str(owner_id),
        "upload-id": str(upload_id),
        "category": "profile_image",
    }

    verified = await adapter.verify_upload(
        key="server-key",
        owner_id=owner_id,
        upload_id=upload_id,
        expected_type="image/png",
        expected_size=8,
        category="profile_image",
    )

    assert verified.size == 8
    assert verified.etag == '"etag"'


@pytest.mark.asyncio
async def test_s3_rejects_mismatched_metadata_and_sanitizes_errors() -> None:
    client = Mock()
    client.head_object.return_value = {
        "Metadata": {"owner-id": "other", "upload-id": "upload", "category": "file"},
        "ContentLength": 8,
        "ContentType": "image/png",
    }
    adapter = S3FileStorage(settings(), client=client)
    with pytest.raises(ValidationError, match="metadata"):
        await adapter.verify_upload(
            key="key", owner_id=uuid4(), upload_id=uuid4(), expected_type="image/png",
            expected_size=8, category="profile_image"
        )

    client.head_object.side_effect = ClientError(
        {"Error": {"Code": "Denied", "Message": "private"}}, "HeadObject"
    )
    with pytest.raises(ExternalServiceError) as error:
        await adapter.exists("key")
    assert "private" not in str(error.value)


@pytest.mark.asyncio
async def test_owner_scoped_file_lookup_hides_another_users_file() -> None:
    service = object.__new__(AuthService)
    session = SimpleNamespace(scalar=AsyncMock(return_value=None))
    service.uow = SimpleNamespace(session=session)
    service.profile_image_storage = Mock()

    with pytest.raises(NotFoundError):
        await service.file_download_url(uuid4(), uuid4())
    service.profile_image_storage.exists.assert_not_called()


@pytest.mark.asyncio
async def test_profile_image_upload_is_verified_before_publishing_reference() -> None:
    owner_id = uuid4()
    upload_id = uuid4()
    user = User(id=owner_id, is_active=True, profile_image_reference=None)
    row = StoredFile(
        id=upload_id,
        owner_user_id=owner_id,
        object_key=f"users/{owner_id}/profile_image/generated.png",
        category="profile_image",
        content_type="image/png",
        expected_size=32,
        actual_size=None,
        etag=None,
        is_complete=False,
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=row))
    service = object.__new__(AuthService)
    service.uow = SimpleNamespace(session=session, commit=AsyncMock())
    service.repository = SimpleNamespace(user_by_id=AsyncMock(return_value=user))
    service.settings = settings()
    service.profile_image_storage = Mock(available=True)
    service.profile_image_storage.verify_upload = AsyncMock(
        return_value=VerifiedObject(
            size=32,
            content_type="image/png",
            etag='"etag"',
        )
    )

    result = await service.complete_file_upload(owner_id, upload_id)

    assert result.id == upload_id
    assert row.is_complete is True
    assert user.profile_image_reference == str(upload_id)
    service.profile_image_storage.verify_upload.assert_awaited_once()
    service.uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_disabled_provider_fails_closed_without_reporting_success() -> None:
    provider = DisabledEmailDelivery()
    assert provider.available is False
    with pytest.raises(ExternalServiceError):
        await provider.send_action_link("person@example.com", "email_verify", "secret")


def test_aws_feature_flags_require_only_their_own_settings() -> None:
    with pytest.raises(ValueError, match="AWS_REGION"):
        AppSettings(PROFILE_IMAGE_STORAGE_ENABLED=True, AWS_S3_BUCKET="bucket")
    with pytest.raises(ValueError, match="AWS_S3_BUCKET"):
        AppSettings(PROFILE_IMAGE_STORAGE_ENABLED=True, AWS_REGION="us-east-1")
    with pytest.raises(ValueError, match="valid region"):
        AppSettings(
            PROFILE_IMAGE_STORAGE_ENABLED=True,
            AWS_REGION="not a region",
            AWS_S3_BUCKET="private-bucket",
        )
    with pytest.raises(ValueError, match="valid S3 bucket"):
        AppSettings(
            PROFILE_IMAGE_STORAGE_ENABLED=True,
            AWS_REGION="us-east-1",
            AWS_S3_BUCKET="INVALID_BUCKET",
        )
    configured = settings()
    assert configured.AWS_S3_BUCKET == "private-test-bucket"
    AppSettings(
        AUTH_EMAIL_DELIVERY_ENABLED=True,
        AWS_REGION="us-east-1",
        AWS_SES_FROM_EMAIL="noreply@example.com",
        AUTH_PUBLIC_BASE_URL="https://example.com",
    )
    AppSettings(
        AUTH_SMS_DELIVERY_ENABLED=True,
        AWS_REGION="us-east-1",
        AWS_SMS_ORIGINATION_IDENTITY="origination",
    )
