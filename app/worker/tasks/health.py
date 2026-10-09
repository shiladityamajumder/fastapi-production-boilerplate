"""Minimal task-level health probe for Celery worker inspection."""

from __future__ import annotations

from celery import current_task

from app.worker.celery_app import celery_app


@celery_app.task(name="app.worker.tasks.health.ping", ignore_result=False)
def ping() -> dict[str, str]:
    """Return a small static worker health response without infrastructure IO."""
    return {"status": "ok", "task_id": str(current_task.request.id)}


__all__ = ["ping"]
