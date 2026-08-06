<div align="center">

# 🏛️ Architecture Guide

### FastAPI Microservice Foundation

<p>
  <img src="https://img.shields.io/badge/Architecture-Layered-4C6EF5" alt="Layered Architecture">
  <img src="https://img.shields.io/badge/Runtime-Async-12B886" alt="Async Runtime">
  <img src="https://img.shields.io/badge/Database-SQLAlchemy_2-D71F00" alt="SQLAlchemy 2">
  <img src="https://img.shields.io/badge/Transactions-Unit_of_Work-7950F2" alt="Unit of Work">
  <img src="https://img.shields.io/badge/Deployment-Docker-2496ED?logo=docker&logoColor=white" alt="Docker">
</p>

<p>
A practical architecture for building reusable, scalable, maintainable, and
production-oriented FastAPI microservices.
</p>

</div>

---

## 📌 1. Purpose

This document defines the architectural principles, component boundaries,
runtime behavior, database ownership rules, transaction model, deployment model,
and extension strategy of the FastAPI microservice foundation.

The architecture is designed for teams building multiple services that must remain:

* easy to understand,
* consistent across repositories,
* asynchronous where appropriate,
* safe under concurrent load,
* testable in isolation,
* explicit about infrastructure ownership,
* deployable independently,
* extensible without redesigning the entire project.

The architecture intentionally avoids unnecessary framework complexity.

The primary rule is:

```text
Router → Service → Repository → Database
```

Every layer has one clear responsibility.

---

## 🎯 2. Architectural Goals

| Goal                          | Description                                                                              |
| ----------------------------- | ---------------------------------------------------------------------------------------- |
| **Clarity**                   | Developers should quickly understand where code belongs.                                 |
| **Separation of concerns**    | HTTP, business logic, persistence, transactions, and infrastructure remain isolated.     |
| **Reusability**               | The same foundation can support many microservices.                                      |
| **Async safety**              | Database engines, sessions, and pools are managed correctly.                             |
| **Testability**               | Each layer can be tested without requiring the complete application stack.               |
| **Explicit transactions**     | Commit and rollback behavior remains visible.                                            |
| **Operational safety**        | Logging, health checks, graceful shutdown, and configuration validation are centralized. |
| **Optional integrations**     | Celery, Redis, MongoDB, PostgreSQL, and MSSQL remain opt-in.                             |
| **Microservice independence** | Each service can be deployed, scaled, and changed independently.                         |

---

## 🧱 3. High-Level Architecture

```mermaid
flowchart LR
    Client[Client]
    Gateway[API Gateway]
    Middleware[Middleware]
    Router[FastAPI Router]
    Service[Application Service]
    Repository[Repository]
    UOW[Unit of Work]
    Registry[Database Registry]
    Database[(External MySQL)]

    Client --> Gateway
    Gateway --> Middleware
    Middleware --> Router
    Router --> Service
    Service --> Repository
    Service --> UOW
    Repository --> UOW
    UOW --> Registry
    Registry --> Database
```

The application is divided into five primary runtime layers:

1. API layer
2. application service layer
3. repository layer
4. transaction layer
5. infrastructure layer

Cross-cutting concerns are implemented through shared core and common packages.

---

## 🔄 4. Request Lifecycle

```mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant M as Middleware
    participant R as Router
    participant S as Service
    participant U as Unit of Work
    participant P as Repository
    participant D as MySQL

    C->>G: HTTP request
    G->>M: Forward validated request
    M->>M: Create request context
    M->>R: Route request
    R->>S: Validated request schema
    S->>U: Open transaction
    S->>P: Execute business persistence
    P->>D: Async SQL query
    D-->>P: Database result
    P-->>S: Mapped result
    S->>U: Commit or rollback
    S-->>R: Service result
    R-->>M: Standard response
    M-->>G: Response with headers
    G-->>C: HTTP response
```

### Request Processing Order

```text
Incoming Request
    ↓
Proxy and Gateway Headers
    ↓
Request Context Middleware
    ↓
Security and Request Validation Middleware
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
Database Adapter
    ↓
External Database
    ↓
Standard Response Envelope
```

---

## 🌐 5. API Layer

The API layer is responsible for HTTP transport concerns.

Main locations:

```text
app/api/
app/modules/<module_name>/router.py
```

### Responsibilities

The API layer should:

* define route paths,
* define HTTP methods,
* parse request bodies,
* parse path parameters,
* parse query parameters,
* parse trusted headers,
* inject dependencies,
* attach OpenAPI metadata,
* return standardized responses,
* allow exceptions to reach centralized handlers.

### The API Layer Should Not

The API layer should not:

* contain SQLAlchemy queries,
* create database sessions,
* commit transactions,
* roll back transactions,
* contain complex business rules,
* create external service clients,
* implement multi-step workflows.

### Example

```python
@router.post(
    path="/products",
    response_model=APIResponseModel,
)
async def create_product(
    payload: CreateProductRequest,
    service: ProductServiceDep,
) -> APIResponseModel:
    result = await service.create_product(
        payload=payload,
    )

    return APIResponse.success(
        message="Product created successfully",
        data=result,
    )
```

The router receives validated input and delegates the use case to the service.

---

## 🧠 6. Application Service Layer

The service layer contains business workflows.

Main location:

```text
app/modules/<module_name>/service.py
```

### Responsibilities

Services should:

* enforce business rules,
* coordinate repositories,
* define transaction intent,
* validate state transitions,
* prevent invalid operations,
* map persistence results to response schemas,
* coordinate multiple repository operations,
* define idempotency behavior,
* raise application-specific exceptions.

### Example Workflow

```text
Validate request
    ↓
Check duplicate record
    ↓
Open Unit of Work
    ↓
Create parent record
    ↓
Create dependent records
    ↓
Commit transaction
    ↓
Return response schema
```

### Services Should Not

Services should not:

* depend on FastAPI request objects,
* return raw ORM models to clients,
* create global sessions,
* hide infrastructure setup,
* contain direct raw SQL unless explicitly justified,
* commit inside every repository call.

---

## 🗃️ 7. Repository Layer

The repository layer isolates persistence logic.

Main location:

```text
app/modules/<module_name>/repository.py
```

### Responsibilities

Repositories should:

* build SQLAlchemy statements,
* execute persistence queries,
* apply validated filters,
* apply validated sorting,
* implement pagination,
* load ORM entities,
* persist ORM entities,
* perform joins,
* use row locking when required,
* return domain-friendly persistence results.

### Repositories Should Not

Repositories should not:

* decide HTTP status codes,
* create API responses,
* implement cross-domain business rules,
* commit transactions automatically,
* create a new session for every method,
* swallow database errors without translation.

### Session Ownership

Repositories receive a session from the Unit of Work.

```mermaid
flowchart LR
    Service[Service]
    UOW[Unit of Work]
    Session[AsyncSession]
    RepoA[Repository A]
    RepoB[Repository B]

    Service --> UOW
    UOW --> Session
    Session --> RepoA
    Session --> RepoB
```

This allows multiple repositories to participate in one transaction.

---

## 🔁 8. Unit of Work

The Unit of Work owns the transaction boundary.

Main location:

```text
app/db/uow.py
```

### Transaction Lifecycle

```mermaid
stateDiagram-v2
    [*] --> SessionCreated
    SessionCreated --> TransactionOpened
    TransactionOpened --> Commit: workflow succeeds
    TransactionOpened --> Rollback: exception occurs
    Commit --> SessionClosed
    Rollback --> SessionClosed
    SessionClosed --> [*]
```

### Responsibilities

The Unit of Work should:

* create an async session,
* begin a transaction,
* expose the session to repositories,
* commit successful workflows,
* roll back failed workflows,
* close the session,
* prevent session leakage.

### Transaction Rule

```text
One business use case
    =
One Unit of Work
    =
One transaction boundary
```

### Example

```python
async with self._uow:
    product = await self._repository.create(
        session=self._uow.session,
        payload=payload,
    )

    await self._audit_repository.create(
        session=self._uow.session,
        product_id=product.id,
    )

    await self._uow.commit()
```

If any operation fails, the Unit of Work rolls back the complete transaction.

---

## 🗄️ 9. Database Architecture

Database infrastructure is located under:

```text
app/db/
```

### Active Database

MySQL is currently the active database integration.

Expected URL:

```text
mysql+asyncmy://username:password@hostname:3306/database_name
```

### Active Components

```text
app/db/mysql.py
app/db/registry.py
app/db/uow.py
app/db/base.py
app/db/sqlalchemy_types.py
```

### Disabled Reference Components

```text
app/db/postgres.py
app/db/mssql.py
app/db/mongo.py
app/db/redis_client.py
```

These integrations must remain inactive unless their complete dependency chain is
enabled.

---

## 🧩 10. Database Adapter Responsibilities

A database adapter owns:

* engine creation,
* connection pool configuration,
* session factory creation,
* connectivity validation,
* graceful shutdown,
* engine disposal,
* driver-specific configuration.

```mermaid
flowchart LR
    Settings[AppSettings]
    Adapter[MySQL Adapter]
    Engine[AsyncEngine]
    Pool[Connection Pool]
    SessionFactory[Async Session Factory]
    Database[(External MySQL)]

    Settings --> Adapter
    Adapter --> Engine
    Engine --> Pool
    Engine --> SessionFactory
    Pool --> Database
```

### Adapter Rules

Database adapters should not:

* contain domain queries,
* create FastAPI responses,
* perform business validation,
* own module-specific repositories,
* run migrations,
* create tables automatically.

---

## 🗂️ 11. Database Registry

The registry centralizes enabled infrastructure adapters.

Main location:

```text
app/db/registry.py
```

### Responsibilities

The registry should:

* construct enabled adapters,
* expose adapters through stable properties,
* report enabled adapter names,
* validate readiness,
* close all adapters during shutdown.

### Registry Flow

```mermaid
flowchart TD
    Settings[Validated Settings]
    Registry[Database Registry]
    MySQL[MySQL Adapter]
    PostgreSQL[PostgreSQL Adapter - Disabled]
    MSSQL[MSSQL Adapter - Disabled]
    Mongo[Mongo Adapter - Disabled]
    Redis[Redis Adapter - Disabled]

    Settings --> Registry
    Registry --> MySQL
    Registry -. disabled .-> PostgreSQL
    Registry -. disabled .-> MSSQL
    Registry -. disabled .-> Mongo
    Registry -. disabled .-> Redis
```

Optional adapters should not affect startup when disabled.

---

## ⚙️ 12. Configuration Architecture

Configuration is centralized in:

```text
app/core/config.py
```

The application should not read environment variables directly throughout the codebase.

### Configuration Sources

```mermaid
flowchart LR
    Env[Environment Variables]
    DotEnv[Local .env]
    Settings[Pydantic AppSettings]
    Application[Application Components]

    Env --> Settings
    DotEnv --> Settings
    Settings --> Application
```

### Configuration Rules

* use `UPPER_SNAKE_CASE` environment variables,
* validate required values at startup,
* validate optional adapters only when enabled,
* never log secrets,
* expose derived values through safe properties,
* fail fast for invalid production configuration,
* keep defaults safe and conservative.

### Secret Values

The following must never be logged:

* database passwords,
* complete connection URLs,
* tokens,
* internal service keys,
* authorization headers,
* private file URLs.

---

## 🧬 13. Dependency Injection

FastAPI dependency injection is used to construct request-scoped components.

Main locations:

```text
app/api/dependencies.py
app/modules/<module_name>/dependencies.py
```

### Dependency Hierarchy

```mermaid
flowchart TD
    Settings[AppSettings]
    Registry[Database Registry]
    UOW[Unit of Work]
    Repository[Repository]
    Service[Service]
    Router[Router]

    Settings --> Registry
    Registry --> UOW
    UOW --> Repository
    Repository --> Service
    UOW --> Service
    Service --> Router
```

### Global Dependencies

Global dependencies may provide:

* settings,
* database registry,
* MySQL adapter,
* Unit of Work,
* request identity,
* correlation information.

### Module Dependencies

Module dependencies should provide:

* repositories,
* application services,
* module-specific clients,
* module-specific strategies.

---

## 🧾 14. Request Context

Request-scoped metadata is managed through:

```text
app/core/request_context.py
```

Recommended context fields:

```text
request_id
correlation_id
user_id
user_role
client_ip
route
method
```

Request context should use `contextvars`.

Do not store request-specific state in mutable global variables.

### Context Flow

```mermaid
flowchart LR
    Headers[Incoming Headers]
    Middleware[Request Context Middleware]
    ContextVars[Context Variables]
    Logger[Structured Logger]
    Service[Service Layer]

    Headers --> Middleware
    Middleware --> ContextVars
    ContextVars --> Logger
    ContextVars --> Service
```

---

## 📝 15. Logging Architecture

Logging is centralized in:

```text
app/core/logging.py
```

### Recommended Structured Fields

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
method
route
status_code
duration_ms
exception_type
```

### Logging Rules

Use:

```python
logger.info(
    "Inventory updated",
    extra={
        "product_id": product_id,
        "warehouse_id": warehouse_id,
    },
)
```

Avoid:

```python
print(payload)
logger.info(mysql_url)
logger.debug(authorization_header)
```

### Sensitive Data

Never log:

* passwords,
* tokens,
* complete database URLs,
* medical records,
* personal information,
* prescription contents,
* private documents,
* unsanitized request bodies.

---

## 🛡️ 16. Middleware Architecture

Middleware is located in:

```text
app/core/middleware.py
```

Possible responsibilities:

* request ID generation,
* correlation ID propagation,
* request timing,
* access logging,
* request size enforcement,
* secure response headers,
* CORS,
* proxy header handling,
* exception correlation.

### Middleware Order

```text
Trusted proxy handling
    ↓
Request ID and correlation context
    ↓
Security headers
    ↓
Request size validation
    ↓
Access logging and timing
    ↓
FastAPI routing
```

Middleware order matters because outer middleware receives the request first and the
response last.

---

## ⚠️ 17. Exception Architecture

Shared exceptions are located in:

```text
app/common/exceptions.py
```

Exception handlers are located in:

```text
app/api/exception_handlers.py
```

### Exception Flow

```mermaid
flowchart LR
    Repository[Repository]
    Service[Service]
    Exception[Application Exception]
    Handler[Exception Handler]
    Response[Standard Error Response]

    Repository --> Service
    Service --> Exception
    Exception --> Handler
    Handler --> Response
```

### Recommended Exception Categories

* validation error,
* resource not found,
* resource conflict,
* unauthorized operation,
* forbidden operation,
* invalid state transition,
* infrastructure unavailable,
* database operation failure,
* internal application error.

### Standard Error Response

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

Raw database exceptions must never be returned to clients.

---

## 📦 18. Response Architecture

Shared response models live in:

```text
app/common/response.py
```

### Successful Response

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

### External and Internal Naming

```text
External JSON
    camelCase

Python
    snake_case

Database
    snake_case
```

Pydantic aliases bridge the boundaries.

---

## 🔍 19. Filtering, Pagination, and Sorting

Reusable helpers live in:

```text
app/common/filters.py
app/common/pagination.py
app/common/sorting.py
```

### Pagination Rules

* page numbering starts at 1,
* page size has a maximum limit,
* invalid values fail validation,
* metadata remains consistent,
* expensive total counts may be optional for large datasets.

### Sorting Rules

Only explicitly allowed fields may be sorted.

Never pass arbitrary client input directly into:

```python
order_by(text(user_input))
```

Instead, map allowed fields:

```python
SORTABLE_FIELDS = {
    "createdAt": Product.created_at,
    "name": Product.name,
}
```

### Filtering Rules

* normalize empty values,
* validate date ranges,
* validate numeric ranges,
* use SQLAlchemy expressions,
* avoid raw SQL string construction,
* keep API aliases separate from ORM column names.

---

## 🧩 20. Module Architecture

Business modules live under:

```text
app/modules/
```

Recommended structure:

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

### Module Flow

```mermaid
flowchart TD
    Router[router.py]
    Dependencies[dependencies.py]
    Service[service.py]
    Repository[repository.py]
    Models[models.py]
    Schemas[schemas.py]
    OpenAPI[openapi.py]

    Router --> Dependencies
    Router --> Schemas
    Router --> OpenAPI
    Dependencies --> Service
    Service --> Repository
    Repository --> Models
    Service --> Schemas
```

### Module Ownership

| File              | Responsibility               |
| ----------------- | ---------------------------- |
| `models.py`       | ORM table mappings           |
| `schemas.py`      | Request and response schemas |
| `repository.py`   | Persistence operations       |
| `service.py`      | Business workflows           |
| `dependencies.py` | Dependency providers         |
| `router.py`       | HTTP endpoints               |
| `openapi.py`      | OpenAPI metadata             |

---

## ❤️ 21. Health Architecture

Health endpoints live in:

```text
app/api/health.py
```

### Health Model

```mermaid
flowchart LR
    Live[/health/live]
    Ready[/health/ready]
    API[FastAPI Process]
    Registry[Database Registry]
    MySQL[(External MySQL)]

    Live --> API
    Ready --> API
    Ready --> Registry
    Registry --> MySQL
```

### Liveness

Liveness answers:

> Is the application process alive and able to respond?

It should not depend on external database availability.

### Readiness

Readiness answers:

> Is the application ready to receive production traffic?

It may validate:

* database registry availability,
* MySQL connectivity,
* required configuration,
* startup initialization state.

### General Health

`GET /health` may provide a summarized service status.

---

## 🌱 22. Application Lifespan

FastAPI lifecycle is managed in:

```text
app/core/lifespan.py
```

### Startup Responsibilities

* load validated settings,
* initialize structured logging,
* create database registry,
* validate required adapters,
* attach resources to application state,
* log application startup.

### Shutdown Responsibilities

* stop accepting new work,
* close database sessions,
* dispose engines and pools,
* close external clients,
* flush and stop logging,
* log application shutdown.

### Lifespan Flow

```mermaid
stateDiagram-v2
    [*] --> Starting
    Starting --> Ready: initialization succeeds
    Starting --> Failed: initialization fails
    Ready --> ShuttingDown: termination signal
    ShuttingDown --> Closed: resources released
    Failed --> [*]
    Closed --> [*]
```

---

## 🧵 23. Worker Architecture

Worker code lives under:

```text
app/worker/
```

Celery is currently disabled.

### Future Worker Structure

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

### Worker Runtime

```mermaid
flowchart LR
    Broker[(Message Broker)]
    Celery[Celery Worker]
    Child[Worker Child Process]
    Loop[Dedicated Async Event Loop]
    Registry[Worker-local Database Registry]
    Database[(External Database)]

    Broker --> Celery
    Celery --> Child
    Child --> Loop
    Loop --> Registry
    Registry --> Database
```

### Worker Rules

When enabled:

* FastAPI and Celery run as separate processes,
* Celery is not started from `app/main.py`,
* each prefork worker child creates its own database registry,
* database pools are created after process fork,
* each task uses one Unit of Work,
* task messages contain serializable data only,
* sessions and ORM models are never placed in messages,
* task entry points remain thin,
* business logic lives in worker module services.

---

## ⏰ 24. Celery Beat Architecture

Periodic schedules live in:

```text
app/worker/beat.py
```

Beat schedules should remain declarative.

Example:

```python
BEAT_SCHEDULE = {
    "rack-replenishment-every-night": {
        "task": (
            "app.worker.tasks."
            "rack_replenishment_task.run"
        ),
        "schedule": crontab(
            hour=22,
            minute=30,
        ),
        "options": {
            "queue": "scheduled",
        },
    },
}
```

Periodic task business logic should not live in Beat configuration.

---

## 📨 25. Event and Message Architecture

Future events should use:

```text
lowercase dot-separated event names
camelCase payload fields
```

Example event name:

```text
inventory.adjusted
```

Example payload:

```json
{
  "eventId": "uuid",
  "eventVersion": 1,
  "occurredAt": "2026-08-06T10:00:00Z",
  "productId": 1001,
  "warehouseId": 2,
  "quantity": 5
}
```

### Event Rules

* event payloads must be serializable,
* events should include stable identifiers,
* consumers should be idempotent,
* schema versions should be explicit,
* internal ORM objects must not be serialized directly.

---

## 📤 26. Outbox Pattern

For reliable future event publishing, use an outbox pattern.

```mermaid
sequenceDiagram
    participant S as Service
    participant DB as Database
    participant O as Outbox Table
    participant P as Publisher
    participant B as Broker

    S->>DB: Update business records
    S->>O: Insert event in same transaction
    DB-->>S: Commit
    P->>O: Read unpublished event
    P->>B: Publish event
    P->>O: Mark event published
```

This avoids inconsistent states where:

* the database commits,
* but event publishing fails.

The API Gateway should not coordinate distributed rollbacks across services.

---

## 🌍 27. Microservice Transaction Boundaries

A local database transaction can only roll back work inside one service's database
boundary.

```mermaid
flowchart LR
    Gateway[API Gateway]
    Order[Order Service]
    Payment[Payment Service]
    Inventory[Inventory Service]

    Gateway --> Order
    Order --> Payment
    Order --> Inventory
```

The gateway must not attempt to manage a shared transaction across these services.

Use:

* local transactions,
* idempotency,
* events,
* sagas,
* compensating actions,
* outbox and inbox patterns.

### Example Saga

```text
Create order
    ↓
Reserve inventory
    ↓
Authorize payment
    ↓
Confirm order
```

Failure handling:

```text
Payment fails
    ↓
Release inventory reservation
    ↓
Mark order failed
```

This is compensation, not a distributed database rollback.

---

## 🔐 28. Security Architecture

The service is intended to run behind an API Gateway inside a private network.

### Trusted Headers

Possible trusted headers:

```text
X-User-ID
X-User-Role
X-Request-ID
X-Correlation-ID
```

These headers are trusted only when:

* the gateway removes client-provided copies,
* the gateway injects validated values,
* the service is not directly exposed publicly,
* internal network controls prevent bypass.

### Security Responsibilities

The service should enforce:

* request validation,
* business authorization where required,
* safe database access,
* secure error handling,
* secret-safe logging,
* request size limits,
* CORS policy,
* secure response headers.

The authentication service should own token issuance and validation rules.

---

## 🗃️ 29. Database Migration Ownership

A dedicated migration repository should own database schema changes.

```mermaid
flowchart TD
    MigrationRepo[Database Migration Repository]
    SharedDB[(Shared Database)]
    ServiceA[Service A]
    ServiceB[Service B]
    ServiceC[Service C]

    MigrationRepo --> SharedDB
    ServiceA --> SharedDB
    ServiceB --> SharedDB
    ServiceC --> SharedDB
```

### Application Services Must Not

* run migrations at startup,
* use automatic schema synchronization,
* call `metadata.create_all()` in production,
* create independent revisions for shared schemas,
* change tables without migration coordination.

### Source of Truth

The migration repository is the source of truth for:

* table names,
* column names,
* indexes,
* constraints,
* relationships,
* enums,
* foreign keys.

Application ORM models map the existing schema.

---

## 🐳 30. Deployment Architecture

The Docker Compose configuration starts only the FastAPI service.

```mermaid
flowchart TB
    Gateway[API Gateway / Load Balancer]
    API1[FastAPI Container 1]
    API2[FastAPI Container 2]
    API3[FastAPI Container 3]
    Database[(Managed External MySQL)]
    Logging[Centralized Logging]

    Gateway --> API1
    Gateway --> API2
    Gateway --> API3

    API1 --> Database
    API2 --> Database
    API3 --> Database

    API1 --> Logging
    API2 --> Logging
    API3 --> Logging
```

### Production Recommendations

* one Uvicorn process per container,
* horizontal scaling through orchestration,
* external managed databases,
* readiness-based traffic routing,
* graceful shutdown,
* centralized logs,
* environment-based secrets,
* no database service inside the application Compose file.

---

## ⚖️ 31. Scaling Model

### API Scaling

Scale by increasing the number of containers.

```text
1 container
    ↓
multiple independent containers
    ↓
load balancer distributes traffic
```

Each container has its own:

* Python process,
* event loop,
* SQLAlchemy engine,
* connection pool,
* application state.

### Database Pool Capacity

Total possible database connections:

```text
number of containers
×
pool size per container
+
overflow capacity
```

Example:

```text
5 containers
×
10 pool connections
=
50 base connections
```

Pool sizing must consider database capacity.

Do not increase:

* Uvicorn workers,
* container replicas,
* pool size,
* overflow,

without calculating total connection demand.

---

## ⚡ 32. Async Execution Model

FastAPI runs on an asyncio event loop.

Async code is valuable for:

* database queries,
* HTTP calls,
* object storage operations,
* message broker communication,
* network-bound workflows.

Async does not automatically improve CPU-heavy code.

CPU-heavy work should later use:

* separate worker processes,
* Celery CPU queues,
* dedicated compute services.

### Blocking Code

Do not call blocking libraries directly inside async endpoints.

Bad:

```python
@router.get("/report")
async def report() -> dict[str, object]:
    result = blocking_library_call()

    return result
```

Blocking calls should be:

* replaced with async libraries,
* moved to thread execution,
* moved to background workers.

---

## 📈 33. Performance Principles

Performance should be measured before optimization.

Inspect:

* slow queries,
* database query plans,
* connection pool waits,
* transaction duration,
* response serialization,
* external dependency latency,
* memory usage,
* CPU usage.

### Common Improvements

* proper indexes,
* bounded pagination,
* selecting required columns only,
* avoiding N+1 queries,
* batch operations,
* bulk inserts,
* short transactions,
* streaming large responses,
* background processing for long-running jobs.

---

## 🧪 34. Testability Architecture

The architecture supports layered testing.

```mermaid
flowchart TB
    E2E[End-to-End]
    Contract[Contract]
    API[API]
    Integration[Integration]
    Unit[Unit]

    E2E --> Contract
    Contract --> API
    API --> Integration
    Integration --> Unit
```

### Unit Tests

Test:

* services,
* validation rules,
* common utilities,
* configuration normalization.

### API Tests

Test:

* status codes,
* response envelopes,
* middleware behavior,
* dependency overrides.

### Integration Tests

Test:

* repositories,
* Unit of Work,
* MySQL adapter,
* transaction behavior.

### Contract Tests

Test:

* OpenAPI paths,
* operation IDs,
* camelCase schemas,
* stable error models.

---

## 🔌 35. Optional Integration Activation

Optional integrations should be enabled through a complete activation workflow.

### PostgreSQL

1. install `asyncpg`,
2. enable settings,
3. enable adapter,
4. enable registry integration,
5. expose dependencies,
6. add readiness checks,
7. add tests.

### MSSQL

1. install `aioodbc`,
2. install `pyodbc`,
3. install Microsoft ODBC system driver,
4. enable settings,
5. enable adapter,
6. add tests.

### MongoDB

1. install `pymongo`,
2. enable settings,
3. enable async client adapter,
4. enable registry integration,
5. add lifecycle and readiness tests.

### Redis

1. install `redis`,
2. define use case,
3. enable settings,
4. implement key prefix strategy,
5. configure timeouts,
6. add readiness checks,
7. add tests.

### Celery

1. enable worker settings,
2. install Celery and broker driver,
3. enable worker configuration,
4. enable routing,
5. enable lifecycle,
6. enable signals,
7. implement tasks,
8. deploy workers separately.

---

## 🚫 36. Anti-Patterns

Avoid these architectural mistakes.

### Fat Routers

Bad:

```python
@router.post("/products")
async def create_product(...):
    # validation
    # database query
    # commit
    # logging
    # response mapping
```

Move workflow logic into a service.

### Repository Commits

Repositories should not commit independently.

Bad:

```python
async def create(...):
    session.add(entity)
    await session.commit()
```

The Unit of Work should commit.

### Global Sessions

Never create:

```python
session = AsyncSession(...)
```

at module level.

### Hidden Infrastructure

Do not create database engines inside random services or repositories.

### Optional Dependencies Becoming Mandatory

Disabled adapters should not break imports when their packages are absent.

### Distributed Transactions Through Gateway

The API Gateway should not coordinate database rollback across services.

---

## 🧭 37. Architectural Guardrails

1. Routers remain thin.
2. Services own business workflows.
3. Repositories own persistence operations.
4. Unit of Work owns transactions.
5. Database adapters own engines and pools.
6. Database registry owns enabled adapters.
7. Configuration remains centralized.
8. Request state uses context-local storage.
9. API fields use camelCase.
10. Python code uses snake_case.
11. Database identifiers use snake_case.
12. Migrations remain outside application services.
13. FastAPI does not start Celery.
14. Worker children do not share parent process pools.
15. Sessions are not shared across requests.
16. Raw infrastructure errors are not returned to clients.
17. Secrets are not logged.
18. Sorting and filtering fields are whitelisted.
19. Optional integrations remain opt-in.
20. Tests follow production layer boundaries.

---

## 🔮 38. Future Architecture Extensions

The architecture supports later addition of:

* Redis caching,
* distributed locks,
* idempotency storage,
* Celery background processing,
* Celery Beat scheduling,
* domain events,
* transactional outbox,
* inbox deduplication,
* OpenTelemetry tracing,
* application metrics,
* centralized audit logging,
* service-to-service clients,
* circuit breakers,
* rate limiting,
* Elasticsearch search adapters.

Each extension should remain isolated behind a clear interface.

---

## 📚 39. Related Documentation

| Document          | Purpose                                  |
| ----------------- | ---------------------------------------- |
| `README.md`       | Project overview and quick start         |
| `STRUCTURE.md`    | Folder and file ownership                |
| `DEVELOPMENT.md`  | Development workflow and standards       |
| `TESTING.md`      | Test strategy and quality gates          |
| `ARCHITECTURE.md` | Architectural rules and runtime behavior |

---

<div align="center">

## 💡 Architecture Principle

**Explicit boundaries create scalable and maintainable services.**

</div>
