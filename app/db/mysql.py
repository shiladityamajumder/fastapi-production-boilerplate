"""File: app/db/mysql.py.

Asynchronous MySQL engine and session lifecycle adapter.

One ``MySQLDatabase`` instance is created per application or Celery worker
process. The adapter owns:

- one SQLAlchemy asynchronous engine,
- one process-local connection pool,
- one reusable asynchronous session factory.

The adapter must never be created before a Celery worker process is forked.
Each request, service operation, or task must create its own ``AsyncSession`` or
``SQLAlchemyUnitOfWork`` from ``session_factory``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator  # noqa: TC003
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import AppSettings  # noqa: TC001
from app.core.logging import get_logger

logger = get_logger(__name__)


class MySQLDatabase:
    """Own one process-local asynchronous MySQL engine and session factory."""

    def __init__(
        self,
        *,
        url: str,
        settings: AppSettings,
    ) -> None:
        """Initialize the MySQL engine and session factory.

        Args:
            url: Validated SQLAlchemy asynchronous MySQL URL.
            settings: Validated application settings.

        Raises:
            ValueError: If the URL is blank.
        """
        normalized_url = url.strip()

        if not normalized_url:
            raise ValueError("MySQL connection URL must not be blank")

        self._engine: AsyncEngine = create_async_engine(
            normalized_url,
            pool_size=settings.SQL_POOL_SIZE,
            max_overflow=settings.SQL_MAX_OVERFLOW,
            pool_timeout=settings.SQL_POOL_TIMEOUT_SECONDS,
            pool_recycle=settings.SQL_POOL_RECYCLE_SECONDS,
            pool_pre_ping=settings.SQL_POOL_PRE_PING,
            pool_use_lifo=settings.SQL_POOL_USE_LIFO,
            pool_reset_on_return="rollback",
            connect_args={
                "connect_timeout": settings.MYSQL_CONNECT_TIMEOUT_SECONDS,
            },
            echo=settings.SQL_ECHO,
            hide_parameters=True,
        )

        self._session_factory: async_sessionmaker[AsyncSession] = (
            async_sessionmaker(
                bind=self._engine,
                class_=AsyncSession,
                autoflush=False,
                expire_on_commit=False,
            )
        )

        logger.info(
            "MySQL database adapter initialized",
            extra={
                "pool_size": settings.SQL_POOL_SIZE,
                "max_overflow": settings.SQL_MAX_OVERFLOW,
            },
        )

    @classmethod
    def from_settings(
        cls,
        settings: AppSettings,
    ) -> MySQLDatabase:
        """Build the adapter from validated application settings.

        Args:
            settings: Validated application settings.

        Returns:
            Initialized MySQL adapter.

        Raises:
            RuntimeError: If MySQL is disabled or not configured.
        """
        if not settings.ENABLE_MYSQL:
            raise RuntimeError("MySQL is not enabled")

        url = settings.mysql_url_value

        if not url:
            raise RuntimeError("MySQL connection URL is not configured")

        return cls(
            url=url,
            settings=settings,
        )

    @property
    def engine(self) -> AsyncEngine:
        """Return the process-local SQLAlchemy asynchronous engine.

        Direct engine access should be limited to infrastructure operations,
        diagnostics, and advanced database behavior.
        """
        return self._engine

    @property
    def session_factory(
        self,
    ) -> async_sessionmaker[AsyncSession]:
        """Return the process-local asynchronous session factory."""
        return self._session_factory

    @asynccontextmanager
    async def session(
        self,
    ) -> AsyncGenerator[AsyncSession]:
        """Yield an isolated session and guarantee cleanup.

        This helper is suitable for read-only workflows or infrastructure
        operations. Transactional write workflows should normally use
        ``SQLAlchemyUnitOfWork``.

        Yields:
            Isolated asynchronous SQLAlchemy session.
        """
        session = self._session_factory()

        try:
            yield session
        finally:
            try:
                if session.in_transaction():
                    await session.rollback()
            finally:
                await session.close()

    async def ping(self) -> None:
        """Execute a lightweight MySQL connectivity query.

        Raises:
            Exception: Propagates connection, authentication, timeout, and
                query failures to the lifecycle boundary.
        """
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

        logger.debug("MySQL connectivity verified")

    async def close(self) -> None:
        """Dispose the engine and all pooled MySQL connections."""
        await self._engine.dispose()

        logger.info("MySQL database adapter closed")


__all__ = [
    "MySQLDatabase",
]
