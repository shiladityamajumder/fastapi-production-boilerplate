# """
# File: app/worker/lifecycle.py

# Process-local asynchronous lifecycle for Celery worker processes.

# Celery tasks are synchronous callables by default, while this application uses
# asynchronous infrastructure such as SQLAlchemy database engines and sessions.
# This module provides one persistent asyncio event loop running in a dedicated
# thread for each Celery worker child process.

# Each worker child owns:

# - one dedicated asyncio event-loop thread,
# - one process-local database registry,
# - database engines and pools created after process fork,
# - deterministic best-effort shutdown.

# Lifecycle rules:

# - never initialize database resources in the Celery parent process,
# - initialize the runtime only after a worker child process is created,
# - never share engines, clients, pools, sessions, or event loops across
#   operating-system processes,
# - execute all asynchronous task code on the persistent worker-local event loop,
# - close the database registry before stopping the event loop,
# - discard inherited runtime references when the process identifier changes.

# FastAPI does not use this lifecycle. The API process uses
# ``app/core/lifespan.py``.
# """

# from __future__ import annotations

# import asyncio
# import os
# from collections.abc import Coroutine
# from concurrent.futures import (
#     Future,
# )
# from concurrent.futures import (
#     TimeoutError as FutureTimeoutError,
# )
# from threading import (
#     Event,
#     Lock,
#     Thread,
# )
# from typing import (
#     Any,
#     TypeVar,
# )

# from app.core.config import (
#     AppSettings,
#     get_settings,
# )
# from app.core.logging import get_logger
# from app.db.registry import DatabaseRegistry

# logger = get_logger(__name__)


# ResultT = TypeVar("ResultT")


# class WorkerRuntime:
#     """
#     Own asynchronous infrastructure for one Celery worker child process.

#     A persistent event loop avoids creating a new loop for every task and keeps
#     asynchronous connection pools bound to one event loop for their complete
#     lifetime.

#     The runtime is process-aware. Any state inherited from a parent process is
#     discarded without attempting cross-process cleanup.
#     """

#     def __init__(self) -> None:
#         """Initialize empty process-local runtime state."""

#         self._state_lock = Lock()
#         self._ready_event = Event()
#         self._stopped_event = Event()

#         self._pid: int | None = None
#         self._settings: AppSettings | None = None
#         self._registry: DatabaseRegistry | None = None

#         self._loop: asyncio.AbstractEventLoop | None = None
#         self._thread: Thread | None = None

#         self._startup_error: BaseException | None = None

#     @property
#     def initialized(self) -> bool:
#         """
#         Return whether the current process owns an active runtime.

#         Returns:
#             ``True`` when the worker-local event loop, thread, and database
#             registry are available for the current operating-system process.
#         """

#         loop = self._loop
#         thread = self._thread

#         return (
#             self._pid == os.getpid()
#             and loop is not None
#             and loop.is_running()
#             and thread is not None
#             and thread.is_alive()
#             and self._registry is not None
#         )

#     @property
#     def settings(self) -> AppSettings:
#         """
#         Return worker-local application settings.

#         The runtime is initialized lazily when necessary.

#         Returns:
#             Validated settings associated with the current worker process.

#         Raises:
#             RuntimeError: If worker initialization fails.
#         """

#         self.initialize()

#         settings = self._settings

#         if settings is None:
#             raise RuntimeError(
#                 "Worker settings are unavailable"
#             )

#         return settings

#     @property
#     def registry(self) -> DatabaseRegistry:
#         """
#         Return worker-local infrastructure registry.

#         The runtime is initialized lazily when necessary.

#         Returns:
#             Database registry owned by the current worker process.

#         Raises:
#             RuntimeError: If worker initialization fails.
#         """

#         self.initialize()

#         registry = self._registry

#         if registry is None:
#             raise RuntimeError(
#                 "Worker infrastructure is unavailable"
#             )

#         return registry

#     def initialize(
#         self,
#         settings: AppSettings | None = None,
#         *,
#         startup_timeout_seconds: float = 5.0,
#     ) -> None:
#         """
#         Initialize process-local asynchronous worker infrastructure.

#         Database adapter construction occurs inside the dedicated event-loop
#         thread after the Celery worker child process has been created. Actual
#         network connections remain lazy until an adapter is first used.

#         Calling this method repeatedly in the same process is safe.

#         Args:
#             settings: Optional validated settings override.
#             startup_timeout_seconds: Maximum number of seconds to wait for the
#                 event-loop thread to initialize.

#         Raises:
#             ValueError: If ``startup_timeout_seconds`` is not positive.
#             RuntimeError: If background jobs are disabled or initialization
#                 fails.
#         """

#         if startup_timeout_seconds <= 0:
#             raise ValueError(
#                 "startup_timeout_seconds must be greater than zero"
#             )

#         current_pid = os.getpid()

#         if self.initialized:
#             return

#         with self._state_lock:
#             if self.initialized:
#                 return

#             if (
#                 self._pid is not None
#                 and self._pid != current_pid
#             ):
#                 # Runtime objects inherited through process forking must never
#                 # be used or closed by the child process.
#                 self._discard_state()

#             resolved_settings = (
#                 settings
#                 or get_settings()
#             )

#             if not resolved_settings.BACKGROUND_JOBS_ENABLED:
#                 raise RuntimeError(
#                     "Background jobs are disabled"
#                 )

#             self._pid = current_pid
#             self._settings = resolved_settings
#             self._startup_error = None

#             self._ready_event.clear()
#             self._stopped_event.clear()

#             thread = Thread(
#                 target=self._event_loop_main,
#                 name=(
#                     f"worker-async-runtime-{current_pid}"
#                 ),
#                 daemon=True,
#             )

#             self._thread = thread
#             thread.start()

#         # Do not hold the state lock while waiting. The event-loop thread may
#         # need to update runtime state before signalling readiness.
#         if not self._ready_event.wait(
#             timeout=startup_timeout_seconds
#         ):
#             self._stop_failed_startup_thread()

#             raise RuntimeError(
#                 "Worker asynchronous runtime startup timed out"
#             )

#         startup_error = self._startup_error

#         if startup_error is not None:
#             self._stop_failed_startup_thread()

#             raise RuntimeError(
#                 "Worker asynchronous runtime initialization failed"
#             ) from startup_error

#         if not self.initialized:
#             self._stop_failed_startup_thread()

#             raise RuntimeError(
#                 "Worker asynchronous runtime is unavailable"
#             )

#         registry = self._registry

#         logger.info(
#             "Worker runtime initialized",
#             extra={
#                 "worker_pid": current_pid,
#                 "enabled_adapters": (
#                     list(registry.adapter_names)
#                     if registry is not None
#                     else []
#                 ),
#             },
#         )

#     def run(
#         self,
#         coroutine: Coroutine[Any, Any, ResultT],
#         *,
#         timeout_seconds: float | None = None,
#     ) -> ResultT:
#         """
#         Execute one coroutine on the worker-local event loop.

#         The caller remains synchronous because Celery invokes ordinary task
#         functions synchronously. The coroutine itself executes on the
#         persistent worker-local asyncio loop.

#         Args:
#             coroutine: Coroutine to execute.
#             timeout_seconds: Optional caller-side wait timeout. Celery hard and
#                 soft task limits remain configured separately.

#         Returns:
#             Result returned by the coroutine.

#         Raises:
#             ValueError: If ``timeout_seconds`` is not positive.
#             RuntimeError: If the worker event loop is unavailable.
#             TimeoutError: If the optional wait timeout expires.
#             Exception: Any exception raised by the coroutine.
#         """

#         if (
#             timeout_seconds is not None
#             and timeout_seconds <= 0
#         ):
#             coroutine.close()

#             raise ValueError(
#                 "timeout_seconds must be greater than zero"
#             )

#         self.initialize()

#         loop = self._loop

#         if loop is None or not loop.is_running():
#             coroutine.close()

#             raise RuntimeError(
#                 "Worker event loop is not running"
#             )

#         future: Future[ResultT] = (
#             asyncio.run_coroutine_threadsafe(
#                 coroutine,
#                 loop,
#             )
#         )

#         try:
#             return future.result(
#                 timeout=timeout_seconds
#             )

#         except FutureTimeoutError as exc:
#             future.cancel()

#             raise TimeoutError(
#                 "Worker coroutine execution timed out"
#             ) from exc

#         except BaseException:
#             if not future.done():
#                 future.cancel()

#             raise

#     def shutdown(
#         self,
#         *,
#         resource_timeout_seconds: float = 15.0,
#         thread_timeout_seconds: float = 5.0,
#     ) -> None:
#         """
#         Close worker-local infrastructure and stop the event loop.

#         Shutdown is best-effort because Celery cannot guarantee that shutdown
#         signals are emitted during forced process termination.

#         Calling this method repeatedly is safe.

#         Args:
#             resource_timeout_seconds: Maximum number of seconds to wait for the
#                 database registry to close.
#             thread_timeout_seconds: Maximum number of seconds to wait for the
#                 event-loop thread to stop.

#         Raises:
#             ValueError: If either timeout is not positive.
#         """

#         if resource_timeout_seconds <= 0:
#             raise ValueError(
#                 "resource_timeout_seconds must be greater than zero"
#             )

#         if thread_timeout_seconds <= 0:
#             raise ValueError(
#                 "thread_timeout_seconds must be greater than zero"
#             )

#         current_pid = os.getpid()

#         with self._state_lock:
#             if self._pid is None:
#                 return

#             if self._pid != current_pid:
#                 # Do not interact with resources inherited from another
#                 # process.
#                 self._discard_state()
#                 return

#             loop = self._loop
#             thread = self._thread
#             registry = self._registry
#             worker_pid = self._pid

#         if loop is None or thread is None:
#             with self._state_lock:
#                 self._discard_state()

#             return

#         logger.info(
#             "Worker runtime shutdown initiated",
#             extra={
#                 "worker_pid": worker_pid,
#             },
#         )

#         if (
#             registry is not None
#             and loop.is_running()
#         ):
#             try:
#                 close_future = (
#                     asyncio.run_coroutine_threadsafe(
#                         registry.close(),
#                         loop,
#                     )
#                 )

#                 close_future.result(
#                     timeout=resource_timeout_seconds
#                 )

#             except FutureTimeoutError:
#                 logger.error(
#                     "Worker infrastructure shutdown timed out",
#                     extra={
#                         "worker_pid": worker_pid,
#                         "timeout_seconds": (
#                             resource_timeout_seconds
#                         ),
#                     },
#                 )

#             except Exception:
#                 logger.exception(
#                     "Worker infrastructure shutdown failed",
#                     extra={
#                         "worker_pid": worker_pid,
#                     },
#                 )

#         if loop.is_running():
#             loop.call_soon_threadsafe(
#                 loop.stop
#             )

#         thread.join(
#             timeout=thread_timeout_seconds
#         )

#         if thread.is_alive():
#             logger.warning(
#                 "Worker event-loop thread did not stop cleanly",
#                 extra={
#                     "worker_pid": worker_pid,
#                     "timeout_seconds": (
#                         thread_timeout_seconds
#                     ),
#                 },
#             )

#         with self._state_lock:
#             self._discard_state()

#         logger.info(
#             "Worker runtime shutdown completed",
#             extra={
#                 "worker_pid": worker_pid,
#             },
#         )

#     def _event_loop_main(self) -> None:
#         """
#         Create and run the worker-local asyncio event loop.

#         This method executes inside the dedicated worker runtime thread.
#         """

#         loop: asyncio.AbstractEventLoop | None = None

#         try:
#             loop = asyncio.new_event_loop()
#             asyncio.set_event_loop(loop)

#             settings = self._settings

#             if settings is None:
#                 raise RuntimeError(
#                     "Worker settings were not initialized"
#                 )

#             # Adapter construction happens inside the worker child process and
#             # on the same thread that owns the event loop.
#             registry = DatabaseRegistry.from_settings(
#                 settings
#             )

#             self._loop = loop
#             self._registry = registry

#         except BaseException as exc:
#             self._startup_error = exc
#             self._ready_event.set()

#             if loop is not None:
#                 asyncio.set_event_loop(None)
#                 loop.close()

#             self._stopped_event.set()
#             return

#         self._ready_event.set()

#         try:
#             loop.run_forever()

#         finally:
#             self._drain_event_loop(
#                 loop
#             )

#             self._stopped_event.set()

#     @staticmethod
#     def _drain_event_loop(
#         loop: asyncio.AbstractEventLoop,
#     ) -> None:
#         """
#         Cancel pending work and close one event loop.

#         Args:
#             loop: Worker-local event loop being shut down.
#         """

#         try:
#             pending_tasks = asyncio.all_tasks(
#                 loop
#             )

#             for task in pending_tasks:
#                 task.cancel()

#             if pending_tasks:
#                 loop.run_until_complete(
#                     asyncio.gather(
#                         *pending_tasks,
#                         return_exceptions=True,
#                     )
#                 )

#             loop.run_until_complete(
#                 loop.shutdown_asyncgens()
#             )

#             loop.run_until_complete(
#                 loop.shutdown_default_executor()
#             )

#         except Exception:
#             logger.exception(
#                 "Worker event-loop cleanup failed"
#             )

#         finally:
#             asyncio.set_event_loop(None)
#             loop.close()

#     def _stop_failed_startup_thread(self) -> None:
#         """
#         Stop and discard a runtime that failed during initialization.

#         This helper avoids dropping references to a thread that may still be
#         running.
#         """

#         with self._state_lock:
#             loop = self._loop
#             thread = self._thread

#         if loop is not None and loop.is_running():
#             loop.call_soon_threadsafe(
#                 loop.stop
#             )

#         if thread is not None and thread.is_alive():
#             thread.join(
#                 timeout=2.0
#             )

#         with self._state_lock:
#             self._discard_state()

#     def _discard_state(self) -> None:
#         """
#         Clear process-local runtime references.

#         This method performs no resource cleanup. It is used after cleanup has
#         completed or when references were inherited from another process and
#         therefore must not be accessed.
#         """

#         self._pid = None
#         self._settings = None
#         self._registry = None

#         self._loop = None
#         self._thread = None

#         self._startup_error = None

#         self._ready_event.clear()
#         self._stopped_event.clear()


# worker_runtime = WorkerRuntime()


# def get_worker_runtime() -> WorkerRuntime:
#     """
#     Return the initialized process-local worker runtime.

#     Returns:
#         Worker runtime owned by the current process.

#     Raises:
#         RuntimeError: If background jobs are disabled or initialization fails.
#     """

#     worker_runtime.initialize()

#     return worker_runtime


# def get_worker_registry() -> DatabaseRegistry:
#     """
#     Return the process-local worker database registry.

#     Returns:
#         Database registry owned by the current worker process.

#     Raises:
#         RuntimeError: If background jobs are disabled or initialization fails.
#     """

#     return get_worker_runtime().registry


# __all__ = [
#     "WorkerRuntime",
#     "get_worker_registry",
#     "get_worker_runtime",
#     "worker_runtime",
# ]
