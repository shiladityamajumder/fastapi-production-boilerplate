# File: app/db/registry.py
"""
===============================================================================
DATABASE REGISTRY (INFRASTRUCTURE RESOURCE MANAGER)
===============================================================================

Central registry responsible for managing all infrastructure adapters used
by the application.

This component provides a single, structured entry point for accessing
external infrastructure resources such as:

    • PostgreSQL
    • MySQL
    • MSSQL
    • MongoDB
    • Redis

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

This module belongs to the Infrastructure Layer.

Responsibilities:

    • Store initialized infrastructure adapters
    • Provide centralized runtime access
    • Validate connectivity during application startup
    • Ensure graceful shutdown of all resources

This module is NOT responsible for:

    • Dependency injection
    • Business logic
    • Transaction management
    • HTTP concerns
    • Repository behavior

-------------------------------------------------------------------------------
WHY A REGISTRY EXISTS
-------------------------------------------------------------------------------

Without a registry, infrastructure resources would typically be stored
individually in FastAPI state:

    app.state.postgres
    app.state.mongo
    app.state.redis

As the system grows this quickly becomes difficult to maintain.

The registry provides a unified interface:

    app.state.db.postgres
    app.state.db.mongo
    app.state.db.redis

This improves:

    • discoverability
    • maintainability
    • testability
    • architectural clarity

-------------------------------------------------------------------------------
LIFECYCLE CONTRACT
-------------------------------------------------------------------------------

Application Startup

    registry = DatabaseRegistry(...)
    await registry.ping_all()

Application Runtime

    request.app.state.db.<adapter>

Application Shutdown

    await registry.close()

-------------------------------------------------------------------------------
FAILURE POLICY
-------------------------------------------------------------------------------

If ANY enabled infrastructure adapter fails its connectivity check:

    → Application startup MUST abort.

The system intentionally fails fast to avoid partial system operation.
"""

from __future__ import annotations

from typing import Optional

from app.core.logging import get_logger
from app.infrastructure.postgres import PostgresDatabase
from app.infrastructure.mysql import MySQLDatabase
from app.infrastructure.mssql import MSSQLDatabase
from app.infrastructure.mongo import MongoDatabase
from app.infrastructure.redis_client import RedisClient


logger = get_logger("db_registry")


# =============================================================================
# DATABASE REGISTRY
# =============================================================================


class DatabaseRegistry:
    """
    Central container for all infrastructure adapters.

    This class acts as the single access point for infrastructure resources
    during application runtime.

    Each adapter is optional and only present when enabled in configuration.

    Example runtime access:

        db = request.app.state.db
        session = db.postgres
        cache = db.redis
    """

    def __init__(
        self,
        *,
        postgres: Optional[PostgresDatabase] = None,
        mysql: Optional[MySQLDatabase] = None,
        mssql: Optional[MSSQLDatabase] = None,
        mongo: Optional[MongoDatabase] = None,
        redis: Optional[RedisClient] = None,
    ) -> None:
        """
        Initialize registry with infrastructure adapters.

        Adapters are injected during application startup.

        Args:
            postgres: PostgreSQL adapter
            mysql: MySQL adapter
            mssql: MSSQL adapter
            mongo: MongoDB adapter
            redis: Redis adapter
        """

        self.postgres = postgres
        self.mysql = mysql
        self.mssql = mssql
        self.mongo = mongo
        self.redis = redis

    # =========================================================================
    # STARTUP HEALTH CHECK
    # =========================================================================

    async def ping_all(self) -> None:
        """
        Validate connectivity for all enabled infrastructure resources.

        This method is executed during application startup.

        Each adapter performs its own connectivity check.

        If any adapter fails, startup must abort to prevent the application
        from running in a partially functional state.
        """

        logger.info("Validating infrastructure connectivity")

        if self.postgres:
            await self.postgres.ping()

        if self.mongo:
            await self.mongo.ping()

        if self.redis:
            await self.redis.ping()

        if self.mysql:
            await self.mysql.ping()

        if self.mssql:
            await self.mssql.ping()

        logger.info("All infrastructure connectivity checks passed")

    # =========================================================================
    # SHUTDOWN
    # =========================================================================

    async def close(self) -> None:
        """
        Gracefully close all infrastructure adapters.

        This method is called during application shutdown.

        Shutdown order prioritizes async infrastructure first to reduce
        the chance of blocking shutdown operations.

        Errors during shutdown are logged but do not interrupt closing of
        other resources.
        """

        logger.info("Shutting down infrastructure adapters")

        adapters = [
            self.redis,
            self.mongo,
            self.postgres,
            self.mysql,
            self.mssql,
        ]

        for adapter in adapters:

            if adapter is None:
                continue

            try:
                await adapter.close()

            except Exception:
                logger.exception("Adapter shutdown failed")

        logger.info("Infrastructure shutdown complete")
