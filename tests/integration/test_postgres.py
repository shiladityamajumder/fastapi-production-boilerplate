"""Tests for PostgreSQL settings, adapter lifecycle, and Alembic setup."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.common.exceptions import InfrastructureUnavailableError
from app.core.config import AppSettings, Environment
from app.db.postgres import PostgreSQLDatabase
from app.db.registry import DatabaseRegistry


_POSTGRES_URL = "postgresql+asyncpg://app_user:local_only@localhost:5432/app_db"


def test_postgres_configuration_requires_async_url() -> None:
    """Enabled PostgreSQL requires a supported asyncpg URL."""
    with pytest.raises(ValidationError, match="POSTGRES_URL"):
        AppSettings(ENABLE_POSTGRES=True)

    with pytest.raises(ValidationError, match="postgresql\+asyncpg"):
        AppSettings(
            ENABLE_POSTGRES=True,
            POSTGRES_URL="postgresql://app_user:local_only@localhost/app_db",
        )

    settings = AppSettings(
        ENVIRONMENT=Environment.TESTING,
        ENABLE_POSTGRES=True,
        POSTGRES_URL=SecretStr(_POSTGRES_URL),
    )
    assert settings.postgres_url_value == _POSTGRES_URL
    assert settings.enabled_database_names == ("postgres",)


def test_postgres_configuration_rejects_invalid_pool_limits() -> None:
    """Shared pool validation applies to the PostgreSQL connection pool."""
    with pytest.raises(ValidationError, match="must not exceed"):
        AppSettings(
            ENABLE_POSTGRES=True,
            POSTGRES_URL=_POSTGRES_URL,
            SQL_POOL_SIZE=200,
            SQL_MAX_OVERFLOW=1,
        )


def test_database_registry_registers_postgres_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registry wiring creates the configured PostgreSQL adapter."""
    settings = AppSettings(
        ENVIRONMENT=Environment.TESTING,
        ENABLE_POSTGRES=True,
        POSTGRES_URL=_POSTGRES_URL,
    )
    adapter = Mock(spec=PostgreSQLDatabase)

    def build_adapter(
        _cls: type[PostgreSQLDatabase],
        _settings: AppSettings,
    ) -> PostgreSQLDatabase:
        return adapter

    monkeypatch.setattr(
        PostgreSQLDatabase,
        "from_settings",
        classmethod(build_adapter),
    )

    registry = DatabaseRegistry.from_settings(settings)

    assert registry.postgres is adapter
    assert registry.adapter_names == ("postgres",)


def test_postgres_registry_is_empty_when_disabled() -> None:
    """Disabled PostgreSQL creates no adapter or connection pool."""
    registry = DatabaseRegistry.from_settings(
        AppSettings(ENABLE_POSTGRES=False),
    )

    assert registry.postgres is None
    assert registry.adapter_names == ()


def test_postgres_adapter_configures_pool_and_driver_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adapter passes validated pool and asyncpg options to SQLAlchemy."""
    engine = Mock(spec=AsyncEngine)
    create_engine = Mock(return_value=engine)
    monkeypatch.setattr("app.db.postgres.create_async_engine", create_engine)
    settings = AppSettings(
        ENVIRONMENT=Environment.TESTING,
        ENABLE_POSTGRES=True,
        POSTGRES_URL=_POSTGRES_URL,
        SQL_POOL_SIZE=4,
        SQL_MAX_OVERFLOW=2,
        POSTGRES_CONNECT_TIMEOUT_SECONDS=7,
        POSTGRES_COMMAND_TIMEOUT_SECONDS=21,
        POSTGRES_APPLICATION_NAME="api-tests",
    )

    database = PostgreSQLDatabase.from_settings(settings)

    create_engine.assert_called_once_with(
        _POSTGRES_URL,
        pool_size=4,
        max_overflow=2,
        pool_timeout=settings.SQL_POOL_TIMEOUT_SECONDS,
        pool_recycle=settings.SQL_POOL_RECYCLE_SECONDS,
        pool_pre_ping=settings.SQL_POOL_PRE_PING,
        pool_use_lifo=settings.SQL_POOL_USE_LIFO,
        pool_reset_on_return="rollback",
        connect_args={
            "timeout": 7,
            "command_timeout": 21,
            "server_settings": {"application_name": "api-tests"},
        },
        echo=settings.SQL_ECHO,
        hide_parameters=True,
    )
    assert database.engine is engine
    assert database.session_factory.kw["bind"] is engine


async def test_postgres_session_rolls_back_and_closes() -> None:
    """Session cleanup rolls back unfinished work and always closes."""
    session = Mock(spec=AsyncSession)
    session.in_transaction.return_value = True
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    database = PostgreSQLDatabase.__new__(PostgreSQLDatabase)
    database._session_factory = Mock(return_value=session)

    async with database.session() as yielded_session:
        assert yielded_session is session

    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()


async def test_postgres_connectivity_failure_is_reported_by_registry() -> None:
    """A failed PostgreSQL ping makes startup validation fail safely."""
    adapter = Mock(spec=PostgreSQLDatabase)
    adapter.ping = AsyncMock(side_effect=ConnectionError("database offline"))
    registry = DatabaseRegistry(postgres=adapter)

    with pytest.raises(InfrastructureUnavailableError) as error:
        await registry.ping_all(timeout_seconds=1)

    assert error.value.details == {"dependencies": ["postgres"]}


def test_alembic_uses_shared_metadata_and_model_discovery() -> None:
    """Alembic points at the shared metadata and existing model package."""
    repository_root = Path(__file__).resolve().parents[2]
    alembic_config = Config(repository_root / "alembic.ini")
    script_directory = ScriptDirectory.from_config(alembic_config)
    environment_file = Path(script_directory.dir) / "env.py"
    environment_source = environment_file.read_text(encoding="utf-8")

    assert environment_file.is_file()
    assert "target_metadata = Base.metadata" in environment_source
    assert "app.modules.example import models" in environment_source
    assert Path(script_directory.dir, "versions").is_dir()
