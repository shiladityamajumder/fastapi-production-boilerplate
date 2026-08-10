# Jenkins deployment

`Jenkinsfile` validates, tests, builds, smoke-tests, optionally publishes, and
deploys the FastAPI image. The active deployment contains only the API service.
Celery worker and beat examples are commented out in `compose.deploy.yml`.

The repository currently has an incomplete quality baseline: pytest collects no
tests, and the existing application has Ruff and mypy findings. Consequently,
`ENFORCE_QUALITY_GATES` defaults to `false` and reports these stages as unstable
without blocking the image build. Set it to `true` as soon as those existing
findings and tests are addressed. Docker build and smoke/deployment health
checks always remain blocking.

## Jenkins prerequisites

The Jenkins agent must be Linux-based and provide:

- Docker Engine with access granted to the Jenkins user
- Docker Compose v2 (`docker compose`)
- Git
- Pipeline, Credentials Binding, JUnit, and Workspace Cleanup plugins
- network access to Python package indexes and the configured image registry

This pipeline deploys on the same Docker host that runs the Jenkins agent. For
a separate deployment host, use a dedicated Jenkins agent label for this job or
replace the deployment stage with the target platform's deployment command.

## Required credential

Create a Jenkins **Secret file** credential named `fastapi-production-env` (or
change `ENV_FILE_CREDENTIAL_ID`). Its content is the production `.env` file.
The pipeline installs it with mode `0600`; it is never added to an image or
printed in the build log. Jenkins removes the workspace copy during post-build
cleanup; the running container retains the environment supplied at creation.

For registry publishing, also create a Jenkins **Username with password**
credential, set `PUSH_IMAGE=true`, and provide `REGISTRY_HOST`,
`REGISTRY_CREDENTIAL_ID`, and a registry-qualified `IMAGE_REPOSITORY` such as
`registry.example.com/team/fastapi-service`.

## Job configuration

Create a Pipeline job using **Pipeline script from SCM** and set the script path
to `cicd/Jenkinsfile`. Builds always run checks and produce an immutable image
tag. Deployment runs only when `DEPLOY=true` and the checked-out branch is
`main`.

The deployed API must become Docker-healthcheck healthy within three minutes.
If it does not, Jenkins prints its logs and restores the previously deployed
image when one exists.

## Enabling Celery later

Before enabling the commented deployment blocks:

1. Enable Celery and the selected broker dependency in `requirements.txt`.
2. Enable the Celery and broker settings in `app/core/config.py`.
3. Enable the modules under `app/worker` and register real task modules.
4. Add `BACKGROUND_JOBS_ENABLED=true`, `CELERY_BROKER_URL`, and any result
   backend settings to the Jenkins-managed environment file.
5. Uncomment `worker` and `beat` in `compose.deploy.yml`.
6. Uncomment the multi-service deployment command in `Jenkinsfile` and disable
   the preceding API-only command.

Worker and beat remain separate processes from FastAPI and reuse the exact same
immutable application image.
