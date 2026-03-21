# File: app/core/config.py
"""
===============================================================================
APPLICATION CONFIGURATION (PRODUCTION-HARDENED, MULTI-DB SAFE)
===============================================================================

Centralized configuration model for the entire application.

Design goals:

    - 12-Factor compliant
    - deterministic startup validation
    - strict infrastructure configuration
    - multi-database safe
    - production hardened

-------------------------------------------------------------------------------
FAILURE PHILOSOPHY
-------------------------------------------------------------------------------

If infrastructure is enabled but misconfigured:

    → application must fail during startup.

Silent degradation is forbidden.

-------------------------------------------------------------------------------
MULTI-DB SUPPORT
-------------------------------------------------------------------------------

Multiple databases may be enabled simultaneously:

    PostgreSQL
    MySQL
    MSSQL
    MongoDB
    Redis

Each ENABLE_* flag activates strict validation for its configuration.

-------------------------------------------------------------------------------
PRODUCTION HARDENING
-------------------------------------------------------------------------------

In production:

    - DEBUG must be False
    - DB_ECHO must be False
"""

from __future__ import annotations

import logging
from enum import Enum
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# =============================================================================
# ENVIRONMENT
# =============================================================================


class Environment(str, Enum):

    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


# =============================================================================
# SETTINGS MODEL
# =============================================================================


class AppSettings(BaseSettings):
    """
    Centralized application configuration.

    Characteristics:

        - immutable after initialization
        - environment driven
        - strictly validated
        - safe for concurrent access
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    # -------------------------------------------------------------------------
    # CORE
    # -------------------------------------------------------------------------

    ENVIRONMENT: Environment = Environment.DEVELOPMENT

    PROJECT_NAME: str = "SSPL_INV"

    API_V1_STR: str = "/api/v1"

    DEBUG: bool = False

    TIMEZONE: str = "UTC"

    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

    # -------------------------------------------------------------------------
    # LOGGING
    # -------------------------------------------------------------------------

    LOG_LEVEL: str = "INFO"

    LOG_DIR: Path = Path("logs")

    LOG_FILE: str = "app.log"

    LOG_MAX_BYTES: int = 10_000_000

    LOG_BACKUP_COUNT: int = 5

    # -------------------------------------------------------------------------
    # DATABASE POOL
    # -------------------------------------------------------------------------

    DB_POOL_SIZE: int = 20

    DB_MAX_OVERFLOW: int = 10

    DB_POOL_TIMEOUT: int = 30

    DB_POOL_RECYCLE: int = 1800

    DB_POOL_PRE_PING: bool = True

    DB_ECHO: bool = False

    # -------------------------------------------------------------------------
    # POSTGRES
    # -------------------------------------------------------------------------

    ENABLE_POSTGRES: bool = False

    POSTGRES_ASYNC_URL: str | None = None

    POSTGRES_SYNC_URL: str | None = None

    # -------------------------------------------------------------------------
    # MYSQL
    # -------------------------------------------------------------------------

    ENABLE_MYSQL: bool = False

    MYSQL_URL: str | None = None

    # -------------------------------------------------------------------------
    # MSSQL
    # -------------------------------------------------------------------------

    ENABLE_MSSQL: bool = False

    MSSQL_URL: str | None = None

    # -------------------------------------------------------------------------
    # REDIS
    # -------------------------------------------------------------------------

    ENABLE_REDIS: bool = False

    REDIS_URL: str | None = None

    REDIS_MAX_CONNECTIONS: int = 100

    REDIS_SOCKET_TIMEOUT: int = 5

    REDIS_SOCKET_CONNECT_TIMEOUT: int = 5

    RATE_LIMIT_ENABLED: bool = False

    RATE_LIMIT_PER_MINUTE: int = 60

    # -------------------------------------------------------------------------
    # MONGODB
    # -------------------------------------------------------------------------

    ENABLE_MONGO: bool = False

    MONGO_URI: str | None = None

    MONGO_DB_NAME: str | None = None

    MONGO_MIN_POOL_SIZE: int = 1

    MONGO_MAX_POOL_SIZE: int = 10

    MONGO_SERVER_SELECTION_TIMEOUT_MS: int = 5000

    # -------------------------------------------------------------------------
    # SERVER
    # -------------------------------------------------------------------------

    PORT: int = 8888

    # =========================================================================
    # VALIDATION
    # =========================================================================

    @model_validator(mode="after")
    def validate_settings(self) -> "AppSettings":

        # -------------------------
        # Logging
        # -------------------------

        if self.LOG_LEVEL.upper() not in logging._nameToLevel:
            raise ValueError(f"Invalid LOG_LEVEL: {self.LOG_LEVEL}")

        try:
            ZoneInfo(self.TIMEZONE)
        except Exception:
            raise ValueError(f"Invalid TIMEZONE: {self.TIMEZONE}")

        # -------------------------
        # Server
        # -------------------------

        if not (0 < self.PORT <= 65535):
            raise ValueError("PORT must be between 1 and 65535")

        # -------------------------
        # DB pool
        # -------------------------

        if self.DB_POOL_SIZE <= 0:
            raise ValueError("DB_POOL_SIZE must be > 0")

        if self.DB_MAX_OVERFLOW < 0:
            raise ValueError("DB_MAX_OVERFLOW must be >= 0")

        if self.DB_POOL_TIMEOUT <= 0:
            raise ValueError("DB_POOL_TIMEOUT must be > 0")

        if self.DB_POOL_RECYCLE < 0:
            raise ValueError("DB_POOL_RECYCLE must be >= 0")

        # -------------------------
        # PostgreSQL
        # -------------------------

        if self.ENABLE_POSTGRES:
            if not self.POSTGRES_ASYNC_URL:
                raise ValueError("POSTGRES_ASYNC_URL required")

            if not self.POSTGRES_SYNC_URL:
                raise ValueError("POSTGRES_SYNC_URL required")

        # -------------------------
        # MySQL
        # -------------------------

        if self.ENABLE_MYSQL and not self.MYSQL_URL:
            raise ValueError("MYSQL_URL required")

        # -------------------------
        # MSSQL
        # -------------------------

        if self.ENABLE_MSSQL and not self.MSSQL_URL:
            raise ValueError("MSSQL_URL required")

        # -------------------------
        # Redis
        # -------------------------

        if self.ENABLE_REDIS:

            if not self.REDIS_URL:
                raise ValueError("REDIS_URL required")

            if self.REDIS_MAX_CONNECTIONS <= 0:
                raise ValueError("REDIS_MAX_CONNECTIONS must be > 0")

            if self.REDIS_SOCKET_TIMEOUT <= 0:
                raise ValueError("REDIS_SOCKET_TIMEOUT must be > 0")

            if self.REDIS_SOCKET_CONNECT_TIMEOUT <= 0:
                raise ValueError(
                    "REDIS_SOCKET_CONNECT_TIMEOUT must be > 0"
                )

        if self.RATE_LIMIT_ENABLED and not self.ENABLE_REDIS:
            raise ValueError(
                "RATE_LIMIT_ENABLED requires ENABLE_REDIS=True"
            )

        if self.RATE_LIMIT_PER_MINUTE <= 0:
            raise ValueError("RATE_LIMIT_PER_MINUTE must be > 0")

        # -------------------------
        # Mongo
        # -------------------------

        if self.ENABLE_MONGO:

            if not self.MONGO_URI:
                raise ValueError("MONGO_URI required")

            if not self.MONGO_DB_NAME:
                raise ValueError("MONGO_DB_NAME required")

            if self.MONGO_MIN_POOL_SIZE > self.MONGO_MAX_POOL_SIZE:
                raise ValueError(
                    "MONGO_MIN_POOL_SIZE cannot exceed MONGO_MAX_POOL_SIZE"
                )

            if self.MONGO_SERVER_SELECTION_TIMEOUT_MS <= 0:
                raise ValueError(
                    "MONGO_SERVER_SELECTION_TIMEOUT_MS must be > 0"
                )

        # -------------------------
        # Production safety
        # -------------------------

        if self.ENVIRONMENT == Environment.PRODUCTION:

            if self.DEBUG:
                raise ValueError("DEBUG must be False in production")

            if self.DB_ECHO:
                raise ValueError("DB_ECHO must be False in production")

        return self


# =============================================================================
# SETTINGS LOADER
# =============================================================================


@lru_cache
def get_settings() -> AppSettings:
    """
    Load application configuration.

    Characteristics:

        - deterministic
        - thread-safe
        - cached
    """

    settings = AppSettings()

    log_dir = (
        settings.LOG_DIR
        if settings.LOG_DIR.is_absolute()
        else settings.BASE_DIR / settings.LOG_DIR
    )

    log_dir.mkdir(parents=True, exist_ok=True)

    return settings
