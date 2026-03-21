# File: app/infrastructure/mongo.py
"""
===============================================================================
MONGODB ASYNC ADAPTER (PRODUCTION-GRADE)
===============================================================================

Provides a production-grade MongoDB adapter built on Motor.

Motor is the official async MongoDB driver for Python and internally uses
PyMongo's connection pooling and monitoring capabilities.

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

Infrastructure Layer ONLY.

This component is responsible for:

    • Mongo client creation
    • Connection pool configuration
    • Connectivity validation
    • Graceful lifecycle management
    • Exposing database handle to repositories

This component is NOT responsible for:

    • HTTP / FastAPI concerns
    • Repository abstraction
    • Business logic
    • Application transaction boundaries
    • Dependency injection

-------------------------------------------------------------------------------
LIFECYCLE CONTRACT
-------------------------------------------------------------------------------

Application Startup
    → MongoDatabase instance created
    → ping() verifies connectivity
    → instance stored in application registry

Application Runtime
    → repositories access db handle

Application Shutdown
    → close() releases connection pool

Exactly ONE client instance per process.

Motor clients are:

    • thread-safe
    • coroutine-safe
    • designed for global reuse

-------------------------------------------------------------------------------
FAILURE POLICY
-------------------------------------------------------------------------------

Configuration errors
    → immediate crash at startup

Connectivity failures
    → startup abort

No silent fallback behavior.

-------------------------------------------------------------------------------
POOLING BEHAVIOR
-------------------------------------------------------------------------------

Motor internally maintains a connection pool.

Configuration parameters allow tuning for:

    • high concurrency workloads
    • containerized environments
    • burst traffic

Recommended production ranges:

    min_pool_size: 1–5
    max_pool_size: 10–100
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.config import AppSettings


logger = get_logger("mongo")


# =============================================================================
# MONGO DATABASE ADAPTER
# =============================================================================


class MongoDatabase:
    """
    Production-grade MongoDB async adapter.

    This class manages the lifecycle of the MongoDB client and provides
    access to the configured database.

    Design guarantees:

        • Exactly one client per process
        • Thread-safe and coroutine-safe
        • Deterministic lifecycle
        • Explicit configuration validation
        • Fail-fast startup behavior
    """

    def __init__(
        self,
        *,
        uri: str,
        db_name: str,
        min_pool_size: int,
        max_pool_size: int,
        server_selection_timeout_ms: int,
    ) -> None:
        """
        Initialize MongoDB client.

        The client is created immediately (no lazy initialization).

        Args:
            uri:
                MongoDB connection URI.

            db_name:
                Target database name.

            min_pool_size:
                Minimum number of connections maintained in pool.

            max_pool_size:
                Maximum number of connections allowed in pool.

            server_selection_timeout_ms:
                Timeout for server selection during initial connection.

        Raises:
            ValueError:
                If configuration values are invalid.
        """

        # ---------------------------------------------------------------------
        # Configuration validation
        # ---------------------------------------------------------------------

        if not uri:
            raise ValueError("Mongo URI must be provided")

        if not db_name:
            raise ValueError("Mongo database name must be provided")

        if min_pool_size < 0:
            raise ValueError("min_pool_size must be >= 0")

        if max_pool_size <= 0:
            raise ValueError("max_pool_size must be > 0")

        if min_pool_size > max_pool_size:
            raise ValueError("min_pool_size cannot exceed max_pool_size")

        if server_selection_timeout_ms <= 0:
            raise ValueError("server_selection_timeout_ms must be > 0")

        # ---------------------------------------------------------------------
        # Internal state
        # ---------------------------------------------------------------------

        self._db_name = db_name

        # Motor client creation (immediate)
        self._client: AsyncIOMotorClient = AsyncIOMotorClient(
            uri,
            minPoolSize=min_pool_size,
            maxPoolSize=max_pool_size,
            serverSelectionTimeoutMS=server_selection_timeout_ms,
            uuidRepresentation="standard",
        )

        logger.info(
            "MongoDB client initialized",
            extra={
                "db": db_name,
                "min_pool": min_pool_size,
                "max_pool": max_pool_size,
            },
        )

    # =========================================================================
    # HEALTH CHECK
    # =========================================================================

    async def ping(self) -> None:
        """
        Validate MongoDB connectivity.

        This method is intended to be called during application startup.

        Ensures:

            • server reachable
            • authentication valid
            • connection pool operational

        Raises:
            Exception if connectivity fails.
        """

        await self._client.admin.command("ping")

        logger.info("MongoDB connectivity verified")

    # =========================================================================
    # DATABASE ACCESS
    # =========================================================================

    @property
    def db(self) -> AsyncIOMotorDatabase:
        """
        Retrieve database handle.

        Returns:
            AsyncIOMotorDatabase instance bound to configured database.

        Notes:
            This method does NOT create new connections.
            Connections are obtained from the internal pool automatically.
        """
        return self._client[self._db_name]

    # =========================================================================
    # CLIENT ACCESS (ADVANCED USE)
    # =========================================================================

    @property
    def client(self) -> AsyncIOMotorClient:
        """
        Expose underlying Mongo client.

        Intended only for advanced infrastructure components
        (metrics, diagnostics, or specialized operations).
        """
        return self._client

    # =========================================================================
    # SHUTDOWN
    # =========================================================================

    async def close(self) -> None:
        """
        Gracefully close MongoDB client.

        Safe to call multiple times.

        Behavior:
            - closes connection pool
            - releases sockets
            - stops monitoring threads
        """

        logger.info("Closing MongoDB client")

        self._client.close()

    # =========================================================================
    # FACTORY METHOD
    # =========================================================================

    @classmethod
    def from_settings(cls, s: AppSettings) -> "MongoDatabase":
        """
        Construct MongoDatabase from validated application settings.

        This factory method enforces configuration contracts and ensures
        infrastructure enablement is explicit.

        Args:
            s:
                Validated AppSettings instance.

        Raises:
            RuntimeError if MongoDB is disabled or misconfigured.
        """

        if not s.ENABLE_MONGO:
            raise RuntimeError("MongoDB disabled via configuration")

        if not s.MONGO_URI:
            raise RuntimeError("MONGO_URI missing")

        if not s.MONGO_DB_NAME:
            raise RuntimeError("MONGO_DB_NAME missing")

        return cls(
            uri=s.MONGO_URI,
            db_name=s.MONGO_DB_NAME,
            min_pool_size=s.MONGO_MIN_POOL_SIZE,
            max_pool_size=s.MONGO_MAX_POOL_SIZE,
            server_selection_timeout_ms=s.MONGO_SERVER_SELECTION_TIMEOUT_MS,
        )


__all__ = [
    "MongoDatabase",
]
