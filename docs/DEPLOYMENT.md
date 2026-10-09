# Deployment runbook

Python 3.12+, FastAPI, Uvicorn, Pydantic 2, SQLAlchemy 2 async, asyncpg, Alembic, and Docker are the active stack. PostgreSQL is the active adapter; other adapters are opt-in references.

## Local

```bash
cp .env.example .env
docker compose up --build
curl http://localhost:8000/health/ready
```

Build an immutable image and run one process per container behind the future gateway. Set `ENVIRONMENT=production`, `DEBUG=false`, `LOG_JSON=true`, restricted CORS, trusted proxy addresses, private database connectivity, and bounded pool sizes.

Use `/health/live` for liveness and `/health/ready` for readiness. Apply shared healthcare migrations from `heathcare_db`; this foundation does not own them.

```text
INFO service_started service=fastapi-service environment=production
INFO request_completed method=GET path=/health/ready status_code=200 request_id=<uuid>
```
