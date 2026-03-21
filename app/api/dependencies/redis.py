# File: app/api/dependencies/redis.pys
"""
===============================================================================
REDIS FASTAPI DEPENDENCIES
===============================================================================
"""

from fastapi import Request
from redis.asyncio import Redis


async def get_redis(request: Request) -> Redis:
    """
    Provide Redis client.

    Intended for:

        - rate limiter
        - cache
        - idempotency store
    """
    return request.app.state.db.redis.client


__all__ = [
    "get_redis",
]