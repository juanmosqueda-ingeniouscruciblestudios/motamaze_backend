import logging
import uuid
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from google.cloud.firestore import AsyncClient
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_firestore_client, get_settings, verify_jwt
from app.services import auth_service, email_service, jwt_service
from app.services import geo_service
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
    # Signal 1 (primary): Google Play BillingConfig.countryCode — wired in T-252
    store_country_code: str | None = None
    # Signal 2 (secondary): Godot OS.get_locale_country()
    device_country_code: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 900
    user_id: str
    is_new_user: bool
    is_child: bool | None = None


class AgeVerifyRequest(BaseModel):
    dob: str  # YYYY-MM-DD


class AgeVerifyResponse(BaseModel):
    is_child: bool
    consent_age_threshold: int


class ParentalConsentRequestBody(BaseModel):
    parent_email: str


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
    request: Request,
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

    # Signal 3: IP corroboration (server-side, never overrides primary)
    client_ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    ip_country = await geo_service.get_ip_country(client_ip, settings.geoip2_db_path) if client_ip else None

    resolved_country, signal_mismatch = geo_service.resolve_country(
        body.store_country_code, body.device_country_code, ip_country
    )
    age_threshold = geo_service.consent_age_threshold(resolved_country)

    user_id, is_new_user, is_child = await auth_service.upsert_user(
        db, sub, email, display_name, photo_url, body.provider,
        country_code=resolved_country,
        consent_age_threshold=age_threshold,
        country_signal_mismatch=signal_mismatch,
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
            "country": resolved_country or "",
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
        is_child=is_child,
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
# POST /auth/age-verify  (T-401 ST-01)
# ---------------------------------------------------------------------------

@router.post("/age-verify", response_model=AgeVerifyResponse)
async def age_verify(
    body: AgeVerifyRequest,
    claims: dict = Depends(verify_jwt),
    db: AsyncClient = Depends(get_firestore_client),
):
    user_id = claims["uid"]

    try:
        dob = date.fromisoformat(body.dob)
    except ValueError:
        raise HTTPException(
            400,
            detail={"error_code": "AGE_VERIFY_INVALID_DOB", "message": "dob must be YYYY-MM-DD"},
        )

    today = date.today()
    if dob >= today:
        raise HTTPException(
            400,
            detail={"error_code": "AGE_VERIFY_INVALID_DOB", "message": "dob must be in the past"},
        )

    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    if age > 120:
        raise HTTPException(
            400,
            detail={"error_code": "AGE_VERIFY_INVALID_DOB", "message": "dob is not plausible"},
        )

    ref = db.collection("users").document(user_id)
    snap = await ref.get()
    if not snap.exists:
        raise HTTPException(
            404,
            detail={"error_code": "USER_NOT_FOUND", "message": "User not found"},
        )

    data = snap.to_dict() or {}
    threshold = (data.get("consent") or {}).get("consent_age_threshold", 13)
    is_child = age < threshold
    now = datetime.now(timezone.utc)

    # Write result — raw DOB is not stored (data minimization per COPPA/LGPD/LFPDPPP)
    await ref.update({
        "consent.is_child": is_child,
        "consent.age_verified_at": now,
        "restricted_features": {
            "leaderboard": is_child,
            "personalized_ads": is_child,
            "share_score": is_child,
        },
    })

    return AgeVerifyResponse(is_child=is_child, consent_age_threshold=threshold)


# ---------------------------------------------------------------------------
# POST /auth/parental-consent/request  (T-401 ST-03)
# ---------------------------------------------------------------------------

@router.post("/parental-consent/request", status_code=202)
async def parental_consent_request(
    body: ParentalConsentRequestBody,
    claims: dict = Depends(verify_jwt),
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
    user_id = claims["uid"]

    if "@" not in body.parent_email or "." not in body.parent_email.split("@")[-1]:
        raise HTTPException(
            400,
            detail={"error_code": "CONSENT_INVALID_EMAIL", "message": "parent_email is not a valid email address"},
        )

    snap = await db.collection("users").document(user_id).get()
    if not snap.exists:
        raise HTTPException(404, detail={"error_code": "USER_NOT_FOUND"})

    data = snap.to_dict() or {}
    consent = data.get("consent") or {}

    if consent.get("is_child") is not True:
        raise HTTPException(
            400,
            detail={"error_code": "CONSENT_NOT_REQUIRED", "message": "User has not been identified as a minor"},
        )

    if consent.get("coppa_compliant") is True:
        return {"message": "Parental consent already verified"}

    consent_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)

    await db.collection("parental_consents").document(consent_token).set({
        "uid": user_id,
        "parent_email": body.parent_email,
        "created_at": now,
        "expires_at": now + timedelta(hours=72),
        "status": "pending",
    })

    consent_url = (
        f"{settings.parental_consent_base_url}/auth/parental-consent/verify?token={consent_token}"
    )
    child_name = data.get("display_name") or "your child"

    try:
        await email_service.send_parental_consent_email(
            to_email=body.parent_email,
            child_name=child_name,
            consent_url=consent_url,
            api_key=settings.sendgrid_api_key,
            from_email=settings.sendgrid_from_email,
            company_website_url=settings.company_website_url,
            privacy_email=settings.privacy_email,
        )
    except Exception as exc:
        logger.error("parental_consent: email send failed uid=%s err=%s", user_id, exc)
        raise HTTPException(
            503,
            detail={"error_code": "CONSENT_EMAIL_FAILED", "message": "Failed to send consent email, please try again"},
        )

    return {"message": "Consent email sent"}


# ---------------------------------------------------------------------------
# GET /auth/parental-consent/verify  (T-401 ST-03) — public, parent clicks link
# ---------------------------------------------------------------------------

@router.get("/parental-consent/verify", response_class=HTMLResponse)
async def parental_consent_verify(
    token: str = Query(...),
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
    snap = await db.collection("parental_consents").document(token).get()

    if not snap.exists:
        return HTMLResponse(_consent_page_error(
            "Link Not Found",
            "This consent link is invalid or has already been used.",
            settings.privacy_email,
        ), status_code=404)

    data = snap.to_dict() or {}
    now = datetime.now(timezone.utc)

    if now > data.get("expires_at", now):
        return HTMLResponse(_consent_page_error(
            "Link Expired",
            "This consent link has expired (valid for 72 hours). "
            "Please ask your child to request a new one from the MotaMaze app.",
            settings.privacy_email,
        ), status_code=410)

    if data.get("status") == "approved":
        return HTMLResponse(_consent_page_success(already_done=True, company_website_url=settings.company_website_url))

    uid = data["uid"]
    await db.collection("parental_consents").document(token).update({"status": "approved"})
    await db.collection("users").document(uid).update({
        "consent.coppa_compliant": True,
        "consent.parental_consent_verified_at": now,
    })

    return HTMLResponse(_consent_page_success(already_done=False, company_website_url=settings.company_website_url))


def _consent_page_success(already_done: bool, company_website_url: str) -> str:
    msg = "Already approved." if already_done else "Thank you! The account has been approved."
    detail = (
        "This account was already verified previously."
        if already_done else
        "Your child can now use MotaMaze. Their account will not show personalized ads "
        "or appear on public leaderboards."
    )
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MotaMaze — Consent Approved</title>
<style>body{{font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:40px 16px;}}
.card{{background:#fff;border-radius:8px;max-width:480px;margin:0 auto;padding:32px;text-align:center;}}
h1{{color:#1a7340;font-size:22px;}} p{{color:#444;line-height:1.6;}}</style></head>
<body><div class="card"><h1>&#10003; {msg}</h1><p>{detail}</p>
<p style="margin-top:24px;font-size:13px;color:#888;">
Ingenious Crucible Studios &mdash; <a href="{company_website_url}">MotaMaze</a></p>
</div></body></html>"""


def _consent_page_error(title: str, detail: str, privacy_email: str) -> str:
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MotaMaze — {title}</title>
<style>body{{font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:40px 16px;}}
.card{{background:#fff;border-radius:8px;max-width:480px;margin:0 auto;padding:32px;text-align:center;}}
h1{{color:#b91c1c;font-size:22px;}} p{{color:#444;line-height:1.6;}}</style></head>
<body><div class="card"><h1>{title}</h1><p>{detail}</p>
<p style="margin-top:24px;font-size:13px;color:#888;">
Questions? <a href="mailto:{privacy_email}">{privacy_email}</a></p>
</div></body></html>"""


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
