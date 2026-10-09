"""SQLAlchemy repository for accounts and authentication state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID  # noqa: TC003

from sqlalchemy import case, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.common.filters import apply_dynamic_filters, apply_prefix_search
from app.common.pagination import PaginationParams, apply_pagination, paginate_scalars
from app.common.sorting import SortOrder, apply_default_sort, apply_sorting
from app.modules.auth.models import (
    AuditLog,
    AuthRateLimit,
    NotificationOutbox,
    OTPChallenge,
    OneTimeToken,
    RefreshSession,
    User,
    UserRole,
)


class AuthRepository:
    """Persistence operations scoped to one request Unit of Work session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind repository operations to the current request session."""
        self.session = session

    async def user_by_id(self, user_id: UUID) -> User | None:
        """Load an account by its UUID."""
        return await self.session.get(User, user_id)

    async def user_by_id_for_update(self, user_id: UUID) -> User | None:
        """Load and lock an account before a sensitive administrative update."""
        return await self.session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )

    async def user_by_identifier(self, identifier: str) -> User | None:
        """Find an account by normalized email or username."""
        result = await self.session.scalar(
            select(User).where(
                or_(User.email == identifier, User.username == identifier)
            )
        )
        return result

    async def user_by_email(self, email: str) -> User | None:
        """Find an account by normalized email."""
        return await self.session.scalar(select(User).where(User.email == email))

    async def user_by_username(self, username: str) -> User | None:
        """Find an account by normalized username."""
        return await self.session.scalar(
            select(User).where(User.username == username)
        )

    async def user_by_mobile(self, mobile_number: str) -> User | None:
        """Find an account by E.164 mobile number."""
        return await self.session.scalar(
            select(User).where(User.mobile_number == mobile_number)
        )

    async def admin_exists(self) -> bool:
        """Return whether any administrator account exists."""
        result = await self.session.scalar(
            select(User.id)
            .where(User.role.in_((UserRole.ADMIN, UserRole.SUPER_ADMIN)))
            .limit(1)
        )
        return result is not None

    async def lock_first_admin_bootstrap(self) -> None:
        """Serialize first-admin creation across concurrent CLI invocations."""
        await self.session.execute(text("SELECT pg_advisory_xact_lock(613470922)"))

    async def super_admin_exists(self) -> bool:
        """Return whether an active SUPER_ADMIN already exists."""
        result = await self.session.scalar(
            select(User.id)
            .where(User.role == UserRole.SUPER_ADMIN, User.is_active.is_(True))
            .limit(1)
        )
        return result is not None

    async def lock_admin_mutations(self) -> None:
        """Serialize role/status changes that could remove the last super admin."""
        await self.session.execute(text("SELECT pg_advisory_xact_lock(613470922)"))

    async def identifier_exists(
        self,
        *,
        email: str | None = None,
        username: str | None = None,
        mobile_number: str | None = None,
        excluding_user_id: UUID | None = None,
    ) -> bool:
        """Check normalized identifiers, optionally excluding one account."""
        filters = []
        if email is not None:
            filters.append(User.email == email)
        if username is not None:
            filters.append(User.username == username)
        if mobile_number is not None:
            filters.append(User.mobile_number == mobile_number)
        query = select(User.id).where(or_(*filters))
        if excluding_user_id is not None:
            query = query.where(User.id != excluding_user_id)
        return await self.session.scalar(query.limit(1)) is not None

    def add_user(self, user: User) -> None:
        """Stage a new account in the current transaction."""
        self.session.add(user)

    async def refresh_by_hash(self, token_hash: str) -> RefreshSession | None:
        """Load and lock refresh-session state by token digest."""
        return await self.session.scalar(
            select(RefreshSession)
            .where(RefreshSession.token_hash == token_hash)
            .with_for_update()
        )

    async def add_refresh(self, token: RefreshSession) -> None:
        """Stage and flush a refresh session to obtain its generated ID."""
        self.session.add(token)
        await self.session.flush()

    async def revoke_user_sessions(self, user_id: UUID, now: datetime) -> int:
        """Revoke every active refresh session owned by an account."""
        result = await self.session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        return result.rowcount or 0

    async def active_super_admin_count(self) -> int:
        """Count active SUPER_ADMIN accounts under the admin mutation lock."""
        return int(
            await self.session.scalar(
                select(func.count(User.id)).where(
                    User.role == UserRole.SUPER_ADMIN,
                    User.is_active.is_(True),
                )
            )
            or 0
        )

    async def list_users(
        self,
        *,
        search: str | None,
        role: UserRole | None,
        is_active: bool | None,
        limit: int,
        offset: int,
        sort_by: str | None = None,
        sort_order: str | SortOrder = SortOrder.DESC,
    ) -> tuple[list[User], int]:
        """Search users with shared filtering, sorting, and pagination helpers."""
        params = PaginationParams(limit=limit, offset=offset)

        def filtered(statement):
            """Apply the same allow-listed filters to count and data queries."""
            statement = apply_dynamic_filters(
                statement,
                filters={"role": role, "is_active": is_active},
                allowed_filters={"role": User.role, "is_active": User.is_active},
                boolean_fields={"is_active"},
            )
            return apply_prefix_search(
                statement,
                search=search,
                columns=(User.email, User.username, User.mobile_number),
                max_length=100,
            )

        total = int(
            await self.session.scalar(
                filtered(select(func.count(User.id)))
            )
            or 0
        )
        query = filtered(select(User))
        if sort_by is None:
            query = apply_default_sort(
                query,
                default_column=User.created_at,
                default_order=sort_order,
            )
        else:
            query = apply_sorting(
                query,
                sort_by=sort_by,
                sort_order=sort_order,
                allowed_fields={
                    "created_at": User.created_at,
                    "email": User.email,
                    "username": User.username,
                    "role": User.role,
                },
            )
        query = apply_pagination(query.order_by(User.id.asc()), params=params)
        result = await self.session.scalars(query)
        return list(result.all()), total

    async def list_audit_logs(
        self,
        *,
        target_user_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[AuditLog], int]:
        """Return paginated audit rows filtered by target and/or actor."""
        params = PaginationParams(limit=limit, offset=offset)
        filters = []
        if target_user_id is not None:
            filters.extend(
                [
                    AuditLog.target_type == "user",
                    AuditLog.target_id == str(target_user_id),
                ]
            )
        if actor_user_id is not None:
            filters.append(AuditLog.actor_user_id == actor_user_id)
        page = await paginate_scalars(
            session=self.session,
            data_statement=(
                select(AuditLog)
                .where(*filters)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            ),
            count_statement=select(func.count(AuditLog.id)).where(*filters),
            params=params,
        )
        return page.items, page.pagination.total_count

    async def list_user_activity(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> tuple[list[AuditLog], int]:
        """Return events where a user was the actor or target."""
        params = PaginationParams(limit=limit, offset=offset)
        predicate = or_(
            (AuditLog.target_type == "user") & (AuditLog.target_id == str(user_id)),
            AuditLog.actor_user_id == user_id,
        )
        page = await paginate_scalars(
            session=self.session,
            data_statement=(
                select(AuditLog)
                .where(predicate)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            ),
            count_statement=(
                select(func.count()).select_from(AuditLog).where(predicate)
            ),
            params=params,
        )
        return page.items, page.pagination.total_count

    def add_audit(self, entry: AuditLog) -> None:
        """Stage an append-only audit row; no update/delete API is exposed."""
        self.session.add(entry)

    async def add_outbox(self, job: NotificationOutbox) -> bool:
        """Insert one encrypted notification job with idempotency protection."""
        statement = (
            insert(NotificationOutbox)
            .values(
                id=job.id,
                idempotency_key=job.idempotency_key,
                kind=job.kind,
                payload_ciphertext=job.payload_ciphertext,
                status=job.status,
                attempts=job.attempts,
                max_attempts=job.max_attempts,
                available_at=job.available_at,
                request_id=job.request_id,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
        )
        result = await self.session.execute(statement)
        return bool(result.rowcount)

    async def outbox_by_id_for_update(
        self, job_id: UUID
    ) -> NotificationOutbox | None:
        """Lock one outbox job while claiming or completing it."""
        return await self.session.scalar(
            select(NotificationOutbox)
            .where(NotificationOutbox.id == job_id)
            .with_for_update()
        )

    async def revoke_family(self, family_id: UUID, now: datetime) -> None:
        """Revoke every active refresh token in a rotated token family."""
        await self.session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.family_id == family_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    async def action_token_by_hash(self, token_hash: str) -> OneTimeToken | None:
        """Load an action token by digest."""
        return await self.session.scalar(
            select(OneTimeToken)
            .where(OneTimeToken.token_hash == token_hash)
            .with_for_update()
        )

    async def action_token_by_id(self, token_id: UUID) -> OneTimeToken | None:
        """Load and lock action-token attempt state by its public identifier."""
        return await self.session.scalar(
            select(OneTimeToken)
            .where(OneTimeToken.id == token_id)
            .with_for_update()
        )

    async def revoke_action_tokens(
        self,
        user_id: UUID,
        purpose: str,
        now: datetime,
    ) -> None:
        """Revoke all outstanding action tokens for one purpose."""
        await self.session.execute(
            update(OneTimeToken)
            .where(
                OneTimeToken.user_id == user_id,
                OneTimeToken.purpose == purpose,
                OneTimeToken.consumed_at.is_(None),
                OneTimeToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    def add_action_token(self, token: OneTimeToken) -> None:
        """Stage a one-time action token."""
        self.session.add(token)

    async def otp_by_id(self, challenge_id: UUID) -> OTPChallenge | None:
        """Load and lock an OTP challenge for one-time verification."""
        return await self.session.scalar(
            select(OTPChallenge)
            .where(OTPChallenge.id == challenge_id)
            .with_for_update()
        )

    async def revoke_mobile_challenges(
        self,
        mobile_number: str,
        purpose: str,
        now: datetime,
    ) -> None:
        """Revoke outstanding challenges for one phone and purpose."""
        await self.session.execute(
            update(OTPChallenge)
            .where(
                OTPChallenge.mobile_number == mobile_number,
                OTPChallenge.purpose == purpose,
                OTPChallenge.consumed_at.is_(None),
                OTPChallenge.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    def add_otp(self, challenge: OTPChallenge) -> None:
        """Stage a hashed one-time challenge."""
        self.session.add(challenge)

    async def consume_rate_limit(
        self,
        key_hash: str,
        *,
        limit: int,
        window_seconds: int,
        now: datetime | None = None,
    ) -> bool:
        """Atomically consume one fixed-window request across processes."""
        current_time = now or datetime.now(UTC)
        cutoff = current_time - timedelta(seconds=window_seconds)
        await self.session.execute(
            delete(AuthRateLimit).where(
                AuthRateLimit.window_started_at < current_time - timedelta(days=1)
            )
        )
        expired = AuthRateLimit.window_started_at < cutoff
        statement = (
            insert(AuthRateLimit)
            .values(
                key_hash=key_hash,
                window_started_at=current_time,
                hits=1,
            )
            .on_conflict_do_update(
                index_elements=[AuthRateLimit.key_hash],
                set_={
                    "window_started_at": case(
                        (expired, current_time),
                        else_=AuthRateLimit.window_started_at,
                    ),
                    "hits": case(
                        (expired, 1),
                        else_=AuthRateLimit.hits + 1,
                    ),
                },
            )
            .returning(AuthRateLimit.hits)
        )
        hits = await self.session.scalar(statement)
        return bool(hits is not None and hits <= limit)


__all__ = ["AuthRepository"]
