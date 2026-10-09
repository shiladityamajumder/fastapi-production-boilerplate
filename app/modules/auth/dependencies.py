"""FastAPI dependencies for current-user and administrator authorization."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: TC002

from app.api.dependencies import PostgreSQLUOWDep, get_app_settings
from app.common.exceptions import AuthenticationError, AuthorizationError
from app.core.config import AppSettings  # noqa: TC001
from app.core.request_context import get_request_id
from app.modules.auth.aws import S3FileStorage
from app.modules.auth.models import User, UserRole
from app.modules.auth.permissions import role_has_permission
from app.modules.auth.service import AuthService

_BEARER = HTTPBearer(auto_error=False)


async def get_auth_service(
    request: Request,
    uow: PostgreSQLUOWDep,
    settings: Annotated[AppSettings, Depends(get_app_settings)],
) -> AuthService:
    """Build an auth use-case service over the request Unit of Work."""
    image_storage = None
    if settings.PROFILE_IMAGE_STORAGE_ENABLED:
        image_storage = await asyncio.to_thread(S3FileStorage, settings)
    return AuthService(
        uow,
        settings,
        profile_image_storage=image_storage,
        request_id=get_request_id(),
        ip_address=(request.client.host if request.client is not None else None),
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    service: AuthServiceDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_BEARER),
    ],
) -> User:
    """Validate an access JWT and reload its active account from PostgreSQL."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError()
    return await service.authenticate_access_token(credentials.credentials)


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_current_admin(
    user: CurrentUserDep,
) -> User:
    """Require the ADMIN role; role is always reloaded from the database."""
    if user.role not in {UserRole.ADMIN, UserRole.SUPER_ADMIN}:
        raise AuthorizationError()
    return user


CurrentAdminDep = Annotated[User, Depends(get_current_admin)]


def require_role(*allowed_roles: UserRole) -> Callable[..., User]:
    """Build a dependency that requires one of the supplied current roles."""
    permitted = frozenset(allowed_roles)

    async def dependency(user: CurrentUserDep) -> User:
        if user.role not in permitted:
            raise AuthorizationError()
        return user

    return dependency


def require_permission(permission: str) -> Callable[..., User]:
    """Build a dependency for a centralized role permission."""

    async def dependency(user: CurrentUserDep) -> User:
        if not role_has_permission(user.role, permission):
            raise AuthorizationError()
        return user

    return dependency


__all__ = [
    "AuthServiceDep",
    "CurrentAdminDep",
    "CurrentUserDep",
    "get_auth_service",
    "get_current_admin",
    "get_current_user",
    "require_permission",
    "require_role",
]
