"""Secure command for bootstrapping the first SUPER_ADMIN account."""

from __future__ import annotations

import asyncio
import getpass
import os
import re
import sys
from uuid import uuid4

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.exc import IntegrityError

from app.common.exceptions import ConflictError
from app.core.config import get_settings
from app.db.postgres import PostgreSQLDatabase
from app.db.uow import SQLAlchemyUnitOfWork
from app.modules.auth.models import AuditLog, User, UserRole
from app.modules.auth.repository import AuthRepository
from app.modules.auth.service import hash_password

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
_MIN_PASSWORD_LENGTH = 12
_MAX_PASSWORD_LENGTH = 128


async def create_first_admin(
    email: str,
    username: str,
    password: str,
) -> None:
    """Bootstrap the first super admin without promoting existing accounts."""
    if len(password) < _MIN_PASSWORD_LENGTH or len(password) > _MAX_PASSWORD_LENGTH:
        raise ValueError("Admin password must contain 12 to 128 characters.")
    settings = get_settings()
    database = PostgreSQLDatabase.from_settings(settings)
    uow = SQLAlchemyUnitOfWork(
        session_factory=database.session_factory,
        database_name="postgres",
    )
    try:
        async with uow:
            repository = AuthRepository(uow.session)
            await repository.lock_first_admin_bootstrap()
            normalized_email = str(TypeAdapter(EmailStr).validate_python(email)).lower()
            normalized_username = username.strip().lower()
            if not _USERNAME_RE.fullmatch(normalized_username):
                raise ValueError(
                    "Username must contain 3-32 letters, numbers, dots, dashes, or underscores."
                )
            existing_email = await repository.user_by_email(normalized_email)
            existing_username = await repository.user_by_username(normalized_username)
            existing = existing_email or existing_username
            if existing is not None:
                if (
                    existing_email is not None
                    and existing_username is not None
                    and existing_email.id == existing_username.id
                    and existing.role == UserRole.SUPER_ADMIN
                    and existing.is_active
                ):
                    return
                raise ConflictError("An account with these identifiers already exists; it was not changed.")
            if await repository.super_admin_exists():
                raise ConflictError("A SUPER_ADMIN already exists.")
            user = User(
                id=uuid4(),
                email=normalized_email,
                username=normalized_username,
                password_hash=hash_password(password),
                role=UserRole.SUPER_ADMIN,
                is_active=True,
                is_verified=True,
                token_version=0,
            )
            repository.add_user(user)
            repository.add_audit(
                AuditLog(
                    action="admin.bootstrap",
                    target_type="user",
                    target_id=str(user.id),
                    outcome="success",
                    safe_metadata={"new_role": UserRole.SUPER_ADMIN.value},
                )
            )
            try:
                await uow.commit()
            except IntegrityError:
                await uow.rollback()
                raise ConflictError("An account with these identifiers already exists.") from None
    finally:
        await database.close()


def main() -> None:
    """Read administrator credentials from environment or hidden prompts."""
    email = os.getenv("ADMIN_EMAIL") or input("Admin email: ").strip()
    username = os.getenv("ADMIN_USERNAME") or input("Admin username: ").strip()
    password = os.getenv("ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
    if len(password) < _MIN_PASSWORD_LENGTH or len(password) > _MAX_PASSWORD_LENGTH:
        print("Admin password must contain 12 to 128 characters.", file=sys.stderr)
        raise SystemExit(2)
    try:
        asyncio.run(create_first_admin(email, username, password))
    except (ConflictError, ValueError, ValidationError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
    print("SUPER_ADMIN created.")


if __name__ == "__main__":
    main()


__all__ = ["create_first_admin", "main"]
