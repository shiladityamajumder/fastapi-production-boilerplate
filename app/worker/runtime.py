"""Worker-child infrastructure with one persistent async event loop."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from concurrent.futures import Future
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.postgres import PostgreSQLDatabase
from app.db.uow import SQLAlchemyUnitOfWork

logger = get_logger(__name__)


class WorkerRuntime:
    """Own the worker process loop and PostgreSQL pool, never inherited pools."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._database: PostgreSQLDatabase | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Create process-local async resources on a dedicated event loop."""
        with self._lock:
            if self._loop is not None and self._thread is not None:
                return
            loop = asyncio.new_event_loop()
            ready = threading.Event()

            def run_loop() -> None:
                asyncio.set_event_loop(loop)
                ready.set()
                loop.run_forever()

            thread = threading.Thread(
                target=run_loop,
                name="celery-async-runtime",
                daemon=True,
            )
            thread.start()
            if not ready.wait(timeout=10):
                loop.call_soon_threadsafe(loop.stop)
                thread.join(timeout=10)
                loop.close()
                raise RuntimeError("Worker event loop did not start")
            try:
                database = PostgreSQLDatabase.from_settings(get_settings())
            except Exception:
                loop.call_soon_threadsafe(loop.stop)
                thread.join(timeout=10)
                loop.close()
                raise
            self._loop = loop
            self._thread = thread
            self._database = database
            logger.info("Worker async runtime initialized")

    def run(self, coroutine: Coroutine[Any, Any, Any]) -> Any:
        """Run an async task on the persistent worker event loop."""
        self.start()
        if self._loop is None:
            raise RuntimeError("Worker event loop is unavailable")
        future: Future[Any] = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result()

    def create_uow(self) -> SQLAlchemyUnitOfWork:
        """Return a Unit of Work bound to this worker's PostgreSQL pool."""
        if self._database is None:
            raise RuntimeError("Worker runtime is not initialized")
        return SQLAlchemyUnitOfWork(
            self._database.session_factory,
            database_name="background_worker",
        )

    def close(self) -> None:
        """Dispose async pools and stop the process-local loop gracefully."""
        loop, thread = self._loop, self._thread
        if loop is None or thread is None:
            return
        if self._database is not None:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._database.close(), loop
                ).result(timeout=20)
            except Exception as exc:
                logger.error(
                    "Worker database shutdown failed",
                    extra={"error_type": type(exc).__name__},
                )
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=20)
        if thread.is_alive():
            logger.error("Worker async runtime thread did not stop")
        else:
            loop.close()
        self._database = None
        self._loop = None
        self._thread = None
        logger.info("Worker async runtime stopped")


worker_runtime = WorkerRuntime()

__all__ = ["WorkerRuntime", "worker_runtime"]
