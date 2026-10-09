<div align="center">

# 🚀 FastAPI Microservice Foundation

### Reusable • Async • Production-Oriented • Microservice-Ready

<p>
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/FastAPI-Async-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/SQLAlchemy-2.x-D71F00?logo=sqlalchemy&logoColor=white" alt="SQLAlchemy 2">
  <img src="https://img.shields.io/badge/PostgreSQL-Async-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/Tests-pytest-0A9EDC?logo=pytest&logoColor=white" alt="pytest">
</p>

<p>
A reusable FastAPI foundation for building consistent, scalable, maintainable,
and production-oriented Python microservices.
</p>

</div>

## Documentation map

- [Architecture](Architecture.md)
- [API reference](docs/API.md)
- [Deployment runbook](docs/DEPLOYMENT.md)
- [Environment template](.env.example)
- [API reference](docs/API_REFERENCE.md)
- [Setup guide](docs/SETUP_GUIDE.md)

---

## 📌 Overview

This repository provides a production-oriented FastAPI service with async
PostgreSQL persistence, explicit Alembic migrations, JWT authentication, RBAC,
audit history, private S3 uploads, optional SES/SMS delivery, and separately
run Celery worker/Beat processes. Its layered application layout is preserved;
external AWS and background services are opt-in through validated settings.

**Quick start:** create a Python 3.12+ virtual environment, install
`requirements.txt` and `requirements-dev.txt`, copy `.env.example` to `.env`,
configure PostgreSQL when enabling auth, run `alembic upgrade head`, then start
with `python -m uvicorn app.main:app --reload`. Full Windows, Linux/macOS,
PostgreSQL, AWS, and admin-bootstrap instructions are in
[`docs/SETUP_GUIDE.md`](docs/SETUP_GUIDE.md).

The active source layout is:

```text
app/
  api/             health, exception handling, and versioned routers
  common/          response, pagination, filtering, and sorting utilities
  core/             settings, middleware, request context, and logging
  db/               PostgreSQL adapter, registry, and Unit of Work
  modules/auth/     auth, user, RBAC, audit, and provider integration
  worker/           optional Celery tasks and outbox processing
  main.py           FastAPI app factory and CLI entry point
migrations/         Alembic environment and revisions
docs/               API, setup, deployment, and architecture guidance
tests/              unit, API, integration, contract, and end-to-end tests
```

Authentication and stored-file APIs require PostgreSQL and remain disabled
until `AUTH_ENABLED=true`. S3, SES, SMS, and background delivery are independent
opt-in features; AWS credentials and verified provider identities must be
supplied by the runtime. The example module is a template and is not mounted
under the current v1 router. PostgreSQL migrations are operator-run, not part
of API startup.
building multiple backend microservices.

It includes a clean separation between:

* HTTP routing,
* application services,
* repositories,
* database adapters,
* transaction management,
* configuration,
* logging,
* middleware,
* request context,
* reusable API utilities,
* tests,
* Docker configuration,
* optional background worker infrastructure.

The project runs as a FastAPI service with asynchronous PostgreSQL support
through SQLAlchemy 2 and asyncpg. Alembic manages schema revisions explicitly.

Microsoft SQL Server and MongoDB remain disabled reference integrations.
Redis and Celery provide the optional background notification and maintenance
processes described below.

---

## 🎯 Primary Goals

| Goal                    | Description                                                                            |
| ----------------------- | -------------------------------------------------------------------------------------- |
| **Reusable**            | Can be copied and adapted for multiple microservices.                                  |
| **Compact**             | Avoids unnecessary abstraction and framework complexity.                               |
| **Async-first**         | Uses asynchronous FastAPI, SQLAlchemy, sessions, and database access.                  |
| **Explicit**            | Routing, dependencies, transactions, and infrastructure ownership remain visible.      |
| **Maintainable**        | Each file and layer has a clear responsibility.                                        |
| **Testable**            | Business, API, persistence, and contract behavior can be tested independently.         |
| **Production-oriented** | Includes structured logging, health checks, Docker, validation, and graceful shutdown. |
| **Extensible**          | Optional databases, Redis, and Celery can be enabled without redesigning the project.  |

---

## 🧱 Technology Stack

### Active Runtime

| Technology         | Purpose                                         |
| ------------------ | ----------------------------------------------- |
| Python 3.12+       | Application runtime                             |
| FastAPI            | Asynchronous API framework                      |
| Uvicorn            | ASGI server                                     |
| Pydantic 2         | Request, response, and configuration validation |
| Pydantic Settings  | Environment-based configuration                 |
| SQLAlchemy 2       | ORM and database query layer                    |
| asyncpg            | Asynchronous PostgreSQL driver                  |
| Alembic            | Explicit PostgreSQL schema migrations           |
| argon2-cffi        | Argon2id password hashing                       |
| PyJWT              | Signed access JWTs                              |
| email-validator    | Email identifier validation                     |
| python-json-logger | Structured JSON logging                         |
| Docker             | Containerized deployment                        |

### Development and Testing

| Tool           | Purpose                         |
| -------------- | ------------------------------- |
| pytest         | Test framework                  |
| pytest-asyncio | Async test support              |
| HTTPX          | API and ASGI testing            |
| pytest-cov     | Test coverage                   |
| Ruff           | Formatting and linting          |
| mypy           | Static type checking            |
| pip-audit      | Dependency vulnerability checks |
| pre-commit     | Automated local quality checks  |

### Disabled Optional Integrations

The following integrations are intentionally disabled:

* Microsoft SQL Server
* MongoDB
* Redis
* Celery Worker
* Celery Beat

They should be enabled only after their configuration, dependencies, registry
integration, health checks, and tests are activated.

---

## 🏗️ Architecture

The project follows a pragmatic layered architecture.

```mermaid
flowchart LR
    Client[Client / API Gateway]
    Router[FastAPI Router]
    Service[Application Service]
    Repository[Repository]
    UOW[Unit of Work]
    Database[(PostgreSQL)]

    Client --> Router
    Router --> Service
    Service --> Repository
    Service --> UOW
    Repository --> UOW
    UOW --> Database
```

The main application flow is:

```text
HTTP Request
    ↓
Middleware and Request Context
    ↓
API Router
    ↓
Dependency Injection
    ↓
Application Service
    ↓
Repository
    ↓
Unit of Work
    ↓
External Database
    ↓
Standard API Response
```

### Architectural Rule

```text
Router → Service → Repository → Database
```

Each layer has a clear responsibility.

| Layer            | Responsibility                                     |
| ---------------- | -------------------------------------------------- |
| Router           | HTTP transport and request parsing                 |
| Service          | Business logic and workflow orchestration          |
| Repository       | Persistence operations and queries                 |
| Unit of Work     | Transaction and session ownership                  |
| Database Adapter | Engine, pool, connection, and lifecycle management |
| Common/Core      | Shared cross-cutting functionality                 |

Detailed architecture is available in:

```text
ARCHITECTURE.md
```

---

## 📁 Project Structure

```text
fastapi-production-boilerplate/
├── app/
│   ├── api/
│   │   ├── v1/
│   │   ├── dependencies.py
│   │   ├── exception_handlers.py
│   │   ├── health.py
│   │   └── router.py
│   ├── common/
│   │   ├── exceptions.py
│   │   ├── execution.py
│   │   ├── filters.py
│   │   ├── pagination.py
│   │   ├── response.py
│   │   └── sorting.py
│   ├── core/
│   │   ├── config.py
│   │   ├── constants.py
│   │   ├── lifespan.py
│   │   ├── logging.py
│   │   ├── middleware.py
│   │   └── request_context.py
│   ├── db/
│   │   ├── base.py
│   │   ├── postgres.py
│   │   ├── mssql.py
│   │   ├── mongo.py
│   │   ├── redis_client.py
│   │   ├── registry.py
│   │   ├── sqlalchemy_types.py
│   │   └── uow.py
│   ├── modules/
│   │   └── example/
│   ├── utils/
│   ├── worker/
│   └── main.py
├── cicd/
├── docs/
├── scripts/
├── tests/
├── .dockerignore
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── README.md
├── ARCHITECTURE.md
├── STRUCTURE.md
├── DEVELOPMENT.md
└── TESTING.md
```

A complete file-by-file explanation is available in:

```text
STRUCTURE.md
```

---

## 🔤 Naming Conventions

The project follows consistent naming rules across API, Python, database, and
event boundaries.

| Boundary              | Convention              | Example                |
| --------------------- | ----------------------- | ---------------------- |
| API request fields    | camelCase               | `productId`            |
| API response fields   | camelCase               | `createdAt`            |
| Query parameters      | camelCase               | `pageSize`             |
| Event payload fields  | camelCase               | `orderId`              |
| URL paths             | kebab-case              | `/product-locations`   |
| Python variables      | snake_case              | `product_id`           |
| Python functions      | snake_case              | `create_product`       |
| Classes               | PascalCase              | `ProductService`       |
| Pydantic schemas      | PascalCase              | `CreateProductRequest` |
| Database tables       | snake_case              | `product_locations`    |
| Database columns      | snake_case              | `created_at`           |
| Constants             | UPPER_SNAKE_CASE        | `DEFAULT_PAGE_SIZE`    |
| Environment variables | UPPER_SNAKE_CASE        | `POSTGRES_URL`         |
| Event names           | dot-separated lowercase | `product.created`      |

Pydantic aliases should convert external camelCase fields into internal
snake_case Python attributes.

---

## ⚙️ Configuration

Application configuration is managed through:

```text
app/core/config.py
```

Local values are loaded from:

```text
.env
```

Production values should be injected through the deployment platform.

### Example

```dotenv
# =============================================================================
# APPLICATION
# =============================================================================

ENVIRONMENT=development
PROJECT_NAME=fastapi_service
APP_VERSION=1.0.0
DEBUG=true

HOST=0.0.0.0
PORT=8000
TIMEZONE=Asia/Kolkata


# =============================================================================
# POSTGRESQL
# =============================================================================

ENABLE_POSTGRES=true
POSTGRES_URL=postgresql+asyncpg://username:password@localhost:5432/database_name
```

Never commit the real `.env` file.

Use `.env.example` to document supported values without including secrets.

---

## 🚀 Local Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd fastapi-production-boilerplate
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Activate on Windows Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

Activate on Linux or macOS:

```bash
source .venv/bin/activate
```

### 3. Upgrade packaging tools

```bash
python -m pip install --upgrade pip setuptools wheel
```

### 4. Install development dependencies

```bash
python -m pip install -r requirements-dev.txt
```

`requirements.txt` and `requirements-dev.txt` are the dependency manifests.
`pyproject.toml` is used only for project metadata and tool configuration.

### 5. Create the environment file

Linux or macOS:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

### 6. Start the application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

After installing the project, the `fastapi-service` command starts the same
application using the configured `HOST` and `PORT` values.

The service will be available at:

```text
http://localhost:8000
```

---

## 📖 API Documentation

FastAPI automatically exposes interactive API documentation.

| Interface    | URL                                  |
| ------------ | ------------------------------------ |
| Swagger UI   | `http://localhost:8000/docs`         |
| ReDoc        | `http://localhost:8000/redoc`        |
| OpenAPI JSON | `http://localhost:8000/openapi.json` |

Documentation availability may be disabled or restricted in production through
application configuration.

---

## ❤️ Health Endpoints

Recommended health routes:

| Endpoint            | Purpose                                              |
| ------------------- | ---------------------------------------------------- |
| `GET /health`       | General service health summary                       |
| `GET /health/live`  | Process liveness                                     |
| `GET /health/ready` | Application readiness and required dependency checks |

### Liveness

Liveness confirms that the FastAPI process can respond.

It should not fail only because an external database is temporarily unavailable.

### Readiness

Readiness confirms that the service is prepared to receive traffic.

It may validate:

* application initialization,
* required configuration,
* PostgreSQL connectivity,
* mandatory infrastructure state.

---

## 🐳 Docker

Docker Compose starts the FastAPI service, PostgreSQL, Redis, Celery workers,
and a separate Celery Beat scheduler. PostgreSQL and Redis use persistent
volumes.

It does not start:

* MSSQL,
* MongoDB,
* MSSQL,
* MongoDB.

Other databases and infrastructure remain external and are configured through
environment variables.

### Build and start

```bash
docker compose up --build
```

### Start in the background

```bash
docker compose up --build -d
```

### View logs

```bash
docker compose logs -f api
```

### Stop

```bash
docker compose down
```

### Rebuild without cache

```bash
docker compose build --no-cache
```

---

## 🗄️ Database Architecture

PostgreSQL is the active database. Docker Compose persists its data in the
`postgres-data` volume; local Windows Python connects through `localhost`.

Expected SQLAlchemy URL:

```text
postgresql+asyncpg://username:password@localhost:5432/database_name
```

Set `POSTGRES_URL` in `.env` or the process environment. URL-encode reserved
characters in usernames and passwords. For Compose, keep `POSTGRES_DOCKER_URL`
in sync with the local URL and use the `postgres` service hostname there.

### Database Ownership Rules

Use Alembic to manage schema changes explicitly. The API never creates tables or
runs migrations during startup. ORM models must inherit from
`app.db.base.Base`; import model modules from `migrations/env.py` so
autogeneration sees the registered feature models, including user and authentication tables.

After installing `requirements-dev.txt` and setting `ENABLE_POSTGRES=true` plus
`POSTGRES_URL`, create and apply revisions from the repository root:

```powershell
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
alembic downgrade -1
```

`alembic downgrade base` reverts all revisions. Review generated migrations
before applying them. For PostgreSQL on Windows, copy `.env.example` to `.env`,
replace the placeholder password, and run `docker compose up -d postgres`. The
Compose service publishes port 5432; keep `POSTGRES_URL` pointed at localhost
when running Python on Windows.

Run the full stack with `docker compose up --build`; Compose overrides the API
container URL to use the `postgres` service hostname. Apply migrations
separately with Alembic. Application startup only validates connectivity.

Alembic revisions in this repository are the reviewed schema history. API
startup checks connectivity only; operators apply revisions explicitly.

---

## 🔄 Transaction Management

The project uses the Unit of Work pattern.

```mermaid
stateDiagram-v2
    [*] --> TransactionOpened
    TransactionOpened --> Commit: success
    TransactionOpened --> Rollback: exception
    Commit --> SessionClosed
    Rollback --> SessionClosed
    SessionClosed --> [*]
```

Rules:

* one session per business use case,
* one Unit of Work per transaction,
* repositories reuse the same transaction session,
* successful workflows commit,
* failed workflows roll back,
* sessions always close,
* sessions are never stored globally.

---

## 📦 API Response Format

Successful response:

```json
{
  "success": true,
  "message": "Products retrieved successfully",
  "data": [],
  "meta": {
    "page": 1,
    "pageSize": 20,
    "totalItems": 0,
    "totalPages": 0,
    "hasNext": false,
    "hasPrevious": false
  }
}
```

Error response:

```json
{
  "success": false,
  "message": "Requested resource was not found",
  "data": null,
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "details": null
  }
}
```

Raw database exceptions, credentials, internal stack traces, and sensitive
configuration must never be returned to clients.

---

## 🧩 Adding a New Business Module

Create a new module using this structure:

```text
app/modules/product/
├── __init__.py
├── dependencies.py
├── models.py
├── openapi.py
├── repository.py
├── router.py
├── schemas.py
└── service.py
```

Recommended implementation order:

1. map the existing database tables,
2. create request and response schemas,
3. implement repository queries,
4. implement application service workflows,
5. expose dependency providers,
6. create API routes,
7. define OpenAPI metadata,
8. register the module router,
9. add unit tests,
10. add API and integration tests.

### Module Responsibilities

| File              | Responsibility                              |
| ----------------- | ------------------------------------------- |
| `models.py`       | SQLAlchemy ORM mappings                     |
| `schemas.py`      | Pydantic request and response schemas       |
| `repository.py`   | Database queries and persistence logic      |
| `service.py`      | Business rules and workflow orchestration   |
| `dependencies.py` | Repository and service dependency providers |
| `router.py`       | FastAPI endpoints                           |
| `openapi.py`      | OpenAPI metadata and examples               |

---

## 🔐 User authentication

Authentication is configured with `AUTH_ENABLED=false` by default. To enable
password and JWT flows, configure PostgreSQL and set `AUTH_ENABLED=true` with a
random `AUTH_JWT_SECRET_KEY` of at least 32 characters. For example, generate a
secret locally with `python -c "import secrets; print(secrets.token_urlsafe(48))"`
and store it only in the environment or secret manager. Do not commit it.

The v1 routes are under `/api/v1/auth`: registration, password login, mobile
OTP request/verification, token refresh and logout, current-user/profile,
password reset/change, and email/mobile verification. Public registration
always creates `USER`. The `create-admin` command bootstraps the first
`SUPER_ADMIN` under a PostgreSQL advisory lock. It is safe to rerun for that
same active account and never upgrades an existing account.

The protected `/api/v1/admin` routes provide user search and pagination,
account updates, role assignment, activation, session revocation, activity,
and audit history. `ADMIN` can manage ordinary users; only `SUPER_ADMIN` can
assign or manage administrative roles. Administrative role and status changes
revoke sessions and increment the account token version. The last active
`SUPER_ADMIN` cannot be demoted or deactivated. Audit rows are written in the
same transaction as sensitive changes and exposed read-only through the API.

Email, SMS, and S3 are independently enabled with `AUTH_EMAIL_DELIVERY_ENABLED`,
`AUTH_SMS_DELIVERY_ENABLED`, and `PROFILE_IMAGE_STORAGE_ENABLED`. Configure
`AWS_REGION` and only the identity each enabled service needs. Boto3 uses the
standard credential provider chain (environment, shared profiles, container
credentials, or an instance/task role); do not add access keys to application
settings or source control. On a workstation, use `aws configure --profile
<profile>` and `AWS_PROFILE=<profile>` (or the normal AWS environment variables).
When a feature is disabled, its API fails closed and does not claim work succeeded.

S3 objects are private. Authenticated clients create an upload form through
`POST /api/v1/auth/files/uploads`, upload directly to S3, then call
`POST /api/v1/auth/files/{upload_id}/complete`. The API records owner metadata,
checks object existence, size, declared type and content signature, then exposes
short-lived owner-only download URLs. Profile images accept JPEG, PNG, and WebP;
generic uploads accept those image types, PDF, and UTF-8 text. The configured
`AWS_S3_MAX_UPLOAD_BYTES` applies to presigned POST conditions and verification.
Configure bucket CORS for your exact web origins with `POST` and the headers
returned in the presigned form. Keep Block Public Access enabled and do not add
public ACLs. Grant the runtime role `s3:PutObject`, `s3:GetObject`, and
`s3:DeleteObject` only for the application key prefix. The existence check also
needs `s3:ListBucket` on this bucket restricted by the `s3:prefix` condition to
`users/*`; do not grant unrestricted bucket listing.

For example, replace the origin below with the deployed frontend origin (and
add a separate exact origin for local development):

```json
[
  {
    "AllowedOrigins": ["https://app.example.com"],
    "AllowedMethods": ["POST"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 300
  }
]
```

For SES v2, verify the sender identity in the selected region and set
`AWS_SES_FROM_EMAIL` to that identity. New SES accounts are commonly in the
sandbox: verify recipient identities too, or request production access before
sending to arbitrary users. Configure `AUTH_PUBLIC_BASE_URL` for your frontend's
action-token handler. Tokens are placed in the URL fragment; the frontend should
read the fragment and POST the token to the existing verification or password
reset endpoint, then remove it from browser history. Grant the runtime role
`ses:SendEmail` for the verified identity. Delivery submission failures are
returned as safe service errors; raw provider details and tokens are not logged
or returned.

For mobile OTP, set `AWS_SMS_ORIGINATION_IDENTITY` to the approved origination
identity for your destination countries. AWS End User Messaging SMS may require
sender registration, phone-number registration, country-specific permissions,
and production access. Grant `sms-voice:SendTextMessage` only for the approved
origination identity. OTP destinations must be E.164 numbers.

Tests inject mocked AWS clients and never send real messages or upload objects.
For an optional local smoke test, use a dedicated AWS profile, a non-production
bucket and verified SES/SMS identities, keep test numbers controlled, and remove
the temporary profile and objects afterward.

Apply the checked-in auth, file metadata, and audit revisions with
`alembic upgrade head`. Create future revisions with
`alembic revision --autogenerate -m "describe change"`;
review generated SQL before upgrade. Roll back one revision with
`alembic downgrade -1`. Migrations are never run during API startup.

To create the first administrator, configure `ENABLE_POSTGRES=true` and
`POSTGRES_URL`, then run `python -m app.modules.auth.cli` (or the installed
`create-admin` command). Provide `ADMIN_EMAIL` and
`ADMIN_USERNAME` in the environment or enter them at the prompts. `ADMIN_PASSWORD`
may be provided by an environment secret; otherwise the CLI requests it without
echoing. No default admin account or password exists.

### Background notifications and scheduled work

The API writes notification requests into the encrypted PostgreSQL outbox in
the same transaction as OTP challenges and email action tokens. API responses
report `pending`; they do not claim that SES or SMS delivery has completed.
Celery workers claim and deliver jobs, and Beat dispatches pending rows and
schedules bounded cleanup. Outbox idempotency keys prevent duplicate job rows;
worker leases prevent ordinary duplicate publications from sending twice.
Delivery is retried with capped exponential backoff and jitter for transient
AWS failures. A process crash after a provider accepts a message but before the
database records completion can still result in a duplicate; SES and SMS do not
offer a shared transaction with PostgreSQL.

Generate a Fernet key and keep it in the local `.env` or a secret manager:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set `BACKGROUND_PAYLOAD_ENCRYPTION_KEY`, `BACKGROUND_JOBS_ENABLED=true`, and
the host `REDIS_URL=redis://localhost:6379/0`. Enable the desired email or SMS
feature flags only after configuring their AWS identities. The Compose services
use `REDIS_DOCKER_URL=redis://redis:6379/0`; Redis remains on the private Compose
network and is not published on a host port.

Apply migrations before starting services, then start the separate processes:

```bash
alembic upgrade head
docker compose up -d postgres redis
docker compose up -d api worker beat
docker compose ps
```

For local Windows development, start Redis and PostgreSQL first, then run the
worker with Celery's `solo` pool and start Beat in another terminal:

```powershell
$env:BACKGROUND_JOBS_ENABLED = "true"
celery -A app.worker.celery_app:celery_app worker --pool=solo --loglevel=INFO
celery -A app.worker.celery_app:celery_app beat --loglevel=INFO
```

Check worker availability with `celery -A app.worker.celery_app:celery_app
inspect ping`; view service failures with `docker compose logs -f worker beat`.
If outbox rows remain pending, check Redis connectivity and Beat logs. If rows
remain processing, check worker health and lease recovery logs. Do not rotate the
outbox encryption key while pending jobs remain, or those payloads cannot be
decrypted. Production Redis should use private networking, authentication, and
TLS; local Compose intentionally keeps it private to its bridge network.

## 🧪 Testing

Run the complete test suite:

```bash
pytest
```

Run only unit tests:

```bash
pytest tests/unit
```

Run API tests:

```bash
pytest tests/api
```

Run integration tests:

```bash
pytest tests/integration
```

Run contract tests:

```bash
pytest tests/contract
```

Run end-to-end tests:

```bash
pytest tests/e2e
```

Run a specific test file:

```bash
pytest tests/api/test_health.py
```

Generate coverage:

```bash
pytest --cov=app --cov-report=term-missing
```

Generate HTML coverage:

```bash
pytest --cov=app --cov-report=html
```

The detailed testing strategy is documented in:

```text
TESTING.md
```

---

## ✅ Code Quality

### Format

```bash
ruff format .
```

### Lint

```bash
ruff check .
```

### Automatically fix safe issues

```bash
ruff check . --fix
```

### Type checking

```bash
mypy app
```

### Dependency security audit

```bash
pip-audit
```

### Recommended local validation

```bash
ruff format .
ruff check .
mypy app
pytest
```

---

## 📋 Development Scripts

Available scripts:

```text
scripts/
├── start.sh
├── lint.sh
└── test.sh
```

Typical usage:

```bash
./scripts/start.sh
./scripts/lint.sh
./scripts/test.sh
```

On Windows, execute the equivalent Uvicorn, Ruff, mypy, and pytest commands
directly when Bash is unavailable.

---

## 📝 Logging

Use the shared logging factory:

```python
from app.core.logging import get_logger


logger = get_logger(__name__)
```

Example:

```python
logger.info(
    "Product created successfully",
    extra={
        "product_id": product_id,
    },
)
```

Never log:

* database passwords,
* complete database URLs,
* access tokens,
* authorization headers,
* private file URLs,
* medical data,
* personal information,
* unsanitized request bodies.

Request-specific information should be propagated through the shared request
context.

---

## 🔐 Security

The project supports production security practices such as:

* non-root Docker execution,
* environment-based secret injection,
* request size limits,
* CORS configuration,
* secure response headers,
* explicit proxy trust,
* strict input validation,
* standardized error handling,
* secret-safe logging,
* external database configuration.

Authentication and authorization should normally be handled by the platform's
authentication service and API Gateway.

Internal identity headers may include:

```text
X-User-ID
X-User-Role
X-Request-ID
X-Correlation-ID
```

These headers must only be trusted when the service is protected by the gateway
and private network controls.

---

## 🧵 Background Worker Support

The project contains a future-ready worker structure:

```text
app/worker/
├── modules/
├── tasks/
├── beat.py
├── celery_app.py
├── config.py
├── lifecycle.py
├── routing.py
└── signals.py
```

Background jobs are optional and disabled by default. When enabled, FastAPI,
the Celery worker, and Beat scheduler run as separate processes.

When enabled:

* Celery runs as a separate process or container,
* FastAPI does not start Celery,
* worker task entry points remain thin,
* business logic lives in worker services,
* each worker child owns its own database registry,
* database engines are created after process fork,
* Beat schedules remain declarative.

---

## 📚 Documentation

| Document          | Description                                  |
| ----------------- | -------------------------------------------- |
| `README.md`       | Project overview and quick start             |
| `ARCHITECTURE.md` | Architecture, boundaries, and runtime design |
| `STRUCTURE.md`    | Folder and file responsibilities             |
| `DEVELOPMENT.md`  | Local development and contribution workflow  |
| `TESTING.md`      | Testing strategy and conventions             |

---

## 🚦 Recommended New-Service Workflow

When creating a new microservice from this template:

1. rename the project metadata,
2. update `PROJECT_NAME`,
3. update `.env.example`,
4. configure the external database URL,
5. remove or replace the example module,
6. map the required database tables,
7. create domain schemas,
8. implement repositories,
9. implement application services,
10. expose API routes,
11. add tests,
12. update documentation,
13. build and run the Docker image.

---

## 🧭 Architectural Guardrails

1. Routers remain thin.
2. Services contain business workflows.
3. Repositories contain persistence logic.
4. Unit of Work owns transactions.
5. Database adapters own engines and pools.
6. Configuration remains centralized.
7. API fields use camelCase.
8. Python code uses snake_case.
9. Database schema changes remain outside business services.
10. Optional integrations remain optional.
11. FastAPI never starts Celery.
12. Database sessions are never shared across requests.
13. Worker children never reuse parent process pools.
14. Secrets are never exposed in logs or responses.
15. Tests follow the same layer boundaries as production code.

---

<div align="center">

## 💡 Built for Consistent Python Microservices

**Explicit architecture creates maintainable systems.**

</div>
