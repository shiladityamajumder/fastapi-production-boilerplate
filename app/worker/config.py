# """
# File: app/worker/config.py

# Typed and immutable configuration for the Celery worker.

# This module translates validated application settings into a worker-specific
# configuration object. It does not:

# - connect to the Celery broker,
# - connect to the result backend,
# - initialize logging,
# - create database engines,
# - initialize worker processes,
# - register Celery signals,
# - or mutate external state.

# Worker configuration is constructed once per process and passed to the Celery
# application factory.
# """

# from __future__ import annotations

# from dataclasses import dataclass
# from typing import (
#     Final,
#     TypeAlias,
# )

# from app.core.config import (
#     AppSettings,
#     get_settings,
# )

# # =============================================================================
# # CELERY SERIALIZATION DEFAULTS
# # =============================================================================

# DEFAULT_TASK_SERIALIZER: Final[str] = "json"
# DEFAULT_RESULT_SERIALIZER: Final[str] = "json"

# DEFAULT_ACCEPT_CONTENT: Final[
#     tuple[str, ...]
# ] = (
#     "json",
# )


# # =============================================================================
# # CELERY EXECUTION DEFAULTS
# # =============================================================================

# DEFAULT_PREFETCH_MULTIPLIER: Final[int] = 1

# DEFAULT_BROKER_CONNECTION_RETRY: Final[bool] = True

# DEFAULT_BROKER_CONNECTION_RETRY_ON_STARTUP: Final[
#     bool
# ] = True

# DEFAULT_WORKER_CANCEL_TASKS_ON_CONNECTION_LOSS: Final[
#     bool
# ] = True


# CelerySettings: TypeAlias = dict[str, object]


# @dataclass(
#     frozen=True,
#     slots=True,
# )
# class WorkerConfig:
#     """
#     Immutable Celery worker configuration.

#     This object contains only normalized values required by Celery. It is
#     intentionally independent from Celery itself so configuration can be
#     validated and tested without creating a Celery application.

#     Broker and result-backend URLs are unwrapped inside the worker process.
#     They must never be logged, returned through APIs, or included in exception
#     details.

#     Attributes:
#         app_name: Logical Celery application name.
#         broker_url: Celery broker connection URL.
#         result_backend: Optional Celery result-backend URL.
#         timezone: IANA timezone used by workers and Celery Beat.
#         task_default_queue: Queue used for tasks without an explicit route.
#         task_always_eager: Execute tasks synchronously in the publishing
#             process.
#         task_ignore_result: Avoid storing successful task results.
#         task_time_limit_seconds: Hard task execution time limit.
#         task_soft_time_limit_seconds: Soft task execution time limit.
#         worker_concurrency: Number of concurrent worker execution units.
#         task_max_retries: Default retry limit used by reusable task helpers.
#         prefetch_multiplier: Number of tasks reserved by each worker execution
#             unit.
#         broker_connection_retry: Retry broker connections after a disconnect.
#         broker_connection_retry_on_startup: Retry the initial broker connection.
#         worker_cancel_long_running_tasks_on_connection_loss: Cancel active tasks
#             when the broker connection is lost.
#     """

#     app_name: str

#     broker_url: str
#     result_backend: str | None

#     timezone: str
#     task_default_queue: str

#     task_always_eager: bool
#     task_ignore_result: bool

#     task_time_limit_seconds: int
#     task_soft_time_limit_seconds: int

#     worker_concurrency: int
#     task_max_retries: int

#     prefetch_multiplier: int = (
#         DEFAULT_PREFETCH_MULTIPLIER
#     )

#     broker_connection_retry: bool = (
#         DEFAULT_BROKER_CONNECTION_RETRY
#     )

#     broker_connection_retry_on_startup: bool = (
#         DEFAULT_BROKER_CONNECTION_RETRY_ON_STARTUP
#     )

#     worker_cancel_long_running_tasks_on_connection_loss: bool = (
#         DEFAULT_WORKER_CANCEL_TASKS_ON_CONNECTION_LOSS
#     )

#     def __post_init__(
#         self,
#     ) -> None:
#         """
#         Validate normalized worker configuration.

#         Raises:
#             ValueError: If a required string is blank, numeric limits are
#                 invalid, or the soft time limit is not lower than the hard
#                 time limit.
#         """

#         self._validate_required_string(
#             self.app_name,
#             "app_name",
#         )

#         self._validate_required_string(
#             self.broker_url,
#             "broker_url",
#         )

#         self._validate_required_string(
#             self.timezone,
#             "timezone",
#         )

#         self._validate_required_string(
#             self.task_default_queue,
#             "task_default_queue",
#         )

#         if (
#             self.result_backend is not None
#             and not self.result_backend.strip()
#         ):
#             raise ValueError(
#                 "result_backend must not be blank when provided"
#             )

#         if self.task_time_limit_seconds <= 0:
#             raise ValueError(
#                 "task_time_limit_seconds must be greater than zero"
#             )

#         if self.task_soft_time_limit_seconds <= 0:
#             raise ValueError(
#                 "task_soft_time_limit_seconds must be greater than zero"
#             )

#         if (
#             self.task_soft_time_limit_seconds
#             >= self.task_time_limit_seconds
#         ):
#             raise ValueError(
#                 "task_soft_time_limit_seconds must be lower than "
#                 "task_time_limit_seconds"
#             )

#         if self.worker_concurrency <= 0:
#             raise ValueError(
#                 "worker_concurrency must be greater than zero"
#             )

#         if self.task_max_retries < 0:
#             raise ValueError(
#                 "task_max_retries must not be negative"
#             )

#         if self.prefetch_multiplier <= 0:
#             raise ValueError(
#                 "prefetch_multiplier must be greater than zero"
#             )

#     @classmethod
#     def from_settings(
#         cls,
#         settings: AppSettings | None = None,
#     ) -> WorkerConfig:
#         """
#         Build normalized worker configuration from application settings.

#         Args:
#             settings: Optional validated application settings. When omitted,
#                 cached process-level settings are loaded through
#                 ``get_settings``.

#         Returns:
#             Immutable and validated worker configuration.

#         Raises:
#             RuntimeError: If background processing is disabled, the broker URL
#                 is missing, or required Celery settings are unavailable.
#             ValueError: If the resulting worker configuration is invalid.
#         """

#         resolved_settings = (
#             settings
#             or get_settings()
#         )

#         if not resolved_settings.BACKGROUND_JOBS_ENABLED:
#             raise RuntimeError(
#                 "Background jobs are disabled"
#             )

#         broker_url = (
#             resolved_settings
#             .celery_broker_url_value
#         )

#         if broker_url is None:
#             raise RuntimeError(
#                 "CELERY_BROKER_URL is required when "
#                 "BACKGROUND_JOBS_ENABLED=true"
#             )

#         return cls(
#             app_name=resolved_settings.PROJECT_NAME,
#             broker_url=broker_url,
#             result_backend=(
#                 resolved_settings
#                 .celery_result_backend_value
#             ),
#             timezone=resolved_settings.TIMEZONE,
#             task_default_queue=(
#                 resolved_settings
#                 .CELERY_TASK_DEFAULT_QUEUE
#             ),
#             task_always_eager=(
#                 resolved_settings
#                 .CELERY_TASK_ALWAYS_EAGER
#             ),
#             task_ignore_result=(
#                 resolved_settings
#                 .CELERY_TASK_IGNORE_RESULT
#             ),
#             task_time_limit_seconds=(
#                 resolved_settings
#                 .CELERY_TASK_TIME_LIMIT_SECONDS
#             ),
#             task_soft_time_limit_seconds=(
#                 resolved_settings
#                 .CELERY_TASK_SOFT_TIME_LIMIT_SECONDS
#             ),
#             worker_concurrency=(
#                 resolved_settings
#                 .CELERY_WORKER_CONCURRENCY
#             ),
#             task_max_retries=(
#                 resolved_settings
#                 .CELERY_TASK_MAX_RETRIES
#             ),
#         )

#     def as_celery_settings(
#         self,
#     ) -> CelerySettings:
#         """
#         Return Celery-compatible configuration values.

#         The returned dictionary contains no application-specific objects and can
#         be passed directly to ``celery.conf.update``.

#         Returns:
#             Celery configuration dictionary.
#         """

#         return {
#             # -----------------------------------------------------------------
#             # Serialization
#             # -----------------------------------------------------------------
#             "task_serializer": (
#                 DEFAULT_TASK_SERIALIZER
#             ),
#             "result_serializer": (
#                 DEFAULT_RESULT_SERIALIZER
#             ),
#             "accept_content": list(
#                 DEFAULT_ACCEPT_CONTENT
#             ),

#             # -----------------------------------------------------------------
#             # Timezone
#             # -----------------------------------------------------------------
#             "timezone": self.timezone,
#             "enable_utc": True,

#             # -----------------------------------------------------------------
#             # Task execution
#             # -----------------------------------------------------------------
#             "task_always_eager": (
#                 self.task_always_eager
#             ),
#             "task_eager_propagates": True,
#             "task_ignore_result": (
#                 self.task_ignore_result
#             ),
#             "task_store_errors_even_if_ignored": False,
#             "task_track_started": True,

#             # Early acknowledgement is the safe default. Individual tasks may
#             # enable late acknowledgement only after confirming idempotency.
#             "task_acks_late": False,
#             "task_reject_on_worker_lost": False,

#             "task_time_limit": (
#                 self.task_time_limit_seconds
#             ),
#             "task_soft_time_limit": (
#                 self.task_soft_time_limit_seconds
#             ),

#             "task_default_queue": (
#                 self.task_default_queue
#             ),

#             # -----------------------------------------------------------------
#             # Worker behavior
#             # -----------------------------------------------------------------
#             "worker_concurrency": (
#                 self.worker_concurrency
#             ),
#             "worker_prefetch_multiplier": (
#                 self.prefetch_multiplier
#             ),
#             "worker_cancel_long_running_tasks_on_connection_loss": (
#                 self
#                 .worker_cancel_long_running_tasks_on_connection_loss
#             ),

#             # Disable event emission unless monitoring explicitly requires it.
#             "worker_send_task_events": False,
#             "task_send_sent_event": False,

#             # -----------------------------------------------------------------
#             # Broker behavior
#             # -----------------------------------------------------------------
#             "broker_connection_retry": (
#                 self.broker_connection_retry
#             ),
#             "broker_connection_retry_on_startup": (
#                 self
#                 .broker_connection_retry_on_startup
#             ),

#             # ``None`` allows unlimited broker reconnection attempts. Container
#             # orchestration should still provide process-level restart policy.
#             "broker_connection_max_retries": None,
#         }

#     @staticmethod
#     def _validate_required_string(
#         value: str,
#         name: str,
#     ) -> None:
#         """
#         Validate a required normalized string.

#         Args:
#             value: String value to validate.
#             name: Logical field name used in the validation error.

#         Raises:
#             ValueError: If the value is blank.
#         """

#         if not value.strip():
#             raise ValueError(
#                 f"{name} must not be blank"
#             )


# __all__ = [
#     "DEFAULT_ACCEPT_CONTENT",
#     "DEFAULT_BROKER_CONNECTION_RETRY",
#     "DEFAULT_BROKER_CONNECTION_RETRY_ON_STARTUP",
#     "DEFAULT_PREFETCH_MULTIPLIER",
#     "DEFAULT_RESULT_SERIALIZER",
#     "DEFAULT_TASK_SERIALIZER",
#     "DEFAULT_WORKER_CANCEL_TASKS_ON_CONNECTION_LOSS",
#     "CelerySettings",
#     "WorkerConfig",
# ]
