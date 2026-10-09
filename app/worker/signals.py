# """
# File: app/worker/signals.py

# Celery worker signal registration and process lifecycle integration.

# This module connects Celery lifecycle signals to the application's structured
# logging and worker-local asynchronous infrastructure.

# Signal responsibilities:

# ``setup_logging``:
#     Prevent Celery from replacing the application's structured logging
#     configuration.

# ``worker_init``:
#     Validate worker configuration in the Celery parent process. Database
#     engines, clients, connection pools, threads, and event loops must not be
#     created here.

# ``worker_process_init``:
#     Initialize logging and asynchronous infrastructure independently inside
#     each worker child process after prefork.

# ``worker_process_shutdown``:
#     Close resources owned by a worker child process.

# ``worker_shutdown``:
#     Perform final best-effort cleanup for the parent process and worker pools
#     that do not emit child-process lifecycle signals.

# Signal registration remains separate from the Celery application factory so
# worker lifecycle behavior can be tested independently.
# """

# from __future__ import annotations

# from typing import Any, Final

# from celery.signals import (
#     setup_logging as celery_setup_logging,
# )
# from celery.signals import (
#     worker_init,
#     worker_process_init,
#     worker_process_shutdown,
#     worker_shutdown,
# )

# from app.core.config import (
#     AppSettings,
#     get_settings,
# )
# from app.core.logging import (
#     get_logger,
#     setup_logging,
#     shutdown_logging,
# )
# from app.worker.lifecycle import worker_runtime

# logger = get_logger(__name__)


# # =============================================================================
# # SIGNAL DISPATCH IDENTIFIERS
# # =============================================================================

# SETUP_LOGGING_DISPATCH_UID: Final[str] = (
#     "app.worker.signals.configure_worker_logging"
# )

# WORKER_INIT_DISPATCH_UID: Final[str] = (
#     "app.worker.signals.validate_worker_startup"
# )

# WORKER_PROCESS_INIT_DISPATCH_UID: Final[str] = (
#     "app.worker.signals.initialize_worker_process"
# )

# WORKER_PROCESS_SHUTDOWN_DISPATCH_UID: Final[str] = (
#     "app.worker.signals.shutdown_worker_process"
# )

# WORKER_SHUTDOWN_DISPATCH_UID: Final[str] = (
#     "app.worker.signals.shutdown_worker"
# )


# # =============================================================================
# # SIGNAL REGISTRATION
# # =============================================================================

# def register_worker_signals() -> None:
#     """
#     Register Celery worker lifecycle handlers.

#     Stable dispatch identifiers prevent duplicate registration when this
#     function is called more than once within the same process. Strong receiver
#     references are used so handlers remain available for the complete worker
#     lifecycle.

#     This function registers handlers only. It does not initialize logging,
#     connect to infrastructure, create threads, or start worker resources.
#     """

#     celery_setup_logging.connect(
#         configure_worker_logging,
#         weak=False,
#         dispatch_uid=SETUP_LOGGING_DISPATCH_UID,
#     )

#     worker_init.connect(
#         validate_worker_startup,
#         weak=False,
#         dispatch_uid=WORKER_INIT_DISPATCH_UID,
#     )

#     worker_process_init.connect(
#         initialize_worker_process,
#         weak=False,
#         dispatch_uid=WORKER_PROCESS_INIT_DISPATCH_UID,
#     )

#     worker_process_shutdown.connect(
#         shutdown_worker_process,
#         weak=False,
#         dispatch_uid=WORKER_PROCESS_SHUTDOWN_DISPATCH_UID,
#     )

#     worker_shutdown.connect(
#         shutdown_worker,
#         weak=False,
#         dispatch_uid=WORKER_SHUTDOWN_DISPATCH_UID,
#     )


# # =============================================================================
# # LOGGING SIGNAL
# # =============================================================================

# def configure_worker_logging(
#     **_: Any,
# ) -> None:
#     """
#     Install the application's structured logging pipeline.

#     Celery normally configures its own logging handlers. Connecting this
#     receiver to Celery's ``setup_logging`` signal prevents Celery from replacing
#     the application's shared logging configuration.

#     The logging implementation must be process-aware so a prefork child creates
#     its own queue, listener thread, and handlers.
#     """

#     setup_logging(
#         get_settings()
#     )


# # =============================================================================
# # PARENT WORKER INITIALIZATION
# # =============================================================================

# def validate_worker_startup(
#     **_: Any,
# ) -> None:
#     """
#     Validate configuration before the worker starts processing tasks.

#     This signal executes in the Celery worker's parent process. It may validate
#     settings and initialize parent-process logging, but it must not create:

#     - database engines,
#     - database sessions,
#     - connection pools,
#     - asynchronous event loops,
#     - worker runtime threads,
#     - MongoDB clients,
#     - Redis clients.

#     Child processes create their own infrastructure through
#     ``initialize_worker_process``.

#     Raises:
#         RuntimeError: If background jobs are disabled or required worker
#             configuration is unavailable.
#     """

#     settings = get_settings()

#     _validate_background_jobs_enabled(
#         settings
#     )

#     setup_logging(
#         settings
#     )

#     logger.info(
#         "Celery worker startup initiated",
#         extra={
#             "default_queue": (
#                 settings.CELERY_TASK_DEFAULT_QUEUE
#             ),
#             "worker_concurrency": (
#                 settings.CELERY_WORKER_CONCURRENCY
#             ),
#             "task_time_limit_seconds": (
#                 settings.CELERY_TASK_TIME_LIMIT_SECONDS
#             ),
#             "task_soft_time_limit_seconds": (
#                 settings
#                 .CELERY_TASK_SOFT_TIME_LIMIT_SECONDS
#             ),
#         },
#     )


# # =============================================================================
# # CHILD PROCESS INITIALIZATION
# # =============================================================================

# def initialize_worker_process(
#     **_: Any,
# ) -> None:
#     """
#     Initialize resources inside one Celery worker child process.

#     This handler runs after prefork. Every worker child independently creates:

#     - its structured logging resources,
#     - its worker-local asyncio event-loop thread,
#     - its process-local database registry,
#     - its database engines and connection pools.

#     No engine, pool, event loop, or client inherited from the Celery parent
#     process may be reused.

#     Raises:
#         RuntimeError: If background jobs are disabled or worker runtime
#             initialization fails.
#     """

#     settings = get_settings()

#     _validate_background_jobs_enabled(
#         settings
#     )

#     # The logging implementation should detect the process identifier change
#     # and create process-local handlers and listener resources.
#     setup_logging(
#         settings
#     )

#     try:
#         worker_runtime.initialize(
#             settings
#         )

#     except Exception:
#         logger.exception(
#             "Celery worker child initialization failed"
#         )

#         # Avoid leaving process-local logging resources active when worker
#         # initialization cannot complete.
#         shutdown_logging()

#         raise

#     logger.info(
#         "Celery worker child initialized",
#         extra={
#             "enabled_adapters": list(
#                 worker_runtime.registry.adapter_names
#             ),
#         },
#     )


# # =============================================================================
# # CHILD PROCESS SHUTDOWN
# # =============================================================================

# def shutdown_worker_process(
#     **_: Any,
# ) -> None:
#     """
#     Close resources owned by one Celery worker child process.

#     Cleanup is best-effort because Celery cannot guarantee that shutdown signals
#     are emitted during forced termination.

#     Worker infrastructure is closed before logging so shutdown failures remain
#     observable.
#     """

#     try:
#         worker_runtime.shutdown()

#     except Exception:
#         # ``WorkerRuntime.shutdown`` already handles expected infrastructure
#         # failures internally. This outer guard protects worker shutdown from an
#         # unexpected lifecycle implementation error.
#         logger.exception(
#             "Unexpected Celery worker child shutdown failure"
#         )

#     finally:
#         shutdown_logging()


# # =============================================================================
# # FINAL WORKER SHUTDOWN
# # =============================================================================

# def shutdown_worker(
#     **_: Any,
# ) -> None:
#     """
#     Perform final best-effort Celery worker cleanup.

#     This handler supports:

#     - the Celery parent process,
#     - solo worker pools,
#     - thread-based worker pools,
#     - worker environments where ``worker_process_shutdown`` is not emitted.

#     Calling worker runtime shutdown repeatedly is safe.
#     """

#     try:
#         worker_runtime.shutdown()

#     except Exception:
#         logger.exception(
#             "Unexpected Celery worker shutdown failure"
#         )

#     finally:
#         logger.info(
#             "Celery worker shutdown completed"
#         )

#         shutdown_logging()


# # =============================================================================
# # INTERNAL HELPERS
# # =============================================================================

# def _validate_background_jobs_enabled(
#     settings: AppSettings,
# ) -> None:
#     """
#     Ensure Celery background processing is enabled.

#     Args:
#         settings: Validated application settings.

#     Raises:
#         RuntimeError: If background processing is disabled.
#     """

#     if not settings.BACKGROUND_JOBS_ENABLED:
#         raise RuntimeError(
#             "Celery worker startup refused because "
#             "BACKGROUND_JOBS_ENABLED=false"
#         )


# __all__ = [
#     "SETUP_LOGGING_DISPATCH_UID",
#     "WORKER_INIT_DISPATCH_UID",
#     "WORKER_PROCESS_INIT_DISPATCH_UID",
#     "WORKER_PROCESS_SHUTDOWN_DISPATCH_UID",
#     "WORKER_SHUTDOWN_DISPATCH_UID",
#     "configure_worker_logging",
#     "initialize_worker_process",
#     "register_worker_signals",
#     "shutdown_worker",
#     "shutdown_worker_process",
#     "validate_worker_startup",
# ]

"""Active Celery process lifecycle signal handlers."""

from __future__ import annotations

from celery.signals import (
    beat_init,
    setup_logging as celery_setup_logging,
    worker_init,
    worker_process_init,
    worker_process_shutdown,
    worker_shutdown,
)

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging, shutdown_logging
from app.worker.runtime import worker_runtime

logger = get_logger(__name__)
_registered = False


def _configure_logging(**_: object) -> None:
    """Use the application's structured logging in Celery processes."""
    setup_logging(get_settings())


def _validate_worker(**_: object) -> None:
    """Fail worker startup when background processing is not enabled."""
    if not get_settings().BACKGROUND_JOBS_ENABLED:
        raise RuntimeError("BACKGROUND_JOBS_ENABLED must be true for Celery")


def _start_worker_process(**_: object) -> None:
    """Initialize process-local async resources after Celery prefork."""
    worker_runtime.start()


def _stop_worker_process(**_: object) -> None:
    """Close process-local async resources on graceful worker shutdown."""
    worker_runtime.close()


def register_worker_signals() -> None:
    """Register worker lifecycle handlers exactly once per process."""
    global _registered
    if _registered:
        return
    celery_setup_logging.connect(_configure_logging, weak=False)
    worker_init.connect(_validate_worker, weak=False)
    beat_init.connect(_validate_worker, weak=False)
    worker_process_init.connect(_start_worker_process, weak=False)
    worker_process_shutdown.connect(_stop_worker_process, weak=False)
    worker_shutdown.connect(_stop_worker_process, weak=False)
    _registered = True


register_worker_signals()

__all__ = ["register_worker_signals"]
