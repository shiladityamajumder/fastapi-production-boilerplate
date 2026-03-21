# File: app/core/rate_limit.py
"""
===============================================================================
PRODUCTION-GRADE REDIS RATE LIMITER (ATOMIC + HORIZONTALLY SAFE)
===============================================================================

Distributed Redis-backed rate limiter designed for high concurrency systems.

Key properties:

    • atomic counter updates via Lua
    • horizontally safe across multiple application instances
    • deterministic behavior using Redis server time
    • O(1) Redis operations per request
    • fail-open strategy for availability

-------------------------------------------------------------------------------
ARCHITECTURAL ROLE
-------------------------------------------------------------------------------

Core infrastructure component responsible for:

    - enforcing request rate limits
    - calculating remaining quota
    - computing reset timestamps

This module DOES NOT:

    - manage Redis lifecycle
    - construct HTTP responses
    - register middleware

-------------------------------------------------------------------------------
FAILURE POLICY
-------------------------------------------------------------------------------

Fail-open on Redis errors.

If Redis becomes unavailable:

    - requests are allowed
    - error is logged
    - system availability is preserved
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Tuple

import redis.asyncio as redis
from fastapi import Request
from redis.exceptions import RedisError

from app.core.logging import get_logger


logger = get_logger("rate_limit")


# =============================================================================
# RATE LIMIT SCOPE
# =============================================================================


class RateLimitScope(str, Enum):
    """
    Defines identity dimension used for rate limiting.

    Current implementation:
        - IP

    Future extensions may include:

        - USER
        - API_KEY
        - TENANT
    """

    IP = "ip"


# =============================================================================
# RATE LIMIT CONFIGURATION
# =============================================================================


@dataclass(frozen=True)
class RateLimitConfig:
    """
    Immutable rate limit configuration.
    """

    limit: int
    window_seconds: int

    def validate(self) -> None:

        if self.limit < 0:
            raise ValueError("Rate limit must be >= 0")

        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")


# =============================================================================
# LUA SCRIPT
# =============================================================================

_LUA_SCRIPT = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end
return current
"""


# =============================================================================
# RATE LIMITER
# =============================================================================


class RateLimiter:
    """
    Redis-backed fixed-window rate limiter.

    Guarantees:

        - atomic counter increments
        - deterministic window boundaries
        - horizontal safety across instances
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        default_config: RateLimitConfig,
        *,
        enabled: bool = True,
        scope: RateLimitScope = RateLimitScope.IP,
        key_prefix: str = "rl",
    ) -> None:

        default_config.validate()

        self._client = redis_client
        self._default_config = default_config
        self._enabled = enabled
        self._scope = scope
        self._key_prefix = key_prefix

        # Pre-register Lua script
        self._script = self._client.register_script(_LUA_SCRIPT)

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def default_config(self) -> RateLimitConfig:
        return self._default_config

    # -------------------------------------------------------------------------
    # Identity Builder
    # -------------------------------------------------------------------------

    def build_key(self, request: Request) -> str:
        """
        Build rate-limit identity key.

        Current implementation uses client IP.
        """

        client_ip = request.client.host if request.client else "unknown"

        identity_hash = hashlib.sha256(
            client_ip.encode("utf-8")
        ).hexdigest()[:16]

        return f"{self._scope.value}:{identity_hash}"

    # -------------------------------------------------------------------------
    # Rate Limit Check
    # -------------------------------------------------------------------------

    async def check(
        self,
        *,
        key: str,
        config: Optional[RateLimitConfig] = None,
    ) -> Tuple[bool, int, int]:
        """
        Check and update rate limit counter.

        Returns:

            allowed
            remaining
            reset_timestamp
        """

        if not self._enabled:
            return True, 0, 0

        if not key:
            raise ValueError("Rate limit key cannot be empty")

        cfg = config or self._default_config
        cfg.validate()

        if cfg.limit == 0:
            return False, 0, 0

        # -------------------------------------------------------------
        # Retrieve Redis server time
        # -------------------------------------------------------------

        try:

            seconds, _ = await self._client.time()
            now = int(seconds)

        except RedisError as exc:

            logger.error("Redis time retrieval failed", exc_info=exc)

            return True, 0, 0

        # -------------------------------------------------------------
        # Compute window
        # -------------------------------------------------------------

        window_start = (now // cfg.window_seconds) * cfg.window_seconds

        redis_key = f"{self._key_prefix}:{window_start}:{key}"

        # -------------------------------------------------------------
        # Atomic increment via Lua
        # -------------------------------------------------------------

        try:

            current = await self._script(
                keys=[redis_key],
                args=[cfg.window_seconds],
            )

            current = int(current)

        except RedisError as exc:

            logger.error("Redis rate limit error", exc_info=exc)

            return True, 0, 0

        allowed = current <= cfg.limit

        remaining = max(cfg.limit - current, 0)

        reset_at = window_start + cfg.window_seconds

        return allowed, remaining, reset_at


# =============================================================================
# ENDPOINT DECORATORS
# =============================================================================


def no_rate_limit(func: Callable) -> Callable:
    """
    Disable rate limiting for endpoint.
    """

    setattr(func, "__no_rate_limit__", True)

    return func


def rate_limit(limit: int, window_seconds: int = 60) -> Callable:
    """
    Apply custom rate limit rule to endpoint.
    """

    cfg = RateLimitConfig(limit=limit, window_seconds=window_seconds)
    cfg.validate()

    def decorator(func: Callable) -> Callable:

        setattr(func, "__rate_limit__", cfg)

        return func

    return decorator
