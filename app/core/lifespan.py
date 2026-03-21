# File: app/core/lifespan.py
"""
===============================================================================
APPLICATION LIFESPAN CONTROLLER (INFRASTRUCTURE BOOTSTRAP LAYER)
===============================================================================

This module defines the authoritative lifecycle controller for the application.

It is responsible for:

    • Initializing infrastructure adapters
    • Validating connectivity (fail-fast strategy)
    • Attaching resources to FastAPI state
    • Ensuring deterministic shutdown of all infrastructure

-------------------------------------------------------------------------------
ARCHITECTURAL POSITION
-------------------------------------------------------------------------------

This module belongs to the Core layer.

It orchestrates infrastructure but does NOT implement it.

It may depend on:

    - Configuration system
    - Infrastructure adapters
    - Database registry

It MUST NOT contain:

    - Business logic
    - Route logic
    - Repository logic
    - Domain behavior

-------------------------------------------------------------------------------
INFRASTRUCTURE OWNERSHIP CONTRACT
-------------------------------------------------------------------------------

All infrastructure resources are attached to:

    app.state.db

Where:

    db → DatabaseRegistry

Example runtime access:

    request.app.state.db.postgres
    request.app.state.db.redis
    request.app.state.db.mongo

This ensures:

    - centralized resource ownership
    - predictable dependency access
    - easier testing
    - consistent lifecycle management

-------------------------------------------------------------------------------
FAILURE POLICY
-------------------------------------------------------------------------------

If any enabled infrastructure fails during startup:

    → Application startup MUST abort.

Partial infrastructure initialization is not allowed.

-------------------------------------------------------------------------------
SHUTDOWN GUARANTEE
-------------------------------------------------------------------------------

During shutdown:

    - Every adapter is closed via DatabaseRegistry
    - Failures are logged but do not interrupt shutdown
    - Resources are released deterministically

-------------------------------------------------------------------------------
EXECUTION FLOW
-------------------------------------------------------------------------------

Startup:

    settings → build adapters → DatabaseRegistry → ping_all()

Runtime:

    request.app.state.db

Shutdown:

    registry.close()

-------------------------------------------------------------------------------
COMPATIBILITY
-------------------------------------------------------------------------------

Designed to work with:

    app.infrastructure.*
    app.db.registry.DatabaseRegistry
    app.db.unit_of_work.UnitOfWork
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import get_logger

from app.db.registry import DatabaseRegistry

from app.infrastructure.postgres import PostgresDatabase
from app.infrastructure.mysql import MySQLDatabase
from app.infrastructure.mssql import MSSQLDatabase
from app.infrastructure.mongo import MongoDatabase
from app.infrastructure.redis_client import RedisClient


logger = get_logger("lifespan")


# =============================================================================
# FASTAPI LIFESPAN CONTROLLER
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifecycle controller.

    This function is passed to FastAPI during application initialization
    and manages startup and shutdown of infrastructure resources.

    Example:

        app = FastAPI(lifespan=lifespan)

    Lifecycle phases:

        1. STARTUP
        2. APPLICATION SERVING
        3. SHUTDOWN
    """

    settings = get_settings()

    logger.info("Application startup initiated")

    try:

        # ---------------------------------------------------------------------
        # INITIALIZE INFRASTRUCTURE ADAPTERS
        # ---------------------------------------------------------------------

        registry = DatabaseRegistry(
            postgres=PostgresDatabase.from_settings(settings)
            if settings.ENABLE_POSTGRES
            else None,

            mysql=MySQLDatabase.from_settings(settings)
            if settings.ENABLE_MYSQL
            else None,

            mssql=MSSQLDatabase.from_settings(settings)
            if settings.ENABLE_MSSQL
            else None,

            mongo=MongoDatabase.from_settings(settings)
            if settings.ENABLE_MONGO
            else None,

            redis=RedisClient.from_settings(settings)
            if settings.ENABLE_REDIS
            else None,
        )

        # ---------------------------------------------------------------------
        # CONNECTIVITY VALIDATION (FAIL-FAST)
        # ---------------------------------------------------------------------

        logger.info("Validating infrastructure connectivity")

        await registry.ping_all()

        logger.info("Infrastructure validation successful")

        # ---------------------------------------------------------------------
        # ATTACH REGISTRY TO APPLICATION STATE
        # ---------------------------------------------------------------------

        app.state.db = registry

        logger.info("Infrastructure registry attached to app.state.db")

        # ---------------------------------------------------------------------
        # APPLICATION SERVING PHASE
        # ---------------------------------------------------------------------

        yield

    except Exception:
        logger.exception("Application startup failed")
        raise

    finally:

        # ---------------------------------------------------------------------
        # SHUTDOWN PHASE
        # ---------------------------------------------------------------------

        logger.info("Application shutdown initiated")

        try:
            registry = getattr(app.state, "db", None)

            if registry is not None:
                await registry.close()

        except Exception:
            logger.exception("Infrastructure shutdown encountered errors")

        logger.info("Application shutdown complete")