# =============================================================================
# FASTAPI SERVICE DOCKER IMAGE
#
# This image runs only the FastAPI web service.
#
# It does not start or manage:
#
# - MySQL
# - PostgreSQL
# - Microsoft SQL Server
# - MongoDB
# - Redis
# - Celery workers
# - Celery Beat
#
# External infrastructure is configured through environment variables.
#
# Python dependencies are installed from ``pyproject.toml``. Only the default
# runtime dependencies are installed. Optional groups such as ``worker``,
# ``redis``, ``postgres``, ``mssql``, and ``mongo`` are not installed.
# =============================================================================


# =============================================================================
# BASE IMAGE
# =============================================================================

FROM python:3.12-slim AS runtime


# =============================================================================
# PYTHON RUNTIME CONFIGURATION
# =============================================================================

# Prevent Python from writing compiled .pyc files inside the container.
ENV PYTHONDONTWRITEBYTECODE=1

# Send Python output directly to container logs without buffering.
ENV PYTHONUNBUFFERED=1

# Disable pip's local package cache to reduce image size.
ENV PIP_NO_CACHE_DIR=1

# Disable pip's automatic version-check request.
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Define the application working directory.
ENV APP_HOME=/app


# =============================================================================
# WORKING DIRECTORY
# =============================================================================

WORKDIR ${APP_HOME}


# =============================================================================
# SYSTEM DEPENDENCIES
# =============================================================================

# Install only the operating-system dependencies required by the service.
#
# build-essential:
#     Supports Python packages that require native compilation when a prebuilt
#     wheel is unavailable.
#
# curl:
#     Used by the Docker container health check.
#
# Package metadata is removed after installation to reduce image size.
RUN apt-get update \
    && apt-get install \
        --no-install-recommends \
        --yes \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*


# =============================================================================
# NON-ROOT APPLICATION USER
# =============================================================================

# Run the FastAPI service as a non-root operating-system user.
RUN groupadd \
        --system \
        appgroup \
    && useradd \
        --system \
        --gid appgroup \
        --create-home \
        --home-dir /home/appuser \
        appuser


# =============================================================================
# PROJECT METADATA
# =============================================================================

# Copy project metadata before application source so Docker can reuse the
# dependency-installation layer when only source files change.
#
# README.md is copied because ``pyproject.toml`` declares it as the project
# readme.
COPY pyproject.toml README.md ./


# =============================================================================
# APPLICATION SOURCE
# =============================================================================

# Copy the application package before installation because setuptools needs
# the package source while building and installing the project.
COPY app ./app


# =============================================================================
# PYTHON DEPENDENCIES
# =============================================================================

# Upgrade the packaging tools and install the project from ``pyproject.toml``.
#
# Running ``pip install .`` installs:
#
# - the FastAPI application package,
# - default runtime dependencies,
# - active MySQL support.
#
# It does not install optional dependency groups such as:
#
# - dev,
# - worker,
# - redis,
# - postgres,
# - mssql,
# - mongo,
# - all-databases,
# - all.
RUN python -m pip install \
        --upgrade \
        pip \
        setuptools \
        wheel \
    && python -m pip install \
        .


# =============================================================================
# FILE OWNERSHIP
# =============================================================================

# Ensure the non-root application user owns the application directory and any
# package metadata generated during installation.
RUN chown \
        --recursive \
        appuser:appgroup \
        ${APP_HOME}


# =============================================================================
# RUNTIME USER
# =============================================================================

USER appuser


# =============================================================================
# NETWORK
# =============================================================================

# Document the internal port exposed by the FastAPI service.
#
# EXPOSE does not publish the port to the host. Port publication is handled by
# Docker Compose or the container platform.
EXPOSE 8000


# =============================================================================
# CONTAINER HEALTH CHECK
# =============================================================================

# Check only the lightweight application liveness endpoint.
#
# A liveness check verifies that the HTTP process is running. It should not
# generally fail because an external database is temporarily unavailable.
#
# Update the path when the application uses a different liveness route.
HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=20s \
    --retries=3 \
    CMD curl \
        --fail \
        --silent \
        --show-error \
        http://127.0.0.1:8000/health/live \
        > /dev/null \
        || exit 1


# =============================================================================
# FASTAPI STARTUP COMMAND
# =============================================================================

# Use Docker's JSON exec form so:
#
# - Uvicorn becomes the main container process,
# - Unix signals are delivered directly to Uvicorn,
# - graceful shutdown works correctly,
# - no intermediate shell process is introduced.
#
# Keep the JSON-array CMD on one physical Dockerfile line so Docker and editor
# language servers parse it as one instruction.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-server-header"]
