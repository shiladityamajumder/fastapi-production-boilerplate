"""Encrypted, retryable notification outbox delivery tasks."""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime, timedelta
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from celery import Task
from sqlalchemy import select

from app.common.exceptions import ExternalServiceError
from app.core.config import AppSettings, get_settings
from app.core.logging import get_logger
from app.db.uow import SQLAlchemyUnitOfWork
from app.modules.auth.aws import AWSSMSDelivery, SESEmailDelivery
from app.modules.auth.models import NotificationOutbox
from app.worker.celery_app import celery_app
from app.worker.outbox import decrypt_payload
from app.worker.runtime import worker_runtime

logger = get_logger(__name__)


async def _run_uow(work):
    uow = worker_runtime.create_uow()
    async with uow:
        return await work(uow)


async def _claim_job(job_id: UUID):
    async def claim(uow: SQLAlchemyUnitOfWork):
        job = await uow.session.scalar(
            select(NotificationOutbox)
            .where(NotificationOutbox.id == job_id)
            .with_for_update()
        )
        if job is None or job.status in {"completed", "failed"}:
            return None
        if job.status == "pending" and job.available_at > datetime.now(UTC):
            return None
        if job.status == "processing" and job.worker_started_at is not None:
            return None
        if job.attempts >= job.max_attempts:
            job.status = "failed"
            job.last_error = "RetryLimitReached"
            job.locked_at = None
            return None
        job.status = "processing"
        job.worker_started_at = datetime.now(UTC)
        job.locked_at = job.worker_started_at
        job.attempts += 1
        return (
            job.kind,
            job.payload_ciphertext,
            job.attempts,
            job.max_attempts,
            job.request_id,
        )

    return await _run_uow(claim)


def _retryable(error: Exception) -> bool:
    cause = error.__cause__ or error
    if isinstance(cause, (BotoCoreError, OSError, TimeoutError)):
        return True
    if isinstance(cause, ClientError):
        response = cause.response
        status_code = response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        code = response.get("Error", {}).get("Code", "")
        return status_code >= 500 or status_code == 429 or code in {
            "ThrottlingException",
            "Throttling",
            "TooManyRequestsException",
            "ServiceUnavailable",
            "RequestTimeout",
        }
    return False


async def _deliver(settings: AppSettings, kind: str, payload: dict[str, object]) -> None:
    if kind == "sms_otp":
        if not settings.AUTH_SMS_DELIVERY_ENABLED:
            raise ValueError("SMS delivery is disabled")
        provider = await asyncio.to_thread(AWSSMSDelivery, settings)
        await provider.send_code(
            str(payload["mobile_number"]), str(payload["code"])
        )
        return
    if kind == "email_action":
        if not settings.AUTH_EMAIL_DELIVERY_ENABLED:
            raise ValueError("Email delivery is disabled")
        provider = await asyncio.to_thread(SESEmailDelivery, settings)
        await provider.send_action_link(
            str(payload["email"]),
            str(payload["purpose"]),
            str(payload["token"]),
        )
        return
    if kind == "email_notification":
        if not settings.AUTH_EMAIL_DELIVERY_ENABLED:
            raise ValueError("Email delivery is disabled")
        provider = await asyncio.to_thread(SESEmailDelivery, settings)
        await provider.send_notification(
            str(payload["email"]),
            str(payload["subject"]),
            str(payload["text_body"]),
            str(payload["html_body"]) if payload.get("html_body") else None,
        )
        return
    raise ValueError("Unsupported notification type")


async def _record_result(
    job_id: UUID,
    *,
    status: str,
    error_type: str | None = None,
    delay_seconds: float = 0,
) -> None:
    async def record(uow: SQLAlchemyUnitOfWork) -> None:
        job = await uow.session.scalar(
            select(NotificationOutbox)
            .where(NotificationOutbox.id == job_id)
            .with_for_update()
        )
        if job is None or job.status in {"completed", "failed"}:
            return
        job.status = status
        job.worker_started_at = None
        job.locked_at = None
        job.last_error = error_type
        if status == "completed":
            job.completed_at = datetime.now(UTC)
        elif status == "pending":
            job.available_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)

    await _run_uow(record)


async def _recover_unpublished(
    jobs: list[tuple[UUID, int]], published: set[UUID], error: Exception
) -> None:
    """Return broker-unpublished rows to the durable pending queue."""

    async def recover(uow: SQLAlchemyUnitOfWork) -> None:
        rows = await uow.session.scalars(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.id.in_(
                    [job_id for job_id, _ in jobs if job_id not in published]
                ),
                NotificationOutbox.status == "processing",
                NotificationOutbox.worker_started_at.is_(None),
            )
            .with_for_update(skip_locked=True)
        )
        for row in rows.all():
            row.status = "pending"
            row.locked_at = None
            row.last_error = type(error).__name__

    await _run_uow(recover)


@celery_app.task(
    bind=True,
    name="app.worker.tasks.notifications.process_outbox_job",
    ignore_result=True,
)
def process_outbox_job(task: Task, job_id: str) -> str:
    """Claim and deliver one encrypted job with bounded database retries."""
    del task
    parsed_id = UUID(job_id)
    settings = get_settings()
    claimed = worker_runtime.run(_claim_job(parsed_id))
    if claimed is None:
        logger.info("Notification job skipped", extra={"job_id": job_id})
        return "skipped"
    kind, ciphertext, attempt, max_attempts, request_id = claimed
    try:
        payload = decrypt_payload(settings, ciphertext)
        worker_runtime.run(_deliver(settings, kind, payload))
    except Exception as exc:
        retry = _retryable(exc) and attempt < max_attempts
        delay = min(900.0, 2.0 ** max(0, attempt - 1)) * random.uniform(0.5, 1.5)
        worker_runtime.run(
            _record_result(
                parsed_id,
                status="pending" if retry else "failed",
                error_type=type(exc).__name__,
                delay_seconds=delay,
            )
        )
        logger.warning(
            "Notification job delivery failed",
            extra={
                "job_id": job_id,
                "kind": kind,
                "request_id": request_id,
                "attempt": attempt,
                "retry_scheduled": retry,
                "error_type": type(exc).__name__,
            },
        )
        return "pending" if retry else "failed"
    worker_runtime.run(_record_result(parsed_id, status="completed"))
    logger.info(
        "Notification job completed",
        extra={
            "job_id": job_id,
            "kind": kind,
            "request_id": request_id,
            "attempt": attempt,
        },
    )
    return "completed"


@celery_app.task(
    name="app.worker.tasks.notifications.dispatch_pending",
    ignore_result=True,
)
def dispatch_pending() -> int:
    """Publish a bounded batch of due PostgreSQL outbox rows to Celery."""
    settings = get_settings()

    async def dispatch() -> list[tuple[UUID, int]]:
        async def select_jobs(uow: SQLAlchemyUnitOfWork) -> list[tuple[UUID, int]]:
            now = datetime.now(UTC)
            jobs = await uow.session.scalars(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.status == "pending",
                    NotificationOutbox.available_at <= now,
                )
                .order_by(NotificationOutbox.available_at, NotificationOutbox.created_at)
                .limit(settings.CELERY_OUTBOX_BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
            selected = list(jobs.all())
            for job in selected:
                job.status = "processing"
                job.locked_at = now
                job.worker_started_at = None
            return [(job.id, job.attempts) for job in selected]

        return await _run_uow(select_jobs)

    jobs = worker_runtime.run(dispatch())
    published: list[UUID] = []
    try:
        for job_id, attempts in jobs:
            process_outbox_job.apply_async(
                args=[str(job_id)],
                task_id=f"outbox-{job_id}-{attempts + 1}",
            )
            published.append(job_id)
    except Exception as exc:
        worker_runtime.run(_recover_unpublished(jobs, set(published), exc))
        logger.warning(
            "Notification job dispatch failed",
            extra={"error_type": type(exc).__name__, "published_count": len(published)},
        )
        raise
    if jobs:
        logger.info("Notification jobs dispatched", extra={"count": len(published)})
    return len(published)


__all__ = ["dispatch_pending", "process_outbox_job"]
