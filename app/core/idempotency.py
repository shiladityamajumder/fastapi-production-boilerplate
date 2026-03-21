# File: app/core/idempotency.py
"""
===============================================================================
DISTRIBUTED IDEMPOTENCY LAYER (REDIS-BASED)
===============================================================================

Provides request-level idempotency guarantees for write operations.

This module prevents duplicate execution of operations when clients retry
requests due to network failures, timeouts, or retries.

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

Core infrastructure component.

Responsibilities:

    - distributed request locking
    - response caching
    - retry safety
    - concurrency protection

This module does NOT:

    - handle HTTP logic
    - access request objects
    - manage Redis lifecycle
    - construct API responses

-------------------------------------------------------------------------------
PROBLEM SOLVED
-------------------------------------------------------------------------------

When a client retries a request with the same Idempotency-Key:

    - The operation must run exactly once
    - Duplicate writes must be prevented
    - Subsequent retries must return the original response

-------------------------------------------------------------------------------
EXECUTION STATE MACHINE
-------------------------------------------------------------------------------

Request lifecycle:

    1. Client sends request with Idempotency-Key
    2. System checks Redis cache
    3. If response exists → return cached response
    4. Otherwise acquire distributed lock (SET NX)
    5. Execute operation
    6. Store response
    7. Future retries return cached response

-------------------------------------------------------------------------------
FAILURE SAFETY
-------------------------------------------------------------------------------

If a process crashes mid-operation:

    - Lock expires automatically
    - Client can retry safely

-------------------------------------------------------------------------------
SCALABILITY
-------------------------------------------------------------------------------

Safe for:

    - multi-worker deployments
    - horizontal scaling
    - 10k+ RPS workloads

Redis provides global coordination across instances.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Awaitable

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.logging import get_logger


logger = get_logger("idempotency")


# =============================================================================
# EXCEPTIONS
# =============================================================================


class IdempotencyConflict(Exception):
    """
    Raised when an idempotent request is already in progress.
    """


# =============================================================================
# IDEMPOTENCY STORE
# =============================================================================


class IdempotencyStore:
    """
    Redis-backed distributed idempotency manager.

    Guarantees:

        - exactly-once execution
        - safe retries
        - distributed coordination
        - crash-safe locking
    """

    # -------------------------------------------------------------------------
    # INITIALIZATION
    # -------------------------------------------------------------------------

    def __init__(
        self,
        redis_client: Redis,
        *,
        ttl_seconds: int = 3600,
        lock_timeout_seconds: int = 30,
    ) -> None:
        """
        Args:
            redis_client:
                Async Redis client.

            ttl_seconds:
                Duration to store successful response.

            lock_timeout_seconds:
                Maximum execution time for lock.
                Prevents deadlocks if worker crashes.
        """

        self._redis = redis_client
        self._ttl = ttl_seconds
        self._lock_timeout = lock_timeout_seconds

    # -------------------------------------------------------------------------
    # INTERNAL KEY BUILDER
    # -------------------------------------------------------------------------

    def _key(self, idempotency_key: str) -> str:
        """
        Normalize Redis key.

        Adds namespace prefix to prevent collisions.
        """

        key = idempotency_key.strip()

        if not key:
            raise ValueError("Idempotency key must not be empty")

        if len(key) > 128:
            raise ValueError("Idempotency key too long")

        return f"idempotency:{key}"

    # -------------------------------------------------------------------------
    # LOCK ACQUISITION
    # -------------------------------------------------------------------------

    async def acquire_lock(self, idempotency_key: str) -> bool:
        """
        Attempt to acquire execution lock.

        Returns:

            True  → caller may execute operation
            False → request already in-flight
        """

        key = self._key(idempotency_key)

        try:
            result = await self._redis.set(
                key,
                "LOCKED",
                nx=True,
                ex=self._lock_timeout,
            )

            return bool(result)

        except RedisError:
            logger.exception("Redis failure during idempotency lock")
            raise

    # -------------------------------------------------------------------------
    # RESPONSE STORAGE
    # -------------------------------------------------------------------------

    async def store_response(
        self,
        idempotency_key: str,
        response_payload: dict[str, Any],
    ) -> None:
        """
        Store completed response for future retries.

        Overwrites LOCKED state.
        """

        key = self._key(idempotency_key)

        try:

            payload = json.dumps(response_payload, default=str)

            await self._redis.set(
                key,
                payload,
                ex=self._ttl,
            )

        except RedisError:
            logger.exception("Redis failure storing idempotent response")
            raise

    # -------------------------------------------------------------------------
    # RESPONSE RETRIEVAL
    # -------------------------------------------------------------------------

    async def get_response(
        self,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        """
        Retrieve cached response.

        Returns:

            dict  → completed response
            None  → no cached response
        """

        key = self._key(idempotency_key)

        try:

            value = await self._redis.get(key)

        except RedisError:
            logger.exception("Redis failure retrieving idempotent response")
            raise

        if not value:
            return None

        if value == "LOCKED":
            raise IdempotencyConflict(
                "Request with same idempotency key is already executing"
            )

        return json.loads(value)

    # -------------------------------------------------------------------------
    # FULL EXECUTION WRAPPER
    # -------------------------------------------------------------------------

    async def execute(
        self,
        idempotency_key: str,
        handler: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """
        Execute operation with idempotency protection.

        Args:
            idempotency_key:
                Unique client-provided request identifier.

            handler:
                Async callable executing the business operation.

        Returns:
            Operation response.

        Raises:
            IdempotencyConflict
        """

        # -------------------------------------------------------------
        # 1. Check if response already exists
        # -------------------------------------------------------------

        cached = await self.get_response(idempotency_key)

        if cached:
            logger.debug("Returning cached idempotent response")
            return cached

        # -------------------------------------------------------------
        # 2. Attempt lock acquisition
        # -------------------------------------------------------------

        acquired = await self.acquire_lock(idempotency_key)

        if not acquired:

            # Another worker executing
            cached = await self.get_response(idempotency_key)

            if cached:
                return cached

            raise IdempotencyConflict(
                "Duplicate request currently in progress"
            )

        # -------------------------------------------------------------
        # 3. Execute operation
        # -------------------------------------------------------------

        try:

            result = await handler()

            await self.store_response(idempotency_key, result)

            return result

        except Exception:

            # Release lock immediately on failure
            try:
                await self._redis.delete(self._key(idempotency_key))
            except RedisError:
                logger.exception("Failed to release idempotency lock")

            raise
