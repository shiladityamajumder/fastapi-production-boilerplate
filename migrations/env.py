"""Alembic environment using the application's async PostgreSQL settings."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection  # noqa: TC002
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.db.base import Base
from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.example import models as example_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    """Return the validated PostgreSQL URL from environment settings."""
    settings = get_settings()
    if not settings.ENABLE_POSTGRES:
        raise RuntimeError("ENABLE_POSTGRES must be true to run migrations")

    url = settings.postgres_url_value
    if not url:
        raise RuntimeError("POSTGRES_URL must be set to run migrations")

    return url


def run_migrations_offline() -> None:
    """Configure migrations without opening a database connection."""
    url = database_url()
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_sync_migrations(connection: Connection) -> None:
    """Run Alembic migrations against a synchronous SQLAlchemy connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations through its sync bridge."""
    config.set_main_option(
        "sqlalchemy.url",
        database_url().replace("%", "%%"),
    )
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(run_sync_migrations)
    finally:
        await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
