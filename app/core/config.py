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

AWS email, SMS, and object storage are configured independently through the
authentication module's delivery and storage adapters.

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
import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import (
    ZoneInfo,
    ZoneInfoNotFoundError,
)

from email_validator import EmailNotValidError, validate_email
from cryptography.fernet import Fernet
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
_MIN_AUTH_SECRET_LENGTH = 32


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

    # Authentication remains disabled until a strong secret is configured.
    AUTH_ENABLED: bool = False
    AUTH_JWT_SECRET_KEY: SecretStr | None = None
    AUTH_ACCESS_TOKEN_MINUTES: int = Field(default=15, ge=1, le=60)
    AUTH_REFRESH_TOKEN_DAYS: int = Field(default=30, ge=1, le=90)
    AUTH_PASSWORD_MIN_LENGTH: int = Field(default=12, ge=12, le=128)
    AUTH_LOGIN_RATE_LIMIT: int = Field(default=10, ge=1, le=100)
    AUTH_LOGIN_RATE_WINDOW_SECONDS: int = Field(default=900, ge=60, le=86400)
    AUTH_OTP_RATE_LIMIT: int = Field(default=3, ge=1, le=20)
    AUTH_OTP_RATE_WINDOW_SECONDS: int = Field(default=3600, ge=60, le=86400)
    AUTH_OTP_TTL_SECONDS: int = Field(default=300, ge=60, le=900)
    AUTH_OTP_MAX_ATTEMPTS: int = Field(default=5, ge=1, le=10)
    AUTH_ACTION_TOKEN_TTL_SECONDS: int = Field(default=1800, ge=300, le=86400)
    AUTH_EMAIL_DELIVERY_ENABLED: bool = False
    AUTH_SMS_DELIVERY_ENABLED: bool = False
    PROFILE_IMAGE_STORAGE_ENABLED: bool = False
    AWS_REGION: str | None = None
    AWS_S3_BUCKET: str | None = None
    AWS_SES_FROM_EMAIL: str | None = None
    AWS_SMS_ORIGINATION_IDENTITY: str | None = None
    AUTH_PUBLIC_BASE_URL: str | None = None
    AWS_CONNECT_TIMEOUT_SECONDS: int = Field(default=3, ge=1, le=30)
    AWS_READ_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=60)
    BACKGROUND_JOBS_ENABLED: bool = False
    REDIS_URL: SecretStr | None = None
    CELERY_RESULT_BACKEND: SecretStr | None = None
    BACKGROUND_PAYLOAD_ENCRYPTION_KEY: SecretStr | None = None
    CELERY_TASK_ALWAYS_EAGER: bool = False
    CELERY_TASK_TIME_LIMIT_SECONDS: int = Field(default=300, ge=10, le=3600)
    CELERY_TASK_SOFT_TIME_LIMIT_SECONDS: int = Field(default=240, ge=5, le=3599)
    CELERY_WORKER_CONCURRENCY: int = Field(default=2, ge=1, le=64)
    CELERY_TASK_MAX_RETRIES: int = Field(default=5, ge=0, le=20)
    CELERY_OUTBOX_BATCH_SIZE: int = Field(default=100, ge=1, le=1000)
    CELERY_OUTBOX_POLL_SECONDS: int = Field(default=10, ge=1, le=300)
    CELERY_OUTBOX_LEASE_SECONDS: int = Field(default=300, ge=30, le=3600)
    CELERY_OUTBOX_RETENTION_DAYS: int = Field(default=30, ge=1, le=3650)
    AUTH_SESSION_RETENTION_DAYS: int = Field(default=30, ge=1, le=3650)
    CELERY_CLEANUP_BATCH_SIZE: int = Field(default=500, ge=1, le=5000)
    AWS_S3_MAX_UPLOAD_BYTES: int = Field(default=5_242_880, ge=1, le=52_428_800)
    AWS_S3_UPLOAD_URL_TTL_SECONDS: int = Field(default=300, ge=60, le=900)
    AWS_S3_DOWNLOAD_URL_TTL_SECONDS: int = Field(default=300, ge=60, le=900)

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
    # REDIS - OPTIONAL CACHE REFERENCE
    # =========================================================================
    #
    # Celery uses the active REDIS_URL and settings declared with auth fields.
    # No general-purpose cache client is created as part of API startup.
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
    # CELERY AND BACKGROUND JOBS - ACTIVE SETTINGS DECLARED ABOVE
    # =========================================================================
    #
    # Celery configuration is in app/worker; Redis is the supported broker.
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

    @field_validator(
        "AWS_REGION",
        "AWS_S3_BUCKET",
        "AWS_SMS_ORIGINATION_IDENTITY",
        "AUTH_PUBLIC_BASE_URL",
    )
    @classmethod
    def normalize_aws_settings(cls, value: str | None) -> str | None:
        """Trim optional AWS identities and action-link configuration."""
        return value.strip() if value is not None else None

    @field_validator("AWS_SES_FROM_EMAIL")
    @classmethod
    def normalize_ses_sender(cls, value: str | None) -> str | None:
        """Normalize and validate the SES sender mailbox when supplied."""
        if value is None or not value.strip():
            return None
        try:
            return validate_email(
                value.strip(), check_deliverability=False
            ).normalized
        except EmailNotValidError as exc:
            raise ValueError(
                "AWS_SES_FROM_EMAIL must be a valid email address"
            ) from exc

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
        self._validate_auth_configuration()
        self._validate_background_jobs_configuration()

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

    def _validate_auth_configuration(self) -> None:
        """Validate authentication secrets and configured AWS adapters."""
        if self.AUTH_ENABLED:
            if not self.ENABLE_POSTGRES:
                raise ValueError("ENABLE_POSTGRES must be true when AUTH_ENABLED is true")
            secret = self._required_secret(
                self.AUTH_JWT_SECRET_KEY,
                "AUTH_JWT_SECRET_KEY",
            )
            if len(secret) < _MIN_AUTH_SECRET_LENGTH:
                raise ValueError("AUTH_JWT_SECRET_KEY must contain at least 32 characters")
        elif self.AUTH_JWT_SECRET_KEY is not None:
            secret = self.AUTH_JWT_SECRET_KEY.get_secret_value().strip()
            if secret and len(secret) < _MIN_AUTH_SECRET_LENGTH:
                raise ValueError("AUTH_JWT_SECRET_KEY must contain at least 32 characters")

        aws_enabled = (
            self.AUTH_EMAIL_DELIVERY_ENABLED
            or self.AUTH_SMS_DELIVERY_ENABLED
            or self.PROFILE_IMAGE_STORAGE_ENABLED
        )
        if aws_enabled and not (self.AWS_REGION or "").strip():
            raise ValueError(
                "AWS_REGION is required when an AWS integration is enabled"
            )
        if aws_enabled and not re.fullmatch(
            r"[a-z]{2}(?:-[a-z0-9]+)+-\d", self.AWS_REGION or ""
        ):
            raise ValueError("AWS_REGION must be a valid region identifier")
        if self.AUTH_EMAIL_DELIVERY_ENABLED:
            self._require_setting(self.AWS_SES_FROM_EMAIL, "AWS_SES_FROM_EMAIL")
            self._validate_http_url(self.AUTH_PUBLIC_BASE_URL, "AUTH_PUBLIC_BASE_URL")
        if self.AUTH_SMS_DELIVERY_ENABLED:
            self._require_setting(
                self.AWS_SMS_ORIGINATION_IDENTITY,
                "AWS_SMS_ORIGINATION_IDENTITY",
            )
        if self.PROFILE_IMAGE_STORAGE_ENABLED:
            self._require_setting(self.AWS_S3_BUCKET, "AWS_S3_BUCKET")
            bucket = self.AWS_S3_BUCKET or ""
            if (
                not 3 <= len(bucket) <= 63
                or not re.fullmatch(r"[a-z0-9][a-z0-9.-]*[a-z0-9]", bucket)
                or ".." in bucket
            ):
                raise ValueError("AWS_S3_BUCKET must be a valid S3 bucket name")

    def _validate_background_jobs_configuration(self) -> None:
        """Validate Redis, Celery, and encrypted notification outbox settings."""
        if self.AUTH_EMAIL_DELIVERY_ENABLED or self.AUTH_SMS_DELIVERY_ENABLED:
            if not self.BACKGROUND_JOBS_ENABLED:
                raise ValueError(
                    "BACKGROUND_JOBS_ENABLED is required for email and SMS delivery"
                )
        if not self.BACKGROUND_JOBS_ENABLED:
            return
        if not self.ENABLE_POSTGRES:
            raise ValueError(
                "ENABLE_POSTGRES must be true when background jobs are enabled"
            )
        redis_url = self._required_secret(self.REDIS_URL, "REDIS_URL")
        self._validate_url_prefix(
            value=redis_url,
            name="REDIS_URL",
            allowed_prefixes=("redis://", "rediss://"),
            message="REDIS_URL must use redis or rediss",
        )
        result_backend = self._optional_secret_value(self.CELERY_RESULT_BACKEND)
        if result_backend:
            self._validate_url_prefix(
                value=result_backend,
                name="CELERY_RESULT_BACKEND",
                allowed_prefixes=("redis://", "rediss://"),
                message="CELERY_RESULT_BACKEND must use redis or rediss",
            )
        encryption_key = self._required_secret(
            self.BACKGROUND_PAYLOAD_ENCRYPTION_KEY,
            "BACKGROUND_PAYLOAD_ENCRYPTION_KEY",
        )
        try:
            Fernet(encryption_key.encode())
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "BACKGROUND_PAYLOAD_ENCRYPTION_KEY must be a Fernet key"
            ) from exc
        if self.CELERY_TASK_SOFT_TIME_LIMIT_SECONDS >= self.CELERY_TASK_TIME_LIMIT_SECONDS:
            raise ValueError(
                "CELERY_TASK_SOFT_TIME_LIMIT_SECONDS must be below the hard limit"
            )

    @staticmethod
    def _require_setting(value: str | None, name: str) -> None:
        if value is None or not value.strip():
            raise ValueError(f"{name} is required when its integration is enabled")

    @staticmethod
    def _validate_http_url(value: str | None, name: str) -> None:
        if value is None:
            raise ValueError(f"{name} is required when email delivery is enabled")
        parsed = urlparse(value)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise ValueError(f"{name} must be a valid HTTP or HTTPS URL")

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

    @property
    def redis_url_value(self) -> str | None:
        """Return the unwrapped Redis broker URL."""
        return self._optional_secret_value(self.REDIS_URL)

    @property
    def celery_result_backend_value(self) -> str | None:
        """Return the optional unwrapped Celery result backend URL."""
        return self._optional_secret_value(self.CELERY_RESULT_BACKEND)

    @property
    def background_payload_encryption_key_value(self) -> str | None:
        """Return the unwrapped encryption key for outbox notification payloads."""
        return self._optional_secret_value(self.BACKGROUND_PAYLOAD_ENCRYPTION_KEY)


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
