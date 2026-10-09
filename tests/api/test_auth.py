"""Authentication use-case and authorization security tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import jwt
import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError as PydanticValidationError

from app.common.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ExternalServiceError,
    ValidationError,
)
from app.core.config import AppSettings, Environment
from app.modules.auth import cli
from app.modules.auth.dependencies import get_current_admin, require_permission
from app.modules.auth.models import OTPChallenge, RefreshSession, User, UserRole
from app.modules.auth.permissions import Permissions, ROLE_PERMISSIONS
from app.modules.auth.schemas import (
    LoginRequest,
    OTPRequest,
    OTPVerifyRequest,
    RegisterRequest,
)
from app.modules.auth.service import AuthService, hash_password
from app.worker.outbox import decrypt_payload

_JWT_SECRET = "testing-only-secret-material-32-bytes-minimum"
_TEST_CREDENTIAL = "A-strong-password-123"
_WRONG_CREDENTIAL = "not-the-account-credential"


class FakeUOW:
    """Minimal Unit of Work test double with an async session placeholder."""

    def __init__(self) -> None:
        self.session = Mock()
        self.session.flush = AsyncMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()


def make_service() -> AuthService:
    settings = AppSettings(
        ENVIRONMENT=Environment.TESTING,
        ENABLE_POSTGRES=True,
        POSTGRES_URL="postgresql+asyncpg://user:pass@localhost/test_db",
        AUTH_ENABLED=True,
        AUTH_JWT_SECRET_KEY=_JWT_SECRET,
        AUTH_EMAIL_DELIVERY_ENABLED=True,
        AUTH_SMS_DELIVERY_ENABLED=True,
        AWS_REGION="us-east-1",
        AWS_SES_FROM_EMAIL="noreply@example.com",
        AWS_SMS_ORIGINATION_IDENTITY="test-originator",
        AUTH_PUBLIC_BASE_URL="https://example.com",
        BACKGROUND_JOBS_ENABLED=True,
        REDIS_URL="redis://localhost:6379/0",
        BACKGROUND_PAYLOAD_ENCRYPTION_KEY=Fernet.generate_key().decode(),
    )
    service = AuthService(FakeUOW(), settings)
    service.repository = Mock()
    service.repository.consume_rate_limit = AsyncMock(return_value=True)
    service.repository.add_refresh = AsyncMock()
    service.repository.user_by_id = AsyncMock()
    service.repository.user_by_identifier = AsyncMock()
    service.repository.otp_by_id = AsyncMock()
    service.repository.user_by_mobile = AsyncMock()
    service.repository.revoke_mobile_challenges = AsyncMock()
    service.repository.add_otp = Mock()
    service.repository.add_user = Mock()
    service.repository.add_outbox = AsyncMock(return_value=True)
    service.repository.revoke_family = AsyncMock()
    service.repository.revoke_user_sessions = AsyncMock()
    return service


def test_auth_settings_require_postgres_and_a_strong_jwt_secret() -> None:
    with pytest.raises(PydanticValidationError, match="ENABLE_POSTGRES"):
        AppSettings(AUTH_ENABLED=True, AUTH_JWT_SECRET_KEY=_JWT_SECRET)
    with pytest.raises(PydanticValidationError, match="at least 32 characters"):
        AppSettings(
            ENABLE_POSTGRES=True,
            POSTGRES_URL="postgresql+asyncpg://user:pass@localhost/test_db",
            AUTH_ENABLED=True,
            AUTH_JWT_SECRET_KEY="too-short",
        )
    with pytest.raises(PydanticValidationError, match="AWS_REGION"):
        AppSettings(AUTH_EMAIL_DELIVERY_ENABLED=True)


@pytest.mark.asyncio
async def test_rate_limited_authentication_request_is_persisted_and_rejected() -> None:
    service = make_service()
    service.repository.consume_rate_limit.return_value = False

    with pytest.raises(ValidationError) as error:
        await service._rate_limit(
            "login",
            "person@example.com",
            "127.0.0.1",
            limit=1,
            window_seconds=60,
        )
    assert error.value.code == "RATE_LIMITED"
    service.uow.commit.assert_awaited_once()


def test_public_registration_normalizes_identifiers_and_never_accepts_role() -> None:
    request = RegisterRequest(
        email="Person@Example.com",
        username="Person.Name",
        password=_TEST_CREDENTIAL,
    )
    assert request.email == "person@example.com"
    assert request.username == "person.name"
    with pytest.raises(PydanticValidationError):
        RegisterRequest(
            email="admin@example.com",
            username="admin-user",
            password=_TEST_CREDENTIAL,
            role="ADMIN",
        )


@pytest.mark.asyncio
async def test_registration_creates_only_user_role_and_does_not_return_hash() -> None:
    service = make_service()
    service.repository.identifier_exists = AsyncMock(return_value=False)
    result = await service.register(
        RegisterRequest(
            email="person@example.com",
            username="person",
            password=_TEST_CREDENTIAL,
        ),
        remote_address="127.0.0.1",
    )
    created = service.repository.add_user.call_args.args[0]
    assert result.role == UserRole.USER.value
    assert created.password_hash != _TEST_CREDENTIAL
    assert "password_hash" not in result.model_dump()
    assert service.uow.commit.await_count == 2


@pytest.mark.asyncio
async def test_password_login_issues_signed_tokens() -> None:
    service = make_service()
    user = User(
        id=uuid4(),
        email="person@example.com",
        username="person",
        password_hash=hash_password(_TEST_CREDENTIAL),
        role=UserRole.USER,
        is_active=True,
        is_verified=True,
        token_version=0,
    )
    service.repository.user_by_identifier.return_value = user

    result = await service.login(
        LoginRequest(
            identifier="PERSON@example.com",
            password=_TEST_CREDENTIAL,
        ),
        remote_address="127.0.0.1",
    )

    claims = jwt.decode(
        result.tokens.access_token,
        _JWT_SECRET,
        algorithms=["HS256"],
    )
    assert claims["sub"] == str(user.id)
    assert result.tokens.refresh_token
    refresh = service.repository.add_refresh.call_args.args[0]
    assert refresh.token_hash != result.tokens.refresh_token


@pytest.mark.asyncio
async def test_invalid_password_is_generic_and_does_not_issue_tokens() -> None:
    service = make_service()
    user = User(
        id=uuid4(),
        email="person@example.com",
        username="person",
        password_hash=hash_password(_TEST_CREDENTIAL),
        role=UserRole.USER,
        is_active=True,
    )
    service.repository.user_by_identifier.return_value = user

    with pytest.raises(AuthenticationError, match="Invalid credentials"):
        await service.login(
            LoginRequest(identifier="person", password=_WRONG_CREDENTIAL),
            remote_address="127.0.0.1",
        )
    service.repository.add_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_token_version_revokes_existing_access_token() -> None:
    service = make_service()
    user = User(
        id=uuid4(),
        role=UserRole.USER,
        is_active=True,
        token_version=0,
    )
    access_token, _ = service._access_token(user)
    service.repository.user_by_id.return_value = user
    assert await service.authenticate_access_token(access_token) is user

    user.token_version = 1
    with pytest.raises(AuthenticationError, match="invalid or expired"):
        await service.authenticate_access_token(access_token)


@pytest.mark.asyncio
async def test_expired_refresh_token_is_revoked() -> None:
    service = make_service()
    row = RefreshSession(
        id=uuid4(),
        user_id=uuid4(),
        family_id=uuid4(),
        token_hash=service._hash_token("expired-refresh-token"),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    service.repository.refresh_by_hash = AsyncMock(return_value=row)

    with pytest.raises(AuthenticationError, match="invalid or expired"):
        await service.refresh(
            "expired-refresh-token",
            remote_address="127.0.0.1",
        )
    assert row.revoked_at is not None
    assert service.uow.commit.await_count == 2


@pytest.mark.asyncio
async def test_reused_refresh_token_revokes_its_token_family() -> None:
    service = make_service()
    row = RefreshSession(
        id=uuid4(),
        user_id=uuid4(),
        family_id=uuid4(),
        token_hash=service._hash_token("reused-refresh-token"),
        expires_at=datetime.now(UTC) + timedelta(days=1),
        revoked_at=datetime.now(UTC),
        replaced_by_id=uuid4(),
    )
    service.repository.refresh_by_hash = AsyncMock(return_value=row)

    with pytest.raises(AuthenticationError, match="reuse"):
        await service.refresh(
            "reused-refresh-token",
            remote_address="127.0.0.1",
        )
    service.repository.revoke_family.assert_awaited_once()
    assert service.repository.revoke_family.await_args.args[0] == row.family_id
    assert service.uow.commit.await_count == 2


@pytest.mark.asyncio
async def test_wrong_otp_increments_bounded_attempt_counter() -> None:
    service = make_service()
    challenge = OTPChallenge(
        id=uuid4(),
        mobile_number="+14155550123",
        purpose="login",
        code_hash=service._hash_otp(uuid4(), "123456"),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        attempts=0,
        max_attempts=2,
    )
    # Hash the actual challenge ID; no plaintext OTP is persisted.
    challenge.code_hash = service._hash_otp(challenge.id, "123456")
    service.repository.otp_by_id.return_value = challenge

    request = OTPVerifyRequest(
        mobile_number="+14155550123",
        challenge_id=challenge.id,
        code="654321",
    )
    with pytest.raises(AuthenticationError, match="invalid or expired"):
        await service.verify_otp(request, remote_address="127.0.0.1")
    assert challenge.attempts == 1
    service.uow.commit.assert_awaited()  # rate counter and failed attempt persist


@pytest.mark.asyncio
async def test_expired_otp_is_rejected() -> None:
    service = make_service()
    challenge = OTPChallenge(
        id=uuid4(),
        mobile_number="+14155550123",
        purpose="login",
        code_hash=service._hash_otp(uuid4(), "123456"),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        max_attempts=5,
    )
    service.repository.otp_by_id.return_value = challenge
    request = OTPVerifyRequest(
        mobile_number="+14155550123",
        challenge_id=challenge.id,
        code="123456",
    )
    with pytest.raises(AuthenticationError):
        await service.verify_otp(request, remote_address="127.0.0.1")


@pytest.mark.asyncio
async def test_successful_otp_consumes_challenge_and_issues_tokens() -> None:
    service = make_service()
    challenge_id = uuid4()
    challenge = OTPChallenge(
        id=challenge_id,
        mobile_number="+14155550123",
        purpose="login",
        code_hash=service._hash_otp(challenge_id, "123456"),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        attempts=0,
        max_attempts=5,
    )
    user = User(
        id=uuid4(),
        mobile_number="+14155550123",
        role=UserRole.USER,
        is_active=True,
        is_verified=True,
        token_version=0,
    )
    service.repository.otp_by_id.return_value = challenge
    service.repository.user_by_mobile.return_value = user

    result = await service.verify_otp(
        OTPVerifyRequest(
            mobile_number="+14155550123",
            challenge_id=challenge_id,
            code="123456",
        ),
        remote_address="127.0.0.1",
    )

    assert challenge.consumed_at is not None
    assert result.user.id == user.id
    service.repository.add_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_otp_code_is_hashed_and_queued_in_encrypted_outbox() -> None:
    service = make_service()
    service.repository.user_by_mobile.return_value = None

    challenge_id = await service.request_otp(
        OTPRequest(mobile_number="+14155550123"),
        remote_address="127.0.0.1",
    )

    row = service.repository.add_otp.call_args.args[0]
    job = service.repository.add_outbox.await_args.args[0]
    payload = decrypt_payload(service.settings, job.payload_ciphertext)
    sent_code = payload["code"]
    assert challenge_id == row.id
    assert len(sent_code) == 6
    assert row.code_hash != sent_code
    assert row.code_hash == service._hash_otp(row.id, sent_code)
    assert payload["mobile_number"] == row.mobile_number
    assert job.status == "pending"
    assert job.idempotency_key == f"otp:{challenge_id}"


@pytest.mark.asyncio
async def test_disabled_sms_provider_fails_without_claiming_delivery() -> None:
    service = make_service()
    service.settings.AUTH_SMS_DELIVERY_ENABLED = False
    with pytest.raises(ExternalServiceError, match="SMS delivery is not configured"):
        await service.request_otp(
            OTPRequest(mobile_number="+14155550123"),
            remote_address="127.0.0.1",
        )
    service.repository.add_otp.assert_not_called()


@pytest.mark.asyncio
async def test_expired_or_reused_action_token_is_rejected() -> None:
    service = make_service()
    token_id = uuid4()
    row = Mock(
        id=token_id,
        purpose="password_reset",
        token_hash=service._hash_token("one-time-secret"),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        consumed_at=None,
        revoked_at=None,
        attempts=0,
        max_attempts=3,
    )
    service.repository.action_token_by_id = AsyncMock(return_value=row)

    with pytest.raises(ValidationError, match="invalid or expired"):
        await service._consume_action_token(
            f"{token_id}.one-time-secret",
            "password_reset",
        )
    assert row.attempts == 1
    service.uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_password_reset_queues_encrypted_delivery_without_leaking_token() -> None:
    service = make_service()
    user = User(
        id=uuid4(),
        email="person@example.com",
        is_active=True,
        password_hash="stored-hash",
    )
    service.repository.user_by_email = AsyncMock(return_value=user)
    service.repository.revoke_action_tokens = AsyncMock()
    service.repository.add_action_token = Mock()
    await service.request_password_reset(
        "person@example.com", remote_address="127.0.0.1"
    )

    job = service.repository.add_outbox.await_args.args[0]
    payload = decrypt_payload(service.settings, job.payload_ciphertext)
    assert job.status == "pending"
    assert job.kind == "email_action"
    assert payload["email"] == user.email
    assert payload["purpose"] == "password_reset"
    assert payload["token"]
    assert job.payload_ciphertext.decode(errors="ignore").find(payload["token"]) == -1


@pytest.mark.asyncio
async def test_general_email_delivery_is_queued_encrypted() -> None:
    service = make_service()

    await service.queue_email_notification(
        email="person@example.com",
        subject="Welcome",
        text_body="Your account is ready.",
        html_body="<p>Your account is ready.</p>",
        idempotency_key="welcome-user-123",
    )

    job = service.repository.add_outbox.await_args.args[0]
    assert job.kind == "email_notification"
    assert job.idempotency_key == "email-notification:welcome-user-123"
    assert job.status == "pending"
    assert decrypt_payload(service.settings, job.payload_ciphertext) == {
        "email": "person@example.com",
        "subject": "Welcome",
        "text_body": "Your account is ready.",
        "html_body": "<p>Your account is ready.</p>",
    }
    service.uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_wrong_action_token_counts_attempts_and_revokes_at_limit() -> None:
    service = make_service()
    token_id = uuid4()
    row = Mock(
        id=token_id,
        purpose="email_verify",
        token_hash=service._hash_token("right-secret"),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        consumed_at=None,
        revoked_at=None,
        attempts=1,
        max_attempts=2,
    )
    service.repository.action_token_by_id = AsyncMock(return_value=row)

    with pytest.raises(ValidationError):
        await service._consume_action_token(
            f"{token_id}.wrong-secret",
            "email_verify",
        )
    assert row.attempts == 2
    assert row.revoked_at is not None
    service.uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_admin_is_forbidden_from_admin_dependency() -> None:
    user = User(id=uuid4(), role=UserRole.USER, is_active=True)
    with pytest.raises(AuthorizationError):
        await get_current_admin(user)


@pytest.mark.asyncio
async def test_role_permissions_are_least_privilege_and_guarded() -> None:
    assert ROLE_PERMISSIONS[UserRole.USER] == frozenset()
    assert Permissions.USERS_ASSIGN_ROLE in ROLE_PERMISSIONS[UserRole.ADMIN]
    assert Permissions.USERS_ASSIGN_ROLE in ROLE_PERMISSIONS[UserRole.SUPER_ADMIN]

    dependency = require_permission(Permissions.USERS_READ)
    with pytest.raises(AuthorizationError):
        await dependency(User(id=uuid4(), role=UserRole.USER, is_active=True))


@pytest.mark.asyncio
async def test_admin_cannot_assign_administrative_role() -> None:
    service = make_service()
    actor = User(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    target = User(id=uuid4(), role=UserRole.USER, is_active=True)
    service.repository.lock_admin_mutations = AsyncMock()
    service.repository.user_by_id = AsyncMock(return_value=actor)
    service.repository.user_by_id_for_update = AsyncMock(return_value=target)

    with pytest.raises(AuthorizationError):
        await service.admin_set_role(actor.id, target.id, UserRole.SUPER_ADMIN)

    service.uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_last_active_super_admin_cannot_be_deactivated() -> None:
    service = make_service()
    actor = User(id=uuid4(), role=UserRole.SUPER_ADMIN, is_active=True)
    target = User(id=uuid4(), role=UserRole.SUPER_ADMIN, is_active=True)
    service.repository.lock_admin_mutations = AsyncMock()
    service.repository.user_by_id = AsyncMock(return_value=actor)
    service.repository.user_by_id_for_update = AsyncMock(return_value=target)
    service.repository.active_super_admin_count = AsyncMock(return_value=1)

    with pytest.raises(ConflictError, match="last active super administrator"):
        await service.admin_set_active(actor.id, target.id, False)

    service.repository.lock_admin_mutations.assert_awaited_once()
    service.uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_deactivation_revokes_sessions_and_audits_change() -> None:
    service = make_service()
    now = datetime.now(UTC)
    actor = User(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    target = User(
        id=uuid4(),
        role=UserRole.USER,
        is_active=True,
        token_version=0,
        created_at=now,
        updated_at=now,
    )
    service.repository.lock_admin_mutations = AsyncMock()
    service.repository.user_by_id = AsyncMock(return_value=actor)
    service.repository.user_by_id_for_update = AsyncMock(return_value=target)
    service.repository.revoke_user_sessions = AsyncMock(return_value=2)
    service.repository.add_audit = Mock()

    result = await service.admin_set_active(actor.id, target.id, False)

    assert not target.is_active
    assert target.token_version == 1
    assert result.id == target.id
    service.repository.revoke_user_sessions.assert_awaited_once()
    service.repository.add_audit.assert_called()
    service.uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_user_list_preserves_filters_and_pagination() -> None:
    service = make_service()
    now = datetime.now(UTC)
    actor = User(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    target = User(
        id=uuid4(),
        email="person@example.com",
        username="person",
        role=UserRole.USER,
        is_active=True,
        is_verified=False,
        created_at=now,
        updated_at=now,
    )
    service.repository.user_by_id = AsyncMock(return_value=actor)
    service.repository.list_users = AsyncMock(return_value=([target], 21))

    result = await service.admin_list_users(
        actor.id,
        search="person",
        role=UserRole.USER,
        is_active=True,
        limit=10,
        offset=20,
        sort_by=None,
        sort_order="desc",
    )

    assert result.total == 21
    assert result.limit == 10
    assert result.offset == 20
    assert result.items[0].id == target.id
    service.repository.list_users.assert_awaited_once_with(
        search="person",
        role=UserRole.USER,
        is_active=True,
        limit=10,
        offset=20,
        sort_by=None,
        sort_order="desc",
    )


def test_audit_metadata_drops_secret_fields() -> None:
    service = make_service()
    assert service._safe_audit_metadata(
        {"reason": "support request", "password": "secret", "refresh_token": "token"}
    ) == {"reason": "support request"}


@pytest.mark.asyncio
async def test_admin_bootstrap_refuses_existing_administrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Mock()
    database.close = AsyncMock()
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: AppSettings(
            ENABLE_POSTGRES=True,
            POSTGRES_URL="postgresql+asyncpg://u:p@localhost/db",
        ),
    )
    monkeypatch.setattr(cli.PostgreSQLDatabase, "from_settings", Mock(return_value=database))

    class FakeAdminUOW:
        session = Mock()

        async def __aenter__(self) -> FakeAdminUOW:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(cli, "SQLAlchemyUnitOfWork", Mock(return_value=FakeAdminUOW()))
    repository = Mock()
    repository.lock_first_admin_bootstrap = AsyncMock()
    repository.user_by_email = AsyncMock(return_value=None)
    repository.user_by_username = AsyncMock(return_value=None)
    repository.super_admin_exists = AsyncMock(return_value=True)
    monkeypatch.setattr(cli, "AuthRepository", Mock(return_value=repository))

    with pytest.raises(ConflictError, match="SUPER_ADMIN already exists"):
        await cli.create_first_admin(
            "another@example.com",
            "another-admin",
            _TEST_CREDENTIAL,
        )
    database.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_bootstrap_does_not_promote_existing_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Mock()
    database.close = AsyncMock()
    settings = AppSettings(
        ENABLE_POSTGRES=True,
        POSTGRES_URL="postgresql+asyncpg://u:p@localhost/db",
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.PostgreSQLDatabase, "from_settings", Mock(return_value=database))

    class FakeAdminUOW:
        session = Mock()

        async def __aenter__(self) -> FakeAdminUOW:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(cli, "SQLAlchemyUnitOfWork", Mock(return_value=FakeAdminUOW()))
    repository = Mock()
    repository.lock_first_admin_bootstrap = AsyncMock()
    existing_user = Mock(id=uuid4(), role=UserRole.USER, is_active=True)
    repository.user_by_email = AsyncMock(return_value=existing_user)
    repository.user_by_username = AsyncMock(return_value=None)
    repository.super_admin_exists = AsyncMock(return_value=False)
    repository.add_user = Mock()
    monkeypatch.setattr(cli, "AuthRepository", Mock(return_value=repository))

    with pytest.raises(ConflictError, match="it was not changed"):
        await cli.create_first_admin(
            "existing@example.com",
            "existing-user",
            _TEST_CREDENTIAL,
        )
    repository.add_user.assert_not_called()
    database.close.assert_awaited_once()
