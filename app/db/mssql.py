# """
# File: app/db/mssql.py

# Asynchronous Microsoft SQL Server engine and session lifecycle adapter.

# The adapter uses SQLAlchemy with the ``mssql+aioodbc`` dialect. One adapter is
# created per API or Celery worker process and shared within that process.

# Each request or task must create its own session or Unit of Work from the
# process-local ``session_factory``.
# """

# from __future__ import annotations

# from collections.abc import AsyncGenerator
# from contextlib import asynccontextmanager
# from typing import Any

# from sqlalchemy import text
# from sqlalchemy.engine import make_url
# from sqlalchemy.ext.asyncio import (
#     AsyncEngine,
#     AsyncSession,
#     async_sessionmaker,
#     create_async_engine,
# )

# from app.core.config import AppSettings
# from app.core.logging import get_logger


# logger = get_logger(__name__)


# class MSSQLDatabase:
#     """
#     Own one process-local SQL Server engine and session factory.
#     """

#     def __init__(
#         self,
#         *,
#         url: str,
#         settings: AppSettings,
#     ) -> None:
#         """
#         Initialize the SQL Server engine and session factory.

#         Args:
#             url: Validated ``mssql+aioodbc`` SQLAlchemy URL.
#             settings: Validated application settings.

#         Raises:
#             ValueError: If the URL is blank.
#         """

#         normalized_url = url.strip()

#         if not normalized_url:
#             raise ValueError(
#                 "Microsoft SQL Server URL must not be blank"
#             )

#         engine_url = make_url(normalized_url)

#         # TrustServerCertificate is applied as a SQL Server connection-string
#         # option without manually modifying or logging the credential-bearing
#         # URL.
#         if settings.MSSQL_TRUST_SERVER_CERTIFICATE:
#             engine_url = engine_url.update_query_dict(
#                 {
#                     "TrustServerCertificate": "yes",
#                 }
#             )

#         connect_args: dict[str, Any] = {
#             "timeout": settings.MSSQL_CONNECT_TIMEOUT_SECONDS,
#         }

#         self._engine: AsyncEngine = create_async_engine(
#             engine_url,
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
#             "Microsoft SQL Server adapter initialized",
#             extra={
#                 "pool_size": settings.SQL_POOL_SIZE,
#                 "max_overflow": settings.SQL_MAX_OVERFLOW,
#                 "trust_server_certificate": (
#                     settings.MSSQL_TRUST_SERVER_CERTIFICATE
#                 ),
#             },
#         )

#     @classmethod
#     def from_settings(
#         cls,
#         settings: AppSettings,
#     ) -> MSSQLDatabase:
#         """
#         Build the adapter from validated application settings.

#         Args:
#             settings: Validated application settings.

#         Returns:
#             Initialized SQL Server adapter.

#         Raises:
#             RuntimeError: If SQL Server is disabled or not configured.
#         """

#         if not settings.ENABLE_MSSQL:
#             raise RuntimeError(
#                 "Microsoft SQL Server is not enabled"
#             )

#         url = settings.mssql_url_value

#         if not url:
#             raise RuntimeError(
#                 "Microsoft SQL Server connection URL is not configured"
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
#         Yield an isolated SQL Server session and guarantee cleanup.

#         This helper does not commit automatically. Transactional writes should
#         normally use ``SQLAlchemyUnitOfWork``.

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
#         Execute a lightweight SQL Server connectivity query.

#         Raises:
#             Exception: Propagates connectivity, authentication, timeout, and
#                 query errors.
#         """

#         async with self._engine.connect() as connection:
#             await connection.execute(
#                 text("SELECT 1")
#             )

#         logger.debug(
#             "Microsoft SQL Server connectivity verified"
#         )

#     async def close(self) -> None:
#         """
#         Dispose the engine and all pooled SQL Server connections.
#         """

#         await self._engine.dispose()

#         logger.info(
#             "Microsoft SQL Server adapter closed"
#         )


# __all__ = [
#     "MSSQLDatabase",
# ]