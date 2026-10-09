"""Batched authentication and outbox retention jobs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.uow import SQLAlchemyUnitOfWork
from app.modules.auth.models import (
    NotificationOutbox,
    OneTimeToken,
    OTPChallenge,
    RefreshSession,
)
from app.worker.celery_app import celery_app
from app.worker.runtime import worker_runtime

logger = get_logger(__name__)


async def _delete_expired(model, predicate, batch_size: int) -> int:
    total = 0
    while True:
        uow = worker_runtime.create_uow()
        async with uow:
            ids = (
                select(model.id)
                .where(predicate)
                .order_by(model.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            result = await uow.session.execute(
                delete(model).where(model.id.in_(ids))
            )
            count = result.rowcount or 0
        total += count
        if count < batch_size:
            return total


@celery_app.task(
    name="app.worker.tasks.maintenance.cleanup_auth_state",
    ignore_result=True,
)
def cleanup_auth_state() -> dict[str, int]:
    """Delete expired authentication state in bounded PostgreSQL batches."""
    settings = get_settings()
    now = datetime.now(UTC)
    revoked_before = now - timedelta(days=settings.AUTH_SESSION_RETENTION_DAYS)

    async def cleanup() -> dict[str, int]:
        return {
            "expired_otp_challenges": await _delete_expired(
                OTPChallenge,
                OTPChallenge.expires_at < now,
                settings.CELERY_CLEANUP_BATCH_SIZE,
            ),
            "expired_action_tokens": await _delete_expired(
                OneTimeToken,
                OneTimeToken.expires_at < now,
                settings.CELERY_CLEANUP_BATCH_SIZE,
            ),
            "expired_or_old_revoked_sessions": await _delete_expired(
                RefreshSession,
                (RefreshSession.expires_at < now)
                | (RefreshSession.revoked_at < revoked_before),
                settings.CELERY_CLEANUP_BATCH_SIZE,
            ),
        }

    counts = worker_runtime.run(cleanup())
    logger.info("Authentication state cleanup completed", extra=counts)
    return counts


@celery_app.task(
    name="app.worker.tasks.maintenance.recover_stale_outbox",
    ignore_result=True,
)
def recover_stale_outbox() -> dict[str, int]:
    """Release expired worker leases and trim old terminal outbox rows."""
    settings = get_settings()
    now = datetime.now(UTC)
    lease_before = now - timedelta(seconds=settings.CELERY_OUTBOX_LEASE_SECONDS)
    terminal_before = now - timedelta(days=settings.CELERY_OUTBOX_RETENTION_DAYS)

    async def recover() -> dict[str, int]:
        uow = worker_runtime.create_uow()
        async with uow:
            result = await uow.session.scalars(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.status == "processing",
                    NotificationOutbox.locked_at < lease_before,
                )
                .order_by(NotificationOutbox.locked_at)
                .limit(settings.CELERY_CLEANUP_BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
            stale = list(result.all())
            retried = 0
            failed = 0
            for job in stale:
                job.worker_started_at = None
                job.locked_at = None
                job.last_error = "WorkerLeaseExpired"
                if job.attempts >= job.max_attempts:
                    job.status = "failed"
                    failed += 1
                else:
                    job.status = "pending"
                    job.available_at = now
                    retried += 1
        deleted = await _delete_expired(
            NotificationOutbox,
            (NotificationOutbox.status.in_(("completed", "failed")))
            & (NotificationOutbox.created_at < terminal_before),
            settings.CELERY_CLEANUP_BATCH_SIZE,
        )
        return {"retried": retried, "failed": failed, "deleted": deleted}

    counts = worker_runtime.run(recover())
    logger.info("Outbox lease recovery completed", extra=counts)
    return counts


__all__ = ["cleanup_auth_state", "recover_stale_outbox"]
