# File: app/infrastructure/mssql.py
"""
===============================================================================
MICROSOFT SQL SERVER DATABASE ADAPTER (PRODUCTION-GRADE)
===============================================================================

Provides Microsoft SQL Server support using SQLAlchemy 2.0 synchronous engine.

This adapter is intended for environments where:

    • legacy systems require MSSQL
    • async drivers are unavailable or unstable
    • synchronous workloads dominate

-------------------------------------------------------------------------------
CRITICAL WARNING
-------------------------------------------------------------------------------

This adapter uses a synchronous SQLAlchemy engine.

Blocking database calls MUST NOT run directly inside async endpoints.

When used inside async contexts, calls must be wrapped using:

    fastapi.concurrency.run_in_threadpool()

Failing to do so WILL block the event loop and degrade performance.

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

Infrastructure Layer ONLY.

Responsible for:

    • engine creation
    • connection pool configuration
    • session factory creation
    • connectivity validation
    • lifecycle management
    • resource cleanup

NOT responsible for:

    • HTTP concerns
    • business logic
    • repository abstraction
    • transaction boundaries

-------------------------------------------------------------------------------
TRANSACTION POLICY
-------------------------------------------------------------------------------

This adapter NEVER auto-commits.

Transaction boundaries must be controlled by:

    • service layer
    • SyncUnitOfWork abstraction (if implemented)

Repositories may call:

    session.flush()

Repositories MUST NOT call:

    session.commit()
    session.rollback()

-------------------------------------------------------------------------------
LIFECYCLE CONTRACT
-------------------------------------------------------------------------------

Application Startup
    → adapter instantiated
    → ping() verifies connectivity

Application Runtime
    → repositories obtain sessions via factory

Application Shutdown
    → close() disposes engine

Exactly ONE engine per process.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.config import AppSettings


logger = get_logger("mssql")


# =============================================================================
# MSSQL DATABASE ADAPTER
# =============================================================================


class MSSQLDatabase:
    """
    Production-grade Microsoft SQL Server adapter.

    This adapter manages the SQLAlchemy engine lifecycle and provides
    a session factory for repositories and services.

    Guarantees:

        • exactly one engine per process
        • deterministic lifecycle
        • explicit configuration validation
        • safe connection pooling
    """

    def __init__(
        self,
        *,
        url: str,
        pool_size: int,
        max_overflow: int,
        pool_timeout: int,
        pool_recycle: int,
        pool_pre_ping: bool,
        echo: bool,
    ) -> None:
        """
        Initialize MSSQL engine and session factory.

        Args:
            url:
                SQLAlchemy connection string.

            pool_size:
                Number of persistent connections maintained in pool.

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

        Raises:
            ValueError if configuration values are invalid.
        """

        # ---------------------------------------------------------------------
        # Defensive configuration validation
        # ---------------------------------------------------------------------

        if not url:
            raise ValueError("Database URL must be provided")

        if pool_size <= 0:
            raise ValueError("pool_size must be > 0")

        if max_overflow < 0:
            raise ValueError("max_overflow must be >= 0")

        if pool_timeout <= 0:
            raise ValueError("pool_timeout must be > 0")

        if pool_recycle < 0:
            raise ValueError("pool_recycle must be >= 0")

        # ---------------------------------------------------------------------
        # Engine creation
        # ---------------------------------------------------------------------

        self._engine: Engine = create_engine(
            url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
            fast_executemany=True,  # important for MSSQL bulk inserts
            echo=echo,
        )

        # ---------------------------------------------------------------------
        # Session factory
        # ---------------------------------------------------------------------

        self._session_factory: sessionmaker[Session] = sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            autoflush=False,
        )

        logger.info(
            "MSSQL engine initialized",
            extra={
                "pool_size": pool_size,
                "max_overflow": max_overflow,
            },
        )

    # =========================================================================
    # SESSION FACTORY
    # =========================================================================

    @property
    def session_factory(self) -> sessionmaker[Session]:
        """
        Expose session factory.

        Intended for:

            • repositories
            • unit-of-work abstractions
            • background workers
        """
        return self._session_factory

    # =========================================================================
    # SESSION CONTEXT MANAGER
    # =========================================================================

    @contextmanager
    def session(self) -> Iterator[Session]:
        """
        Provide synchronous SQLAlchemy session.

        Behavior:

            • does NOT auto-commit
            • does NOT auto-rollback
            • service layer controls transaction boundary

        Example:

            with db.session() as session:
                repo = ProductRepository(session)
        """
        with self._session_factory() as session:
            yield session

    # =========================================================================
    # HEALTH CHECK
    # =========================================================================

    async def ping(self) -> None:
        """
        Validate database connectivity.

        This method is async-safe and can be used during
        async application startup.

        Internally executes sync query in threadpool.
        """

        loop = asyncio.get_running_loop()

        await loop.run_in_executor(None, self._sync_ping)

        logger.info("MSSQL connectivity verified")

    def _sync_ping(self) -> None:
        """Internal synchronous connectivity check."""
        with self._engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    # =========================================================================
    # SHUTDOWN
    # =========================================================================

    async def close(self) -> None:
        """
        Dispose SQLAlchemy engine.

        Releases all pooled connections.
        """

        logger.info("Disposing MSSQL engine")

        self._engine.dispose()

    # =========================================================================
    # FACTORY METHOD
    # =========================================================================

    @classmethod
    def from_settings(cls, s: AppSettings) -> "MSSQLDatabase":
        """
        Construct adapter from validated application settings.

        Args:
            s:
                validated AppSettings instance.

        Raises:
            RuntimeError if MSSQL is disabled or misconfigured.
        """

        if not s.ENABLE_MSSQL:
            raise RuntimeError("MSSQL disabled via configuration")

        if not s.MSSQL_URL:
            raise RuntimeError("MSSQL_URL missing")

        return cls(
            url=s.MSSQL_URL,
            pool_size=s.DB_POOL_SIZE,
            max_overflow=s.DB_MAX_OVERFLOW,
            pool_timeout=s.DB_POOL_TIMEOUT,
            pool_recycle=s.DB_POOL_RECYCLE,
            pool_pre_ping=s.DB_POOL_PRE_PING,
            echo=s.DB_ECHO,
        )


__all__ = [
    "MSSQLDatabase",
]
