<div align="center">

# 🗂️ Project Structure Guide

### Folder and File Responsibilities

<p>
  <img src="https://img.shields.io/badge/Structure-Modular-845EF7" alt="Modular Structure">
  <img src="https://img.shields.io/badge/Design-Explicit-12B886" alt="Explicit Design">
  <img src="https://img.shields.io/badge/Scope-Microservices-228BE6" alt="Microservices">
  <img src="https://img.shields.io/badge/Runtime-FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI">
</p>

<p>
A complete guide to the responsibility, ownership, and placement rules for every
folder and file in the FastAPI microservice foundation.
</p>

</div>

---

## 📌 1. Purpose

This document explains the project structure and defines where each type of code
belongs.

The structure is designed to keep:

* HTTP transport logic,
* business workflows,
* persistence logic,
* transaction handling,
* configuration,
* logging,
* database infrastructure,
* optional workers,
* tests,
* deployment files,

clearly separated.

The primary dependency flow is:

```text
Router
    ↓
Service
    ↓
Repository
    ↓
Unit of Work
    ↓
Database Adapter
```

Each file should have one clear reason to change.

---

## 🌳 2. Complete Project Structure

```text
fastapi_project_structure/
├── app/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   └── router.py
│   │   ├── __init__.py
│   │   ├── dependencies.py
│   │   ├── exception_handlers.py
│   │   ├── health.py
│   │   └── router.py
│   ├── common/
│   │   ├── __init__.py
│   │   ├── exceptions.py
│   │   ├── execution.py
│   │   ├── filters.py
│   │   ├── pagination.py
│   │   ├── response.py
│   │   └── sorting.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── constants.py
│   │   ├── lifespan.py
│   │   ├── logging.py
│   │   ├── middleware.py
│   │   └── request_context.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── mongo.py
│   │   ├── mssql.py
│   │   ├── mysql.py
│   │   ├── postgres.py
│   │   ├── redis_client.py
│   │   ├── registry.py
│   │   ├── sqlalchemy_types.py
│   │   └── uow.py
│   ├── modules/
│   │   ├── example/
│   │   │   ├── __init__.py
│   │   │   ├── dependencies.py
│   │   │   ├── models.py
│   │   │   ├── openapi.py
│   │   │   ├── repository.py
│   │   │   ├── router.py
│   │   │   ├── schemas.py
│   │   │   └── service.py
│   │   └── __init__.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── datetime_utils.py
│   │   ├── debug.py
│   │   └── id_utils.py
│   ├── worker/
│   │   ├── modules/
│   │   │   ├── dummy_modules/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── schemas.py
│   │   │   │   └── service.py
│   │   │   └── __init__.py
│   │   ├── tasks/
│   │   │   ├── __init__.py
│   │   │   └── dummy_task.py
│   │   ├── __init__.py
│   │   ├── beat.py
│   │   ├── celery_app.py
│   │   ├── config.py
│   │   ├── lifecycle.py
│   │   ├── routing.py
│   │   └── signals.py
│   ├── __init__.py
│   └── main.py
├── cicd/
│   └── Jenkinsfile
├── docs/
├── scripts/
│   ├── lint.sh
│   ├── start.sh
│   └── test.sh
├── tests/
│   ├── api/
│   │   ├── __init__.py
│   │   └── test_health.py
│   ├── contract/
│   │   ├── __init__.py
│   │   └── test_openapi.py
│   ├── e2e/
│   │   ├── __init__.py
│   │   └── test_service.py
│   ├── integration/
│   │   ├── __init__.py
│   │   └── test_database.py
│   ├── unit/
│   │   ├── __init__.py
│   │   └── test_common.py
│   ├── __init__.py
│   └── conftest.py
├── .dockerignore
├── .env.example
├── .gitignore
├── ARCHITECTURE.md
├── DEVELOPMENT.md
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── README.md
├── requirements-dev.txt
├── requirements.txt
├── STRUCTURE.md
└── TESTING.md
```

---

## 📦 3. `app/`

The `app` package contains all application runtime code.

```text
app/
├── api/
├── common/
├── core/
├── db/
├── modules/
├── utils/
├── worker/
├── __init__.py
└── main.py
```

### Responsibility

The `app` package owns:

* application startup,
* API routing,
* middleware,
* configuration,
* database access,
* domain modules,
* shared utilities,
* optional background worker infrastructure.

It should not contain:

* CI pipeline files,
* deployment-only scripts,
* project documentation,
* test code,
* local environment files.

---

## 🚀 4. `app/main.py`

```text
app/main.py
```

This is the FastAPI application composition root.

### Responsibilities

`main.py` should:

* create the FastAPI application,
* register the application lifespan,
* register middleware,
* register exception handlers,
* include root API routers,
* configure OpenAPI metadata,
* expose the `app` object used by Uvicorn.

### It Should Not

`main.py` should not:

* contain business logic,
* execute SQL queries,
* create module-specific repositories,
* manually open database sessions,
* start Celery,
* start Celery Beat,
* run migrations.

### Expected Runtime Entry Point

```text
app.main:app
```

Example Docker command:

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 🌐 5. `app/api/`

The `api` package contains shared HTTP composition and cross-module API concerns.

```text
app/api/
├── v1/
├── __init__.py
├── dependencies.py
├── exception_handlers.py
├── health.py
└── router.py
```

---

## 🧭 6. `app/api/router.py`

The root API router.

### Responsibilities

* include health routes,
* include versioned API routers,
* define shared tags,
* define global prefixes where required,
* keep API composition centralized.

Example:

```python
api_router.include_router(
    health_router,
)

api_router.include_router(
    v1_router,
    prefix="/api/v1",
)
```

The file should not import repositories or services directly.

---

## 🔢 7. `app/api/v1/`

Version-specific API composition.

```text
app/api/v1/
├── __init__.py
└── router.py
```

### `router.py`

This file aggregates all version 1 business routers.

Example:

```python
v1_router.include_router(
    product_router,
    prefix="/products",
    tags=["Products"],
)
```

### Purpose

Versioned routing allows:

* backward compatibility,
* controlled deprecation,
* gradual API evolution,
* stable external contracts.

Module routers should not define `/api/v1` themselves.

---

## 🔌 8. `app/api/dependencies.py`

Shared FastAPI dependency providers.

### Responsibilities

This file may expose:

* application settings,
* database registry,
* MySQL adapter,
* Unit of Work,
* trusted request identity,
* request and correlation context.

### Example Dependency Flow

```mermaid
flowchart TD
    Settings[AppSettings]
    Registry[Database Registry]
    MySQL[MySQL Adapter]
    UOW[Unit of Work]
    Router[FastAPI Router]

    Settings --> Registry
    Registry --> MySQL
    MySQL --> UOW
    UOW --> Router
```

### Placement Rule

Use this file for dependencies shared across multiple modules.

Module-specific repository and service providers belong in:

```text
app/modules/<module_name>/dependencies.py
```

---

## ⚠️ 9. `app/api/exception_handlers.py`

Centralized API exception mapping.

### Responsibilities

* handle application exceptions,
* handle FastAPI validation errors,
* handle Starlette HTTP exceptions,
* handle unexpected exceptions,
* produce the standard error envelope,
* log internal failures safely.

### It Should Not

* expose raw SQL errors,
* expose stack traces,
* expose secrets,
* contain business validation rules,
* duplicate exception classes.

Exception classes belong in:

```text
app/common/exceptions.py
```

---

## ❤️ 10. `app/api/health.py`

Health and operational endpoints.

Recommended routes:

```text
GET /health
GET /health/live
GET /health/ready
```

### Responsibilities

#### `/health/live`

Checks whether the FastAPI process can respond.

#### `/health/ready`

Checks whether required infrastructure is available.

#### `/health`

Returns an overall service health summary.

### Rules

Liveness should remain lightweight.

Readiness may check:

* MySQL connectivity,
* registry initialization,
* required settings,
* mandatory application state.

---

## 🧰 11. `app/common/`

Reusable application primitives that are not tied to a specific domain.

```text
app/common/
├── __init__.py
├── exceptions.py
├── execution.py
├── filters.py
├── pagination.py
├── response.py
└── sorting.py
```

---

## ❗ 12. `app/common/exceptions.py`

Shared application exception hierarchy.

### Typical Exceptions

* `ApplicationError`
* `ValidationError`
* `ResourceNotFoundError`
* `ResourceConflictError`
* `InvalidOperationError`
* `InfrastructureUnavailableError`

### Responsibilities

* define stable machine-readable error codes,
* define safe client-facing messages,
* carry optional structured details,
* remain independent of FastAPI.

### Rule

Exceptions should represent application meaning, not transport details.

Bad:

```python
raise HTTPException(
    status_code=404,
)
```

inside a repository.

Better:

```python
raise ResourceNotFoundError(
    message="Product was not found",
)
```

The API handler converts it into an HTTP response.

---

## ⚙️ 13. `app/common/execution.py`

Reusable execution helpers.

Possible responsibilities:

* safe retry helpers,
* timeout wrappers,
* controlled concurrency,
* operation timing,
* exception translation,
* async utility execution.

### Guardrail

Do not hide business workflows inside generic execution helpers.

This file should support services, not replace them.

---

## 🔍 14. `app/common/filters.py`

Reusable filter definitions and normalization.

### Responsibilities

* define base filter schemas,
* normalize blank values,
* validate date ranges,
* validate numeric ranges,
* convert external aliases,
* support safe query construction.

### Rule

Filter schemas describe input.

Repositories decide how validated filters map to database expressions.

---

## 📄 15. `app/common/pagination.py`

Shared pagination primitives.

### Responsibilities

* validate `page`,
* validate `pageSize`,
* enforce maximum page size,
* calculate offsets,
* calculate total pages,
* generate pagination metadata.

Recommended external response:

```json
{
  "page": 1,
  "pageSize": 20,
  "totalItems": 100,
  "totalPages": 5,
  "hasNext": true,
  "hasPrevious": false
}
```

---

## ↕️ 16. `app/common/sorting.py`

Safe sorting definitions.

### Responsibilities

* validate sort direction,
* normalize external sort names,
* support allowed-field mappings,
* reject unsupported fields.

### Security Rule

Never insert raw client-provided sort values into SQL.

Bad:

```python
statement.order_by(text(sort_by))
```

Better:

```python
sort_column = SORTABLE_FIELDS[sort_by]
```

---

## 📦 17. `app/common/response.py`

Shared API response models.

### Responsibilities

* define success envelopes,
* define error envelopes,
* define metadata models,
* serialize external fields using camelCase.

Successful response:

```json
{
  "success": true,
  "message": "Products retrieved successfully",
  "data": [],
  "meta": null
}
```

Error response:

```json
{
  "success": false,
  "message": "Product was not found",
  "data": null,
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "details": null
  }
}
```

---

## 🧠 18. `app/core/`

Application-wide runtime infrastructure.

```text
app/core/
├── __init__.py
├── config.py
├── constants.py
├── lifespan.py
├── logging.py
├── middleware.py
└── request_context.py
```

---

## ⚙️ 19. `app/core/config.py`

Single validated configuration source.

### Responsibilities

* application metadata,
* environment selection,
* server settings,
* CORS settings,
* security settings,
* logging settings,
* health settings,
* SQLAlchemy pool settings,
* MySQL settings,
* environment-specific validation,
* derived configuration helpers.

### Rules

* environment variables use `UPPER_SNAKE_CASE`,
* secrets are never logged,
* optional integrations validate only when enabled,
* production validation fails fast,
* direct `os.environ` reads are avoided elsewhere.

---

## 📌 20. `app/core/constants.py`

Stable constants that are not deployment configuration.

Examples:

```text
DEFAULT_PAGE_SIZE
MAX_PAGE_SIZE
REQUEST_ID_HEADER
CORRELATION_ID_HEADER
```

### Do Not Store

* secrets,
* database URLs,
* environment-specific hosts,
* credentials,
* deployment-specific values.

Those belong in `config.py`.

---

## 🌱 21. `app/core/lifespan.py`

FastAPI startup and shutdown lifecycle.

### Startup Responsibilities

* initialize logging,
* load settings,
* create database registry,
* validate required adapters,
* attach resources to application state,
* log successful startup.

### Shutdown Responsibilities

* close database adapters,
* dispose engines,
* close clients,
* flush logging,
* log shutdown completion.

### Rule

FastAPI lifecycle should not initialize Celery worker infrastructure.

---

## 📝 22. `app/core/logging.py`

Shared structured logging pipeline.

### Responsibilities

* configure console logging,
* optionally configure JSON logs,
* optionally configure file logs,
* attach request context,
* format exceptions,
* safely shut down logging resources.

### Logging Fields

Recommended:

```text
timestamp
level
logger
message
service
environment
request_id
correlation_id
user_id
route
method
duration_ms
```

---

## 🛡️ 23. `app/core/middleware.py`

Cross-cutting HTTP middleware.

### Possible Responsibilities

* request ID generation,
* correlation ID propagation,
* access logging,
* request timing,
* request size limits,
* secure headers,
* trusted proxy handling,
* CORS registration.

### It Should Not

* implement domain authorization,
* query business tables,
* open transactions,
* contain module-specific logic.

---

## 🧬 24. `app/core/request_context.py`

Context-local request metadata.

### Responsibilities

* store request ID,
* store correlation ID,
* store trusted user ID,
* store trusted user role,
* expose safe getter functions,
* clear context after each request.

### Implementation

Use `contextvars`.

Do not use mutable global dictionaries for request-specific state.

---

## 🗄️ 25. `app/db/`

Database and transaction infrastructure.

```text
app/db/
├── __init__.py
├── base.py
├── mongo.py
├── mssql.py
├── mysql.py
├── postgres.py
├── redis_client.py
├── registry.py
├── sqlalchemy_types.py
└── uow.py
```

---

## 🧱 26. `app/db/base.py`

Shared database interfaces and abstractions.

Possible contents:

* adapter protocols,
* health result types,
* common database exceptions,
* lifecycle contracts,
* shared type aliases.

The file should remain independent of domain models.

---

## 🐬 27. `app/db/mysql.py`

Active asynchronous MySQL adapter.

### Responsibilities

* create `AsyncEngine`,
* configure connection pooling,
* create `async_sessionmaker`,
* validate connectivity,
* expose the engine,
* expose the session factory,
* dispose the engine during shutdown.

Expected URL:

```text
mysql+asyncmy://username:password@hostname:3306/database_name
```

### It Should Not

* contain product queries,
* define business repositories,
* commit application workflows,
* run migrations.

---

## 🐘 28. `app/db/postgres.py`

Disabled PostgreSQL reference adapter.

### Activation Requirements

1. install `asyncpg`,
2. enable PostgreSQL settings,
3. enable registry integration,
4. add dependency providers,
5. add readiness checks,
6. add integration tests.

Expected URL:

```text
postgresql+asyncpg://username:password@hostname:5432/database_name
```

---

## 🪟 29. `app/db/mssql.py`

Disabled Microsoft SQL Server adapter.

### Activation Requirements

1. install `aioodbc`,
2. install `pyodbc`,
3. install Microsoft ODBC Driver 18,
4. enable settings,
5. enable registry integration,
6. add tests.

Example URL:

```text
mssql+aioodbc://username:password@hostname:1433/database_name
```

---

## 🍃 30. `app/db/mongo.py`

Disabled MongoDB adapter.

### Responsibilities When Enabled

* create async MongoDB client,
* validate connectivity,
* expose database handles,
* close client during shutdown,
* support readiness checks.

### Rule

MongoDB clients must not be created when MongoDB is disabled.

---

## 🔴 31. `app/db/redis_client.py`

Disabled Redis adapter.

Potential future uses:

* caching,
* distributed locks,
* idempotency keys,
* rate limiting,
* Celery broker,
* Celery result backend.

### Activation Requirements

* install Redis package,
* define key prefix strategy,
* configure timeouts,
* configure retry behavior,
* enable lifecycle,
* add readiness checks,
* add integration tests.

---

## 🗂️ 32. `app/db/registry.py`

Central infrastructure adapter registry.

### Responsibilities

* create enabled adapters,
* expose enabled adapters,
* report adapter names,
* validate health,
* close all adapters.

### Active State

Currently:

```text
MySQL: enabled
PostgreSQL: disabled
MSSQL: disabled
MongoDB: disabled
Redis: disabled
```

---

## 🧪 33. `app/db/sqlalchemy_types.py`

Reusable SQLAlchemy type helpers.

Possible contents:

* UTC-aware datetime type,
* custom boolean conversion,
* dialect-safe JSON handling,
* reusable enum helpers,
* database-specific normalization.

### Rule

Only add custom types when the database schema requires them.

Avoid unnecessary abstraction over built-in SQLAlchemy types.

---

## 🔁 34. `app/db/uow.py`

Unit of Work implementation.

### Responsibilities

* create one session per use case,
* begin a transaction,
* expose the session,
* commit,
* roll back,
* close the session,
* support async context management.

### Rule

Repositories should not commit independently.

The Unit of Work owns the transaction boundary.

---

## 🧩 35. `app/modules/`

Business-domain modules.

```text
app/modules/
├── example/
└── __init__.py
```

Each module should represent one cohesive business capability.

Examples:

```text
products
inventory
warehouses
orders
payments
notifications
```

Avoid creating modules based only on technical layers.

---

## 📘 36. `app/modules/example/`

Reference domain module.

```text
app/modules/example/
├── __init__.py
├── dependencies.py
├── models.py
├── openapi.py
├── repository.py
├── router.py
├── schemas.py
└── service.py
```

The example module demonstrates the expected structure for new business modules.

It should eventually be:

* replaced by a real domain module,
* renamed,
* or removed after the team understands the pattern.

---

## 🗃️ 37. `models.py`

SQLAlchemy ORM mappings.

### Responsibilities

* map existing tables,
* map column names exactly,
* map constraints,
* map indexes,
* map foreign keys,
* define relationships where required,
* expose typed ORM attributes.

### Rules

* database identifiers remain snake_case,
* models must reflect the source schema,
* avoid migration logic,
* avoid API schemas in this file,
* avoid business workflows.

---

## 🧾 38. `schemas.py`

Pydantic request and response schemas.

### Responsibilities

* validate request payloads,
* validate query data,
* serialize responses,
* expose external camelCase aliases,
* support ORM-to-response mapping.

### Naming Examples

```text
CreateProductRequest
UpdateProductRequest
ProductResponse
ProductListResponse
```

### Boundary Rule

```text
External API fields
    camelCase

Python fields
    snake_case
```

---

## 🗄️ 39. `repository.py`

Module-specific persistence operations.

### Responsibilities

* create SQLAlchemy statements,
* query ORM models,
* apply filters,
* apply sorting,
* apply pagination,
* insert and update records,
* perform safe locking,
* return mapped persistence data.

### It Should Not

* produce HTTP responses,
* contain FastAPI dependencies,
* commit transactions,
* implement complete workflows.

---

## 🧠 40. `service.py`

Business use cases and workflows.

### Responsibilities

* validate business rules,
* coordinate repositories,
* control transaction intent,
* enforce state transitions,
* map output schemas,
* raise application exceptions.

### Example

```text
Validate product
    ↓
Check duplicate code
    ↓
Create product
    ↓
Create inventory record
    ↓
Commit transaction
```

---

## 🔌 41. `dependencies.py`

Module-specific dependency providers.

### Responsibilities

* create repositories,
* create services,
* inject Unit of Work,
* expose typed dependency aliases.

Example:

```python
ProductServiceDep = Annotated[
    ProductService,
    Depends(get_product_service),
]
```

### Rule

Do not instantiate long-lived infrastructure directly here.

Reuse global registry and adapter dependencies.

---

## 🌐 42. `router.py`

Module-specific FastAPI routes.

### Responsibilities

* define HTTP paths,
* accept validated schemas,
* inject services,
* return standard responses,
* attach module OpenAPI metadata.

### Rule

Routers remain thin.

---

## 📖 43. `openapi.py`

Module-specific OpenAPI metadata.

### Responsibilities

* summaries,
* descriptions,
* operation IDs,
* response metadata,
* request examples,
* deprecation markers.

This keeps router declarations compact and readable.

---

## 🧰 44. `app/utils/`

Small, reusable, domain-neutral helpers.

```text
app/utils/
├── __init__.py
├── datetime_utils.py
├── debug.py
└── id_utils.py
```

Utilities should be:

* small,
* pure where possible,
* independently testable,
* free from business-specific dependencies.

---

## 🕒 45. `datetime_utils.py`

Date and time helpers.

Possible responsibilities:

* UTC normalization,
* timezone conversion,
* ISO serialization,
* safe date parsing,
* date range helpers.

### Rule

Prefer timezone-aware datetimes.

---

## 🐞 46. `debug.py`

Development-only debug output.

### Rules

Debug output should:

* run only in development,
* require `DEBUG=true`,
* use `print(..., flush=True)`,
* never print secrets,
* never print medical data,
* remain disabled in production.

Production code should use structured logging.

---

## 🆔 47. `id_utils.py`

Identifier helpers.

Possible responsibilities:

* UUID generation,
* request ID generation,
* correlation ID generation,
* identifier normalization,
* safe validation.

---

## 🧵 48. `app/worker/`

Optional background worker infrastructure.

```text
app/worker/
├── modules/
├── tasks/
├── __init__.py
├── beat.py
├── celery_app.py
├── config.py
├── lifecycle.py
├── routing.py
└── signals.py
```

Celery is currently disabled.

The FastAPI process must not start worker infrastructure.

---

## ⚙️ 49. `app/worker/config.py`

Immutable Celery worker configuration.

### Responsibilities When Enabled

* normalize Celery settings,
* validate worker configuration,
* expose Celery-compatible values,
* avoid connecting to any broker.

---

## 🧭 50. `app/worker/routing.py`

Queue declarations and task routing.

### Responsibilities

* define exchanges,
* define queues,
* define routing keys,
* map tasks to queues,
* validate route targets.

### Rule

Do not create one queue per task.

Queues should represent execution characteristics.

---

## ⏰ 51. `app/worker/beat.py`

Declarative periodic schedule configuration.

### Responsibilities

* define stable schedule names,
* define task names,
* define schedule expressions,
* route scheduled tasks,
* validate schedule structure.

Business logic must not live in Beat configuration.

---

## 🔄 52. `app/worker/lifecycle.py`

Worker-child asynchronous runtime.

### Responsibilities When Enabled

Each worker child owns:

* one async event loop thread,
* one process-local database registry,
* its own database engines,
* its own connection pools,
* graceful shutdown.

### Rule

Never reuse database pools created before process fork.

---

## 📡 53. `app/worker/signals.py`

Celery signal registration.

### Responsibilities

* configure worker logging,
* validate parent worker startup,
* initialize child process resources,
* shut down child resources,
* perform final best-effort cleanup.

Signal handlers should remain independently testable.

---

## 🚀 54. `app/worker/celery_app.py`

Celery application factory.

### Responsibilities When Enabled

* create Celery application,
* apply worker configuration,
* register queues,
* register routes,
* register Beat schedules,
* register task modules,
* register lifecycle signals.

### Rule

This file should be activated last.

---

## 📨 55. `app/worker/tasks/`

Thin Celery task entry points.

```text
app/worker/tasks/
├── __init__.py
└── dummy_task.py
```

### A Task Should

* accept serializable arguments,
* establish task context,
* invoke a worker service,
* define retry behavior,
* return serializable output.

### A Task Should Not

* contain large business workflows,
* create global sessions,
* embed SQL queries,
* pass ORM objects,
* start event loops per invocation.

---

## 🧠 56. `app/worker/modules/`

Worker-specific business workflows.

```text
app/worker/modules/
└── dummy_modules/
    ├── __init__.py
    ├── repository.py
    ├── schemas.py
    └── service.py
```

### Purpose

Background workflows may require:

* dedicated schemas,
* repositories,
* services,
* retry-safe logic,
* idempotency.

Worker module services contain the actual background business logic.

---

## 🧪 57. `tests/`

Test code organized by confidence level.

```text
tests/
├── api/
├── contract/
├── e2e/
├── integration/
├── unit/
├── __init__.py
└── conftest.py
```

---

## ⚡ 58. `tests/unit/`

Fast isolated tests.

### Tests

* services,
* utilities,
* validation,
* pagination,
* sorting,
* configuration,
* exceptions.

### Must Not Require

* real database,
* network access,
* Docker,
* Celery broker,
* Redis.

---

## 🌐 59. `tests/api/`

FastAPI route tests.

### Tests

* status codes,
* request validation,
* response envelopes,
* headers,
* middleware,
* health routes,
* dependency overrides.

---

## 🔗 60. `tests/integration/`

Infrastructure integration tests.

### Tests

* database adapters,
* repositories,
* transactions,
* connection lifecycle,
* readiness behavior.

Integration tests should use a dedicated test database.

---

## 📜 61. `tests/contract/`

External contract tests.

### Tests

* OpenAPI paths,
* operation IDs,
* schema field names,
* camelCase aliases,
* error envelopes,
* endpoint stability.

---

## 🌍 62. `tests/e2e/`

Complete service workflow tests.

### Purpose

Verify multiple layers together:

```text
API
    ↓
Service
    ↓
Repository
    ↓
Database
```

Use these tests sparingly because they are slower.

---

## 🧰 63. `tests/conftest.py`

Shared pytest fixtures.

Possible fixtures:

* test application,
* test settings,
* async HTTP client,
* fake repositories,
* fake Unit of Work,
* database session,
* request headers,
* deterministic IDs.

Keep fixtures focused and predictable.

---

## 📜 64. `scripts/`

Developer and CI helper scripts.

```text
scripts/
├── lint.sh
├── start.sh
└── test.sh
```

### `start.sh`

Starts the local FastAPI service.

### `lint.sh`

Runs:

* Ruff formatting check,
* Ruff linting,
* mypy.

### `test.sh`

Runs:

* pytest,
* coverage,
* selected test categories.

Scripts should fail immediately when a command fails.

---

## 🔁 65. `cicd/`

Continuous integration and deployment definitions.

```text
cicd/
└── Jenkinsfile
```

Recommended pipeline stages:

1. checkout,
2. install Python,
3. install dependencies,
4. format check,
5. lint,
6. type check,
7. unit tests,
8. API tests,
9. contract tests,
10. integration tests,
11. security audit,
12. Docker build,
13. deployment.

---

## 📚 66. `docs/`

Additional technical documentation.

Possible future files:

```text
docs/
├── API_GUIDE.md
├── DATABASE_MAPPING.md
├── DEPLOYMENT.md
├── ERROR_CODES.md
├── OBSERVABILITY.md
└── SECURITY.md
```

Root-level documentation should remain limited to the most important project guides.

---

## 🐳 67. `Dockerfile`

Builds the FastAPI service image.

### Responsibilities

* use Python 3.12 slim image,
* install runtime dependencies,
* copy application source,
* run as non-root user,
* expose the API port,
* configure liveness health check,
* start Uvicorn.

### It Does Not

* start MySQL,
* start Redis,
* start Celery,
* start Beat,
* run migrations.

---

## 🐳 68. `docker-compose.yml`

Runs only the FastAPI service.

### Responsibilities

* build the image,
* load `.env`,
* publish the API port,
* configure health checks,
* configure restart policy,
* apply resource limits,
* configure logging.

External infrastructure is configured through environment URLs.

---

## 📦 69. `pyproject.toml`

Project metadata and Python tool configuration.

### Contains

* project metadata,
* Python version,
* setuptools configuration,
* pytest configuration,
* coverage configuration,
* Ruff configuration,
* mypy configuration.

---

## 📋 70. `requirements.txt`

Authoritative production dependency manifest.

Active packages include:

* FastAPI,
* Uvicorn,
* Pydantic,
* SQLAlchemy,
* asyncmy,
* structured logging.

Optional database and worker packages remain commented.

---

## 🧪 71. `requirements-dev.txt`

Development dependency file.

Includes:

```text
-r requirements.txt
```

and adds:

* pytest,
* pytest-asyncio,
* HTTPX,
* coverage,
* Ruff,
* mypy,
* pip-audit,
* pre-commit,
* debugging tools.

---

## 🔐 72. `.env.example`

Documents supported environment variables.

### Rules

* no real credentials,
* no private URLs,
* safe placeholder values,
* clear comments,
* disabled optional integrations remain commented.

Developers copy it to:

```text
.env
```

---

## 🚫 73. `.gitignore`

Excludes:

* virtual environments,
* cache files,
* test output,
* coverage output,
* local environment files,
* IDE files,
* build output,
* logs,
* temporary files.

---

## 📦 74. `.dockerignore`

Reduces Docker build context.

Excludes:

* Git metadata,
* virtual environments,
* tests when not needed,
* cache files,
* local secrets,
* IDE files,
* coverage output,
* build artifacts.

---

## 📖 75. Root Documentation Files

| File              | Responsibility                              |
| ----------------- | ------------------------------------------- |
| `README.md`       | Project overview and quick start            |
| `ARCHITECTURE.md` | Architectural principles and runtime design |
| `STRUCTURE.md`    | Folder and file responsibilities            |
| `DEVELOPMENT.md`  | Local development workflow                  |
| `TESTING.md`      | Testing strategy and quality gates          |

---

## ➕ 76. Adding a New Module

Create:

```text
app/modules/<module_name>/
├── __init__.py
├── dependencies.py
├── models.py
├── openapi.py
├── repository.py
├── router.py
├── schemas.py
└── service.py
```

Then:

1. map existing database tables,
2. define request schemas,
3. define response schemas,
4. implement repository operations,
5. implement service workflows,
6. expose dependencies,
7. create API routes,
8. define OpenAPI metadata,
9. register the router,
10. add tests,
11. update documentation.

---

## 🧭 77. Placement Rules

| Code Type                     | Correct Location          |
| ----------------------------- | ------------------------- |
| HTTP request parsing          | `router.py`               |
| Business validation           | `service.py`              |
| SQLAlchemy query              | `repository.py`           |
| ORM mapping                   | `models.py`               |
| Request/response model        | `schemas.py`              |
| Transaction management        | `db/uow.py`               |
| Engine and pool configuration | `db/<adapter>.py`         |
| Global configuration          | `core/config.py`          |
| Shared application exception  | `common/exceptions.py`    |
| Response envelope             | `common/response.py`      |
| Pagination helper             | `common/pagination.py`    |
| Request context               | `core/request_context.py` |
| Worker queue definition       | `worker/routing.py`       |
| Periodic schedule             | `worker/beat.py`          |
| Background task declaration   | `worker/tasks/`           |
| Background workflow           | `worker/modules/`         |
| Local script                  | `scripts/`                |
| Automated test                | `tests/`                  |

---

## 🚫 78. Common Placement Mistakes

### SQL Queries in Routers

Incorrect:

```text
router.py
    contains SQLAlchemy query
```

Correct:

```text
router.py
    ↓
service.py
    ↓
repository.py
```

### Commits in Repositories

Incorrect:

```python
await session.commit()
```

inside every repository method.

Correct:

```text
Unit of Work owns commit and rollback.
```

### Business Logic in Schemas

Pydantic schemas validate structure and field-level rules.

Complex workflows belong in services.

### Global Database Sessions

Never create global `AsyncSession` instances.

### Celery Startup in FastAPI

Do not import and start Celery from `app/main.py`.

---

## ✅ 79. Structure Review Checklist

Before adding a file, ask:

* [ ] Does this code already belong in an existing file?
* [ ] Is the responsibility domain-specific or shared?
* [ ] Does it belong to HTTP, business, persistence, or infrastructure?
* [ ] Will this introduce a reverse dependency?
* [ ] Is this optional integration truly isolated?
* [ ] Can the component be tested independently?
* [ ] Does the filename clearly describe its ownership?
* [ ] Does the module expose the correct `__all__`?
* [ ] Is the module docstring present?
* [ ] Are comments explaining intent rather than repeating code?

---

<div align="center">

## 💡 Structure Principle

**Every file should have one clear reason to change.**

</div>
