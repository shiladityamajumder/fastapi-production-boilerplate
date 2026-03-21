# File: app/infrastructure/postgres.py
"""
===============================================================================
POSTGRESQL DATABASE ADAPTER (PRODUCTION-GRADE)
===============================================================================

Provides PostgreSQL support using SQLAlchemy 2.0 with dual-engine architecture.

    • Async engine → primary runtime engine (FastAPI / async workloads)
    • Sync engine  → background workers / migrations / CLI tools

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

Infrastructure Layer ONLY.

Responsible for:

    • engine construction
    • connection pool configuration
    • session factory creation
    • connectivity validation
    • lifecycle management
    • graceful shutdown

NOT responsible for:

    • HTTP concerns
    • business logic
    • repository abstraction
    • transaction boundaries

-------------------------------------------------------------------------------
TRANSACTION POLICY
-------------------------------------------------------------------------------

This adapter NEVER auto-commits.

Transaction lifecycle must be controlled by:

    async with UnitOfWork(session):

Repositories may call:

    session.flush()

Repositories MUST NOT call:

    session.commit()
    session.rollback()

-------------------------------------------------------------------------------
ENGINE ARCHITECTURE
-------------------------------------------------------------------------------

Two engines are created:

Async Engine
    → used by FastAPI endpoints
    → used by async repositories

Sync Engine
    → used by background workers
    → used by scripts / CLI
    → used by migrations

Exactly ONE instance per process.

-------------------------------------------------------------------------------
LIFECYCLE CONTRACT
-------------------------------------------------------------------------------

Application Startup
    → adapter instantiated
    → ping() verifies connectivity

Application Runtime
    → repositories obtain sessions via factory

Application Shutdown
    → close() disposes both engines
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.config import AppSettings


logger = get_logger("postgres")


# =============================================================================
# POSTGRES DATABASE ADAPTER
# =============================================================================


class PostgresDatabase:
    """
    Production-grade PostgreSQL adapter.

    Manages async and sync SQLAlchemy engines and session factories.

    Guarantees:

        • exactly one engine pair per process
        • safe connection pooling
        • deterministic lifecycle
        • fail-fast configuration validation
    """

    def __init__(
        self,
        *,
        async_url: str,
        sync_url: str,
        pool_size: int,
        max_overflow: int,
        pool_timeout: int,
        pool_recycle: int,
        pool_pre_ping: bool,
        echo: bool,
    ) -> None:
        """
        Initialize PostgreSQL async and sync engines.

        Args:
            async_url:
                SQLAlchemy async connection string.

            sync_url:
                SQLAlchemy sync connection string.

            pool_size:
                Persistent connection pool size.

            max_overflow:
                Maximum temporary overflow connections.

            pool_timeout:
                Seconds to wait for available connection.

            pool_recycle:
                Seconds before connection recycled.

            pool_pre_ping:
                Enable connection liveness checks.

            echo:
                Enable SQL logging (development only).
        """

        # ---------------------------------------------------------------------
        # Defensive configuration validation
        # ---------------------------------------------------------------------

        if not async_url:
            raise ValueError("Async database URL must be provided")

        if not sync_url:
            raise ValueError("Sync database URL must be provided")

        if pool_size <= 0:
            raise ValueError("pool_size must be > 0")

        if max_overflow < 0:
            raise ValueError("max_overflow must be >= 0")

        if pool_timeout <= 0:
            raise ValueError("pool_timeout must be > 0")

        if pool_recycle < 0:
            raise ValueError("pool_recycle must be >= 0")

        # ---------------------------------------------------------------------
        # ASYNC ENGINE
        # ---------------------------------------------------------------------

        self._async_engine: AsyncEngine = create_async_engine(
            async_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
            echo=echo,
        )

        # ---------------------------------------------------------------------
        # SYNC ENGINE
        # ---------------------------------------------------------------------

        self._sync_engine: Engine = create_engine(
            sync_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
            echo=echo,
        )

        # ---------------------------------------------------------------------
        # SESSION FACTORIES
        # ---------------------------------------------------------------------

        self._async_session_factory: async_sessionmaker[AsyncSession] = (
            async_sessionmaker(
                bind=self._async_engine,
                expire_on_commit=False,
                autoflush=False,
            )
        )

        self._sync_session_factory: sessionmaker[Session] = sessionmaker(
            bind=self._sync_engine,
            expire_on_commit=False,
            autoflush=False,
        )

        logger.info(
            "PostgreSQL engines initialized",
            extra={
                "pool_size": pool_size,
                "max_overflow": max_overflow,
            },
        )

    # =========================================================================
    # SESSION FACTORIES
    # =========================================================================

    @property
    def async_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """
        Expose async session factory.

        Intended for:

            • async repositories
            • UnitOfWork
            • async background jobs
        """
        return self._async_session_factory

    @property
    def sync_session_factory(self) -> sessionmaker[Session]:
        """
        Expose sync session factory.

        Intended for:

            • background workers
            • CLI scripts
            • migration tooling
        """
        return self._sync_session_factory

    # =========================================================================
    # SESSION CONTEXT MANAGERS
    # =========================================================================

    @asynccontextmanager
    async def async_session(self) -> AsyncIterator[AsyncSession]:
        """
        Provide async SQLAlchemy session.

        Behavior:

            • does NOT auto-commit
            • does NOT auto-rollback
            • UnitOfWork controls transaction lifecycle
        """

        async with self._async_session_factory() as session:
            yield session

    @contextmanager
    def sync_session(self) -> Iterator[Session]:
        """
        Provide synchronous SQLAlchemy session.

        Must NOT be used inside async endpoints without threadpool.
        """

        with self._sync_session_factory() as session:
            yield session

    # =========================================================================
    # HEALTH CHECK
    # =========================================================================

    async def ping(self) -> None:
        """
        Validate database connectivity.

        Intended for application startup validation.

        Uses async engine for primary connectivity test.
        """

        async with self._async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        logger.info("PostgreSQL connectivity verified")

    # =========================================================================
    # SHUTDOWN
    # =========================================================================

    async def close(self) -> None:
        """
        Dispose both async and sync engines.

        Releases connection pools and closes sockets.
        """

        logger.info("Disposing PostgreSQL engines")

        await self._async_engine.dispose()
        self._sync_engine.dispose()

    # =========================================================================
    # FACTORY METHOD
    # =========================================================================

    @classmethod
    def from_settings(cls, s: AppSettings) -> "PostgresDatabase":
        """
        Construct adapter from validated application settings.

        Args:
            s:
                validated AppSettings instance.

        Raises:
            RuntimeError if PostgreSQL configuration is invalid.
        """

        if not s.ENABLE_POSTGRES:
            raise RuntimeError("PostgreSQL disabled via configuration")

        if not s.POSTGRES_ASYNC_URL:
            raise RuntimeError("POSTGRES_ASYNC_URL missing")

        if not s.POSTGRES_SYNC_URL:
            raise RuntimeError("POSTGRES_SYNC_URL missing")

        return cls(
            async_url=s.POSTGRES_ASYNC_URL,
            sync_url=s.POSTGRES_SYNC_URL,
            pool_size=s.DB_POOL_SIZE,
            max_overflow=s.DB_MAX_OVERFLOW,
            pool_timeout=s.DB_POOL_TIMEOUT,
            pool_recycle=s.DB_POOL_RECYCLE,
            pool_pre_ping=s.DB_POOL_PRE_PING,
            echo=s.DB_ECHO,
        )


__all__ = [
    "PostgresDatabase",
]
