<!-- PROJECT TITLE -->

<h1 align="center">
🚀 Fast API Boilerplate Request Service
</h1>

<p align="center">
<b>Production-grade FastAPI backend built with Clean Architecture, modular services, and scalable infrastructure.</b>
</p>

<p align="center">
Designed for high-performance APIs, modular development, and long-term maintainability.
</p>

<br>

<!-- BADGES -->

<p align="center">

<img src="https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
<img src="https://img.shields.io/badge/Architecture-Clean%20Architecture-purple?style=for-the-badge" />
<img src="https://img.shields.io/badge/Async-Ready-success?style=for-the-badge" />
<img src="https://img.shields.io/badge/License-Internal-lightgrey?style=for-the-badge" />

</p>

<br>

<p align="center">

⚡ **High-performance async backend**  
🧩 **Modular feature architecture**  
🛡 **Unified error & response contracts**  
🔄 **Atomic transaction boundaries**  
🚀 **Production-ready infrastructure**

</p>

---

# 🧠 Overview

This project is a **high-quality FastAPI backend service** built using a **clean, modular architecture** designed for:

- scalability
- maintainability
- clear separation of concerns
- infrastructure flexibility

The architecture supports **multiple databases, Redis caching, background tasks, and modular domain services** while remaining lightweight for development.

The system is designed to support:

- microservice deployment
- high-throughput APIs
- large team development
- long-term maintainability

---

# 🧩 Architecture Philosophy

The system follows a **layered architecture inspired by Clean Architecture and Hexagonal design**.

Core principles:

✔ Business logic isolated from infrastructure  
✔ No framework leakage into domain logic  
✔ Explicit transaction management  
✔ Centralized response and error contracts  
✔ Modular feature development  

---

# 🧭 System Architecture

```
HTTP Request
     │
     ▼
Middleware Stack
     │
     ▼
API Routes
     │
     ▼
Dependencies
     │
     ▼
Service Layer
     │
     ▼
Unit Of Work
     │
     ▼
Repository Layer
     │
     ▼
Infrastructure Adapters
     │
     ▼
Database / Cache
```

---

# 📦 Project Structure

```
fastapi-production-boilerplate
│
├── app
│   │
│   ├── main.py                  # FastAPI application entrypoint
│   │
│   ├── api                      # API layer
│   │   ├── dependencies         # FastAPI dependency providers
│   │   └── v1                   # Versioned API routers
│   │
│   ├── core                     # Application core
│   │   ├── config.py            # Environment configuration
│   │   ├── lifespan.py          # Application startup / shutdown
│   │   ├── middleware.py        # HTTP middleware stack
│   │   ├── logging.py           # Logging infrastructure
│   │   ├── rate_limit.py        # Redis rate limiter
│   │   ├── execution.py         # Service execution wrapper
│   │   ├── idempotency.py       # Distributed idempotency
│   │   └── request_context.py   # Request context handling
│   │
│   ├── common                   # Shared API utilities
│   │   ├── exceptions.py        # Domain error model
│   │   └── response.py          # Unified API response schema
│   │
│   ├── db                       # Database layer
│   │   ├── base.py              # SQLAlchemy declarative base
│   │   ├── registry.py          # Database registry
│   │   └── unit_of_work.py      # Transaction boundary
│   │
│   ├── infrastructure           # Infrastructure adapters
│   │   ├── postgres.py
│   │   ├── mysql.py
│   │   ├── mssql.py
│   │   ├── mongo.py
│   │   └── redis_client.py
│   │
│   ├── modules                  # Feature modules
│   │   ├── product
│   │   └── templates
│   │
│   ├── tasks                    # Background jobs (Celery etc)
│   │
│   └── utils                    # Shared utility helpers
│
├── docker                       # Container configuration
│
├── logs                         # Application logs
│
├── .env                         # Local environment configuration
├── .env.example                 # Example environment variables
├── requirements.txt             # Python dependencies
└── README.md
```

---

# 🧱 Module Architecture

Each feature module follows a **consistent internal structure**.

Example module layout:

```
modules/product
│
├── constants.py
├── dependencies.py
├── models.py
├── repository.py
├── schemas.py
├── service.py
├── routes.py
├── openapi.py
└── utils.py
```

This design guarantees **predictable development patterns** and allows developers to onboard quickly.

---

# 🔄 Request Flow

Example API request lifecycle:

```
Client Request
     │
     ▼
FastAPI Router
     │
     ▼
Dependency Injection
     │
     ▼
Service Layer
     │
     ▼
UnitOfWork Transaction
     │
     ▼
Repository
     │
     ▼
Database Adapter
     │
     ▼
Database
```

---

# ⚙️ Technology Stack

| Layer | Technology |
|------|-------------|
| Framework | FastAPI |
| Runtime | Python 3.11+ |
| Validation | Pydantic v2 |
| ORM | SQLAlchemy 2.0 |
| Async DB | asyncpg |
| Cache | Redis |
| Background Jobs | Celery (optional) |
| Containerization | Docker |

---

# 🛠 Local Development

## 1️⃣ Clone Repository

```bash
git clone github.com/shiladityamajumder/fastapi-production-boilerplate.git
cd fastapi-production-boilerplate
```

---

## 2️⃣ Create Virtual Environment

```bash
python -m venv venv
```

Activate environment.

**Windows**

```bash
venv\Scripts\activate
```

**Linux / macOS**

```bash
source venv/bin/activate
```

---

## 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4️⃣ Configure Environment

Create `.env` file from template.

```bash
cp .env.example .env
```

For development without infrastructure:

```env
ENABLE_POSTGRES=false
ENABLE_MYSQL=false
ENABLE_MSSQL=false
ENABLE_MONGO=false
ENABLE_REDIS=false
```

---

# ▶ Running the Application

Start the server from project root:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8888
```

Application will start at:

```
http://localhost:8888
```

---

# 📡 API Documentation

Interactive API documentation is available at:

```
/docs
```

Example:

```
http://localhost:8888/docs
```

Documentation is **automatically disabled in production environments**.

---

# 🧪 Health Endpoints

### Liveness Probe

```
GET /health/live
```

Example response:

```json
{
  "success": true,
  "status": "success",
  "code": 200,
  "message": "Operation completed successfully",
  "data": {
    "status": "alive"
  }
}
```

---

### Readiness Probe

```
GET /health/ready
```

Used by:

- Kubernetes readiness checks
- load balancer health verification

---

# 🔌 Infrastructure Configuration

External services are **feature-flag controlled**.

### PostgreSQL

```env
ENABLE_POSTGRES=true

POSTGRES_ASYNC_URL=postgresql+asyncpg://user:password@localhost:5432/db
POSTGRES_SYNC_URL=postgresql://user:password@localhost:5432/db
```

---

### MongoDB

```env
ENABLE_MONGO=true

MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=fastapi-production-boilerplate
```

---

### Redis

```env
ENABLE_REDIS=true

REDIS_URL=redis://localhost:6379/0
RATE_LIMIT_ENABLED=true
```

If an enabled service fails connectivity validation, **application startup aborts** to avoid running in a degraded state.

---

# 🔐 Unified Response Contract

Every API response follows a **single unified schema**.

Example:

```json
{
  "success": true,
  "status": "success",
  "code": 200,
  "message": "...",
  "data": {},
  "meta": {
    "request_id": "...",
    "api_version": "v1",
    "timestamp": "2026-01-01T10:00:00Z",
    "errors": null
  }
}
```

Benefits:

- predictable client integration
- centralized response formatting
- built-in observability

---

# 🚦 Error Handling

Domain services raise structured exceptions.

Supported domain errors:

| Exception | HTTP Status |
|-----------|-------------|
| NotFoundError | 404 |
| ConflictError | 409 |
| UnauthorizedError | 401 |
| ForbiddenError | 403 |

All errors are automatically converted to the unified API response format.

---

# 🧾 Logging System

Logging includes:

- structured JSON logs in production
- readable logs in development
- request correlation IDs
- non-blocking logging pipeline

Log file location:

```
logs/app.log
```

---

# 🧱 Database Transaction Model

Transactions are managed using the **Unit Of Work pattern**.

Example:

```python
async with UnitOfWork(session):
    repository.create(...)
```

Guarantees:

- atomic operations
- deterministic commit behavior
- automatic rollback on error

---

# 🐳 Docker (Optional)

Container configuration is located in:

```
docker/
```

Run application using Docker:

```bash
docker compose up --build
```

---

# 📈 Future Extensions

The architecture is ready for:

- distributed microservices
- event-driven messaging
- background workers
- distributed tracing
- service mesh deployments

---

# 🤝 Development Guidelines

✔ Keep routes thin  
✔ Put business logic inside services  
✔ Repositories only handle persistence  
✔ Never construct JSONResponse manually  

Always return responses using:

```python
APIResponse.success(...)
APIResponse.error(...)
```

---

# 📜 License

This project is licensed under the MIT License.

---

# Built With

FastAPI + Clean Architecture principles

Designed for scalable backend systems.

---

# 🧪 Testing Strategy

The service is designed to support both **unit tests** and **integration tests**.

Testing layers include:

- service-level unit tests
- repository database tests
- API endpoint integration tests

Recommended testing stack:

| Tool | Purpose |
|-----|--------|
| pytest | test runner |
| pytest-asyncio | async test support |
| httpx | async API client |
| factory-boy | test data generation |

Example test execution:

```bash
pytest
```

Example structure:

```
tests/
│
├── unit
│   ├── services
│   └── utils
│
├── integration
│   ├── api
│   └── repositories
│
└── conftest.py
```

---

# 🧰 Development Tooling

Recommended development tools:

| Tool | Purpose |
|-----|---------|
| Black | code formatting |
| Ruff | linting |
| MyPy | static typing |
| Pre-commit | automated code quality |

Example installation:

```bash
pip install black ruff mypy pre-commit
```

Example pre-commit setup:

```bash
pre-commit install
```

This ensures all commits pass linting and formatting checks.

---

# 🧭 Configuration Management

Application configuration is managed through **environment variables**.

Configuration is loaded using **Pydantic Settings**, ensuring:

- deterministic startup
- strict validation
- typed configuration access

Configuration source priority:

```
Environment Variables
      ↓
.env file
      ↓
Default values in AppSettings
```

All configuration variables are documented in:

```
.env.example
```

---

# 🧱 Database Strategy

The architecture supports **multiple database backends simultaneously**.

Supported engines:

| Database | Purpose |
|---------|--------|
| PostgreSQL | primary relational database |
| MySQL | legacy integration support |
| MSSQL | enterprise system integration |
| MongoDB | document storage |
| Redis | caching and rate limiting |

Database access is abstracted through:

```
Repository Layer
     ↓
Unit Of Work
     ↓
Database Adapter
```

This allows **easy infrastructure replacement without affecting business logic**.

---

# ⚡ Performance Considerations

The system is optimized for **high-throughput APIs**.

Performance strategies include:

- asynchronous database access
- connection pooling
- non-blocking logging
- centralized middleware
- rate limiting support
- idempotent request handling

Typical request latency (local development):

```
~2ms - 8ms per request
```

---

# 🔍 Observability

The system includes built-in observability mechanisms.

Features include:

- request correlation IDs
- structured logging
- health probes
- centralized error reporting

These features enable easy integration with:

- ELK stack
- Datadog
- Prometheus
- Grafana

---

# 🛡 Security Considerations

The architecture includes several security-oriented design choices:

- centralized error handling
- strict configuration validation
- idempotent request support
- request rate limiting
- infrastructure validation during startup

Future extensions may include:

- OAuth2 authentication
- JWT authorization
- audit logging
- API key management

---

# 🔄 Deployment Model

The service is designed to support multiple deployment strategies.

Supported environments:

| Environment | Purpose |
|------------|--------|
| Local development | developer machines |
| Containerized | Docker deployments |
| Cloud native | Kubernetes clusters |

Typical deployment pipeline:

```
Git Commit
     ↓
CI Pipeline
     ↓
Build Docker Image
     ↓
Push to Registry
     ↓
Deploy to Environment
```

---

# 🧩 Extending the System

New features should be implemented as **self-contained modules**.

Steps to add a new module:

1. Create module directory

```
app/modules/new_feature
```

2. Implement required components

```
models.py
schemas.py
repository.py
service.py
routes.py
openapi.py
```

3. Register router inside:

```
app/api/v1/router.py
```

This ensures the system remains **modular and scalable**.

---

# 📚 API Versioning Strategy

All APIs are versioned using **URL-based versioning**.

Example:

```
/api/v1/templates
/api/v1/products
```

Future versions may introduce:

```
/api/v2/...
```

This guarantees **backward compatibility** for clients.

---

# 🧑‍💻 Contribution Guidelines

When contributing to this repository:

1. Keep routes thin
2. Place business logic in services
3. Use repositories only for persistence
4. Use APIResponse for all responses
5. Follow existing module structure

Pull requests should include:

- clear description
- unit tests when applicable
- documentation updates

---

# 📌 Coding Standards

The codebase follows modern Python best practices:

- Python 3.11+
- type annotations everywhere
- explicit transaction boundaries
- dependency injection via FastAPI

General principles:

```
Thin Controllers
Rich Services
Explicit Infrastructure
```

---

# 📎 Additional Resources

Helpful documentation:

FastAPI  
https://fastapi.tiangolo.com/

SQLAlchemy 2.0  
https://docs.sqlalchemy.org/

Pydantic  
https://docs.pydantic.dev/

---

# 📣 Maintainers

Maintained by Shiladitya Majumder and contributors.

For questions or internal support, contact the service maintainers.

---

# ⭐ Final Notes

This repository is designed to serve as a **production-grade backend template** for building scalable Python services.

Key characteristics:

- clean architecture
- modular feature design
- infrastructure flexibility
- strong operational observability

It can serve as a foundation for:

- internal APIs
- microservices
- enterprise backend systems
- high-throughput platforms

---