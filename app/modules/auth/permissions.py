"""Central role-to-permission policy for administrative operations."""

from __future__ import annotations

from app.modules.auth.models import UserRole


class Permissions:
    """Stable permission identifiers used by services and route guards."""

    USERS_READ = "users:read"
    USERS_CREATE = "users:create"
    USERS_UPDATE = "users:update"
    USERS_STATUS = "users:status"
    USERS_REVOKE_SESSIONS = "users:sessions:revoke"
    USERS_ASSIGN_ROLE = "users:roles:assign"
    AUDIT_READ = "audit:read"
    USER_ACTIVITY_READ = "users:activity:read"


ROLE_PERMISSIONS: dict[UserRole, frozenset[str]] = {
    UserRole.USER: frozenset(),
    UserRole.ADMIN: frozenset(
        {
            Permissions.USERS_READ,
            Permissions.USERS_CREATE,
            Permissions.USERS_UPDATE,
            Permissions.USERS_STATUS,
            Permissions.USERS_REVOKE_SESSIONS,
            Permissions.USERS_ASSIGN_ROLE,
            Permissions.AUDIT_READ,
            Permissions.USER_ACTIVITY_READ,
        }
    ),
    UserRole.SUPER_ADMIN: frozenset(
        {
            Permissions.USERS_READ,
            Permissions.USERS_CREATE,
            Permissions.USERS_UPDATE,
            Permissions.USERS_STATUS,
            Permissions.USERS_REVOKE_SESSIONS,
            Permissions.USERS_ASSIGN_ROLE,
            Permissions.AUDIT_READ,
            Permissions.USER_ACTIVITY_READ,
        }
    ),
}


def role_has_permission(role: UserRole, permission: str) -> bool:
    """Check one permission against the centralized least-privilege mapping."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


__all__ = ["Permissions", "ROLE_PERMISSIONS", "role_has_permission"]
