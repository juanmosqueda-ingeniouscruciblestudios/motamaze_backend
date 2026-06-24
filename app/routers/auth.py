import logging

from fastapi import APIRouter, Depends, HTTPException
from google.cloud.firestore import AsyncClient
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_firestore_client, get_settings
from app.services import auth_service, jwt_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    provider: str
    id_token: str
    platform: str
    app_version: str
    device_model: str | None = None
    os_version: str | None = None
    country: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 900
    user_id: str
    is_new_user: bool


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
    if body.provider == "google":
        try:
            claims = await auth_service.verify_google_token(
                body.id_token, settings.google_oauth_client_id
            )
        except ValueError as exc:
            msg = str(exc).lower()
            if "expired" in msg:
                raise HTTPException(
                    401,
                    detail={"error_code": "AUTH_TOKEN_EXPIRED", "message": "id_token has expired"},
                )
            raise HTTPException(
                401,
                detail={"error_code": "AUTH_TOKEN_INVALID", "message": "id_token verification failed"},
            )
        sub = claims["sub"]
        email = claims.get("email", "")
        display_name = claims.get("name", "")
        photo_url = claims.get("picture")

    elif body.provider == "apple":
        raise HTTPException(
            501,
            detail={"error_code": "NOT_IMPLEMENTED", "message": "Apple sign-in not yet implemented"},
        )
    else:
        raise HTTPException(
            400,
            detail={"error_code": "AUTH_MISSING_FIELDS", "message": f"Unknown provider: {body.provider}"},
        )

    user_id, is_new_user = await auth_service.upsert_user(
        db, sub, email, display_name, photo_url, body.provider
    )

    refresh_tok = jwt_service.create_refresh_token()
    token_hash = jwt_service.hash_refresh_token(refresh_tok)

    session_id = await auth_service.create_session(
        db, user_id, token_hash, body.platform, body.os_version, body.app_version
    )

    access_tok, _jti = jwt_service.create_access_token(
        user_id=user_id,
        provider=body.provider,
        session_id=session_id,
        project_id=settings.gcp_project_id,
        secret_name=settings.jwt_secret_name,
        key_id=settings.jwt_key_id,
        issuer=settings.jwt_issuer,
    )

    return LoginResponse(
        access_token=access_tok,
        refresh_token=refresh_tok,
        user_id=user_id,
        is_new_user=is_new_user,
    )


# POST /auth/refresh           — T-122
# GET  /auth/pending/{state}   — T-122
# POST /auth/logout            — T-122
# DELETE /auth/account         — T-123
