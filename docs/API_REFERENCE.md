# API Reference

This reference describes routes registered by `app.main:create_app` with the
default API prefix `/api/v1`. Successful API responses use the common envelope
`{ "success": true, "message": "...", "data": ..., "error": null,
"meta": { "request_id": "...", "correlation_id": "...", "api_version":
"v1", "timestamp": "...", "pagination": null } }`. Errors use the same
envelope with `success: false`, `data: null`, and an `error` object containing a
stable `code` and optional `details`. Request validation errors are HTTP 422.

Authentication uses `Authorization: Bearer <access_token>` for protected
routes. Refresh credentials are sent in JSON bodies. Examples omit envelope
metadata for readability. Registration is available only when `AUTH_ENABLED`
is true and PostgreSQL is configured. Email, SMS, and file endpoints also
require their corresponding delivery/storage flags and provider configuration.

## Authentication and JWT

Public routes are marked **Public**. Protected routes require an active account
and a valid bearer access token. Password inputs have a 12–128 character
schema limit (the configured minimum cannot be lower than 12); usernames are
3–32 ASCII letters, digits, dots, underscores, or dashes; mobile numbers use
E.164; OTP codes are six digits. Resource identifiers in path parameters are
UUIDs. Email fields use Pydantic email validation.

| Method and path | Purpose | Access |
|---|---|---|
| `POST /api/v1/auth/register` | Create a public `USER` account. | Public |
| `POST /api/v1/auth/login` | Login by email or username and password. | Public |
| `POST /api/v1/auth/otp/request` | Request a mobile login challenge. | Public; SMS feature required |
| `POST /api/v1/auth/otp/verify` | Verify challenge and issue access/refresh tokens. | Public; challenge must be live and within attempt limit |
| `POST /api/v1/auth/refresh` | Rotate a refresh token. | Refresh token in request body |
| `POST /api/v1/auth/logout` | Revoke the supplied refresh session. | Refresh token in request body |
| `POST /api/v1/auth/logout-all` | Revoke sessions for the current account. | Bearer token |
| `GET /api/v1/auth/me` | Read the current public account. | Bearer token |
| `POST /api/v1/auth/password/forgot` | Start password recovery; response avoids account enumeration. | Public; email delivery required to deliver |
| `POST /api/v1/auth/password/reset` | Use a one-time reset token and new password. | Reset token in body |
| `POST /api/v1/auth/password/change` | Change current account password. | Bearer token |
| `DELETE /api/v1/auth/me` | Deactivate the current account. | Bearer token |

Examples:

```http
POST /api/v1/auth/register
Content-Type: application/json
```

```json
{"email":"person@example.test","username":"person_1","password":"Replace-With-A-Long-Password"}
```

```json
{"identifier":"person@example.test","password":"Replace-With-A-Long-Password"}
```

Login returns `data.tokens` (`access_token`, `refresh_token`, `token_type`,
`expires_in`) and a public `data.user`. Registration returns a user without
credentials. OTP request returns a challenge ID and `delivery_status: pending`;
it never returns the code. OTP verify body:

```json
{"mobile_number":"+14155550123","challenge_id":"00000000-0000-4000-8000-000000000001","code":"123456"}
```

Refresh and logout body: `{"refresh_token":"<opaque refresh token>"}`.
Forgot-password body: `{"email":"person@example.test"}`. Reset body:
`{"token":"<one-time token>","new_password":"Replace-With-A-Long-Password"}`.
Change-password body accepts optional `current_password` and requires
`new_password`.

## User management

| Method and path | Purpose | Access |
|---|---|---|
| `POST /api/v1/auth/email/verification/request` | Queue email verification instructions. | Bearer token; email delivery enabled |
| `POST /api/v1/auth/email/verification/confirm` | Confirm a one-time email token. | Token in body |
| `POST /api/v1/auth/mobile/verification/request` | Start verification for an E.164 number. | Bearer token; SMS delivery enabled |
| `POST /api/v1/auth/mobile/verification/confirm` | Confirm challenge and code. | Bearer token; six-digit code |
| `PATCH /api/v1/auth/me` | Update current profile username/mobile number. | Bearer token |
| `GET /api/v1/auth/admin/users/{user_id}` | Read a user profile through the legacy admin route. | Bearer token with `ADMIN` or `SUPER_ADMIN` role |

Email request returns `delivery_status: pending`; this is queue status and does
not assert provider delivery. Email confirm body is `{"token":"<one-time token>"}`.
Profile updates accept optional `username` and `mobile_number`; uniqueness and
E.164 validation apply. Public registration cannot assign a role.

## Admin and RBAC

All routes below require bearer authentication plus the listed permission.
Role-to-permission assignments are enforced server-side; `SUPER_ADMIN` has the
administrative permissions and only `SUPER_ADMIN` may grant administrative
roles. The `USER` role has no admin permissions.

| Method and path | Purpose | Required permission |
|---|---|---|
| `GET /api/v1/admin/users` | Search, filter, paginate, and sort users. | `users:read` |
| `GET /api/v1/admin/users/{user_id}` | Read user details. | `users:read` |
| `POST /api/v1/admin/users` | Create an account with an authorized role. | `users:create` |
| `PATCH /api/v1/admin/users/{user_id}` | Update account details. | `users:update` |
| `PUT /api/v1/admin/users/{user_id}/role` | Change role; last active super-admin protections apply. | `users:roles:assign` |
| `POST /api/v1/admin/users/{user_id}/activate` | Activate account. | `users:status` |
| `POST /api/v1/admin/users/{user_id}/deactivate` | Deactivate account and revoke sessions. | `users:status` |
| `POST /api/v1/admin/users/{user_id}/sessions/revoke` | Revoke target sessions. | `users:sessions:revoke` |
| `GET /api/v1/admin/users/{user_id}/activity` | View activity for a user. | `users:activity:read` |
| `GET /api/v1/admin/audit` | Search audit history. | `audit:read` |

List users supports `search` (up to 100 characters), `role`, `is_active`,
`sort_by` (`created_at`, `email`, `username`, or `role`), `sort_order` (`asc`
or `desc`), `limit`, and `offset`. User-list pagination defaults to `limit=20`
and `offset=0`, with `limit` 1–100 and `offset` 0–100000. Audit/activity
supports `limit` 1–100, `offset` ≥0 and, for audit search, optional
`target_user_id` and `actor_user_id`. Invalid filter or sort values return 422. Self-demotion,
self-deactivation, and removal of the last active `SUPER_ADMIN` are rejected.

Admin create body:

```json
{"email":"new-user@example.test","username":"new_user","mobile_number":"+14155550123","password":"Optional-Long-Password","role":"USER"}
```

Fields shown as optional may be omitted; role is one of `USER`, `ADMIN`, or
`SUPER_ADMIN`, subject to permission checks. Admin role body is `{"role":"USER"}`.

Admin detail updates accept one or more of email, username, and mobile number;
role and status changes use dedicated endpoints:

```json
{"username":"renamed_user"}
```

Profile update body example:

```json
{"username":"renamed_user","mobile_number":"+14155550123"}
```

Change-password body example:

```json
{"current_password":"Current-Long-Password","new_password":"New-Long-Password"}
```

## File uploads and AWS S3

| Method and path | Purpose | Access |
|---|---|---|
| `POST /api/v1/auth/files/uploads` | Create a constrained private S3 upload form and ownership record. | Bearer token; `PROFILE_IMAGE_STORAGE_ENABLED=true` |
| `POST /api/v1/auth/files/{upload_id}/complete` | Verify S3 object metadata and complete upload. | Bearer token; owner only |
| `GET /api/v1/auth/files/{file_id}/download` | Create a short-lived private download URL. | Bearer token; owner only |
| `DELETE /api/v1/auth/files/{file_id}` | Delete owned file and clear profile reference when applicable. | Bearer token; owner only |

Create body: `{"category":"profile_image","content_type":"image/png","size":2048}`.
Category is `profile_image` or `file`; `size` is positive and at most the
request schema cap of 50 MiB (the configured S3 cap defaults to 5 MiB and may
be lower). Profile images support JPEG, PNG, and WebP; generic files also
support PDF and plain text. The API returns a presigned POST `url`,
form `fields`, and `expires_in`; the client posts the file directly to S3, then
calls completion with no body. Stored objects are private. API success does not
expose an object path as an authorization mechanism.

## Email and OTP verification

Email/password reset use the routes under `/auth/email/verification` and
`/auth/password`; mobile verification uses `/auth/mobile/verification`. Login
OTP uses `/auth/otp`. Delivery endpoints are feature-dependent. Disabled
delivery/storage ports fail safely; responses report pending only when a
notification has been accepted into the configured outbox. OTP values and
one-time tokens are not returned or logged.

## Health and system

| Method and path | Purpose | Authentication |
|---|---|---|
| `GET /` | Service/API discovery descriptor. | Public |
| `GET /health/live` | Process liveness; no dependency checks. | Public |
| `GET /health/ready` | Startup readiness and enabled dependency availability, including PostgreSQL. | Public |
| `GET /health/deep` | Sanitized per-dependency diagnostics when deep health is enabled. | Public |

Readiness returns 503 until startup completes or a required enabled dependency
is unavailable. Deep health can return 503 when a dependency check fails. The
responses do not include credentials, connection strings, or stack traces.

## OpenAPI and common errors

In non-production, Swagger UI is `/docs`, ReDoc is `/redoc`, and the schema is
`/openapi.json`. These routes are disabled when `ENVIRONMENT=production`.
Protected routes expose HTTP bearer security in OpenAPI. All route response
models use the shared response envelope; common errors include 401
`AUTHENTICATION_REQUIRED`, 403 `PERMISSION_DENIED`, 404 resource/route not
found, 409 conflicts, 422 validation failures, 429 rate limits, and 503
dependency unavailability. Exact error codes and status depend on the failure.

## Other implemented modules

The example module is not currently mounted in the v1 router, so it has no
public endpoints. Worker task and CLI commands are operational interfaces, not
HTTP endpoints. Use `create-admin` only for initial super-admin bootstrap.
