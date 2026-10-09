# Setup Guide

This guide supports Python 3.12–3.14. Settings are loaded from environment
variables and `.env` (case-insensitive names); `.env` is ignored by Git. Copy
`.env.example` and replace the clearly marked placeholders before enabling
PostgreSQL, authentication, or AWS services.

## Python environment

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt
Copy-Item .env.example .env
```

If PowerShell blocks activation, use `Set-ExecutionPolicy -Scope Process
RemoteSigned` in that terminal, or invoke `.\.venv\Scripts\python.exe` directly.

### Linux/macOS

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
```

For an installed `fastapi-service` or `create-admin` command, install the local
project in editable mode with `python -m pip install -e .`.

## Minimal local setup (AWS disabled)

The service can start without PostgreSQL, auth, Redis, or AWS for liveness and
smoke checks. Keep these settings in `.env`:

```dotenv
ENABLE_POSTGRES=false
AUTH_ENABLED=false
BACKGROUND_JOBS_ENABLED=false
AUTH_EMAIL_DELIVERY_ENABLED=false
AUTH_SMS_DELIVERY_ENABLED=false
PROFILE_IMAGE_STORAGE_ENABLED=false
```

Start the server:

```powershell
python -m uvicorn app.main:app --reload
```

```sh
python -m uvicorn app.main:app --reload
```

Visit `http://127.0.0.1:8000/health/live` and, outside production,
`http://127.0.0.1:8000/docs`. With no enabled dependencies, readiness succeeds
after application startup. It does not exercise authenticated endpoints;
protected auth endpoints require the PostgreSQL setup below.

## PostgreSQL and authentication

Install PostgreSQL locally or use the Compose PostgreSQL service. Create a
database and least-privilege application role, then set:

```dotenv
ENABLE_POSTGRES=true
POSTGRES_URL=postgresql+asyncpg://app_user:replace-this@localhost:5432/app_db
AUTH_ENABLED=true
AUTH_JWT_SECRET_KEY=replace-with-at-least-32-random-characters
```

URL-encode reserved characters in a database password. The URL must use the
`postgresql+asyncpg://` SQLAlchemy driver. To generate a JWT signing secret:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

```sh
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Put the generated value in `.env` or a secret manager; never commit it. For a
local PostgreSQL server, `POSTGRES_URL` should use `localhost`. Containers use
the Compose service hostname `postgres` through `POSTGRES_DOCKER_URL`.

## Alembic migrations

Migrations are explicit and never run during API startup. With PostgreSQL
reachable and `.env` configured:

```sh
alembic heads
alembic history
alembic upgrade head
```

Create a schema revision after changing SQLAlchemy models:

```sh
alembic revision --autogenerate -m "describe schema change"
```

Review and edit the generated revision before applying it. Roll back one
revision with `alembic downgrade -1`; use `alembic downgrade <revision>` only
after reviewing the target and data impact. Do not run downgrade commands as a
routine setup step. Alembic reads the async PostgreSQL URL from application
settings and uses shared `Base.metadata` with model discovery.

## Bootstrap the first SUPER_ADMIN

After migrations, set `ENABLE_POSTGRES=true`, `POSTGRES_URL`,
`AUTH_ENABLED=true`, and a valid JWT secret. Then run:

```powershell
create-admin
```

or, without editable installation:

```sh
python -m app.modules.auth.cli
```

The command prompts for missing email, username, and password values; password
input is hidden. `ADMIN_EMAIL`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD` can be
provided through a secure environment/secret manager for non-interactive use.
The bootstrap is idempotent/concurrency-safe and will not silently promote an
existing user. No default administrator credentials exist.

## Full setup with AWS integrations

Keep AWS features disabled until each provider identity and permission is
ready. boto3 uses the standard AWS credential chain: workload IAM role, shared
credentials/config profile, web identity, or environment-provided credentials.
Static access keys are not required when roles or profiles are available. For
local development, configure `aws configure` or set `AWS_PROFILE`; do not put
AWS secrets in source or this example file.

### S3

Set `PROFILE_IMAGE_STORAGE_ENABLED=true`, `AWS_REGION`, and `AWS_S3_BUCKET`.
Create a private bucket with block-public-access enabled and grant the runtime
role only the required object operations for the application's key prefix.
Configure bucket CORS for the trusted browser origins and `POST` uploads,
including the required signed form fields and headers. The API constrains file
size/type, records owner metadata in PostgreSQL, and verifies the stored object
before completion. Keep URLs short-lived and bucket objects private.

### SES email

Set `BACKGROUND_JOBS_ENABLED=true`, `AUTH_EMAIL_DELIVERY_ENABLED=true`,
`AWS_REGION`, `AWS_SES_FROM_EMAIL`, `AUTH_PUBLIC_BASE_URL`,
`ENABLE_POSTGRES=true`, `POSTGRES_URL`, `REDIS_URL`, and
`BACKGROUND_PAYLOAD_ENCRYPTION_KEY`. Verify the SES sender identity in the
selected region. New SES accounts may be restricted to the sandbox, where
recipient identities must also be verified. Request production access before
sending to unverified recipients. Grant the role only the SES send operation
for the intended identity.

### SMS / mobile OTP

Set `BACKGROUND_JOBS_ENABLED=true`, `AUTH_SMS_DELIVERY_ENABLED=true`,
`AWS_REGION`, and `AWS_SMS_ORIGINATION_IDENTITY`, plus the shared PostgreSQL,
Redis, and outbox encryption settings above. Register the appropriate sender
identity and destination-country registrations with AWS End User Messaging SMS.
Grant only the required SMS send permission. Mobile numbers must be E.164.

### AWS permissions and local credentials

Use separate least-privilege roles for deployment environments. S3 needs only
the required `PutObject`, `HeadObject`, `GetObject`, and `DeleteObject` actions
for the application prefix; SES needs send permission; SMS needs the relevant
send permission. Scope resources to the configured bucket, sender identity, or
origination identity where AWS supports it. For local development use an AWS
profile or short-lived SSO credentials. Never paste access keys into command
history or commit them.

## Compose services

Configure `.env` first. The example supports local and container URLs
(`POSTGRES_URL`/`POSTGRES_DOCKER_URL` and `REDIS_URL`/`REDIS_DOCKER_URL`). The
Compose deployment starts API, PostgreSQL, Redis, worker, and Beat services;
configure a Fernet outbox key before enabling background jobs:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
docker compose up -d postgres redis
```

```sh
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
docker compose up -d postgres redis
```

Run `alembic upgrade head` from the host using a host-reachable PostgreSQL URL,
or run it from the API container after it is available. Then start the
application services with `docker compose up -d api worker beat`. Use
`docker compose logs -f api worker beat` to inspect service startup. In local
Windows development, Celery can use the solo pool in a separate terminal:

```powershell
celery -A app.worker.celery_app:celery_app worker --pool=solo --loglevel=INFO
celery -A app.worker.celery_app:celery_app beat --loglevel=INFO
```

## Tests and lint

```sh
ruff check .
pytest
```

The test suite includes mocked AWS provider tests. Tests requiring an actual
PostgreSQL server or AWS account are external integration checks and need those
services configured separately; ordinary unit/API tests should not send real
messages or upload objects.

## Common configuration errors

- **`POSTGRES_URL` required/invalid:** set `ENABLE_POSTGRES=true` and use an
  async driver URL beginning `postgresql+asyncpg://`.
- **Authentication secret rejected:** set `AUTH_JWT_SECRET_KEY` to a random
  value of at least 32 characters; auth also requires PostgreSQL.
- **AWS region/identity missing:** enable only the service being configured;
  provide its required region, bucket, SES sender, or SMS origination identity.
- **Delivery feature rejected:** email/SMS delivery requires background jobs,
  Redis, PostgreSQL, and the outbox encryption key; start worker and Beat.
- **S3 operation denied:** confirm the selected IAM identity, bucket region,
  private bucket policy, prefix permissions, and browser CORS rules.
- **Compose cannot resolve PostgreSQL/Redis:** use the Docker URLs with service
  names (`postgres`, `redis`) inside containers and localhost URLs from the host.
- **No interactive admin password:** use a terminal prompt or provide the
  `ADMIN_*` bootstrap values through a secure environment source.

See [API Reference](API_REFERENCE.md), [Deployment](DEPLOYMENT.md), and the
root [README](../README.md) for route and operational details.
