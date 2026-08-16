# API reference

This repository is a reusable service foundation, not a business-domain API.

| Method | Path | Authorization | Use |
|---|---|---|---|
| GET | / | None | Service descriptor and version. |
| GET | /health/live | None | Container liveness probe. |
| GET | /health/ready | None | Dependency readiness probe. |
| GET | /health/deep | Internal only | Bounded dependency diagnostics. |

The foundation does not impose user authentication. The gateway or consuming service must add it. Domain routes are mounted below the configured `/api/v1` prefix.

Keep external fields camelCase, URL paths kebab-case, and internal Python names snake_case. Add domain API details to the consuming service's `docs/API.md`.
