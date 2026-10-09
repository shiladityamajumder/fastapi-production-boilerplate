"""File: app/core/config.py.

Typed, immutable, environment-driven application configuration.

Settings are loaded from environment variables and an optional local ``.env``
file. Validation is performed once per process through ``get_settings()``.

Current active relational database:

- PostgreSQL through asyncpg

Reference integrations retained as commented code:

- Microsoft SQL Server
- MongoDB
- Redis
- Celery background jobs

Unused email, notification, AI, and other external-service configuration is
intentionally excluded. Such settings should be introduced only when the
corresponding integration is implemented.

This module is limited to configuration parsing and validation. It must not:

- initialize logging,
- create directories,
- connect to databases,
- initialize cache clients,
- initialize background workers,
- or mutate external state.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import (
    ZoneInfo,
    ZoneInfoNotFoundError,
)

from pydantic import (
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)

# =============================================================================
# CONFIGURATION LIMITS
# =============================================================================

_MAX_SQL_CONNECTIONS_PER_PROCESS = 200


class Environment(StrEnum):
    """Supported application runtime environments."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class AppSettings(BaseSettings):
    """Validated process-level application settings.

    Settings are immutable after initialization. Infrastructure adapters should
    receive this object through dependency injection instead of reading
    environment variables directly.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    # =========================================================================
    # APPLICATION
    # =========================================================================

    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    PROJECT_NAME: str = "fastapi_service"
    APP_VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    DEBUG: bool = False
    TIMEZONE: str = "Asia/Kolkata"

    BASE_DIR: Path = Path(__file__).resolve().parents[2]

    # =========================================================================
    # SERVER
    # =========================================================================

    # ASGI server bind address. Binding to all interfaces is intentional for
    # containerized and externally proxied deployments. This does not control
    # HTTP Host-header validation.
    HOST: str = "0.0.0.0"  # noqa: S104

    PORT: int = Field(
        default=8000,
        ge=1,
        le=65_535,
    )

    CORS_ALLOWED_ORIGINS: list[str] = Field(
        default_factory=list,
    )

    CORS_ALLOW_CREDENTIALS: bool = False

    MAX_REQUEST_BODY_BYTES: int = Field(
        default=2_097_152,
        ge=1,
    )

    SLOW_REQUEST_THRESHOLD_MS: int = Field(
        default=1_000,
        ge=1,
    )

    SECURE_HEADERS_ENABLED: bool = True
    HSTS_ENABLED: bool = False

    # Proxy headers should be trusted only when requests are guaranteed to pass
    # through an approved gateway, reverse proxy, or load balancer.
    TRUST_PROXY_HEADERS: bool = False
    TRUSTED_PROXY_IPS: str = ""

    # =========================================================================
    # LOGGING
    # =========================================================================

    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    LOG_TO_FILE: bool = False

    LOG_DIR: Path = Path("logs")
    LOG_FILE: str = "app.log"

    LOG_MAX_BYTES: int = Field(
        default=10_000_000,
        ge=1,
    )

    LOG_BACKUP_COUNT: int = Field(
        default=5,
        ge=0,
    )

    LOG_QUEUE_SIZE: int = Field(
        default=10_000,
        ge=100,
    )

    SENSITIVE_DATA_REDACTION_ENABLED: bool = True

    # =========================================================================
    # HEALTH CHECKS
    # =========================================================================

    HEALTHCHECK_TIMEOUT_SECONDS: float = Field(
        default=3.0,
        gt=0,
    )

    DEEP_HEALTH_ENABLED: bool = True

    # =========================================================================
    # SHARED SQLALCHEMY POOL SETTINGS
    # =========================================================================

    SQL_POOL_SIZE: int = Field(
        default=10,
        ge=1,
    )

    SQL_MAX_OVERFLOW: int = Field(
        default=10,
        ge=0,
    )

    SQL_POOL_TIMEOUT_SECONDS: int = Field(
        default=10,
        ge=1,
    )

    SQL_POOL_RECYCLE_SECONDS: int = Field(
        default=1_800,
        ge=0,
    )

    SQL_POOL_PRE_PING: bool = True
    SQL_POOL_USE_LIFO: bool = True
    SQL_ECHO: bool = False

    # =========================================================================
# POSTGRESQL - ACTIVE DATABASE
    # =========================================================================

    ENABLE_POSTGRES: bool = False
    POSTGRES_URL: SecretStr | None = None

    POSTGRES_CONNECT_TIMEOUT_SECONDS: int = Field(
        default=5,
        ge=1,
    )

    POSTGRES_COMMAND_TIMEOUT_SECONDS: int = Field(
        default=30,
        ge=1,
    )

    POSTGRES_APPLICATION_NAME: str = "fastapi_service"

    # =========================================================================
    # MICROSOFT SQL SERVER - COMMENTED REFERENCE
    # =========================================================================
    #
    # To enable Microsoft SQL Server:
    #
    # 1. Uncomment this settings block.
    # 2. Uncomment ``_validate_mssql_configuration``.
    # 3. Uncomment its call inside ``validate_cross_field_rules``.
    # 4. Uncomment ``mssql_url_value``.
    # 5. Uncomment MSSQL sections in ``app/db/registry.py``.
    # 6. Uncomment MSSQL sections in ``app/api/dependencies.py``.
    # 7. Ensure ``app/db/mssql.py`` is active.
    # 8. Install ``aioodbc`` and ``pyodbc``.
    # 9. Configure ``ENABLE_MSSQL`` and ``MSSQL_URL``.
    #
    # ENABLE_MSSQL: bool = False
    # MSSQL_URL: SecretStr | None = None
    #
    # MSSQL_CONNECT_TIMEOUT_SECONDS: int = Field(
    #     default=5,
    #     ge=1,
    # )
    #
    # MSSQL_TRUST_SERVER_CERTIFICATE: bool = False

    # =========================================================================
    # POSTGRESQL - ACTIVE DATABASE
    # =========================================================================
    #
    # =========================================================================
    # MONGODB - COMMENTED REFERENCE
    # =========================================================================
    #
    # To enable MongoDB:
    #
    # 1. Uncomment this settings block.
    # 2. Uncomment the MongoDB field validators.
    # 3. Uncomment ``_validate_mongo_configuration``.
    # 4. Uncomment its call inside ``validate_cross_field_rules``.
    # 5. Uncomment ``mongo_uri_value``.
    # 6. Uncomment MongoDB sections in ``app/db/registry.py``.
    # 7. Uncomment MongoDB sections in ``app/api/dependencies.py``.
    # 8. Ensure ``app/db/mongo.py`` is active.
    # 9. Install ``pymongo``.
    # 10. Configure ``ENABLE_MONGO``, ``MONGO_URI``, and ``MONGO_DB_NAME``.
    #
    # ENABLE_MONGO: bool = False
    # MONGO_URI: SecretStr | None = None
    # MONGO_DB_NAME: str | None = None
    #
    # MONGO_MIN_POOL_SIZE: int = Field(
    #     default=1,
    #     ge=0,
    # )
    #
    # MONGO_MAX_POOL_SIZE: int = Field(
    #     default=50,
    #     ge=1,
    # )
    #
    # MONGO_SERVER_SELECTION_TIMEOUT_MS: int = Field(
    #     default=3_000,
    #     ge=1,
    # )
    #
    # MONGO_CONNECT_TIMEOUT_MS: int = Field(
    #     default=3_000,
    #     ge=1,
    # )
    #
    # MONGO_SOCKET_TIMEOUT_MS: int = Field(
    #     default=5_000,
    #     ge=1,
    # )
    #
    # MONGO_RETRY_WRITES: bool = True
    # MONGO_READ_PREFERENCE: str = "primary"
    # MONGO_WRITE_CONCERN: str = "majority"

    # =========================================================================
    # REDIS - COMMENTED REFERENCE
    # =========================================================================
    #
    # To enable Redis:
    #
    # 1. Uncomment this settings block.
    # 2. Uncomment ``_validate_redis_configuration``.
    # 3. Uncomment its call inside ``validate_cross_field_rules``.
    # 4. Uncomment ``redis_url_value``.
    # 5. Uncomment Redis sections in ``app/db/registry.py``.
    # 6. Uncomment Redis sections in ``app/api/dependencies.py``.
    # 7. Ensure ``app/db/redis_client.py`` is active.
    # 8. Install ``redis``.
    # 9. Configure ``ENABLE_REDIS`` and ``REDIS_URL``.
    #
    # ENABLE_REDIS: bool = False
    # REDIS_URL: SecretStr | None = None
    #
    # REDIS_MAX_CONNECTIONS: int = Field(
    #     default=100,
    #     ge=1,
    # )
    #
    # REDIS_SOCKET_TIMEOUT_SECONDS: float = Field(
    #     default=2.0,
    #     gt=0,
    # )
    #
    # REDIS_CONNECT_TIMEOUT_SECONDS: float = Field(
    #     default=2.0,
    #     gt=0,
    # )
    #
    # REDIS_HEALTH_CHECK_INTERVAL_SECONDS: int = Field(
    #     default=30,
    #     ge=1,
    # )
    #
    # REDIS_RETRY_ON_TIMEOUT: bool = True
    # REDIS_KEY_PREFIX: str = "fastapi-service"
    #
    # REDIS_DEFAULT_TTL_SECONDS: int = Field(
    #     default=300,
    #     ge=1,
    # )

    # =========================================================================
    # CELERY AND BACKGROUND JOBS - COMMENTED REFERENCE
    # =========================================================================
    #
    # To enable Celery:
    #
    # 1. Uncomment this settings block.
    # 2. Uncomment ``_validate_background_jobs_configuration``.
    # 3. Uncomment its call inside ``validate_cross_field_rules``.
    # 4. Uncomment the Celery URL validation helper.
    # 5. Uncomment the Celery derived properties.
    # 6. Activate the files inside ``app/tasks``.
    # 7. Install ``celery`` and the selected broker transport dependency.
    # 8. Configure ``BACKGROUND_JOBS_ENABLED`` and ``CELERY_BROKER_URL``.
    #
    # Redis is not automatically required by Celery. Celery may use Redis,
    # RabbitMQ, or another explicitly supported broker.
    #
    # BACKGROUND_JOBS_ENABLED: bool = False
    #
    # CELERY_BROKER_URL: SecretStr | None = None
    # CELERY_RESULT_BACKEND: SecretStr | None = None
    #
    # CELERY_TASK_ALWAYS_EAGER: bool = False
    # CELERY_TASK_IGNORE_RESULT: bool = True
    #
    # CELERY_TASK_TIME_LIMIT_SECONDS: int = Field(
    #     default=300,
    #     ge=1,
    # )
    #
    # CELERY_TASK_SOFT_TIME_LIMIT_SECONDS: int = Field(
    #     default=270,
    #     ge=1,
    # )
    #
    # CELERY_WORKER_CONCURRENCY: int = Field(
    #     default=4,
    #     ge=1,
    # )
    #
    # CELERY_TASK_MAX_RETRIES: int = Field(
    #     default=3,
    #     ge=0,
    # )
    #
    # CELERY_TASK_DEFAULT_QUEUE: str = "default"

    # =========================================================================
    # FIELD VALIDATORS
    # =========================================================================

    @field_validator("API_V1_STR")
    @classmethod
    def validate_api_prefix(
        cls,
        value: str,
    ) -> str:
        """Normalize and validate the versioned API path prefix.

        Args:
            value: Configured API prefix.

        Returns:
            Normalized API prefix.

        Raises:
            ValueError: If the prefix is invalid.
        """
        normalized = value.strip()

        if not normalized:
            raise ValueError("API_V1_STR must not be blank")

        if not normalized.startswith("/"):
            raise ValueError("API_V1_STR must start with '/'")

        if normalized == "/":
            raise ValueError("API_V1_STR must not use the root path")

        if "?" in normalized or "#" in normalized:
            raise ValueError(
                "API_V1_STR must not contain query parameters or fragments"
            )

        return normalized.rstrip("/")

    @field_validator(
        "PROJECT_NAME",
        "APP_VERSION",
        "LOG_FILE",
    )
    @classmethod
    def validate_required_identifiers(
        cls,
        value: str,
    ) -> str:
        """Normalize and validate required identifier settings.

        Args:
            value: Configured identifier.

        Returns:
            Stripped identifier.

        Raises:
            ValueError: If the identifier is blank.
        """
        normalized = value.strip()

        if not normalized:
            raise ValueError("value must not be blank")

        return normalized

    @field_validator(
        "CORS_ALLOWED_ORIGINS",
        mode="before",
    )
    @classmethod
    def parse_cors_allowed_origins(
        cls,
        value: object,
    ) -> list[str]:
        """Parse and normalize allowed CORS origins.

        Environment values may be supplied as:

        - a JSON-style list parsed by the settings library,
        - a Python list, tuple, or set,
        - a comma-separated string.

        Args:
            value: Raw configured origins.

        Returns:
            Normalized and deduplicated origins.

        Raises:
            TypeError: If the value is not a supported input type.
        """
        if value is None or value == "":
            return []

        if isinstance(value, str):
            values = value.split(",")

        elif isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            values = list(value)

        else:
            raise TypeError(
                "CORS_ALLOWED_ORIGINS must be a list, tuple, set, "
                "or comma-separated string"
            )

        normalized = [
            str(item).strip()
            for item in values
            if str(item).strip()
        ]

        return list(
            dict.fromkeys(normalized)
        )

    @field_validator("LOG_LEVEL")
    @classmethod
    def normalize_log_level(
        cls,
        value: str,
    ) -> str:
        """Normalize and validate the Python logging level.

        Args:
            value: Configured log level.

        Returns:
            Uppercase logging level.

        Raises:
            ValueError: If the level is unknown.
        """
        normalized = value.strip().upper()

        if normalized not in logging.getLevelNamesMapping():
            raise ValueError(
                f"Invalid LOG_LEVEL: {value}"
            )

        return normalized

    @field_validator("TIMEZONE")
    @classmethod
    def validate_timezone(
        cls,
        value: str,
    ) -> str:
        """Validate the configured IANA timezone.

        Args:
            value: Configured timezone name.

        Returns:
            Normalized timezone name.

        Raises:
            ValueError: If the timezone is blank or invalid.
        """
        normalized = value.strip()

        if not normalized:
            raise ValueError("TIMEZONE must not be blank")

        try:
            ZoneInfo(normalized)

        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                f"Invalid TIMEZONE: {normalized}"
            ) from exc

        return normalized

    @field_validator("HOST")
    @classmethod
    def validate_host(
        cls,
        value: str,
    ) -> str:
        """Normalize the ASGI server bind address.

        This setting controls where the server listens. It does not validate
        incoming HTTP Host headers.

        Args:
            value: Configured server bind address.

        Returns:
            Normalized bind address.

        Raises:
            ValueError: If the address is blank.
        """
        normalized = value.strip()

        if not normalized:
            raise ValueError("HOST must not be blank")

        return normalized

    @field_validator("TRUSTED_PROXY_IPS", "POSTGRES_APPLICATION_NAME")
    @classmethod
    def normalize_optional_strings(
        cls,
        value: str,
    ) -> str:
        """Normalize optional string configuration.

        Args:
            value: Raw string value.

        Returns:
            Stripped string value.
        """
        return value.strip()

    # =========================================================================
    # CROSS-FIELD VALIDATION
    # =========================================================================

    @model_validator(mode="after")
    def validate_cross_field_rules(
        self,
    ) -> AppSettings:
        """Validate integration dependencies and production safety rules.

        Returns:
            Validated settings instance.
        """
        self._validate_database_pool_configuration()
        self._validate_postgres_configuration()

        # Optional database and cache validation calls belong here when their
        # respective integrations are enabled.

        self._validate_cors_configuration()
        self._validate_proxy_configuration()
        self._validate_production_configuration()

        return self

    def _validate_database_pool_configuration(
        self,
    ) -> None:
        """Prevent unexpectedly large SQL connection pools per process.

        Raises:
            ValueError: If the configured maximum exceeds the allowed limit.
        """
        maximum_connections = (
            self.SQL_POOL_SIZE
            + self.SQL_MAX_OVERFLOW
        )

        if (
            maximum_connections
            > _MAX_SQL_CONNECTIONS_PER_PROCESS
        ):
            raise ValueError(
                "SQL_POOL_SIZE plus SQL_MAX_OVERFLOW must not exceed "
                f"{_MAX_SQL_CONNECTIONS_PER_PROCESS} connections per process"
            )

    def _validate_postgres_configuration(
        self,
    ) -> None:
        """Validate PostgreSQL configuration when it is enabled.

        Raises:
            ValueError: If the URL is missing, invalid, or uses an unsupported
                asynchronous driver.
        """
        if not self.ENABLE_POSTGRES:
            return

        url = self._required_secret(
            self.POSTGRES_URL,
            "POSTGRES_URL",
        )

        self._validate_url_prefix(
            value=url,
            name="POSTGRES_URL",
            allowed_prefixes=("postgresql+asyncpg://",),
            message="POSTGRES_URL must use postgresql+asyncpg",
        )

    def _validate_cors_configuration(
        self,
    ) -> None:
        """Reject unsafe wildcard and credential combinations.

        Raises:
            ValueError: If wildcard origins are combined with credentials.
        """
        if (
            self.CORS_ALLOW_CREDENTIALS
            and "*" in self.CORS_ALLOWED_ORIGINS
        ):
            raise ValueError(
                "Wildcard CORS origins cannot be used with credentials"
            )

    def _validate_proxy_configuration(
        self,
    ) -> None:
        """Require explicit proxy addresses when proxy headers are trusted.

        Raises:
            ValueError: If proxy trust is enabled without configured proxies.
        """
        if (
            self.TRUST_PROXY_HEADERS
            and not self.trusted_proxy_ip_list
        ):
            raise ValueError(
                "TRUSTED_PROXY_IPS is required when "
                "TRUST_PROXY_HEADERS=true"
            )

    def _validate_production_configuration(
        self,
    ) -> None:
        """Enforce production safety requirements owned by this application.

        Raises:
            ValueError: If an unsafe production setting is detected.
        """
        if self.ENVIRONMENT != Environment.PRODUCTION:
            return

        if self.DEBUG:
            raise ValueError(
                "DEBUG must be false in production"
            )

        if self.SQL_ECHO:
            raise ValueError(
                "SQL_ECHO must be false in production"
            )

        if self.LOG_TO_FILE:
            raise ValueError(
                "LOG_TO_FILE should be false in production containers"
            )

        if not self.LOG_JSON:
            raise ValueError(
                "LOG_JSON must be true in production"
            )

        if not self.SECURE_HEADERS_ENABLED:
            raise ValueError(
                "SECURE_HEADERS_ENABLED must be true in production"
            )

        if "*" in self.CORS_ALLOWED_ORIGINS:
            raise ValueError(
                "Production CORS_ALLOWED_ORIGINS must not "
                "contain a wildcard"
            )

    # =========================================================================
    # INTERNAL VALIDATION HELPERS
    # =========================================================================

    @staticmethod
    def _required_secret(
        value: SecretStr | None,
        name: str,
    ) -> str:
        """Return a required normalized secret value.

        Args:
            value: Optional secret setting.
            name: Configuration field name.

        Returns:
            Unwrapped and stripped secret value.

        Raises:
            ValueError: If the value is missing or blank.
        """
        if value is None:
            raise ValueError(
                f"{name} is required when its integration is enabled"
            )

        secret = value.get_secret_value().strip()

        if not secret:
            raise ValueError(
                f"{name} is required when its integration is enabled"
            )

        return secret

    @staticmethod
    def _validate_url_prefix(
        *,
        value: str,
        name: str,
        allowed_prefixes: tuple[str, ...],
        message: str,
    ) -> None:
        """Validate a connection URL and its driver prefix.

        Args:
            value: Connection URL.
            name: Configuration field name.
            allowed_prefixes: Accepted connection prefixes.
            message: Validation message for an unsupported prefix.

        Raises:
            ValueError: If the prefix or URL structure is invalid.
        """
        if not value.startswith(allowed_prefixes):
            raise ValueError(message)

        parsed = urlparse(value)

        if not parsed.scheme or not parsed.netloc:
            raise ValueError(
                f"{name} must be a valid connection URL"
            )

    @staticmethod
    def _optional_secret_value(
        value: SecretStr | None,
    ) -> str | None:
        """Return an unwrapped optional secret value.

        Args:
            value: Optional secret.

        Returns:
            Normalized secret or ``None``.
        """
        if value is None:
            return None

        normalized = value.get_secret_value().strip()

        return normalized or None

    # =========================================================================
    # DERIVED PROPERTIES
    # =========================================================================

    @property
    def log_directory(
        self,
    ) -> Path:
        """Return the absolute log directory without creating it.

        Returns:
            Absolute log directory.
        """
        if self.LOG_DIR.is_absolute():
            return self.LOG_DIR

        return self.BASE_DIR / self.LOG_DIR

    @property
    def trusted_proxy_ip_list(
        self,
    ) -> tuple[str, ...]:
        """Return normalized trusted proxy addresses or network ranges.

        Returns:
            Deduplicated trusted proxy values.
        """
        values = (
            item.strip()
            for item in self.TRUSTED_PROXY_IPS.split(",")
        )

        return tuple(
            dict.fromkeys(
                item
                for item in values
                if item
            )
        )

    @property
    def enabled_database_names(
        self,
    ) -> tuple[str, ...]:
        """Return names of active database integrations.

        PostgreSQL is currently the only active database integration.

        Returns:
            Enabled database names.
        """
        enabled: list[str] = []

        if self.ENABLE_POSTGRES:
            enabled.append("postgres")

        return tuple(enabled)

    @property
    def postgres_url_value(
        self,
    ) -> str | None:
        """Return the unwrapped PostgreSQL connection URL.

        Returns:
            PostgreSQL connection URL or ``None``.
        """
        return self._optional_secret_value(
            self.POSTGRES_URL
        )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached and validated process configuration.

    Application code should use this function instead of constructing
    ``AppSettings`` repeatedly.

    Returns:
        Cached immutable settings.
    """
    return AppSettings()


def clear_settings_cache() -> None:
    """Clear the cached settings object.

    This helper is intended for tests that temporarily replace environment
    configuration.
    """
    get_settings.cache_clear()


__all__ = [
    "AppSettings",
    "Environment",
    "clear_settings_cache",
    "get_settings",
]
