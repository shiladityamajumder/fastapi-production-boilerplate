# File: app/api/health.py
"""
===============================================================================
SERVICE HEALTH & READINESS PROBES
===============================================================================

Provides operational health endpoints used by:

    • Kubernetes
    • Load balancers
    • Infrastructure monitoring systems
    • SRE debugging tools

-------------------------------------------------------------------------------
HEALTH CHECK TYPES
-------------------------------------------------------------------------------

This module implements three categories of health checks:

1 LIVENESS PROBE

    Endpoint:
        GET /health/live

    Purpose:
        Indicates that the application process is alive.

    Does NOT verify:
        • database connectivity
        • external dependencies

    Typical usage:
        Kubernetes livenessProbe

    If this endpoint fails:
        → container should be restarted.

-------------------------------------------------------------------------------

2 READINESS PROBE

    Endpoint:
        GET /health/ready

    Purpose:
        Indicates that the service is ready to receive traffic.

    Verifies:
        • critical infrastructure connectivity

    Example checks:
        • primary SQL database
        • Redis cache

    Typical usage:
        Kubernetes readinessProbe

    If this endpoint fails:
        → service removed from load balancer.

-------------------------------------------------------------------------------

3 DEEP HEALTH CHECK

    Endpoint:
        GET /health/deep

    Purpose:
        Full infrastructure diagnostics for operators.

    Verifies:
        • all configured infrastructure components
        • individual subsystem status

    Intended for:
        • observability dashboards
        • debugging incidents
        • SRE inspection

-------------------------------------------------------------------------------
ARCHITECTURAL RULES
-------------------------------------------------------------------------------

Health endpoints:

    • must NOT execute heavy queries
    • must NOT mutate state
    • must remain extremely fast
    • must tolerate partial infrastructure failure

All checks use lightweight "ping" operations.

-------------------------------------------------------------------------------
FAILURE POLICY
-------------------------------------------------------------------------------

Liveness:
    Always succeeds unless process is unhealthy.

Readiness:
    Fails if critical dependencies fail.

Deep Health:
    Returns full subsystem breakdown.
"""

from __future__ import annotations

import time
from typing import Dict, Any

from fastapi import APIRouter, Request

from app.common.response import APIResponse
from app.core.logging import get_logger

logger = get_logger("health")

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)

# =============================================================================
# INTERNAL HEALTH CHECK UTILITIES
# =============================================================================


async def _check_postgres(db_registry) -> Dict[str, Any]:
    """Check PostgreSQL connectivity."""
    try:
        if not db_registry.postgres:
            return {"enabled": False}

        await db_registry.postgres.ping()
        return {"enabled": True, "status": "healthy"}

    except Exception as exc:
        logger.exception("Postgres health check failed")
        return {"enabled": True, "status": "unhealthy", "error": str(exc)}


async def _check_mysql(db_registry) -> Dict[str, Any]:
    """Check MySQL connectivity."""
    try:
        if not db_registry.mysql:
            return {"enabled": False}

        await db_registry.mysql.ping()
        return {"enabled": True, "status": "healthy"}

    except Exception as exc:
        logger.exception("MySQL health check failed")
        return {"enabled": True, "status": "unhealthy", "error": str(exc)}


async def _check_mssql(db_registry) -> Dict[str, Any]:
    """Check MSSQL connectivity."""
    try:
        if not db_registry.mssql:
            return {"enabled": False}

        await db_registry.mssql.ping()
        return {"enabled": True, "status": "healthy"}

    except Exception as exc:
        logger.exception("MSSQL health check failed")
        return {"enabled": True, "status": "unhealthy", "error": str(exc)}


async def _check_mongo(db_registry) -> Dict[str, Any]:
    """Check MongoDB connectivity."""
    try:
        if not db_registry.mongo:
            return {"enabled": False}

        await db_registry.mongo.ping()
        return {"enabled": True, "status": "healthy"}

    except Exception as exc:
        logger.exception("Mongo health check failed")
        return {"enabled": True, "status": "unhealthy", "error": str(exc)}


async def _check_redis(db_registry) -> Dict[str, Any]:
    """Check Redis connectivity."""
    try:
        if not db_registry.redis:
            return {"enabled": False}

        await db_registry.redis.ping()
        return {"enabled": True, "status": "healthy"}

    except Exception as exc:
        logger.exception("Redis health check failed")
        return {"enabled": True, "status": "unhealthy", "error": str(exc)}


# =============================================================================
# LIVENESS PROBE
# =============================================================================


@router.get("/live")
async def liveness():
    """
    Liveness probe.

    Indicates that the application process is running.

    This endpoint should remain extremely lightweight
    and should never depend on infrastructure.
    """

    return APIResponse.success(
        message="Service is alive",
        data={"status": "alive"},
    )


# =============================================================================
# READINESS PROBE
# =============================================================================


@router.get("/ready")
async def readiness(request: Request):
    """
    Readiness probe.

    Verifies that the service is ready to handle requests.

    This typically checks only **critical dependencies**
    required for serving traffic.
    """

    start = time.perf_counter()

    db_registry = request.app.state.db

    postgres = await _check_postgres(db_registry)
    redis = await _check_redis(db_registry)

    ready = True

    if postgres.get("status") == "unhealthy":
        ready = False

    if redis.get("status") == "unhealthy":
        ready = False

    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    return APIResponse.success(
        message="Service readiness check",
        data={
            "ready": ready,
            "checks": {
                "postgres": postgres,
                "redis": redis,
            },
            "duration_ms": duration_ms,
        },
    )


# =============================================================================
# DEEP HEALTH CHECK
# =============================================================================


@router.get("/deep")
async def deep_health(request: Request):
    """
    Full infrastructure health diagnostics.

    This endpoint performs checks on all configured
    infrastructure components and returns detailed
    subsystem status.

    Intended for operators and monitoring systems.
    """

    start = time.perf_counter()

    db_registry = request.app.state.db

    postgres = await _check_postgres(db_registry)
    mysql = await _check_mysql(db_registry)
    mssql = await _check_mssql(db_registry)
    mongo = await _check_mongo(db_registry)
    redis = await _check_redis(db_registry)

    checks = {
        "postgres": postgres,
        "mysql": mysql,
        "mssql": mssql,
        "mongo": mongo,
        "redis": redis,
    }

    healthy = all(
        svc.get("status", "healthy") != "unhealthy"
        for svc in checks.values()
        if svc.get("enabled")
    )

    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    return APIResponse.success(
        message="Deep health diagnostics",
        data={
            "healthy": healthy,
            "checks": checks,
            "duration_ms": duration_ms,
        },
    )


__all__ = ["router"]
