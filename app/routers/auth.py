import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from google.cloud.firestore import AsyncClient
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_firestore_client, get_settings, verify_jwt
from app.services import auth_service, jwt_service
from app.services.bq_streaming import stream_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

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


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 900


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    background_tasks: BackgroundTasks,
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

    session_id = str(uuid.uuid4())
    refresh_tok = jwt_service.create_refresh_token(session_id)
    _, secret = jwt_service.extract_session_and_secret(refresh_tok)
    token_hash = jwt_service.hash_refresh_token(secret)

    await auth_service.create_session(
        db, user_id, session_id, token_hash, body.platform, body.os_version, body.app_version
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

    now = datetime.now(timezone.utc)
    background_tasks.add_task(
        stream_event, "login_events",
        {
            "event_timestamp": now.isoformat(),
            "event_date": now.date().isoformat(),
            "user_id": user_id,
            "session_id": session_id,
            "platform": body.platform,
            "app_version": body.app_version,
            "country": body.country or "",
            "login_method": f"{body.provider}_oauth",
            "is_new_user": is_new_user,
            "age_verified": False,
            "device_model": body.device_model or "",
            "os_version": body.os_version or "",
        },
        settings.gcp_project_id, settings.bq_dataset,
        row_id=f"login_{session_id}",
    )
    background_tasks.add_task(
        stream_event, "session_durations",
        {
            "event_timestamp": now.isoformat(),
            "event_date": now.date().isoformat(),
            "session_id": session_id,
            "user_id": user_id,
            "platform": body.platform,
            "app_version": body.app_version,
            "event_type": "session_start",
            "session_duration_secs": None,
        },
        settings.gcp_project_id, settings.bq_dataset,
        row_id=f"session_{session_id}_start",
    )

    return LoginResponse(
        access_token=access_tok,
        refresh_token=refresh_tok,
        user_id=user_id,
        is_new_user=is_new_user,
    )


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------

@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
    if not body.refresh_token:
        raise HTTPException(
            400,
            detail={"error_code": "AUTH_MISSING_FIELDS", "message": "refresh_token is required"},
        )

    try:
        uid, old_session = await auth_service.consume_refresh_session(db, body.refresh_token)
    except ValueError as exc:
        error_code = str(exc)
        status = 401
        raise HTTPException(status, detail={"error_code": error_code, "message": error_code})

    provider = old_session.get("device", {}) and "google"  # provider not stored in session — default google for MVP

    new_session_id = str(uuid.uuid4())
    new_refresh = jwt_service.create_refresh_token(new_session_id)
    _, secret = jwt_service.extract_session_and_secret(new_refresh)
    token_hash = jwt_service.hash_refresh_token(secret)

    device = old_session.get("device") or {}
    await auth_service.create_session(
        db,
        uid,
        new_session_id,
        token_hash,
        device.get("platform"),
        device.get("os_version"),
        device.get("app_version"),
    )

    access_tok, _jti = jwt_service.create_access_token(
        user_id=uid,
        provider="google",
        session_id=new_session_id,
        project_id=settings.gcp_project_id,
        secret_name=settings.jwt_secret_name,
        key_id=settings.jwt_key_id,
        issuer=settings.jwt_issuer,
    )

    return RefreshResponse(access_token=access_tok, refresh_token=new_refresh)


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

@router.post("/logout")
async def logout(
    background_tasks: BackgroundTasks,
    claims: dict = Depends(verify_jwt),
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
    jti = claims["jti"]
    session_id = claims.get("sid", "")
    user_id = claims.get("uid", "")
    exp_ts = claims.get("exp", 0)
    jti_exp = datetime.fromtimestamp(exp_ts, tz=timezone.utc)

    ended_at, duration_secs = await auth_service.revoke_session(db, session_id, jti, jti_exp)

    background_tasks.add_task(
        stream_event, "session_durations",
        {
            "event_timestamp": ended_at.isoformat(),
            "event_date": ended_at.date().isoformat(),
            "session_id": session_id,
            "user_id": user_id,
            "platform": None,
            "app_version": None,
            "event_type": "session_end",
            "session_duration_secs": duration_secs,
        },
        settings.gcp_project_id, settings.bq_dataset,
        row_id=f"session_{session_id}_end",
    )

    return {"message": "Session revoked"}


# ---------------------------------------------------------------------------
# GET /auth/pending/{state_token}
# ---------------------------------------------------------------------------

@router.get("/pending/{state_token}")
async def pending(
    state_token: str,
    db: AsyncClient = Depends(get_firestore_client),
):
    state = await auth_service.get_pending_oauth(db, state_token)
    if state is None:
        raise HTTPException(
            404,
            detail={"error_code": "AUTH_STATE_NOT_FOUND", "message": "State token not found or expired"},
        )
    return state


# ---------------------------------------------------------------------------
# DELETE /auth/account  (DATA-002 ST-10 / T-123)
# ---------------------------------------------------------------------------

@router.delete("/account")
async def delete_account(
    background_tasks: BackgroundTasks,
    claims: dict = Depends(verify_jwt),
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
    user_id = claims.get("uid", "")
    jti = claims["jti"]
    session_id = claims.get("sid", "")
    exp_ts = claims.get("exp", 0)
    jti_exp = datetime.fromtimestamp(exp_ts, tz=timezone.utc)

    # 409 if deletion already pending
    user_snap = await db.collection("users").document(user_id).get()
    if user_snap.exists:
        data = user_snap.to_dict() or {}
        if data.get("delete_requested_at") is not None:
            raise HTTPException(
                409,
                detail={"error_code": "AUTH_DELETION_PENDING", "message": "Account deletion already in progress"},
            )

    now = datetime.now(timezone.utc)
    deletion_id = f"del_{uuid.uuid4().hex[:8]}"

    # Mark user synchronously — source of truth for duplicate check
    await db.collection("users").document(user_id).update({"delete_requested_at": now})

    # Revoke current session immediately
    await auth_service.revoke_session(db, session_id, jti, jti_exp)

    # BQ: account_deletions row (best-effort background task)
    background_tasks.add_task(
        stream_event, "account_deletions",
        {
            "requested_at": now.isoformat(),
            "request_date": now.date().isoformat(),
            "user_id": user_id,
            "platform": None,
            "request_source": "user_request",
            "status": "pending",
            "completed_at": None,
            "tables_purged": [],
            "notes": deletion_id,
        },
        settings.gcp_project_id, settings.bq_dataset,
        row_id=f"deletion_{user_id}",
    )

    return JSONResponse(
        status_code=202,
        content={"message": "Account deletion queued", "deletion_id": deletion_id},
    )
