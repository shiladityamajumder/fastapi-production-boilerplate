"""Focused unit tests for notification task failure handling."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from app.worker.tasks import maintenance
from app.worker.tasks import notifications


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (OSError("network unavailable"), True),
        (BotoCoreError(), True),
        (
            ClientError(
                {"Error": {"Code": "ThrottlingException"}}, "SendEmail"
            ),
            True,
        ),
        (
            ClientError(
                {
                    "Error": {"Code": "MessageRejected"},
                    "ResponseMetadata": {"HTTPStatusCode": 400},
                },
                "SendEmail",
            ),
            False,
        ),
        (ValueError("invalid notification"), False),
    ],
)
def test_delivery_errors_are_classified_for_retry(
    error: Exception, expected: bool
) -> None:
    assert notifications._retryable(error) is expected


@pytest.mark.parametrize(
    ("delivery_error", "expected_status"),
    [
        (None, "completed"),
        (OSError("temporary"), "pending"),
        (ValueError("bad"), "failed"),
    ],
)
def test_outbox_task_records_completion_retry_or_permanent_failure(
    monkeypatch: pytest.MonkeyPatch,
    delivery_error: Exception | None,
    expected_status: str,
) -> None:
    job_id = uuid4()
    settings = SimpleNamespace()
    claimed = ("email_notification", b"ciphertext", 1, 3, "request-123")
    recorded_statuses: list[str] = []

    async def deliver(*_args: object, **_kwargs: object) -> None:
        if delivery_error is not None:
            raise delivery_error

    def run(coroutine: object) -> object:
        name = coroutine.cr_code.co_name  # type: ignore[attr-defined]
        if name == "_claim_job":
            coroutine.close()  # type: ignore[attr-defined]
            return claimed
        if name == "deliver":
            return asyncio.run(coroutine)  # type: ignore[arg-type]
        if name == "_record_result":
            recorded_statuses.append(
                coroutine.cr_frame.f_locals["status"]  # type: ignore[attr-defined]
            )
            coroutine.close()  # type: ignore[attr-defined]
            return None
        pytest.fail(f"Unexpected worker coroutine: {name}")

    monkeypatch.setattr(notifications, "get_settings", lambda: settings)
    monkeypatch.setattr(notifications, "decrypt_payload", lambda *_: {})
    monkeypatch.setattr(notifications.worker_runtime, "run", run)
    monkeypatch.setattr(notifications, "_deliver", deliver)
    monkeypatch.setattr(notifications.random, "uniform", lambda *_: 1.0)

    result = notifications.process_outbox_job.run(str(job_id))

    assert result == expected_status
    assert recorded_statuses == [expected_status]


def test_scheduled_auth_cleanup_deletes_expired_state_in_configured_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        AUTH_SESSION_RETENTION_DAYS=30,
        CELERY_CLEANUP_BATCH_SIZE=37,
    )
    batches: list[tuple[str, int]] = []

    async def delete_expired(model: type, _predicate: object, batch_size: int) -> int:
        batches.append((model.__name__, batch_size))
        return 2

    monkeypatch.setattr(maintenance, "get_settings", lambda: settings)
    monkeypatch.setattr(maintenance, "_delete_expired", delete_expired)
    monkeypatch.setattr(
        maintenance.worker_runtime,
        "run",
        lambda coroutine: asyncio.run(coroutine),
    )

    results = maintenance.cleanup_auth_state.run()

    assert results == {
        "expired_otp_challenges": 2,
        "expired_action_tokens": 2,
        "expired_or_old_revoked_sessions": 2,
    }
    assert batches == [
        ("OTPChallenge", 37),
        ("OneTimeToken", 37),
        ("RefreshSession", 37),
    ]


@pytest.mark.asyncio
async def test_dispatch_recovery_requeues_only_unpublished_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published_id = uuid4()
    pending_id = uuid4()
    pending_row = SimpleNamespace(
        status="processing", locked_at=object(), last_error=None
    )
    rows = SimpleNamespace(all=lambda: [pending_row])
    session = SimpleNamespace(scalars=AsyncMock(return_value=rows))

    async def run_uow(operation: Any) -> None:
        await operation(SimpleNamespace(session=session))

    monkeypatch.setattr(notifications, "_run_uow", run_uow)

    await notifications._recover_unpublished(
        [(published_id, 0), (pending_id, 0)],
        {published_id},
        OSError("broker unavailable"),
    )

    assert pending_row.status == "pending"
    assert pending_row.locked_at is None
    assert pending_row.last_error == "OSError"
    session.scalars.assert_awaited_once()
