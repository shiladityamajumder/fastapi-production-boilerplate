# """
# File: app/db/redis_client.py

# Asynchronous Redis client lifecycle adapter.

# Redis is optional and may be used for:

# - Celery broker or result storage,
# - application caching,
# - idempotency records,
# - distributed locks,
# - short-lived coordination data.

# Redis is not used for API rate limiting in this service foundation.

# One client is created per FastAPI or Celery worker process. The client owns its
# connection pool and must be closed during process shutdown.
# """

# from __future__ import annotations

# from redis.asyncio import Redis

# from app.core.config import AppSettings
# from app.core.logging import get_logger


# logger = get_logger(__name__)


# class RedisClient:
#     """
#     Own one process-local asynchronous Redis client and connection pool.
#     """

#     def __init__(
#         self,
#         *,
#         url: str,
#         settings: AppSettings,
#     ) -> None:
#         """
#         Initialize the Redis client.

#         Args:
#             url: Validated Redis connection URL.
#             settings: Validated application settings.

#         Raises:
#             ValueError: If the Redis URL is blank.
#         """

#         normalized_url = url.strip()

#         if not normalized_url:
#             raise ValueError(
#                 "Redis connection URL must not be blank"
#             )

#         self._client: Redis = Redis.from_url(
#             normalized_url,
#             encoding="utf-8",
#             decode_responses=True,
#             max_connections=settings.REDIS_MAX_CONNECTIONS,
#             socket_timeout=(
#                 settings.REDIS_SOCKET_TIMEOUT_SECONDS
#             ),
#             socket_connect_timeout=(
#                 settings.REDIS_CONNECT_TIMEOUT_SECONDS
#             ),
#             retry_on_timeout=settings.REDIS_RETRY_ON_TIMEOUT,
#             health_check_interval=(
#                 settings.REDIS_HEALTH_CHECK_INTERVAL_SECONDS
#             ),
#             client_name=settings.PROJECT_NAME,
#         )

#         self._key_prefix = settings.REDIS_KEY_PREFIX
#         self._default_ttl_seconds = (
#             settings.REDIS_DEFAULT_TTL_SECONDS
#         )

#         logger.info(
#             "Redis client adapter initialized",
#             extra={
#                 "max_connections": settings.REDIS_MAX_CONNECTIONS,
#                 "key_prefix": self._key_prefix,
#             },
#         )

#     @classmethod
#     def from_settings(
#         cls,
#         settings: AppSettings,
#     ) -> RedisClient:
#         """
#         Build the adapter from validated application settings.

#         Args:
#             settings: Validated application settings.

#         Returns:
#             Initialized Redis adapter.

#         Raises:
#             RuntimeError: If Redis is disabled or not configured.
#         """

#         if not settings.ENABLE_REDIS:
#             raise RuntimeError(
#                 "Redis is not enabled"
#             )

#         url = settings.redis_url_value

#         if not url:
#             raise RuntimeError(
#                 "Redis connection URL is not configured"
#             )

#         return cls(
#             url=url,
#             settings=settings,
#         )

#     @property
#     def client(self) -> Redis:
#         """
#         Return the process-local asynchronous Redis client.
#         """

#         return self._client

#     @property
#     def key_prefix(self) -> str:
#         """
#         Return the service-level Redis key prefix.
#         """

#         return self._key_prefix

#     @property
#     def default_ttl_seconds(self) -> int:
#         """
#         Return the default application Redis TTL.
#         """

#         return self._default_ttl_seconds

#     def build_key(
#         self,
#         *parts: object,
#     ) -> str:
#         """
#         Build a namespaced Redis key.

#         Empty key segments and segments containing the namespace delimiter are
#         rejected to prevent ambiguous keys.

#         Args:
#             *parts: Key segments converted to strings.

#         Returns:
#             Namespaced Redis key.

#         Raises:
#             ValueError: If no segments are provided or a segment is invalid.
#         """

#         if not parts:
#             raise ValueError(
#                 "At least one Redis key segment is required"
#             )

#         normalized_parts: list[str] = []

#         for part in parts:
#             normalized = str(part).strip()

#             if not normalized:
#                 raise ValueError(
#                     "Redis key segments must not be blank"
#                 )

#             if ":" in normalized:
#                 raise ValueError(
#                     "Redis key segments must not contain ':'"
#                 )

#             normalized_parts.append(normalized)

#         return ":".join(
#             [
#                 self._key_prefix,
#                 *normalized_parts,
#             ]
#         )

#     async def ping(self) -> None:
#         """
#         Verify Redis connectivity and command execution.

#         Raises:
#             Exception: Propagates connection, authentication, and timeout
#                 failures.
#         """

#         await self._client.ping()

#         logger.debug(
#             "Redis connectivity verified"
#         )

#     async def close(self) -> None:
#         """
#         Close the Redis client and its owned connection pool.
#         """

#         await self._client.aclose()

#         logger.info(
#             "Redis client adapter closed"
#         )


# __all__ = [
#     "RedisClient",
# ]
