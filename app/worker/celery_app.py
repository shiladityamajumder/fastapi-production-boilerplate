# """
# File: app/worker/celery_app.py

# Celery application factory.

# This module creates the reusable Celery application used by worker and Beat
# processes. Constructing the Celery object does not establish broker, result
# backend, database, or cache connections.

# Network connections are opened only when:

# - an application publishes a task,
# - a worker starts consuming messages,
# - or Celery Beat starts publishing scheduled tasks.

# Task implementations must be explicitly registered through ``TASK_MODULES``.
# Celery autodiscovery is intentionally avoided so task registration remains
# deterministic and easy to review.

# This module must not:

# - contain business logic,
# - initialize database resources,
# - create worker event loops,
# - define task implementations,
# - or silently create undeclared queues.
# """

# from __future__ import annotations

# from typing import Final

# from celery import Celery

# from app.core.config import (
#     AppSettings,
#     get_settings,
# )
# from app.worker.beat import (
#     get_beat_schedule,
#     validate_beat_schedule,
# )
# from app.worker.config import WorkerConfig
# from app.worker.routing import (
#     TASK_ROUTES,
#     build_task_queues,
#     validate_task_routes,
# )
# from app.worker.signals import (
#     register_worker_signals,
# )

# # =============================================================================
# # TASK MODULE REGISTRATION
# # =============================================================================

# TASK_MODULES: Final[tuple[str, ...]] = (
#     # Add explicit task module import paths here.
#     #
#     # Example:
#     #
#     # "app.worker.tasks.rack_replenishment_task",
# )


# def create_celery_app(
#     settings: AppSettings | None = None,
#     *,
#     include_beat_schedule: bool = False,
# ) -> Celery:
#     """
#     Create and configure the Celery application.

#     Constructing the application does not connect to the broker or result
#     backend. Celery establishes those connections only when tasks are
#     published or consumed.

#     Queue declarations and task routes are validated before they are applied.
#     Undeclared queues are not created automatically.

#     Args:
#         settings: Optional validated application settings. When omitted, the
#             cached process-level settings are loaded through ``get_settings``.
#         include_beat_schedule: Whether to include the declarative Celery Beat
#             schedule in the application configuration.

#     Returns:
#         Fully configured Celery application.

#     Raises:
#         RuntimeError: If background processing is disabled or required worker
#             settings are missing.
#         ValueError: If queue routing or Beat configuration is invalid.
#     """

#     resolved_settings = (
#         settings
#         or get_settings()
#     )

#     worker_config = WorkerConfig.from_settings(
#         resolved_settings
#     )

#     task_queues = build_task_queues()

#     validate_task_routes(
#         TASK_ROUTES,
#         task_queues,
#     )

#     application = Celery(
#         main=worker_config.app_name,
#         broker=worker_config.broker_url,
#         backend=worker_config.result_backend,
#         include=list(TASK_MODULES),
#     )

#     application.conf.update(
#         worker_config.as_celery_settings()
#     )

#     application.conf.update(
#         task_queues=task_queues,
#         task_routes=TASK_ROUTES,
#         task_create_missing_queues=False,
#     )

#     if include_beat_schedule:
#         beat_schedule = get_beat_schedule()

#         validate_beat_schedule(
#             beat_schedule
#         )

#         application.conf.beat_schedule = (
#             beat_schedule
#         )

#     # Operational tooling may inspect this custom configuration value without
#     # re-reading the complete application settings object.
#     application.conf.background_jobs_enabled = True

#     return application


# # =============================================================================
# # WORKER SIGNAL REGISTRATION
# # =============================================================================

# # Signal registration is explicit and idempotent. The handlers themselves live
# # in ``app.worker.signals`` so lifecycle behavior remains independently
# # testable.
# register_worker_signals()


# # =============================================================================
# # CELERY CLI ENTRY POINT
# # =============================================================================

# # Worker:
# #
# #     celery \
# #         -A app.worker.celery_app:celery_app \
# #         worker \
# #         --loglevel=INFO
# #
# # Beat:
# #
# #     celery \
# #         -A app.worker.celery_app:celery_beat_app \
# #         beat \
# #         --loglevel=INFO
# #
# # A separate Beat application is created so the normal worker application does
# # not carry periodic schedule configuration unnecessarily.

# celery_app = create_celery_app(
#     include_beat_schedule=False,
# )

# celery_beat_app = create_celery_app(
#     include_beat_schedule=True,
# )


# __all__ = [
#     "TASK_MODULES",
#     "celery_app",
#     "celery_beat_app",
#     "create_celery_app",
# ]

"""Celery app entry points for independent worker and Beat processes."""

from __future__ import annotations

from celery import Celery

from app.core.config import AppSettings, get_settings
from app.worker.config import build_celery_settings
from app.worker.signals import register_worker_signals


def create_celery_app(settings: AppSettings | None = None) -> Celery:
    """Create Celery configuration without contacting Redis or PostgreSQL."""
    resolved = settings or get_settings()
    app = Celery("fastapi_service")
    app.conf.update(build_celery_settings(resolved))
    app.conf.update(
        include=[
            "app.worker.tasks.notifications",
            "app.worker.tasks.maintenance",
            "app.worker.tasks.health",
        ]
    )
    app.set_default()
    app.autodiscover_tasks(["app.worker.tasks"])
    return app


celery_app = create_celery_app()
register_worker_signals()

__all__ = ["celery_app", "create_celery_app"]
