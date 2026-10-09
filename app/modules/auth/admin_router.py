"""Administrative user and audit endpoints."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID  # noqa: TC003

from fastapi import APIRouter, Depends, Query, status

from app.common.pagination import PaginationParams
from app.common.response import (
    APIResponse,
    APIResponseModel,
    STANDARD_ERROR_RESPONSES,
)
from app.common.sorting import SortOrder
from app.modules.auth.dependencies import AuthServiceDep, require_permission
from app.modules.auth.models import User, UserRole  # noqa: TC001
from app.modules.auth.permissions import Permissions
from app.modules.auth.schemas import (
    AdminRoleUpdateRequest,
    AdminUserCreateRequest,
    AdminUserDetail,
    AdminUserPage,
    AdminUserUpdateRequest,
    AuditLogPage,
)

router = APIRouter(
    prefix="/admin",
    tags=["Administration"],
    responses=STANDARD_ERROR_RESPONSES,
)


@router.get(
    "/users",
    response_model=APIResponseModel[AdminUserPage],
    summary="List users",
    description=(
        "Search and filter user accounts. Results use bounded offset pagination "
        "and allow-listed sorting. Requires the users:read permission."
    ),
)
async def list_users(
    actor: Annotated[User, Depends(require_permission(Permissions.USERS_READ))],
    service: AuthServiceDep,
    pagination: Annotated[PaginationParams, Depends()],
    search: Annotated[str | None, Query(max_length=100)] = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
    sort_by: Literal["created_at", "email", "username", "role"] | None = None,
    sort_order: SortOrder = SortOrder.DESC,
) -> object:  # noqa: PLR0913
    """Search and paginate users for an authorized administrator."""
    result = await service.admin_list_users(
        actor.id,
        search=search,
        role=role,
        is_active=is_active,
        limit=pagination.limit,
        offset=pagination.offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return APIResponse.success(data=result, message="Users loaded.")


@router.get(
    "/users/{user_id}",
    response_model=APIResponseModel[AdminUserDetail],
    summary="Get user details",
)
async def get_user(
    user_id: UUID,
    actor: Annotated[User, Depends(require_permission(Permissions.USERS_READ))],
    service: AuthServiceDep,
) -> object:
    """Load one user record."""
    result = await service.admin_get_user(actor.id, user_id)
    return APIResponse.success(data=result, message="User loaded.")


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    response_model=APIResponseModel[AdminUserDetail],
    summary="Create a user account",
)
async def create_user(
    body: AdminUserCreateRequest,
    actor: Annotated[User, Depends(require_permission(Permissions.USERS_CREATE))],
    service: AuthServiceDep,
) -> object:
    """Create a user with a role allowed to the current administrator."""
    result = await service.admin_create_user(actor.id, body)
    return APIResponse.success(data=result, message="User created.")


@router.patch(
    "/users/{user_id}",
    response_model=APIResponseModel[AdminUserDetail],
    summary="Update user details",
)
async def update_user(
    user_id: UUID,
    body: AdminUserUpdateRequest,
    actor: Annotated[User, Depends(require_permission(Permissions.USERS_UPDATE))],
    service: AuthServiceDep,
) -> object:
    """Update an account's non-role details."""
    result = await service.admin_update_user(actor.id, user_id, body)
    return APIResponse.success(data=result, message="User updated.")


@router.put(
    "/users/{user_id}/role",
    response_model=APIResponseModel[AdminUserDetail],
    summary="Assign a user role",
)
async def update_user_role(
    user_id: UUID,
    body: AdminRoleUpdateRequest,
    actor: Annotated[User, Depends(require_permission(Permissions.USERS_ASSIGN_ROLE))],
    service: AuthServiceDep,
) -> object:
    """Assign a role subject to super administrator policy."""
    result = await service.admin_set_role(actor.id, user_id, body.role)
    return APIResponse.success(data=result, message="User role updated.")


@router.post(
    "/users/{user_id}/activate",
    response_model=APIResponseModel[AdminUserDetail],
    summary="Activate a user account",
)
async def activate_user(
    user_id: UUID,
    actor: Annotated[User, Depends(require_permission(Permissions.USERS_STATUS))],
    service: AuthServiceDep,
) -> object:
    """Activate an account."""
    result = await service.admin_set_active(actor.id, user_id, True)
    return APIResponse.success(data=result, message="User activated.")


@router.post(
    "/users/{user_id}/deactivate",
    response_model=APIResponseModel[AdminUserDetail],
    summary="Deactivate a user account",
)
async def deactivate_user(
    user_id: UUID,
    actor: Annotated[User, Depends(require_permission(Permissions.USERS_STATUS))],
    service: AuthServiceDep,
) -> object:
    """Deactivate an account and invalidate its sessions."""
    result = await service.admin_set_active(actor.id, user_id, False)
    return APIResponse.success(data=result, message="User deactivated.")


@router.post(
    "/users/{user_id}/sessions/revoke",
    response_model=APIResponseModel[dict[str, int]],
    summary="Revoke user sessions",
)
async def revoke_user_sessions(
    user_id: UUID,
    actor: Annotated[User, Depends(require_permission(Permissions.USERS_REVOKE_SESSIONS))],
    service: AuthServiceDep,
) -> object:
    """Revoke a user's active refresh sessions."""
    count = await service.admin_revoke_sessions(actor.id, user_id)
    return APIResponse.success(data={"revoked_sessions": count}, message="User sessions revoked.")


@router.get(
    "/users/{user_id}/activity",
    response_model=APIResponseModel[AuditLogPage],
    summary="View user activity",
)
async def user_activity(
    user_id: UUID,
    actor: Annotated[User, Depends(require_permission(Permissions.USER_ACTIVITY_READ))],
    service: AuthServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> object:
    """Return audit events involving the requested user."""
    result = await service.admin_audit_logs(
        actor.id, target_user_id=user_id, limit=limit, offset=offset, activity=True
    )
    return APIResponse.success(data=result, message="User activity loaded.")


@router.get(
    "/audit",
    response_model=APIResponseModel[AuditLogPage],
    summary="Search audit history",
)
async def audit_logs(
    actor: Annotated[User, Depends(require_permission(Permissions.AUDIT_READ))],
    service: AuthServiceDep,
    target_user_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> object:  # noqa: PLR0913
    """Search audit history using actor and target filters."""
    result = await service.admin_audit_logs(
        actor.id,
        target_user_id=target_user_id,
        actor_user_id=actor_user_id,
        limit=limit,
        offset=offset,
    )
    return APIResponse.success(data=result, message="Audit history loaded.")


__all__ = ["router"]
