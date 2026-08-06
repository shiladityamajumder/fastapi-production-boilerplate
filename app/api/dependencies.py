"""
File: app/api/dependencies.py

FastAPI dependency providers for application settings and infrastructure.

Current active database integration:

- MySQL

Reference integrations retained as commented code:

- Microsoft SQL Server
- PostgreSQL
- MongoDB
- Redis application client

Every SQLAlchemy session and Unit of Work is request-scoped. The MySQL engine
and session factory remain process-scoped and are owned by
``DatabaseRegistry``.

To enable another integration, uncomment its complete block in this file and
the corresponding blocks in:

- app/core/config.py
- app/db/registry.py
- the relevant adapter file inside app/db
- dependency and package configuration
- environment configuration
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import (
    Depends,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import (
    InfrastructureUnavailableError,
)
from app.core.config import AppSettings
from app.db.mysql import MySQLDatabase
from app.db.registry import DatabaseRegistry
from app.db.uow import SQLAlchemyUnitOfWork


# =============================================================================
# OPTIONAL DATABASE AND CACHE IMPORTS
# =============================================================================
#
# MySQL is currently the only active database integration.
#
# To enable another integration:
#
# 1. Uncomment its import below.
# 2. Uncomment its adapter provider.
# 3. Uncomment its session provider when relational.
# 4. Uncomment its Unit of Work provider when relational.
# 5. Uncomment its dependency aliases.
# 6. Add its public names to ``__all__``.
# 7. Uncomment the matching settings in ``app/core/config.py``.
# 8. Uncomment its registry blocks in ``app/db/registry.py``.
# 9. Install the required driver or client package.
#
# Multiple integrations may be enabled by uncommenting their full blocks
# together.
# =============================================================================


# -----------------------------------------------------------------------------
# MICROSOFT SQL SERVER SUPPORT
#
# Required packages:
#     aioodbc
#     pyodbc
#
# Related files:
#     app/db/mssql.py
#     app/core/config.py
#     app/db/registry.py
# -----------------------------------------------------------------------------
# from app.db.mssql import MSSQLDatabase


# -----------------------------------------------------------------------------
# POSTGRESQL SUPPORT
#
# Required package:
#     asyncpg
#
# Related files:
#     app/db/postgres.py
#     app/core/config.py
#     app/db/registry.py
# -----------------------------------------------------------------------------
# from app.db.postgres import PostgreSQLDatabase


# -----------------------------------------------------------------------------
# MONGODB SUPPORT
#
# Required package:
#     pymongo
#
# Related files:
#     app/db/mongo.py
#     app/core/config.py
#     app/db/registry.py
# -----------------------------------------------------------------------------
# from app.db.mongo import MongoDatabase


# -----------------------------------------------------------------------------
# APPLICATION REDIS SUPPORT
#
# Required package:
#     redis
#
# Related files:
#     app/db/redis_client.py
#     app/core/config.py
#     app/db/registry.py
#
# Application Redis is independent of Celery's broker configuration.
# -----------------------------------------------------------------------------
# from app.db.redis_client import RedisClient


# =============================================================================
# CORE APPLICATION DEPENDENCIES
# =============================================================================

def get_app_settings(
    request: Request,
) -> AppSettings:
    """
    Return settings owned by the FastAPI application.

    Args:
        request: Current FastAPI request.

    Returns:
        Immutable process-level application settings.

    Raises:
        InfrastructureUnavailableError: If settings were not attached during
            application creation.
    """

    settings = getattr(
        request.app.state,
        "settings",
        None,
    )

    if not isinstance(
        settings,
        AppSettings,
    ):
        raise InfrastructureUnavailableError(
            "Application settings are unavailable."
        )

    return settings


def get_database_registry(
    request: Request,
) -> DatabaseRegistry:
    """
    Return the startup-created process-local infrastructure registry.

    Args:
        request: Current FastAPI request.

    Returns:
        Infrastructure registry created by the application lifespan.

    Raises:
        InfrastructureUnavailableError: If startup has not initialized the
            registry.
    """

    registry = getattr(
        request.app.state,
        "db",
        None,
    )

    if not isinstance(
        registry,
        DatabaseRegistry,
    ):
        raise InfrastructureUnavailableError(
            "Application infrastructure has not completed startup."
        )

    return registry


# =============================================================================
# MYSQL DEPENDENCIES - ACTIVE
# =============================================================================

def get_mysql_database(
    registry: Annotated[
        DatabaseRegistry,
        Depends(get_database_registry),
    ],
) -> MySQLDatabase:
    """
    Return the configured MySQL adapter.

    Args:
        registry: Process-local infrastructure registry.

    Returns:
        Configured MySQL adapter.

    Raises:
        InfrastructureUnavailableError: If MySQL is disabled or unavailable.
    """

    if registry.mysql is None:
        raise InfrastructureUnavailableError(
            "MySQL is not configured for this service."
        )

    return registry.mysql


async def get_mysql_session(
    database: Annotated[
        MySQLDatabase,
        Depends(get_mysql_database),
    ],
) -> AsyncIterator[AsyncSession]:
    """
    Yield one request-scoped MySQL session.

    The adapter rolls back any transaction left open by the caller and closes
    the session during dependency cleanup.

    Args:
        database: Configured MySQL adapter.

    Yields:
        Isolated asynchronous SQLAlchemy session.
    """

    async with database.session() as session:
        yield session


async def get_mysql_uow(
    database: Annotated[
        MySQLDatabase,
        Depends(get_mysql_database),
    ],
) -> AsyncIterator[SQLAlchemyUnitOfWork]:
    """
    Yield one request-scoped MySQL Unit of Work.

    The Unit of Work creates its session only when entered through
    ``async with``. Dependency cleanup closes any session or transaction left
    active by an interrupted request.

    Args:
        database: Configured MySQL adapter.

    Yields:
        Request-scoped SQLAlchemy Unit of Work.
    """

    unit_of_work = SQLAlchemyUnitOfWork(
        session_factory=database.session_factory,
        database_name="mysql",
    )

    try:
        yield unit_of_work
    finally:
        await unit_of_work.close()


# =============================================================================
# MICROSOFT SQL SERVER DEPENDENCIES - COMMENTED REFERENCE
# =============================================================================
#
# To enable Microsoft SQL Server:
#
# 1. Uncomment the ``MSSQLDatabase`` import.
# 2. Uncomment the provider functions below.
# 3. Uncomment the MSSQL aliases near the bottom of this file.
# 4. Add the MSSQL names to ``__all__``.
# 5. Uncomment MSSQL configuration and registry blocks.
#
# def get_mssql_database(
#     registry: Annotated[
#         DatabaseRegistry,
#         Depends(get_database_registry),
#     ],
# ) -> MSSQLDatabase:
#     """
#     Return the configured Microsoft SQL Server adapter.
#
#     Raises:
#         InfrastructureUnavailableError: If SQL Server is unavailable.
#     """
#
#     if registry.mssql is None:
#         raise InfrastructureUnavailableError(
#             "Microsoft SQL Server is not configured for this service."
#         )
#
#     return registry.mssql
#
#
# async def get_mssql_session(
#     database: Annotated[
#         MSSQLDatabase,
#         Depends(get_mssql_database),
#     ],
# ) -> AsyncIterator[AsyncSession]:
#     """Yield one request-scoped Microsoft SQL Server session."""
#
#     async with database.session() as session:
#         yield session
#
#
# async def get_mssql_uow(
#     database: Annotated[
#         MSSQLDatabase,
#         Depends(get_mssql_database),
#     ],
# ) -> AsyncIterator[SQLAlchemyUnitOfWork]:
#     """Yield one request-scoped Microsoft SQL Server Unit of Work."""
#
#     unit_of_work = SQLAlchemyUnitOfWork(
#         session_factory=database.session_factory,
#         database_name="mssql",
#     )
#
#     try:
#         yield unit_of_work
#     finally:
#         await unit_of_work.close()


# =============================================================================
# POSTGRESQL DEPENDENCIES - COMMENTED REFERENCE
# =============================================================================
#
# To enable PostgreSQL:
#
# 1. Uncomment the ``PostgreSQLDatabase`` import.
# 2. Uncomment the provider functions below.
# 3. Uncomment the PostgreSQL aliases near the bottom of this file.
# 4. Add the PostgreSQL names to ``__all__``.
# 5. Uncomment PostgreSQL configuration and registry blocks.
#
# def get_postgres_database(
#     registry: Annotated[
#         DatabaseRegistry,
#         Depends(get_database_registry),
#     ],
# ) -> PostgreSQLDatabase:
#     """
#     Return the configured PostgreSQL adapter.
#
#     Raises:
#         InfrastructureUnavailableError: If PostgreSQL is unavailable.
#     """
#
#     if registry.postgres is None:
#         raise InfrastructureUnavailableError(
#             "PostgreSQL is not configured for this service."
#         )
#
#     return registry.postgres
#
#
# async def get_postgres_session(
#     database: Annotated[
#         PostgreSQLDatabase,
#         Depends(get_postgres_database),
#     ],
# ) -> AsyncIterator[AsyncSession]:
#     """Yield one request-scoped PostgreSQL session."""
#
#     async with database.session() as session:
#         yield session
#
#
# async def get_postgres_uow(
#     database: Annotated[
#         PostgreSQLDatabase,
#         Depends(get_postgres_database),
#     ],
# ) -> AsyncIterator[SQLAlchemyUnitOfWork]:
#     """Yield one request-scoped PostgreSQL Unit of Work."""
#
#     unit_of_work = SQLAlchemyUnitOfWork(
#         session_factory=database.session_factory,
#         database_name="postgres",
#     )
#
#     try:
#         yield unit_of_work
#     finally:
#         await unit_of_work.close()


# =============================================================================
# MONGODB DEPENDENCY - COMMENTED REFERENCE
# =============================================================================
#
# To enable MongoDB:
#
# 1. Uncomment the ``MongoDatabase`` import.
# 2. Uncomment the provider below.
# 3. Uncomment ``MongoDatabaseDep``.
# 4. Add MongoDB names to ``__all__``.
# 5. Uncomment MongoDB configuration and registry blocks.
#
# def get_mongo_database(
#     registry: Annotated[
#         DatabaseRegistry,
#         Depends(get_database_registry),
#     ],
# ) -> MongoDatabase:
#     """
#     Return the configured MongoDB adapter.
#
#     Raises:
#         InfrastructureUnavailableError: If MongoDB is unavailable.
#     """
#
#     if registry.mongo is None:
#         raise InfrastructureUnavailableError(
#             "MongoDB is not configured for this service."
#         )
#
#     return registry.mongo


# =============================================================================
# APPLICATION REDIS DEPENDENCY - COMMENTED REFERENCE
# =============================================================================
#
# To enable the application Redis client:
#
# 1. Uncomment the ``RedisClient`` import.
# 2. Uncomment the provider below.
# 3. Uncomment ``RedisClientDep``.
# 4. Add Redis names to ``__all__``.
# 5. Uncomment Redis configuration and registry blocks.
#
# This dependency is unrelated to Celery's broker connection.
#
# def get_redis_client(
#     registry: Annotated[
#         DatabaseRegistry,
#         Depends(get_database_registry),
#     ],
# ) -> RedisClient:
#     """
#     Return the configured application Redis adapter.
#
#     Raises:
#         InfrastructureUnavailableError: If Redis is unavailable.
#     """
#
#     if registry.redis is None:
#         raise InfrastructureUnavailableError(
#             "Redis is not configured for this service."
#         )
#
#     return registry.redis


# =============================================================================
# ACTIVE DEPENDENCY ALIASES
# =============================================================================

SettingsDep = Annotated[
    AppSettings,
    Depends(get_app_settings),
]

DatabaseRegistryDep = Annotated[
    DatabaseRegistry,
    Depends(get_database_registry),
]

MySQLDatabaseDep = Annotated[
    MySQLDatabase,
    Depends(get_mysql_database),
]

MySQLSessionDep = Annotated[
    AsyncSession,
    Depends(get_mysql_session),
]

MySQLUOWDep = Annotated[
    SQLAlchemyUnitOfWork,
    Depends(get_mysql_uow),
]


# =============================================================================
# OPTIONAL DEPENDENCY ALIASES - COMMENTED REFERENCE
# =============================================================================


# -----------------------------------------------------------------------------
# MICROSOFT SQL SERVER
# -----------------------------------------------------------------------------
#
# MSSQLDatabaseDep = Annotated[
#     MSSQLDatabase,
#     Depends(get_mssql_database),
# ]
#
# MSSQLSessionDep = Annotated[
#     AsyncSession,
#     Depends(get_mssql_session),
# ]
#
# MSSQLUOWDep = Annotated[
#     SQLAlchemyUnitOfWork,
#     Depends(get_mssql_uow),
# ]


# -----------------------------------------------------------------------------
# POSTGRESQL
# -----------------------------------------------------------------------------
#
# PostgreSQLDatabaseDep = Annotated[
#     PostgreSQLDatabase,
#     Depends(get_postgres_database),
# ]
#
# PostgreSQLSessionDep = Annotated[
#     AsyncSession,
#     Depends(get_postgres_session),
# ]
#
# PostgreSQLUOWDep = Annotated[
#     SQLAlchemyUnitOfWork,
#     Depends(get_postgres_uow),
# ]


# -----------------------------------------------------------------------------
# MONGODB
# -----------------------------------------------------------------------------
#
# MongoDatabaseDep = Annotated[
#     MongoDatabase,
#     Depends(get_mongo_database),
# ]


# -----------------------------------------------------------------------------
# APPLICATION REDIS
# -----------------------------------------------------------------------------
#
# RedisClientDep = Annotated[
#     RedisClient,
#     Depends(get_redis_client),
# ]


__all__ = [
    "DatabaseRegistryDep",
    "MySQLDatabaseDep",
    "MySQLSessionDep",
    "MySQLUOWDep",
    "SettingsDep",
    "get_app_settings",
    "get_database_registry",
    "get_mysql_database",
    "get_mysql_session",
    "get_mysql_uow",

    # -------------------------------------------------------------------------
    # MICROSOFT SQL SERVER
    #
    # Uncomment when MSSQL dependencies are activated.
    # -------------------------------------------------------------------------
    # "MSSQLDatabaseDep",
    # "MSSQLSessionDep",
    # "MSSQLUOWDep",
    # "get_mssql_database",
    # "get_mssql_session",
    # "get_mssql_uow",

    # -------------------------------------------------------------------------
    # POSTGRESQL
    #
    # Uncomment when PostgreSQL dependencies are activated.
    # -------------------------------------------------------------------------
    # "PostgreSQLDatabaseDep",
    # "PostgreSQLSessionDep",
    # "PostgreSQLUOWDep",
    # "get_postgres_database",
    # "get_postgres_session",
    # "get_postgres_uow",

    # -------------------------------------------------------------------------
    # MONGODB
    #
    # Uncomment when MongoDB dependencies are activated.
    # -------------------------------------------------------------------------
    # "MongoDatabaseDep",
    # "get_mongo_database",

    # -------------------------------------------------------------------------
    # APPLICATION REDIS
    #
    # Uncomment when Redis dependencies are activated.
    # -------------------------------------------------------------------------
    # "RedisClientDep",
    # "get_redis_client",
]