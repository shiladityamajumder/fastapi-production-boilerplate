"""Version-one account and authentication endpoints."""

from __future__ import annotations

from uuid import UUID  # noqa: TC003

from fastapi import APIRouter, Request, status

from app.common.response import (
    APIResponse,
    APIResponseModel,
    STANDARD_ERROR_RESPONSES,
)
from app.modules.auth.dependencies import AuthServiceDep, CurrentAdminDep, CurrentUserDep
from app.modules.auth.schemas import (
    AuthResult,
    ChangePasswordRequest,
    DeliveryQueuedResult,
    EmailRequest,
    FileDownloadResult,
    FileResult,
    FileUploadRequest,
    FileUploadResult,
    LoginRequest,
    MessageResult,
    OTPChallengeResult,
    OTPRequest,
    OTPVerifyRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
    TokenRequest,
    UserPublic,
)  # noqa: TC001

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    responses=STANDARD_ERROR_RESPONSES,
)


def _remote_address(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=APIResponseModel[UserPublic],
    summary="Register an account",
)
async def register(
    body: RegisterRequest,
    request: Request,
    service: AuthServiceDep,
) -> object:
    """Create a public USER account; callers cannot submit a role."""
    user = await service.register(body, remote_address=_remote_address(request))
    return APIResponse.success(
        data=user,
        message="Account created.",
        status_code=status.HTTP_201_CREATED,
    )


@router.post(
    "/login",
    response_model=APIResponseModel[AuthResult],
    summary="Sign in with email or username",
)
async def login(
    body: LoginRequest,
    request: Request,
    service: AuthServiceDep,
) -> object:
    """Authenticate using a normalized email or username."""
    result = await service.login(body, remote_address=_remote_address(request))
    return APIResponse.success(data=result, message="Signed in.")


@router.post(
    "/otp/request",
    response_model=APIResponseModel[OTPChallengeResult],
    summary="Request a mobile login code",
)
async def request_otp(
    body: OTPRequest,
    request: Request,
    service: AuthServiceDep,
) -> object:
    """Request a phone-login challenge through the configured SMS port."""
    challenge_id = await service.request_otp(
        body,
        remote_address=_remote_address(request),
    )
    return APIResponse.success(
        data=OTPChallengeResult(challenge_id=challenge_id),
        message="If deliverable, a code is queued for delivery.",
    )


@router.post(
    "/otp/verify",
    response_model=APIResponseModel[AuthResult],
    summary="Verify a mobile login code",
)
async def verify_otp(
    body: OTPVerifyRequest,
    request: Request,
    service: AuthServiceDep,
) -> object:
    """Verify a phone-login challenge and issue credentials."""
    result = await service.verify_otp(
        body,
        remote_address=_remote_address(request),
    )
    return APIResponse.success(data=result, message="Signed in.")


@router.post(
    "/refresh",
    response_model=APIResponseModel[TokenPair],
    summary="Rotate refresh tokens",
)
async def refresh(
    body: RefreshRequest,
    request: Request,
    service: AuthServiceDep,
) -> object:
    """Rotate the supplied refresh credential."""
    tokens = await service.refresh(
        body.refresh_token,
        remote_address=_remote_address(request),
    )
    return APIResponse.success(data=tokens, message="Tokens refreshed.")


@router.post("/logout", response_model=APIResponseModel[MessageResult])
async def logout(body: RefreshRequest, service: AuthServiceDep) -> object:
    """Revoke the supplied refresh session."""
    await service.logout(body.refresh_token)
    return APIResponse.success(data=MessageResult(), message="Signed out.")


@router.post("/logout-all", response_model=APIResponseModel[MessageResult])
async def logout_all(user: CurrentUserDep, service: AuthServiceDep) -> object:
    """Revoke all sessions and access tokens for the current account."""
    await service.logout_all(user.id)
    return APIResponse.success(data=MessageResult(), message="Signed out everywhere.")


@router.get(
    "/me",
    response_model=APIResponseModel[UserPublic],
    summary="Get the current account",
)
async def current_user(user: CurrentUserDep, service: AuthServiceDep) -> object:
    """Return the current account's public profile."""
    profile = await service.current_user(user.id)
    return APIResponse.success(data=profile, message="Account loaded.")


@router.post(
    "/password/forgot",
    response_model=APIResponseModel[DeliveryQueuedResult],
    summary="Request a password reset",
)
async def forgot_password(
    body: EmailRequest,
    request: Request,
    service: AuthServiceDep,
) -> object:
    """Request password recovery with an anti-enumeration response."""
    await service.request_password_reset(
        str(body.email),
        remote_address=_remote_address(request),
    )
    return APIResponse.success(
        data=DeliveryQueuedResult(),
        message="If the account can receive recovery mail, a request is pending.",
    )


@router.post(
    "/password/reset",
    response_model=APIResponseModel[MessageResult],
    summary="Reset a password",
)
async def reset_password(
    body: ResetPasswordRequest,
    service: AuthServiceDep,
) -> object:
    """Complete a password reset using a one-time email token."""
    await service.reset_password(body)
    return APIResponse.success(data=MessageResult(), message="Password updated.")


@router.post(
    "/password/change",
    response_model=APIResponseModel[MessageResult],
    summary="Change the current password",
)
async def change_password(
    body: ChangePasswordRequest,
    user: CurrentUserDep,
    service: AuthServiceDep,
) -> object:
    """Change a password for the authenticated account."""
    await service.change_password(user.id, body)
    return APIResponse.success(data=MessageResult(), message="Password updated.")


@router.post(
    "/email/verification/request",
    response_model=APIResponseModel[DeliveryQueuedResult],
    summary="Request email verification",
)
async def request_email_verification(
    user: CurrentUserDep,
    service: AuthServiceDep,
) -> object:
    """Request email verification delivery for the current account."""
    await service.request_email_verification(user.id)
    return APIResponse.success(
        data=DeliveryQueuedResult(),
        message="Verification instructions are queued.",
    )


@router.post(
    "/email/verification/confirm",
    response_model=APIResponseModel[UserPublic],
    summary="Confirm email verification",
)
async def verify_email(
    body: TokenRequest,
    service: AuthServiceDep,
) -> object:
    user = await service.verify_email(body.token)
    return APIResponse.success(data=user, message="Email verified.")


@router.post(
    "/mobile/verification/request",
    response_model=APIResponseModel[OTPChallengeResult],
    summary="Request mobile verification",
)
async def request_mobile_verification(
    body: OTPRequest,
    request: Request,
    user: CurrentUserDep,
    service: AuthServiceDep,
) -> object:
    """Start verification for a new E.164 mobile number."""
    challenge_id = await service.request_otp(
        body,
        remote_address=_remote_address(request),
        purpose="mobile_verify",
        user_id=user.id,
    )
    return APIResponse.success(
        data=OTPChallengeResult(challenge_id=challenge_id),
        message="Verification challenge and delivery are pending.",
    )


@router.post(
    "/mobile/verification/confirm",
    response_model=APIResponseModel[UserPublic],
    summary="Confirm mobile verification",
)
async def confirm_mobile_verification(
    body: OTPVerifyRequest,
    request: Request,
    user: CurrentUserDep,
    service: AuthServiceDep,
) -> object:
    """Confirm the current account's mobile number with a one-time code."""
    result = await service.verify_otp(
        body,
        remote_address=_remote_address(request),
        purpose="mobile_verify",
        user_id=user.id,
    )
    return APIResponse.success(data=result, message="Mobile number verified.")


@router.patch(
    "/me",
    response_model=APIResponseModel[UserPublic],
    summary="Update the current profile",
)
async def update_profile(
    body: ProfileUpdateRequest,
    user: CurrentUserDep,
    service: AuthServiceDep,
) -> object:
    """Update editable profile identifiers for the current account."""
    profile = await service.update_profile(user.id, body)
    return APIResponse.success(data=profile, message="Profile updated.")


@router.post(
    "/files/uploads",
    status_code=status.HTTP_201_CREATED,
    response_model=APIResponseModel[FileUploadResult],
    summary="Create a private file upload",
)
async def create_file_upload(
    body: FileUploadRequest,
    user: CurrentUserDep,
    service: AuthServiceDep,
) -> object:
    """Create a constrained private upload owned by the authenticated user."""
    result = await service.create_file_upload(user.id, body)
    return APIResponse.success(
        data=result,
        message="Upload initialized.",
        status_code=status.HTTP_201_CREATED,
    )


@router.post(
    "/files/{upload_id}/complete",
    response_model=APIResponseModel[FileResult],
    summary="Verify and complete a file upload",
)
async def complete_file_upload(
    upload_id: UUID,
    user: CurrentUserDep,
    service: AuthServiceDep,
) -> object:
    """Verify an uploaded S3 object and publish its metadata to the owner."""
    result: FileResult = await service.complete_file_upload(user.id, upload_id)
    return APIResponse.success(data=result, message="Upload verified.")


@router.get(
    "/files/{file_id}/download",
    response_model=APIResponseModel[FileDownloadResult],
    summary="Create a private download link",
)
async def get_file_download_url(
    file_id: UUID,
    user: CurrentUserDep,
    service: AuthServiceDep,
) -> object:
    """Return a short-lived download URL for an owned completed object."""
    result: FileDownloadResult = await service.file_download_url(user.id, file_id)
    return APIResponse.success(data=result, message="Download URL created.")


@router.delete(
    "/files/{file_id}",
    response_model=APIResponseModel[MessageResult],
    summary="Delete an owned file",
)
async def delete_file(
    file_id: UUID,
    user: CurrentUserDep,
    service: AuthServiceDep,
) -> object:
    """Delete an owned file and clear it when used as the profile image."""
    await service.delete_file(user.id, file_id)
    return APIResponse.success(data=MessageResult(), message="File deleted.")


@router.delete(
    "/me",
    response_model=APIResponseModel[MessageResult],
    summary="Deactivate the current account",
)
async def deactivate_account(user: CurrentUserDep, service: AuthServiceDep) -> object:
    """Deactivate the authenticated account."""
    await service.deactivate_account(user.id)
    return APIResponse.success(data=MessageResult(), message="Account deactivated.")


@router.get(
    "/admin/users/{user_id}",
    response_model=APIResponseModel[UserPublic],
    summary="Get a user profile as an administrator",
)
async def admin_get_user(
    user_id: UUID,
    _: CurrentAdminDep,
    service: AuthServiceDep,
) -> object:
    """Example protected account-management route for administrators."""
    profile = await service.current_user(user_id)
    return APIResponse.success(data=profile, message="Account loaded.")


__all__ = ["router"]
