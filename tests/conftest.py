"""Shared fixtures for FastAPI application smoke tests."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import AppSettings, Environment
from app.main import create_app


@pytest.fixture
def app_settings() -> AppSettings:
    """Return isolated settings with all database integrations disabled."""
    return AppSettings(
        ENVIRONMENT=Environment.TESTING,
        PROJECT_NAME="test-service",
        APP_VERSION="0.0.1",
        ENABLE_POSTGRES=False,
        LOG_TO_FILE=False,
    )


@pytest.fixture
def app(app_settings: AppSettings) -> FastAPI:
    """Create a fresh FastAPI application using test configuration."""
    return create_app(app_settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Start and stop the application lifespan around API requests."""
    with TestClient(app) as test_client:
        yield test_client
