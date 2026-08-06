"""File: app/core/lifespan.py.

FastAPI startup and shutdown orchestration.

This module owns process-level infrastructure lifecycle for the API process.
Celery workers must use their own worker lifecycle and must not reuse database
engines or connection pools created by FastAPI.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator  # noqa: TC003
from contextlib import asynccontextmanager

from fastapi import FastAPI  # noqa: TC002

from app.core.config import AppSettings  # noqa: TC001
from app.core.logging import get_logger
from app.db.registry import DatabaseRegistry

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncGenerator[None]:
    """Initialize and close process-wide API infrastructure.

    Startup responsibilities:

    - create the database registry from validated settings,
    - initialize only enabled infrastructure adapters,
    - verify required infrastructure connectivity,
    - expose the registry through ``app.state``,
    - mark the application ready only after startup succeeds.

    Shutdown responsibilities:

    - immediately mark the process as unavailable,
    - close all initialized infrastructure adapters,
    - release database and cache connection pools.

    Args:
        app: FastAPI application instance.

    Yields:
        Control to FastAPI after infrastructure startup completes.

    Raises:
        Exception: Propagates startup, runtime, or shutdown infrastructure
            failures.
    """
    settings: AppSettings = app.state.settings

    # The registry creates only integrations explicitly enabled in settings.
    registry = DatabaseRegistry.from_settings(
        settings,
    )

    app.state.ready = False
    app.state.db = registry

    logger.info(
        "Application startup initiated",
        extra={
            "environment": settings.ENVIRONMENT.value,
            "configured_databases": list(
                settings.enabled_database_names,
            ),
        },
    )

    try:
        # A startup connectivity check prevents the API from reporting ready
        # when a required infrastructure dependency is unavailable.
        await registry.ping_all(
            timeout_seconds=(
                settings.HEALTHCHECK_TIMEOUT_SECONDS
            ),
        )

        app.state.ready = True

        logger.info(
            "Application startup completed",
            extra={
                "enabled_adapters": list(
                    registry.adapters,
                ),
            },
        )

        yield

    except Exception:
        logger.exception(
            "Application startup or runtime infrastructure failure"
        )
        raise

    finally:
        # Readiness is removed before connections begin closing so traffic can
        # be drained by the gateway or orchestrator.
        app.state.ready = False

        logger.info(
            "Application shutdown initiated"
        )

        try:
            await registry.close()
        except Exception:
            logger.exception(
                "Application infrastructure shutdown failed"
            )
            raise
        else:
            logger.info(
                "Application shutdown completed"
            )


__all__ = [
    "lifespan",
]
