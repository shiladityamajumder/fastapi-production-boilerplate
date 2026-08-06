"""File: app/db/registry.py.

Lifecycle registry for configured database and cache adapters.

Current active integration:

- MySQL

Reference implementations retained as commented code:

- Microsoft SQL Server
- PostgreSQL
- MongoDB
- Redis

To enable another integration, uncomment every block for that integration in
this file and complete the related activation steps documented beside its
import.

FastAPI and Celery worker processes must each create their own registry.
Database engines, clients, and connection pools must never be shared across
operating-system processes.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping  # noqa: TC003
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from app.common.exceptions import (
    InfrastructureUnavailableError,
)
from app.core.config import AppSettings  # noqa: TC001
from app.core.logging import get_logger
from app.db.mysql import MySQLDatabase

# =============================================================================
# OPTIONAL DATABASE AND CACHE IMPORTS
# =============================================================================
#
# MySQL is currently the only active database integration.
#
# To activate another integration:
#
# 1. Uncomment its import below.
# 2. Uncomment its constructor argument and instance attribute.
# 3. Uncomment its ``from_settings`` initialization block.
# 4. Uncomment its registration inside the ``adapters`` property.
# 5. Uncomment its settings in ``app/core/config.py``.
# 6. Uncomment its API dependencies.
# 7. Install its required Python package or database driver.
# 8. Add its connection settings to the environment configuration.
#
# Multiple integrations may be enabled by uncommenting their complete blocks
# together.
# =============================================================================


# -----------------------------------------------------------------------------
# MICROSOFT SQL SERVER SUPPORT
#
# Related files:
#     app/db/mssql.py
#     app/core/config.py
#     app/api/dependencies.py or app/api/dependencies/mssql.py
#
# Required packages:
#     aioodbc
#     pyodbc
#
# Required environment configuration:
#     ENABLE_MSSQL=true
#     MSSQL_URL=...
# -----------------------------------------------------------------------------
# from app.db.mssql import MSSQLDatabase


# -----------------------------------------------------------------------------
# POSTGRESQL SUPPORT
#
# Related files:
#     app/db/postgres.py
#     app/core/config.py
#     app/api/dependencies.py or app/api/dependencies/postgres.py
#
# Required package:
#     asyncpg
#
# Required environment configuration:
#     ENABLE_POSTGRES=true
#     POSTGRES_URL=...
# -----------------------------------------------------------------------------
# from app.db.postgres import PostgreSQLDatabase


# -----------------------------------------------------------------------------
# MONGODB SUPPORT
#
# Related files:
#     app/db/mongo.py
#     app/core/config.py
#     app/api/dependencies.py or app/api/dependencies/mongo.py
#
# Required package:
#     pymongo
#
# Required environment configuration:
#     ENABLE_MONGO=true
#     MONGO_URI=...
#     MONGO_DB_NAME=...
# -----------------------------------------------------------------------------
# from app.db.mongo import MongoDatabase


# -----------------------------------------------------------------------------
# REDIS SUPPORT
#
# Related files:
#     app/db/redis_client.py
#     app/core/config.py
#     app/api/dependencies.py or app/api/dependencies/redis.py
#
# Required package:
#     redis
#
# Required environment configuration:
#     ENABLE_REDIS=true
#     REDIS_URL=...
#
# Application Redis is independent of the Celery broker. Celery may use Redis
# as its broker without enabling this application Redis adapter.
# -----------------------------------------------------------------------------
# from app.db.redis_client import RedisClient


logger = get_logger(__name__)


@runtime_checkable
class InfrastructureAdapter(Protocol):
    """Minimal lifecycle contract implemented by infrastructure adapters.

    Every active adapter owns its engine, client, or connection pool and must
    validate and release those resources through this contract.
    """

    async def ping(self) -> None:
        """Validate dependency connectivity.

        Raises:
            Exception: If the dependency cannot be reached.
        """
        ...

    async def close(self) -> None:
        """Release resources owned by the adapter."""
        ...


@dataclass(
    frozen=True,
    slots=True,
)
class HealthStatus:
    """Sanitized health result for an active infrastructure adapter.

    Attributes:
        healthy: Whether the adapter responded successfully.
        duration_ms: Health-check duration in milliseconds.
    """

    healthy: bool
    duration_ms: float


class DatabaseRegistry:
    """Own infrastructure adapters configured for the current process.

    MySQL is currently active. Other adapter implementations remain in this
    file as commented reference blocks and create no imports, clients, engines,
    pools, startup checks, or shutdown work.

    Each FastAPI process and Celery worker child must construct its own
    ``DatabaseRegistry``.
    """

    def __init__(
        self,
        *,
        mysql: MySQLDatabase | None = None,
        # ---------------------------------------------------------------------
        # MICROSOFT SQL SERVER
        #
        # Uncomment together with the MSSQL import and all MSSQL blocks below.
        # ---------------------------------------------------------------------
        # mssql: MSSQLDatabase | None = None,
        # ---------------------------------------------------------------------
        # POSTGRESQL
        #
        # Uncomment together with the PostgreSQL import and all PostgreSQL
        # blocks below.
        # ---------------------------------------------------------------------
        # postgres: PostgreSQLDatabase | None = None,
        # ---------------------------------------------------------------------
        # MONGODB
        #
        # Uncomment together with the MongoDB import and all MongoDB blocks
        # below.
        # ---------------------------------------------------------------------
        # mongo: MongoDatabase | None = None,
        # ---------------------------------------------------------------------
        # REDIS
        #
        # Uncomment together with the Redis import and all Redis blocks below.
        # ---------------------------------------------------------------------
        # redis: RedisClient | None = None,
    ) -> None:
        """Initialize the infrastructure registry.

        Args:
            mysql: Optional active MySQL adapter.

        Optional constructor arguments for MSSQL, PostgreSQL, MongoDB, and Redis
        are retained as commented reference blocks.
        """
        self.mysql = mysql

        # ---------------------------------------------------------------------
        # MICROSOFT SQL SERVER
        # ---------------------------------------------------------------------
        # self.mssql = mssql

        # ---------------------------------------------------------------------
        # POSTGRESQL
        # ---------------------------------------------------------------------
        # self.postgres = postgres

        # ---------------------------------------------------------------------
        # MONGODB
        # ---------------------------------------------------------------------
        # self.mongo = mongo

        # ---------------------------------------------------------------------
        # REDIS
        # ---------------------------------------------------------------------
        # self.redis = redis

    @classmethod
    def from_settings(
        cls,
        settings: AppSettings,
    ) -> DatabaseRegistry:
        """Construct active infrastructure adapters from configuration.

        MySQL is currently the only active integration.

        Args:
            settings: Validated application settings.

        Returns:
            Registry containing the configured MySQL adapter, or an empty
            registry when MySQL is disabled.

        Raises:
            RuntimeError: If MySQL is enabled but incompletely configured.
        """
        return cls(
            mysql=(
                MySQLDatabase.from_settings(settings) if settings.ENABLE_MYSQL else None
            ),
            # -----------------------------------------------------------------
            # MICROSOFT SQL SERVER
            #
            # Activation requirements:
            #     - Uncomment the MSSQL import.
            #     - Uncomment the MSSQL constructor argument and attribute.
            #     - Uncomment this block.
            #     - Uncomment ENABLE_MSSQL and MSSQL settings in config.py.
            #     - Install aioodbc and pyodbc.
            # -----------------------------------------------------------------
            # mssql=(
            #     MSSQLDatabase.from_settings(settings)
            #     if settings.ENABLE_MSSQL
            #     else None
            # ),
            # -----------------------------------------------------------------
            # POSTGRESQL
            #
            # Activation requirements:
            #     - Uncomment the PostgreSQL import.
            #     - Uncomment the PostgreSQL constructor argument and attribute.
            #     - Uncomment this block.
            #     - Uncomment ENABLE_POSTGRES and related settings in config.py.
            #     - Install asyncpg.
            # -----------------------------------------------------------------
            # postgres=(
            #     PostgreSQLDatabase.from_settings(settings)
            #     if settings.ENABLE_POSTGRES
            #     else None
            # ),
            # -----------------------------------------------------------------
            # MONGODB
            #
            # Activation requirements:
            #     - Uncomment the MongoDB import.
            #     - Uncomment the MongoDB constructor argument and attribute.
            #     - Uncomment this block.
            #     - Uncomment ENABLE_MONGO and related settings in config.py.
            #     - Install pymongo.
            # -----------------------------------------------------------------
            # mongo=(
            #     MongoDatabase.from_settings(settings)
            #     if settings.ENABLE_MONGO
            #     else None
            # ),
            # -----------------------------------------------------------------
            # REDIS
            #
            # Activation requirements:
            #     - Uncomment the Redis import.
            #     - Uncomment the Redis constructor argument and attribute.
            #     - Uncomment this block.
            #     - Uncomment ENABLE_REDIS and related settings in config.py.
            #     - Install redis.
            # -----------------------------------------------------------------
            # redis=(
            #     RedisClient.from_settings(settings)
            #     if settings.ENABLE_REDIS
            #     else None
            # ),
        )

    @property
    def adapters(
        self,
    ) -> Mapping[str, InfrastructureAdapter]:
        """Return active adapters in deterministic lifecycle order.

        Only active, initialized adapters are included. Health checks and
        shutdown operations use this mapping, so commented integrations are
        ignored completely.

        Returns:
            Read-only mapping of adapter names to instances.
        """
        configured: dict[
            str,
            InfrastructureAdapter,
        ] = {}

        if self.mysql is not None:
            configured["mysql"] = self.mysql

        # ---------------------------------------------------------------------
        # MICROSOFT SQL SERVER
        #
        # Uncomment together with all other MSSQL blocks.
        # ---------------------------------------------------------------------
        # if self.mssql is not None:
        #     configured["mssql"] = self.mssql

        # ---------------------------------------------------------------------
        # POSTGRESQL
        #
        # Uncomment together with all other PostgreSQL blocks.
        # ---------------------------------------------------------------------
        # if self.postgres is not None:
        #     configured["postgres"] = self.postgres

        # ---------------------------------------------------------------------
        # MONGODB
        #
        # Uncomment together with all other MongoDB blocks.
        # ---------------------------------------------------------------------
        # if self.mongo is not None:
        #     configured["mongo"] = self.mongo

        # ---------------------------------------------------------------------
        # REDIS
        #
        # Uncomment together with all other Redis blocks.
        # ---------------------------------------------------------------------
        # if self.redis is not None:
        #     configured["redis"] = self.redis

        return MappingProxyType(configured)

    @property
    def adapter_names(
        self,
    ) -> tuple[str, ...]:
        """Return active adapter names.

        Returns:
            Adapter names in lifecycle order.
        """
        return tuple(self.adapters)

    async def check_all(
        self,
        *,
        timeout_seconds: float,
    ) -> dict[str, HealthStatus]:
        """Check all active dependencies concurrently.

        Each active adapter receives an independent timeout. Disabled or
        commented integrations are not imported, initialized, or checked.

        Failures are logged internally with stack traces but returned as
        sanitized health results.

        Args:
            timeout_seconds: Maximum duration allowed for each adapter check.

        Returns:
            Health results indexed by active adapter name.

        Raises:
            ValueError: If ``timeout_seconds`` is not positive.
        """
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        async def check_adapter(
            name: str,
            adapter: InfrastructureAdapter,
        ) -> tuple[str, HealthStatus]:
            """Check one active adapter.

            Args:
                name: Registered adapter name.
                adapter: Active infrastructure adapter.

            Returns:
                Adapter name and sanitized health result.
            """
            started_at = time.perf_counter()
            healthy = True

            try:
                async with asyncio.timeout(timeout_seconds):
                    await adapter.ping()

            except Exception:
                healthy = False

                logger.warning(
                    "Infrastructure health check failed",
                    extra={
                        "adapter": name,
                    },
                    exc_info=True,
                )

            duration_ms = round(
                (time.perf_counter() - started_at) * 1_000,
                2,
            )

            return (
                name,
                HealthStatus(
                    healthy=healthy,
                    duration_ms=duration_ms,
                ),
            )

        configured_adapters = self.adapters

        if not configured_adapters:
            return {}

        results = await asyncio.gather(
            *(
                check_adapter(
                    name,
                    adapter,
                )
                for name, adapter in configured_adapters.items()
            )
        )

        return dict(results)

    async def ping_all(
        self,
        *,
        timeout_seconds: float,
    ) -> None:
        """Validate every active dependency during process startup.

        A process must not report ready when an active dependency is
        unavailable. Commented integrations do not participate in startup
        validation.

        Args:
            timeout_seconds: Maximum duration allowed for each adapter check.

        Raises:
            ValueError: If ``timeout_seconds`` is not positive.
            InfrastructureUnavailableError: If one or more active adapters
                fail.
        """
        checks = await self.check_all(
            timeout_seconds=timeout_seconds,
        )

        unavailable = [name for name, result in checks.items() if not result.healthy]

        if unavailable:
            raise InfrastructureUnavailableError(
                message=("Required infrastructure failed startup validation."),
                details={
                    "dependencies": unavailable,
                },
            )

    async def close(self) -> None:
        """Close active adapters in reverse lifecycle order.

        Shutdown continues when one adapter fails so all remaining resources
        still receive a cleanup attempt.

        Commented integrations produce no shutdown behavior.
        """
        configured_adapters = tuple(self.adapters.items())

        for name, adapter in reversed(configured_adapters):
            try:
                await adapter.close()

            except Exception:
                logger.exception(
                    "Infrastructure adapter shutdown failed",
                    extra={
                        "adapter": name,
                    },
                )


__all__ = [
    "DatabaseRegistry",
    "HealthStatus",
    "InfrastructureAdapter",
]
