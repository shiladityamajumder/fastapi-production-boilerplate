# """
# File: app/db/postgres.py

# Asynchronous PostgreSQL engine and session lifecycle adapter.

# The adapter uses SQLAlchemy with the ``postgresql+asyncpg`` dialect. One
# adapter must be created per FastAPI or Celery worker process.

# The engine and its connection pool are process-local. Requests and Celery tasks
# must create isolated sessions or Unit of Work instances from
# ``session_factory``.
# """

# from __future__ import annotations

# from collections.abc import AsyncGenerator
# from contextlib import asynccontextmanager
# from typing import Any

# from sqlalchemy import text
# from sqlalchemy.ext.asyncio import (
#     AsyncEngine,
#     AsyncSession,
#     async_sessionmaker,
#     create_async_engine,
# )

# from app.core.config import AppSettings
# from app.core.logging import get_logger


# logger = get_logger(__name__)


# class PostgreSQLDatabase:
#     """
#     Own one process-local PostgreSQL engine and session factory.
#     """

#     def __init__(
#         self,
#         *,
#         url: str,
#         settings: AppSettings,
#     ) -> None:
#         """
#         Initialize the PostgreSQL engine and session factory.

#         Args:
#             url: Validated ``postgresql+asyncpg`` SQLAlchemy URL.
#             settings: Validated application settings.

#         Raises:
#             ValueError: If the PostgreSQL URL is blank.
#         """

#         normalized_url = url.strip()

#         if not normalized_url:
#             raise ValueError(
#                 "PostgreSQL connection URL must not be blank"
#             )

#         server_settings: dict[str, str] = {}

#         if settings.POSTGRES_APPLICATION_NAME:
#             server_settings["application_name"] = (
#                 settings.POSTGRES_APPLICATION_NAME
#             )

#         connect_args: dict[str, Any] = {
#             "timeout": settings.POSTGRES_CONNECT_TIMEOUT_SECONDS,
#             "command_timeout": (
#                 settings.POSTGRES_COMMAND_TIMEOUT_SECONDS
#             ),
#         }

#         if server_settings:
#             connect_args["server_settings"] = server_settings

#         self._engine: AsyncEngine = create_async_engine(
#             normalized_url,
#             pool_size=settings.SQL_POOL_SIZE,
#             max_overflow=settings.SQL_MAX_OVERFLOW,
#             pool_timeout=settings.SQL_POOL_TIMEOUT_SECONDS,
#             pool_recycle=settings.SQL_POOL_RECYCLE_SECONDS,
#             pool_pre_ping=settings.SQL_POOL_PRE_PING,
#             pool_use_lifo=settings.SQL_POOL_USE_LIFO,
#             pool_reset_on_return="rollback",
#             connect_args=connect_args,
#             echo=settings.SQL_ECHO,
#             hide_parameters=True,
#         )

#         self._session_factory: async_sessionmaker[AsyncSession] = (
#             async_sessionmaker(
#                 bind=self._engine,
#                 class_=AsyncSession,
#                 autoflush=False,
#                 expire_on_commit=False,
#             )
#         )

#         logger.info(
#             "PostgreSQL database adapter initialized",
#             extra={
#                 "pool_size": settings.SQL_POOL_SIZE,
#                 "max_overflow": settings.SQL_MAX_OVERFLOW,
#                 "application_name": (
#                     settings.POSTGRES_APPLICATION_NAME or None
#                 ),
#             },
#         )

#     @classmethod
#     def from_settings(
#         cls,
#         settings: AppSettings,
#     ) -> PostgreSQLDatabase:
#         """
#         Build the adapter from validated application settings.

#         Args:
#             settings: Validated application settings.

#         Returns:
#             Initialized PostgreSQL adapter.

#         Raises:
#             RuntimeError: If PostgreSQL is disabled or not configured.
#         """

#         if not settings.ENABLE_POSTGRES:
#             raise RuntimeError(
#                 "PostgreSQL is not enabled"
#             )

#         url = settings.postgres_url_value

#         if not url:
#             raise RuntimeError(
#                 "PostgreSQL connection URL is not configured"
#             )

#         return cls(
#             url=url,
#             settings=settings,
#         )

#     @property
#     def engine(self) -> AsyncEngine:
#         """
#         Return the process-local SQLAlchemy asynchronous engine.
#         """

#         return self._engine

#     @property
#     def session_factory(
#         self,
#     ) -> async_sessionmaker[AsyncSession]:
#         """
#         Return the process-local asynchronous session factory.
#         """

#         return self._session_factory

#     @asynccontextmanager
#     async def session(
#         self,
#     ) -> AsyncGenerator[AsyncSession]:
#         """
#         Yield an isolated PostgreSQL session and guarantee cleanup.

#         This helper does not commit automatically. Transactional write
#         operations should normally use ``SQLAlchemyUnitOfWork``.

#         Yields:
#             Isolated asynchronous SQLAlchemy session.
#         """

#         session = self._session_factory()

#         try:
#             yield session
#         finally:
#             try:
#                 if session.in_transaction():
#                     await session.rollback()
#             finally:
#                 await session.close()

#     async def ping(self) -> None:
#         """
#         Execute a lightweight PostgreSQL connectivity query.

#         Raises:
#             Exception: Propagates connectivity, authentication, timeout, and
#                 query errors.
#         """

#         async with self._engine.connect() as connection:
#             await connection.execute(
#                 text("SELECT 1")
#             )

#         logger.debug(
#             "PostgreSQL connectivity verified"
#         )

#     async def close(self) -> None:
#         """
#         Dispose the engine and all pooled PostgreSQL connections.
#         """

#         await self._engine.dispose()

#         logger.info(
#             "PostgreSQL database adapter closed"
#         )


# __all__ = [
#     "PostgreSQLDatabase",
# ]
