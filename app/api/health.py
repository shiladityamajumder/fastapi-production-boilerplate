"""File: app/api/health.py.

Liveness, readiness, and bounded infrastructure diagnostics.

Health endpoints follow these rules:

- liveness checks only whether the ASGI process can respond,
- readiness confirms startup completion and enabled dependency availability,
- deep health exposes sanitized timings only when explicitly enabled,
- disabled dependencies are omitted completely,
- connection URLs, driver errors, credentials, and stack traces are never
  exposed.

Health routes remain outside the versioned API prefix.
"""

from __future__ import annotations

from typing import Literal

from fastapi import (
    APIRouter,
    Request,
    status,
)
from fastapi.responses import JSONResponse  # noqa: TC002
from pydantic import Field

from app.common.response import (
    APIModel,
    APIResponse,
    APIResponseModel,
    STANDARD_ERROR_RESPONSES,
)
from app.core.config import AppSettings
from app.db.registry import (
    DatabaseRegistry,
    HealthStatus,
)

router = APIRouter(
    prefix="/health",
    tags=["Health"],
    responses=STANDARD_ERROR_RESPONSES,
)


class HealthCheckPayload(APIModel):
    """Safe status for one enabled infrastructure dependency."""

    healthy: bool
    duration_ms: float | None = Field(default=None, ge=0)


class LivenessPayload(APIModel):
    """Liveness state independent of infrastructure availability."""

    status: Literal["alive"]


class ReadinessPayload(APIModel):
    """Traffic readiness and sanitized enabled dependency checks."""

    ready: bool
    checks: dict[str, HealthCheckPayload]


class DeepHealthPayload(APIModel):
    """Detailed, sanitized dependency health data."""

    healthy: bool
    checks: dict[str, HealthCheckPayload]


def _get_health_dependencies(
    request: Request,
) -> tuple[AppSettings, DatabaseRegistry]:
    """Return health-check settings and infrastructure registry.

    Args:
        request: Current FastAPI request.

    Returns:
        Tuple containing settings and infrastructure registry.

    Raises:
        TypeError: If the application state contains an unexpected object type.
    """
    settings = getattr(
        request.app.state,
        "settings",
        None,
    )

    registry = getattr(
        request.app.state,
        "db",
        None,
    )

    if not isinstance(
        settings,
        AppSettings,
    ):
        raise TypeError(
            "Application settings are unavailable or invalid"
        )

    if not isinstance(
        registry,
        DatabaseRegistry,
    ):
        raise TypeError(
            "Infrastructure registry is unavailable or invalid"
        )

    return settings, registry


def _serialize_checks(
    checks: dict[str, HealthStatus],
    *,
    include_duration: bool,
) -> dict[str, dict[str, bool | float]]:
    """Convert internal dependency results into a safe API payload.

    Only enabled adapters are present because ``DatabaseRegistry.check_all``
    does not return disabled integrations.

    Args:
        checks: Health results indexed by adapter name.
        include_duration: Include health-check timing when ``True``.

    Returns:
        Sanitized health-check payload.
    """
    serialized: dict[
        str,
        dict[str, bool | float],
    ] = {}

    for name, result in checks.items():
        payload: dict[str, bool | float] = {
            "healthy": result.healthy,
        }

        if include_duration:
            payload["durationMs"] = result.duration_ms

        serialized[name] = payload

    return serialized


@router.get(
    "/live",
    summary="Process liveness",
    description="Reports process liveness without querying external dependencies.",
    response_model=APIResponseModel[LivenessPayload],
)
async def liveness() -> JSONResponse:
    """Return success when the ASGI process can serve requests.

    Liveness intentionally performs no database, cache, or external-service
    calls. Dependency failures must not cause an orchestrator to repeatedly
    restart an otherwise functioning process.

    Returns:
        Canonical liveness response.
    """
    return APIResponse.success(
        message="Service is alive.",
        data={
            "status": "alive",
        },
    )


@router.get(
    "/ready",
    summary="Traffic readiness",
    description=(
        "Checks PostgreSQL and other enabled dependencies before traffic is routed."
    ),
    response_model=APIResponseModel[ReadinessPayload],
)
async def readiness(
    request: Request,
) -> JSONResponse:
    """Return whether the service is ready to receive application traffic.

    The readiness endpoint checks only infrastructure adapters enabled for this
    service. Each check is bounded by the configured timeout.

    Args:
        request: Current FastAPI request.

    Returns:
        HTTP 200 when ready or HTTP 503 when unavailable.
    """
    if not getattr(
        request.app.state,
        "ready",
        False,
    ):
        return APIResponse.error(
            error_code="SERVICE_NOT_READY",
            message="The service is not ready to receive traffic.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        settings, registry = _get_health_dependencies(
            request
        )
    except TypeError:
        return APIResponse.error(
            error_code="SERVICE_NOT_READY",
            message="The service is not ready to receive traffic.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    checks = await registry.check_all(
        timeout_seconds=(
            settings.HEALTHCHECK_TIMEOUT_SECONDS
        ),
    )

    ready = all(
        result.healthy
        for result in checks.values()
    )

    serialized_checks = _serialize_checks(
        checks,
        include_duration=False,
    )

    if not ready:
        return APIResponse.error(
            error_code="SERVICE_NOT_READY",
            message=(
                "One or more required dependencies are unavailable."
            ),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={
                "checks": serialized_checks,
            },
        )

    return APIResponse.success(
        message="Service is ready to receive traffic.",
        data={
            "ready": True,
            "checks": serialized_checks,
        },
    )


@router.get(
    "/deep",
    summary="Detailed infrastructure diagnostics",
    description=(
        "Returns sanitized status for enabled dependencies without connection details."
    ),
    response_model=APIResponseModel[DeepHealthPayload],
)
async def deep_health(
    request: Request,
) -> JSONResponse:
    """Return sanitized dependency status and execution timing.

    The endpoint is hidden logically when deep diagnostics are disabled. It
    never returns raw exceptions, hosts, connection URLs, credentials, or
    database driver details.

    Args:
        request: Current FastAPI request.

    Returns:
        Sanitized dependency health response.
    """
    settings = getattr(
        request.app.state,
        "settings",
        None,
    )

    if (
        not isinstance(
            settings,
            AppSettings,
        )
        or not settings.DEEP_HEALTH_ENABLED
    ):
        return APIResponse.error(
            error_code="ROUTE_NOT_FOUND",
            message="The requested route was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    registry = getattr(
        request.app.state,
        "db",
        None,
    )

    if not isinstance(
        registry,
        DatabaseRegistry,
    ):
        return APIResponse.error(
            error_code="SERVICE_NOT_READY",
            message="The service is not ready to receive traffic.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    checks = await registry.check_all(
        timeout_seconds=(
            settings.HEALTHCHECK_TIMEOUT_SECONDS
        ),
    )

    healthy = all(
        result.healthy
        for result in checks.values()
    )

    payload = {
        "healthy": healthy,
        "checks": _serialize_checks(
            checks,
            include_duration=True,
        ),
    }

    if not healthy:
        return APIResponse.error(
            error_code="DEPENDENCY_HEALTH_CHECK_FAILED",
            message=(
                "One or more dependencies failed the health check."
            ),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=payload,
        )

    return APIResponse.success(
        message="All enabled dependencies are healthy.",
        data=payload,
    )


__all__ = [
    "router",
]
