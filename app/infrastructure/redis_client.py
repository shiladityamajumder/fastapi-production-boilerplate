# File: app/infrastructure/redis_client.py
"""
===============================================================================
REDIS ASYNC ADAPTER (PRODUCTION-GRADE)
===============================================================================

Provides Redis client abstraction using redis.asyncio.

This adapter manages the Redis client lifecycle and exposes a shared
connection pool for infrastructure components.

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

Infrastructure Layer ONLY.

Responsible for:

    • Redis client creation
    • Connection pool configuration
    • Connectivity validation
    • Lifecycle management
    • Graceful shutdown
    • Exposing Redis client

NOT responsible for:

    • rate limiting logic
    • idempotency logic
    • caching strategies
    • business logic
    • HTTP concerns

Those concerns belong to higher-level infrastructure modules.

-------------------------------------------------------------------------------
CLIENT SAFETY
-------------------------------------------------------------------------------

redis.asyncio.Redis client instances are:

    • coroutine-safe
    • thread-safe
    • connection-pooled

Exactly ONE Redis client instance should exist per process.

The client internally manages connection pooling and socket reuse.

-------------------------------------------------------------------------------
LIFECYCLE CONTRACT
-------------------------------------------------------------------------------

Application Startup
    → adapter instantiated
    → ping() verifies connectivity

Application Runtime
    → services and infrastructure components access Redis client

Application Shutdown
    → close() releases connection pool

-------------------------------------------------------------------------------
FAILURE POLICY
-------------------------------------------------------------------------------

If ENABLE_REDIS=True and configuration invalid
    → application must fail at startup

If ping() fails
    → startup must abort

No silent fallback.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Awaitable, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.config import AppSettings


logger = get_logger("redis")


# =============================================================================
# REDIS CLIENT ADAPTER
# =============================================================================


class RedisClient:
    """
    Production-grade Redis adapter.

    Manages Redis client lifecycle and connection pool.

    Guarantees:

        • exactly one client per process
        • deterministic lifecycle
        • safe connection pooling
        • fail-fast configuration validation
    """

    def __init__(
        self,
        *,
        url: str,
        max_connections: int,
        socket_timeout: float,
        socket_connect_timeout: float,
    ) -> None:
        """
        Initialize Redis client and connection pool.

        Args:
            url:
                Redis connection URL.

            max_connections:
                Maximum connection pool size.

            socket_timeout:
                Socket read timeout in seconds.

            socket_connect_timeout:
                Socket connection timeout in seconds.

        Raises:
            ValueError if configuration values are invalid.
        """

        # ---------------------------------------------------------------------
        # Defensive configuration validation
        # ---------------------------------------------------------------------

        if not url:
            raise ValueError("Redis URL must be provided")

        if max_connections <= 0:
            raise ValueError("max_connections must be > 0")

        if socket_timeout <= 0:
            raise ValueError("socket_timeout must be > 0")

        if socket_connect_timeout <= 0:
            raise ValueError("socket_connect_timeout must be > 0")

        # ---------------------------------------------------------------------
        # Redis client creation
        # ---------------------------------------------------------------------

        self._client: Redis = Redis.from_url(
            url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
        )

        logger.info(
            "Redis client initialized",
            extra={
                "max_connections": max_connections,
                "socket_timeout": socket_timeout,
            },
        )

    # =========================================================================
    # CLIENT ACCESS
    # =========================================================================

    @property
    def client(self) -> Redis:
        """
        Expose underlying Redis client.

        Intended for use by infrastructure components such as:

            • RateLimiter
            • IdempotencyStore
            • CacheLayer
            • Distributed locks
        """
        return self._client

    # =========================================================================
    # HEALTH CHECK
    # =========================================================================

    async def ping(self, timeout: float = 5.0) -> None:
        """
        Validate Redis connectivity.

        Used during application startup.

        Args:
            timeout:
                Maximum seconds allowed for connectivity check.

        Raises:
            RedisError
            asyncio.TimeoutError
        """

        try:
            # redis.asyncio type stubs incorrectly allow non-awaitable
            ping_coro = cast(Awaitable[bool], self._client.ping())

            await asyncio.wait_for(ping_coro, timeout=timeout)

            logger.info("Redis connectivity verified")

        except (RedisError, asyncio.TimeoutError):

            logger.exception("Redis connectivity check failed")

            raise

    # =========================================================================
    # SHUTDOWN
    # =========================================================================

    async def close(self) -> None:
        """
        Gracefully close Redis client and connection pool.

        Behavior:

            • closes connection pool
            • releases sockets
            • stops background tasks

        Safe to call multiple times.
        """

        logger.info("Closing Redis client")

        try:
            await self._client.close()

        except Exception:
            logger.exception("Redis shutdown encountered error")

    # =========================================================================
    # FACTORY METHOD
    # =========================================================================

    @classmethod
    def from_settings(cls, s: AppSettings) -> "RedisClient":
        """
        Construct Redis adapter from validated application settings.

        Args:
            s:
                validated AppSettings instance.

        Raises:
            RuntimeError if Redis configuration invalid.
        """

        if not s.ENABLE_REDIS:
            raise RuntimeError("Redis disabled via configuration")

        if not s.REDIS_URL:
            raise RuntimeError("REDIS_URL missing")

        return cls(
            url=s.REDIS_URL,
            max_connections=s.REDIS_MAX_CONNECTIONS,
            socket_timeout=s.REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=s.REDIS_SOCKET_CONNECT_TIMEOUT,
        )


__all__ = [
    "RedisClient",
]
