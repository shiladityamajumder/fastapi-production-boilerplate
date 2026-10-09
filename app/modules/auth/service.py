"""Authentication use cases and security-sensitive token lifecycle."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any  # noqa: TC003
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.common.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from app.core.config import AppSettings  # noqa: TC001
from app.db.uow import SQLAlchemyUnitOfWork  # noqa: TC001
from app.modules.auth.models import (
    AuditLog,
    NotificationOutbox,
    OTPChallenge,
    OneTimeToken,
    RefreshSession,
    StoredFile,
    User,
    UserRole,
)
from app.modules.auth.permissions import Permissions, role_has_permission
from app.modules.auth.providers import (
    DisabledProfileImageStorage,
    ProfileImageStorage,
)  # noqa: TC001
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    AdminRoleUpdateRequest,
    AdminUserCreateRequest,
    AdminUserDetail,
    AdminUserPage,
    AdminUserUpdateRequest,
    AuditLogPage,
    AuditLogPublic,
    AuthResult,
    ChangePasswordRequest,
    FileDownloadResult,
    FileResult,
    FileUploadRequest,
    FileUploadResult,
    LoginRequest,
    OTPRequest,
    OTPVerifyRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
    UserPublic,
)  # noqa: TC001
from app.worker.outbox import encrypt_payload

_PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
_OPAQUE_TOKEN_BYTES = 48
_MIN_AUTH_SECRET_LENGTH = 32


def hash_password(password: str) -> str:
    """Hash a password with the configured Argon2id implementation."""
    return _PASSWORDS.hash(password)


class AuthService:
    """Application service scoped to one PostgreSQL Unit of Work."""

    def __init__(
        self,
        uow: SQLAlchemyUnitOfWork,
        settings: AppSettings,
        *,
        profile_image_storage: ProfileImageStorage | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Bind use cases to request persistence and optional delivery ports."""
        self.uow = uow
        self.settings = settings
        self.repository = AuthRepository(uow.session)
        self.profile_image_storage = (
            profile_image_storage or DisabledProfileImageStorage()
        )
        self.request_id = request_id
        self.ip_address = ip_address

    @property
    def session(self) -> AsyncSession:
        """Expose the active Unit of Work session to repository adapters."""
        return self.uow.session

    def _require_enabled(self) -> str:
        secret = self.settings.AUTH_JWT_SECRET_KEY
        if not self.settings.AUTH_ENABLED or secret is None:
            raise ExternalServiceError("Authentication is not enabled for this service.")
        value = secret.get_secret_value().strip()
        if len(value) < _MIN_AUTH_SECRET_LENGTH:
            raise ExternalServiceError("Authentication is not configured safely.")
        return value

    async def _rate_limit(
        self,
        operation: str,
        identity: str,
        remote_address: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> None:
        raw_key = f"{operation}\0{identity}\0{remote_address}".encode()
        key_hash = hashlib.sha256(raw_key).hexdigest()
        allowed = await self.repository.consume_rate_limit(
            key_hash,
            limit=limit,
            window_seconds=window_seconds,
        )
        await self.uow.commit()
        if not allowed:
            raise ValidationError("Too many authentication attempts. Try again later.", code="RATE_LIMITED")

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _hash_otp(self, challenge_id: UUID, code: str) -> str:
        secret = self._require_enabled().encode()
        payload = f"otp:{challenge_id}:{code}".encode()
        return hmac.new(secret, payload, hashlib.sha256).hexdigest()

    def _validate_password(self, password: str) -> None:
        if len(password) < self.settings.AUTH_PASSWORD_MIN_LENGTH:
            raise ValidationError(
                f"Password must contain at least {self.settings.AUTH_PASSWORD_MIN_LENGTH} characters."
            )

    @staticmethod
    def _user_public(user: User) -> UserPublic:
        return UserPublic(
            id=user.id,
            email=user.email,
            username=user.username,
            mobile_number=user.mobile_number,
            role=user.role.value,
            is_active=user.is_active,
            is_verified=user.is_verified,
            profile_image_reference=user.profile_image_reference,
        )

    @staticmethod
    def _safe_audit_metadata(
        metadata: dict[str, str | int | bool | None] | None,
    ) -> dict[str, str | int | bool | None]:
        """Filter metadata to a small allowlist that cannot hold credentials."""
        safe_keys = {
            "reason",
            "field",
            "previous_role",
            "new_role",
            "session_count",
        }
        if not metadata:
            return {}
        safe: dict[str, str | int | bool | None] = {}
        for key, value in metadata.items():
            if key not in safe_keys:
                continue
            if isinstance(value, str):
                safe[key] = value[:128]
            elif isinstance(value, (int, bool)) or value is None:
                safe[key] = value
        return safe

    def _audit(
        self,
        *,
        action: str,
        target_type: str,
        target_id: UUID | str | None,
        outcome: str = "success",
        actor_id: UUID | None = None,
        metadata: dict[str, str | int | bool | None] | None = None,
    ) -> None:
        """Stage a safe append-only audit row in the active transaction."""
        self.repository.add_audit(
            AuditLog(
                actor_user_id=actor_id,
                action=action,
                target_type=target_type,
                target_id=str(target_id) if target_id is not None else None,
                request_id=self.request_id,
                ip_address=self.ip_address,
                outcome=outcome,
                safe_metadata=self._safe_audit_metadata(metadata),
            )
        )

    async def _enqueue_notification(
        self,
        *,
        kind: str,
        idempotency_key: str,
        payload: dict[str, str],
    ) -> None:
        """Stage encrypted delivery work in the current database transaction."""
        if not self.settings.BACKGROUND_JOBS_ENABLED:
            raise ExternalServiceError("Background notification delivery is unavailable.")
        await self.repository.add_outbox(
            NotificationOutbox(
                id=uuid4(),
                idempotency_key=idempotency_key,
                kind=kind,
                payload_ciphertext=encrypt_payload(self.settings, payload),
                status="pending",
                attempts=0,
                max_attempts=self.settings.CELERY_TASK_MAX_RETRIES + 1,
                available_at=datetime.now(UTC),
                request_id=self.request_id,
            )
        )

    async def queue_email_notification(
        self,
        *,
        email: str,
        subject: str,
        text_body: str,
        idempotency_key: str,
        html_body: str | None = None,
    ) -> None:
        """Queue an encrypted general email notification transactionally."""
        self._require_enabled()
        if not self.settings.AUTH_EMAIL_DELIVERY_ENABLED:
            raise ExternalServiceError("Email delivery is not configured.")
        normalized_key = idempotency_key.strip()
        if (
            not normalized_key
            or len(normalized_key) > 100
            or not email.strip()
            or not subject.strip()
            or not text_body.strip()
        ):
            raise ValidationError("Notification details are invalid.")
        await self._enqueue_notification(
            kind="email_notification",
            idempotency_key=f"email-notification:{normalized_key}",
            payload={
                "email": email.strip(),
                "subject": subject.strip(),
                "text_body": text_body,
                "html_body": html_body or "",
            },
        )
        await self.uow.commit()

    def _access_token(self, user: User) -> tuple[str, int]:
        secret = self._require_enabled()
        now = datetime.now(UTC)
        expires = now + timedelta(minutes=self.settings.AUTH_ACCESS_TOKEN_MINUTES)
        claims = {
            "sub": str(user.id),
            "typ": "access",
            "ver": user.token_version,
            "iat": now,
            "exp": expires,
            "jti": str(uuid4()),
        }
        token = jwt.encode(claims, secret, algorithm="HS256")
        return token, self.settings.AUTH_ACCESS_TOKEN_MINUTES * 60

    async def _issue_tokens(
        self,
        user: User,
        *,
        family_id: UUID | None = None,
    ) -> TokenPair:
        access_token, expires_in = self._access_token(user)
        refresh_token = secrets.token_urlsafe(_OPAQUE_TOKEN_BYTES)
        refresh_row = RefreshSession(
            user_id=user.id,
            family_id=family_id or uuid4(),
            token_hash=self._hash_token(refresh_token),
            expires_at=datetime.now(UTC)
            + timedelta(days=self.settings.AUTH_REFRESH_TOKEN_DAYS),
        )
        await self.repository.add_refresh(refresh_row)
        await self.uow.commit()
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )

    async def _auth_result(self, user: User) -> AuthResult:
        if not user.is_active:
            raise AuthenticationError("Invalid credentials.")
        tokens = await self._issue_tokens(user)
        return AuthResult(tokens=tokens, user=self._user_public(user))

    async def register(
        self,
        request: RegisterRequest,
        *,
        remote_address: str,
    ) -> UserPublic:
        """Create a normalized public account with the USER role."""
        self._require_enabled()
        self._validate_password(request.password)
        await self._rate_limit(
            "register",
            remote_address,
            remote_address,
            limit=self.settings.AUTH_LOGIN_RATE_LIMIT,
            window_seconds=self.settings.AUTH_LOGIN_RATE_WINDOW_SECONDS,
        )
        if await self.repository.identifier_exists(
            email=request.email,
            username=request.username,
        ):
            raise ConflictError("An account with these identifiers already exists.")
        user = User(
            id=uuid4(),
            email=request.email,
            username=request.username,
            password_hash=hash_password(request.password),
            role=UserRole.USER,
            is_active=True,
            is_verified=False,
        )
        self.repository.add_user(user)
        self._audit(
            action="account.registered",
            target_type="user",
            target_id=user.id,
            actor_id=user.id,
        )
        try:
            await self.uow.commit()
        except IntegrityError:
            await self.uow.rollback()
            raise ConflictError("An account with these identifiers already exists.") from None
        return self._user_public(user)

    async def login(
        self,
        request: LoginRequest,
        *,
        remote_address: str,
    ) -> AuthResult:
        """Authenticate an email or username and issue a token pair."""
        self._require_enabled()
        await self._rate_limit(
            "login",
            request.identifier,
            remote_address,
            limit=self.settings.AUTH_LOGIN_RATE_LIMIT,
            window_seconds=self.settings.AUTH_LOGIN_RATE_WINDOW_SECONDS,
        )
        user = await self.repository.user_by_identifier(request.identifier)
        valid_password = False
        if user is not None and user.password_hash:
            try:
                valid_password = _PASSWORDS.verify(user.password_hash, request.password)
            except (InvalidHashError, VerificationError, VerifyMismatchError):
                valid_password = False
        else:
            # Keep unknown and passwordless identifiers near the Argon2 cost of
            # a real password verification without a reusable dummy credential.
            _PASSWORDS.hash(request.password)
        if not valid_password or user is None or not user.is_active:
            self._audit(
                action="auth.login",
                target_type="user",
                target_id=user.id if user is not None else None,
                actor_id=user.id if user is not None else None,
                outcome="failure",
                metadata={"reason": "invalid_credentials"},
            )
            await self.uow.commit()
            raise AuthenticationError("Invalid credentials.")
        self._audit(
            action="auth.login",
            target_type="user",
            target_id=user.id,
            actor_id=user.id,
        )
        return await self._auth_result(user)

    async def request_otp(
        self,
        request: OTPRequest,
        *,
        remote_address: str,
        purpose: str = "login",
        user_id: UUID | None = None,
    ) -> UUID:
        """Create, persist, and deliver a purpose-bound mobile challenge."""
        self._require_enabled()
        if not self.settings.AUTH_SMS_DELIVERY_ENABLED:
            raise ExternalServiceError("SMS delivery is not configured.")
        await self._rate_limit(
            f"otp_{purpose}",
            request.mobile_number,
            remote_address,
            limit=self.settings.AUTH_OTP_RATE_LIMIT,
            window_seconds=self.settings.AUTH_OTP_RATE_WINDOW_SECONDS,
        )
        mobile_owner = await self.repository.user_by_mobile(request.mobile_number)
        user = mobile_owner
        if purpose == "mobile_verify":
            user = await self.repository.user_by_id(user_id or UUID(int=0))
            if user is None or not user.is_active:
                raise NotFoundError("Account or mobile number was not found.")
            if mobile_owner is not None and mobile_owner.id != user.id:
                raise ConflictError("This mobile number is already assigned to an account.")
        challenge_id = uuid4()
        code = f"{secrets.randbelow(1_000_000):06d}"
        challenge = OTPChallenge(
            id=challenge_id,
            mobile_number=request.mobile_number,
            user_id=user.id if user else user_id,
            purpose=purpose,
            code_hash=self._hash_otp(challenge_id, code),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=self.settings.AUTH_OTP_TTL_SECONDS),
            max_attempts=self.settings.AUTH_OTP_MAX_ATTEMPTS,
        )
        await self.repository.revoke_mobile_challenges(
            request.mobile_number,
            purpose,
            datetime.now(UTC),
        )
        self.repository.add_otp(challenge)
        await self._enqueue_notification(
            kind="sms_otp",
            idempotency_key=f"otp:{challenge_id}",
            payload={
                "mobile_number": request.mobile_number,
                "code": code,
            },
        )
        await self.uow.commit()
        return challenge_id

    async def verify_otp(
        self,
        request: OTPVerifyRequest,
        *,
        remote_address: str,
        purpose: str = "login",
        user_id: UUID | None = None,
    ) -> AuthResult | UserPublic:
        """Consume a valid mobile challenge for login or phone verification."""
        secret = self._require_enabled()
        await self._rate_limit(
            f"otp_verify_{purpose}",
            request.mobile_number,
            remote_address,
            limit=self.settings.AUTH_LOGIN_RATE_LIMIT,
            window_seconds=self.settings.AUTH_LOGIN_RATE_WINDOW_SECONDS,
        )
        challenge = await self.repository.otp_by_id(request.challenge_id)
        now = datetime.now(UTC)
        valid = (
            challenge is not None
            and challenge.mobile_number == request.mobile_number
            and challenge.purpose == purpose
            and challenge.consumed_at is None
            and challenge.revoked_at is None
            and challenge.expires_at > now
            and challenge.attempts < challenge.max_attempts
        )
        if not valid or challenge is None:
            self._audit(
                action="auth.otp.verify",
                target_type="otp_challenge",
                target_id=request.challenge_id,
                actor_id=user_id,
                outcome="failure",
                metadata={"reason": "invalid_or_expired"},
            )
            await self.uow.commit()
            raise AuthenticationError("The one-time code is invalid or expired.")
        if purpose == "mobile_verify" and challenge.user_id != user_id:
            self._audit(
                action="auth.otp.verify",
                target_type="otp_challenge",
                target_id=challenge.id,
                actor_id=user_id,
                outcome="failure",
                metadata={"reason": "invalid_or_expired"},
            )
            await self.uow.commit()
            raise AuthenticationError("The one-time code is invalid or expired.")
        challenge.attempts += 1
        expected_hash = hmac.new(
            secret.encode(),
            f"otp:{challenge.id}:{request.code}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(challenge.code_hash, expected_hash):
            if challenge.attempts >= challenge.max_attempts:
                challenge.revoked_at = now
            self._audit(
                action="auth.otp.verify",
                target_type="otp_challenge",
                target_id=challenge.id,
                actor_id=challenge.user_id,
                outcome="failure",
                metadata={"reason": "invalid_code"},
            )
            await self.uow.commit()
            raise AuthenticationError("The one-time code is invalid or expired.")
        challenge.consumed_at = now
        if purpose == "mobile_verify":
            user = await self.repository.user_by_id(challenge.user_id or UUID(int=0))
            if user is None or not user.is_active:
                await self.uow.commit()
                raise AuthenticationError("The one-time code is invalid or expired.")
            if await self.repository.identifier_exists(
                mobile_number=request.mobile_number,
                excluding_user_id=user.id,
            ):
                await self.uow.commit()
                raise ConflictError("This mobile number is already assigned to an account.")
            user.mobile_number = request.mobile_number
            user.is_verified = True
            self._audit(
                action="auth.mobile.verified",
                target_type="user",
                target_id=user.id,
                actor_id=user.id,
            )
            await self.uow.commit()
            return self._user_public(user)

        user = await self.repository.user_by_mobile(request.mobile_number)
        if user is None:
            user = User(
                id=uuid4(),
                mobile_number=request.mobile_number,
                role=UserRole.USER,
                is_active=True,
                is_verified=True,
                token_version=0,
            )
            self.repository.add_user(user)
            try:
                await self.session.flush()
            except IntegrityError:
                await self.uow.rollback()
                raise AuthenticationError(
                    "The one-time code is invalid or expired."
                ) from None
        if not user.is_active:
            self._audit(
                action="auth.otp.login",
                target_type="user",
                target_id=user.id,
                actor_id=user.id,
                outcome="failure",
                metadata={"reason": "inactive_account"},
            )
            await self.uow.commit()
            raise AuthenticationError("The one-time code is invalid or expired.")
        self._audit(
            action="auth.otp.login",
            target_type="user",
            target_id=user.id,
            actor_id=user.id,
        )
        return await self._auth_result(user)

    async def refresh(
        self,
        token: str,
        *,
        remote_address: str,
    ) -> TokenPair:
        """Rotate a refresh token and revoke its predecessor atomically."""
        self._require_enabled()
        await self._rate_limit(
            "refresh",
            self._hash_token(token),
            remote_address,
            limit=self.settings.AUTH_LOGIN_RATE_LIMIT,
            window_seconds=self.settings.AUTH_LOGIN_RATE_WINDOW_SECONDS,
        )
        row = await self.repository.refresh_by_hash(self._hash_token(token))
        now = datetime.now(UTC)
        if row is None:
            raise AuthenticationError("Refresh token is invalid or expired.")
        if row.revoked_at is not None or row.replaced_by_id is not None:
            await self.repository.revoke_family(row.family_id, now)
            await self.uow.commit()
            raise AuthenticationError("Refresh token reuse was detected.")
        if row.expires_at <= now:
            row.revoked_at = now
            await self.uow.commit()
            raise AuthenticationError("Refresh token is invalid or expired.")
        user = await self.repository.user_by_id(row.user_id)
        if user is None or not user.is_active:
            row.revoked_at = now
            await self.uow.commit()
            raise AuthenticationError("Refresh token is invalid or expired.")
        replacement_raw = secrets.token_urlsafe(_OPAQUE_TOKEN_BYTES)
        replacement = RefreshSession(
            user_id=user.id,
            family_id=row.family_id,
            token_hash=self._hash_token(replacement_raw),
            expires_at=now + timedelta(days=self.settings.AUTH_REFRESH_TOKEN_DAYS),
        )
        row.revoked_at = now
        await self.repository.add_refresh(replacement)
        row.replaced_by_id = replacement.id
        await self.uow.commit()
        access, expires_in = self._access_token(user)
        return TokenPair(
            access_token=access,
            refresh_token=replacement_raw,
            expires_in=expires_in,
        )

    async def logout(self, token: str) -> None:
        """Revoke one refresh session if it is still active."""
        row = await self.repository.refresh_by_hash(self._hash_token(token))
        if row is not None and row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
            self._audit(
                action="auth.session.revoked",
                target_type="session",
                target_id=row.id,
                actor_id=row.user_id,
            )
            await self.uow.commit()

    async def logout_all(self, user_id: UUID) -> None:
        """Revoke all refresh sessions and increment the access-token version."""
        revoked = await self.repository.revoke_user_sessions(user_id, datetime.now(UTC))
        user = await self.repository.user_by_id(user_id)
        if user is not None:
            user.token_version += 1
            self._audit(
                action="auth.sessions.revoked",
                target_type="user",
                target_id=user_id,
                actor_id=user_id,
                metadata={"session_count": revoked},
            )
        await self.uow.commit()

    async def authenticate_access_token(self, token: str) -> User:
        """Validate an access JWT and reload its active, current account."""
        secret = self._require_enabled()
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options={"require": ["exp", "iat", "sub", "typ", "jti"]},
            )
        except jwt.PyJWTError:
            raise AuthenticationError("Access token is invalid or expired.") from None
        if claims.get("typ") != "access":
            raise AuthenticationError("Access token is invalid or expired.")
        try:
            user_id = UUID(claims["sub"])
        except (KeyError, ValueError):
            raise AuthenticationError("Access token is invalid or expired.") from None
        user = await self.repository.user_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Access token is invalid or expired.")
        if claims.get("ver") != user.token_version:
            raise AuthenticationError("Access token is invalid or expired.")
        return user

    async def current_user(self, user_id: UUID) -> UserPublic:
        """Return a safe profile for an active account."""
        user = await self.repository.user_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Account is unavailable.")
        return self._user_public(user)

    async def request_password_reset(
        self,
        email: str,
        *,
        remote_address: str,
    ) -> None:
        """Request recovery delivery without disclosing account existence."""
        self._require_enabled()
        if not self.settings.AUTH_EMAIL_DELIVERY_ENABLED:
            raise ExternalServiceError("Email delivery is not configured.")
        await self._rate_limit(
            "password_reset",
            email,
            remote_address,
            limit=self.settings.AUTH_LOGIN_RATE_LIMIT,
            window_seconds=self.settings.AUTH_LOGIN_RATE_WINDOW_SECONDS,
        )
        user = await self.repository.user_by_email(email)
        if user is None or not user.is_active or user.password_hash is None:
            return
        try:
            await self._deliver_action_token(user, "password_reset")
        except ExternalServiceError:
            # Keep provider submission failures from revealing account existence.
            return

    async def request_email_verification(self, user_id: UUID) -> None:
        """Create and deliver a one-time email verification link."""
        self._require_enabled()
        if not self.settings.AUTH_EMAIL_DELIVERY_ENABLED:
            raise ExternalServiceError("Email delivery is not configured.")
        user = await self.repository.user_by_id(user_id)
        if user is None or not user.is_active or user.email is None or user.is_verified:
            raise NotFoundError("A verifiable email account was not found.")
        await self._rate_limit(
            "email_verify",
            str(user.id),
            "authenticated",
            limit=self.settings.AUTH_OTP_RATE_LIMIT,
            window_seconds=self.settings.AUTH_OTP_RATE_WINDOW_SECONDS,
        )
        await self._deliver_action_token(user, "email_verify")

    async def _deliver_action_token(self, user: User, purpose: str) -> None:
        if user.email is None:
            raise NotFoundError("A deliverable account email was not found.")
        now = datetime.now(UTC)
        await self.repository.revoke_action_tokens(user.id, purpose, now)
        token_id = uuid4()
        token_secret = secrets.token_urlsafe(_OPAQUE_TOKEN_BYTES)
        raw_token = f"{token_id}.{token_secret}"
        token = OneTimeToken(
            id=token_id,
            user_id=user.id,
            purpose=purpose,
            token_hash=self._hash_token(token_secret),
            expires_at=now
            + timedelta(seconds=self.settings.AUTH_ACTION_TOKEN_TTL_SECONDS),
            max_attempts=self.settings.AUTH_OTP_MAX_ATTEMPTS,
        )
        self.repository.add_action_token(token)
        self._audit(
            action=f"auth.{purpose}.requested",
            target_type="user",
            target_id=user.id,
            actor_id=user.id,
        )
        await self._enqueue_notification(
            kind="email_action",
            idempotency_key=f"email-action:{token_id}",
            payload={
                "email": user.email,
                "purpose": purpose,
                "token": raw_token,
            },
        )
        await self.uow.commit()

    async def _consume_action_token(self, raw_token: str, purpose: str) -> OneTimeToken:
        try:
            token_id_raw, token_secret = raw_token.split(".", maxsplit=1)
            token_id = UUID(token_id_raw)
        except ValueError:
            raise ValidationError("The action token is invalid or expired.") from None
        row = await self.repository.action_token_by_id(token_id)
        now = datetime.now(UTC)
        if row is None:
            raise ValidationError("The action token is invalid or expired.")
        row.attempts += 1
        valid_hash = hmac.compare_digest(
            row.token_hash,
            self._hash_token(token_secret),
        )
        if (
            not valid_hash
            or row.purpose != purpose
            or row.expires_at <= now
            or row.consumed_at is not None
            or row.revoked_at is not None
            or row.attempts > row.max_attempts
        ):
            if row.attempts >= row.max_attempts:
                row.revoked_at = now
            await self.uow.commit()
            raise ValidationError("The action token is invalid or expired.")
        return row

    async def verify_email(self, raw_token: str) -> UserPublic:
        """Consume one valid email-verification token."""
        self._require_enabled()
        row = await self._consume_action_token(raw_token, "email_verify")
        user = await self.repository.user_by_id(row.user_id)
        if user is None or not user.is_active:
            await self.uow.commit()
            raise ValidationError("The action token is invalid or expired.")
        row.consumed_at = datetime.now(UTC)
        user.is_verified = True
        await self.uow.commit()
        return self._user_public(user)

    async def reset_password(self, request: ResetPasswordRequest) -> None:
        """Consume a reset token, replace the password, and revoke sessions."""
        self._require_enabled()
        self._validate_password(request.new_password)
        row = await self._consume_action_token(request.token, "password_reset")
        user = await self.repository.user_by_id(row.user_id)
        if user is None or not user.is_active:
            await self.uow.commit()
            raise ValidationError("The action token is invalid or expired.")
        row.consumed_at = datetime.now(UTC)
        user.password_hash = hash_password(request.new_password)
        user.token_version += 1
        revoked = await self.repository.revoke_user_sessions(user.id, datetime.now(UTC))
        self._audit(
            action="auth.password.reset",
            target_type="user",
            target_id=user.id,
            actor_id=user.id,
        )
        self._audit(
            action="auth.sessions.revoked",
            target_type="user",
            target_id=user.id,
            actor_id=user.id,
            metadata={"session_count": revoked},
        )
        await self.uow.commit()

    async def change_password(
        self,
        user_id: UUID,
        request: ChangePasswordRequest,
    ) -> None:
        """Verify the current password and replace it, revoking old sessions."""
        self._require_enabled()
        self._validate_password(request.new_password)
        user = await self.repository.user_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Account is unavailable.")
        if user.password_hash is not None:
            valid = False
            if request.current_password is not None:
                try:
                    valid = _PASSWORDS.verify(user.password_hash, request.current_password)
                except (InvalidHashError, VerificationError, VerifyMismatchError):
                    valid = False
            if not valid:
                raise AuthenticationError("Current password is invalid.")
        user.password_hash = hash_password(request.new_password)
        user.token_version += 1
        revoked = await self.repository.revoke_user_sessions(user.id, datetime.now(UTC))
        self._audit(
            action="auth.password.changed",
            target_type="user",
            target_id=user.id,
            actor_id=user.id,
        )
        self._audit(
            action="auth.sessions.revoked",
            target_type="user",
            target_id=user.id,
            actor_id=user.id,
            metadata={"session_count": revoked},
        )
        await self.uow.commit()

    async def update_profile(
        self,
        user_id: UUID,
        request: ProfileUpdateRequest,
    ) -> UserPublic:
        """Update identifiers after normalization and uniqueness checks."""
        user = await self.repository.user_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Account is unavailable.")
        if await self.repository.identifier_exists(
            username=request.username,
            mobile_number=request.mobile_number,
            excluding_user_id=user_id,
        ):
            raise ConflictError("An account with these identifiers already exists.")
        changed: list[str] = []
        if request.username is not None:
            user.username = request.username
            changed.append("username")
        if request.mobile_number is not None and request.mobile_number != user.mobile_number:
            user.mobile_number = request.mobile_number
            user.is_verified = False
            changed.append("mobile_number")
        if changed:
            self._audit(
                action="account.profile.updated",
                target_type="user",
                target_id=user.id,
                actor_id=user.id,
                metadata={"field": ",".join(changed)},
            )
        try:
            await self.uow.commit()
        except IntegrityError:
            await self.uow.rollback()
            raise ConflictError(
                "An account with these identifiers already exists."
            ) from None
        return self._user_public(user)

    async def create_file_upload(
        self, user_id: UUID, request: FileUploadRequest
    ) -> FileUploadResult:
        """Create a size and type constrained upload for the current owner."""
        if not getattr(self.profile_image_storage, "available", True):
            raise ExternalServiceError("File storage is not configured.")
        user = await self.repository.user_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Account is unavailable.")
        if request.size > self.settings.AWS_S3_MAX_UPLOAD_BYTES:
            raise ValidationError("The file type or size is not supported.")
        upload_id = uuid4()
        upload = await self.profile_image_storage.create_upload(
            owner_id=user_id,
            upload_id=upload_id,
            category=request.category,
            content_type=request.content_type,
            size=request.size,
        )
        row = StoredFile(
            id=upload_id,
            owner_user_id=user_id,
            object_key=upload.key,
            category=request.category,
            content_type=request.content_type,
            expected_size=request.size,
        )
        self.session.add(row)
        await self.uow.commit()
        return FileUploadResult(
            upload_id=upload_id,
            url=upload.url,
            fields=upload.fields,
            expires_in=upload.expires_in,
        )

    async def complete_file_upload(self, user_id: UUID, upload_id: UUID) -> FileResult:
        """Verify the remote object before making it available in the API."""
        if not getattr(self.profile_image_storage, "available", True):
            raise ExternalServiceError("File storage is not configured.")
        row = await self.session.scalar(
            select(StoredFile)
            .where(StoredFile.id == upload_id, StoredFile.owner_user_id == user_id)
            .with_for_update()
        )
        if row is None:
            raise NotFoundError("File upload was not found.")
        if row.is_complete:
            return FileResult(
                id=row.id,
                category=row.category,
                content_type=row.content_type,
                size=row.actual_size or row.expected_size,
            )
        verified = await self.profile_image_storage.verify_upload(
            key=row.object_key,
            owner_id=user_id,
            upload_id=row.id,
            expected_type=row.content_type,
            expected_size=row.expected_size,
            category=row.category,
        )
        row.actual_size = verified.size
        row.etag = verified.etag
        row.is_complete = True
        row.completed_at = datetime.now(UTC)
        if row.category == "profile_image":
            user = await self.repository.user_by_id(user_id)
            if user is None or not user.is_active:
                raise AuthenticationError("Account is unavailable.")
            user.profile_image_reference = str(row.id)
        await self.uow.commit()
        return FileResult(
            id=row.id,
            category=row.category,
            content_type=row.content_type,
            size=row.actual_size,
        )

    async def file_download_url(
        self, user_id: UUID, file_id: UUID
    ) -> FileDownloadResult:
        """Return a short-lived URL only for a completed object owned by caller."""
        row = await self.session.scalar(
            select(StoredFile).where(
                StoredFile.id == file_id,
                StoredFile.owner_user_id == user_id,
                StoredFile.is_complete.is_(True),
            )
        )
        if row is None:
            raise NotFoundError("File was not found.")
        if not await self.profile_image_storage.exists(row.object_key):
            raise NotFoundError("File was not found.")
        return FileDownloadResult(
            url=await self.profile_image_storage.temporary_download_url(row.object_key),
            expires_in=self.settings.AWS_S3_DOWNLOAD_URL_TTL_SECONDS,
        )

    async def delete_file(self, user_id: UUID, file_id: UUID) -> None:
        """Delete only a completed object belonging to the authenticated owner."""
        row = await self.session.scalar(
            select(StoredFile)
            .where(StoredFile.id == file_id, StoredFile.owner_user_id == user_id)
            .with_for_update()
        )
        if row is None:
            raise NotFoundError("File was not found.")
        await self.profile_image_storage.delete(row.object_key)
        if row.category == "profile_image":
            user = await self.repository.user_by_id(user_id)
            if user is not None and user.profile_image_reference == str(row.id):
                user.profile_image_reference = None
        await self.session.delete(row)
        await self.uow.commit()

    async def admin_list_users(
        self,
        actor_id: UUID,
        *,
        search: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str | None = None,
        sort_order: str = "desc",
    ) -> AdminUserPage:  # noqa: PLR0913
        """Return a filtered, bounded page of users for an authorized actor."""
        await self._admin_actor(actor_id, Permissions.USERS_READ)
        users, total = await self.repository.list_users(
            search=search,
            role=role,
            is_active=is_active,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return AdminUserPage(
            items=[self._admin_user_detail(user) for user in users],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def admin_get_user(self, actor_id: UUID, user_id: UUID) -> AdminUserDetail:
        """Return one user record to an authorized administrator."""
        await self._admin_actor(actor_id, Permissions.USERS_READ)
        user = await self.repository.user_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return self._admin_user_detail(user)

    async def admin_create_user(
        self, actor_id: UUID, payload: AdminUserCreateRequest
    ) -> AdminUserDetail:
        """Create a user and audit the action in the same transaction."""
        await self.repository.lock_admin_mutations()
        actor = await self._admin_actor(actor_id, Permissions.USERS_CREATE)
        if payload.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN} and actor.role != UserRole.SUPER_ADMIN:
            raise AuthorizationError("Only a super administrator can assign administrative roles")
        email = str(payload.email)
        username = payload.username
        if await self.repository.user_by_email(email) or await self.repository.user_by_username(username):
            raise ConflictError("An account with those identifiers already exists")
        user = User(
            id=uuid4(),
            email=email,
            username=username,
            mobile_number=payload.mobile_number,
            password_hash=hash_password(payload.password) if payload.password else None,
            role=payload.role,
            is_active=True,
            is_verified=False,
        )
        self.repository.add_user(user)
        self._audit(
            action="admin.user.created",
            target_type="user",
            target_id=user.id,
            actor_id=actor.id,
            metadata={"new_role": user.role.value},
        )
        try:
            await self.uow.commit()
        except IntegrityError as exc:
            await self.uow.rollback()
            raise ConflictError("An account with those identifiers already exists") from exc
        return self._admin_user_detail(user)

    async def admin_update_user(
        self, actor_id: UUID, user_id: UUID, payload: AdminUserUpdateRequest
    ) -> AdminUserDetail:
        """Update validated identifiers without accepting role or status fields."""
        await self.repository.lock_admin_mutations()
        actor = await self._admin_actor(actor_id, Permissions.USERS_UPDATE)
        user = await self.repository.user_by_id_for_update(user_id)
        self._require_user(user)
        self._guard_elevated_target(actor, user)
        changed: list[str] = []
        if payload.email is not None:
            user.email = str(payload.email)
            user.is_verified = False
            await self.repository.revoke_action_tokens(
                user.id, "email_verify", datetime.now(UTC)
            )
            changed.append("email")
        if payload.username is not None:
            user.username = payload.username
            changed.append("username")
        if payload.mobile_number is not None:
            user.mobile_number = payload.mobile_number
            user.is_verified = False
            changed.append("mobile_number")
        self._audit(
            action="admin.user.updated",
            target_type="user",
            target_id=user.id,
            actor_id=actor.id,
            metadata={"field": ",".join(changed)},
        )
        try:
            await self.uow.commit()
        except IntegrityError as exc:
            await self.uow.rollback()
            raise ConflictError("An account with those identifiers already exists") from exc
        return self._admin_user_detail(user)

    async def admin_set_role(
        self, actor_id: UUID, user_id: UUID, role: UserRole
    ) -> AdminUserDetail:
        """Change a user's role while protecting the last super administrator."""
        await self.repository.lock_admin_mutations()
        actor = await self._admin_actor(actor_id, Permissions.USERS_ASSIGN_ROLE)
        user = await self.repository.user_by_id_for_update(user_id)
        self._require_user(user)
        self._guard_elevated_target(actor, user)
        if role in {UserRole.ADMIN, UserRole.SUPER_ADMIN} and actor.role != UserRole.SUPER_ADMIN:
            raise AuthorizationError("Only a super administrator can assign administrative roles")
        if user.id == actor.id and role != user.role:
            raise ConflictError("Administrators cannot change their own role")
        previous_role = user.role
        if previous_role == role:
            return self._admin_user_detail(user)
        if previous_role == UserRole.SUPER_ADMIN and role != UserRole.SUPER_ADMIN:
            if await self.repository.active_super_admin_count() <= 1:
                raise ConflictError("Cannot remove the last active super administrator")
        user.role = role
        user.token_version += 1
        revoked = await self.repository.revoke_user_sessions(user.id, datetime.now(UTC))
        self._audit(
            action="admin.user.role_changed",
            target_type="user",
            target_id=user.id,
            actor_id=actor.id,
            metadata={"previous_role": previous_role.value, "new_role": role.value},
        )
        self._audit(
            action="admin.user.sessions_revoked",
            target_type="user",
            target_id=user.id,
            actor_id=actor.id,
            metadata={"session_count": revoked},
        )
        await self.uow.commit()
        return self._admin_user_detail(user)

    async def admin_set_active(
        self, actor_id: UUID, user_id: UUID, is_active: bool
    ) -> AdminUserDetail:
        """Change account status and revoke sessions when disabling an account."""
        await self.repository.lock_admin_mutations()
        actor = await self._admin_actor(actor_id, Permissions.USERS_STATUS)
        user = await self.repository.user_by_id_for_update(user_id)
        self._require_user(user)
        self._guard_elevated_target(actor, user)
        if user.id == actor.id and not is_active:
            raise ConflictError("Administrators cannot deactivate their own account")
        if user.is_active == is_active:
            return self._admin_user_detail(user)
        if user.role == UserRole.SUPER_ADMIN and user.is_active and not is_active:
            if await self.repository.active_super_admin_count() <= 1:
                raise ConflictError("Cannot deactivate the last active super administrator")
        user.is_active = is_active
        session_count = 0
        if not is_active:
            user.token_version += 1
            session_count = await self.repository.revoke_user_sessions(user.id, datetime.now(UTC))
        self._audit(
            action="admin.user.activated" if is_active else "admin.user.deactivated",
            target_type="user",
            target_id=user.id,
            actor_id=actor.id,
        )
        if session_count:
            self._audit(
                action="admin.user.sessions_revoked",
                target_type="user",
                target_id=user.id,
                actor_id=actor.id,
                metadata={"session_count": session_count},
            )
        await self.uow.commit()
        return self._admin_user_detail(user)

    async def admin_revoke_sessions(self, actor_id: UUID, user_id: UUID) -> int:
        """Immediately invalidate access and refresh sessions for one user."""
        await self.repository.lock_admin_mutations()
        actor = await self._admin_actor(actor_id, Permissions.USERS_REVOKE_SESSIONS)
        user = await self.repository.user_by_id_for_update(user_id)
        self._require_user(user)
        self._guard_elevated_target(actor, user)
        user.token_version += 1
        count = await self.repository.revoke_user_sessions(user.id, datetime.now(UTC))
        self._audit(
            action="admin.user.sessions_revoked",
            target_type="user",
            target_id=user.id,
            actor_id=actor.id,
            metadata={"session_count": count},
        )
        await self.uow.commit()
        return count

    async def admin_audit_logs(
        self,
        actor_id: UUID,
        *,
        target_user_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
        activity: bool = False,
    ) -> AuditLogPage:  # noqa: PLR0913
        """Return paginated audit events for an authorized administrator."""
        required_permission = (
            Permissions.USER_ACTIVITY_READ if activity else Permissions.AUDIT_READ
        )
        await self._admin_actor(actor_id, required_permission)
        if activity and target_user_id is not None:
            entries, total = await self.repository.list_user_activity(target_user_id, limit=limit, offset=offset)
        else:
            entries, total = await self.repository.list_audit_logs(target_user_id=target_user_id, actor_user_id=actor_user_id, limit=limit, offset=offset)
        return AuditLogPage(
            items=[
                AuditLogPublic(
                    id=entry.id,
                    actor_user_id=entry.actor_user_id,
                    action=entry.action,
                    target_type=entry.target_type,
                    target_id=entry.target_id,
                    request_id=entry.request_id,
                    ip_address=entry.ip_address,
                    outcome=entry.outcome,
                    metadata=entry.safe_metadata,
                    created_at=entry.created_at,
                )
                for entry in entries
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def _admin_actor(self, actor_id: UUID, permission: str) -> User:
        actor = await self.repository.user_by_id(actor_id)
        self._require_user(actor)
        if not actor.is_active or not role_has_permission(actor.role, permission):
            raise AuthorizationError("Insufficient permission")
        return actor

    @staticmethod
    def _require_user(user: User | None) -> User:
        if user is None:
            raise NotFoundError("User not found")
        return user

    @staticmethod
    def _guard_elevated_target(actor: User, target: User) -> None:
        if target.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN} and actor.role != UserRole.SUPER_ADMIN:
            raise AuthorizationError("Only a super administrator can manage administrators")

    @staticmethod
    def _admin_user_detail(user: User) -> AdminUserDetail:
        return AdminUserDetail(
            id=user.id,
            email=user.email,
            username=user.username,
            mobile_number=user.mobile_number,
            role=user.role,
            is_active=user.is_active,
            is_verified=user.is_verified,
            profile_image_reference=user.profile_image_reference,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    async def deactivate_account(self, user_id: UUID) -> None:
        """Deactivate an account and revoke its refresh sessions."""
        await self.repository.lock_admin_mutations()
        user = await self.repository.user_by_id(user_id)
        if user is None or not user.is_active:
            raise NotFoundError("Account was not found.")
        if user.role in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
            raise ConflictError("Administrators cannot deactivate their own account.")
        user.is_active = False
        user.token_version += 1
        revoked = await self.repository.revoke_user_sessions(user.id, datetime.now(UTC))
        self._audit(
            action="account.deactivated",
            target_type="user",
            target_id=user.id,
            actor_id=user.id,
        )
        self._audit(
            action="auth.sessions.revoked",
            target_type="user",
            target_id=user.id,
            actor_id=user.id,
            metadata={"session_count": revoked},
        )
        await self.uow.commit()

    async def require_admin(self, user_id: UUID) -> User:
        """Return an active administrator or raise an authorization error."""
        user = await self.repository.user_by_id(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Account is unavailable.")
        if user.role not in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
            raise AuthorizationError()
        return user


__all__ = ["AuthService", "hash_password"]
