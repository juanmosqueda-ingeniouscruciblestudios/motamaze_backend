import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from google.auth.transport import requests as google_requests
from google.cloud.firestore import AsyncClient
from google.oauth2 import id_token as google_id_token

from app.services import jwt_service


def _verify_google_token_sync(token: str, client_id: str) -> dict:
    return google_id_token.verify_oauth2_token(
        token,
        google_requests.Request(),
        audience=client_id,
    )


async def verify_google_token(token: str, client_id: str) -> dict:
    # verify_oauth2_token fetches Google certs over HTTPS — run in thread to avoid
    # blocking the async event loop.
    return await asyncio.to_thread(_verify_google_token_sync, token, client_id)


async def upsert_user(
    db: AsyncClient,
    sub: str,
    email: str,
    display_name: str,
    photo_url: str | None,
    provider: str,
) -> tuple[str, bool]:
    now = datetime.now(timezone.utc)
    ref = db.collection("users").document(sub)
    snap = await ref.get()
    is_new = not snap.exists
    if is_new:
        await ref.set({
            "uid": sub,
            "email": email,
            "display_name": display_name,
            "photo_url": photo_url,
            "created_at": now,
            "updated_at": now,
            "equipped_skin": None,
            "delete_requested_at": None,
            "consent": {
                "coppa_compliant": False,
                "gdpr_consent": None,
                "ccpa_opt_out": False,
                "age_verified_at": None,
            },
        })
    else:
        await ref.update({
            "email": email,
            "display_name": display_name,
            "photo_url": photo_url,
            "updated_at": now,
        })
    return sub, is_new


async def create_session(
    db: AsyncClient,
    uid: str,
    session_id: str,
    token_hash: str,
    platform: str | None,
    os_version: str | None,
    app_version: str | None,
) -> None:
    now = datetime.now(timezone.utc)
    device: dict = {}
    if platform:
        device["platform"] = platform
    if os_version:
        device["os_version"] = os_version
    if app_version:
        device["app_version"] = app_version
    await db.collection("sessions").document(session_id).set({
        "session_id": session_id,
        "uid": uid,
        "token_hash": token_hash,
        "started_at": now,
        "expires_at": now + timedelta(days=14),
        "ended_at": None,
        "duration_secs": None,
        "device": device or None,
    })


async def consume_refresh_session(
    db: AsyncClient, refresh_token: str
) -> tuple[str, dict]:
    """Validates and deletes the session atomically. Returns (uid, session_data).
    Raises ValueError on invalid, expired, or mismatched token."""
    try:
        session_id, secret = jwt_service.extract_session_and_secret(refresh_token)
    except ValueError:
        raise ValueError("AUTH_REFRESH_INVALID")

    snap = await db.collection("sessions").document(session_id).get()
    if not snap.exists:
        raise ValueError("AUTH_REFRESH_INVALID")

    session = snap.to_dict()

    if datetime.now(timezone.utc) > session["expires_at"]:
        raise ValueError("AUTH_REFRESH_EXPIRED")

    if not jwt_service.verify_refresh_token(secret, session["token_hash"]):
        raise ValueError("AUTH_REFRESH_INVALID")

    # Delete old session immediately — prevents replay attacks.
    await db.collection("sessions").document(session_id).delete()

    return session["uid"], session


async def revoke_session(
    db: AsyncClient,
    session_id: str,
    jti: str,
    jti_exp: datetime,
) -> tuple[datetime, int | None]:
    """Marks session as ended and adds JTI to the revocation list.
    Returns (ended_at, duration_secs) for BQ session_durations row."""
    now = datetime.now(timezone.utc)
    duration: int | None = None

    snap = await db.collection("sessions").document(session_id).get()
    if snap.exists:
        data = snap.to_dict()
        started_at = data.get("started_at")
        duration = int((now - started_at).total_seconds()) if started_at else None
        await db.collection("sessions").document(session_id).update({
            "ended_at": now,
            "duration_secs": duration,
        })

    # expires_at drives the Firestore TTL policy — auto-deletes after token expiry.
    await db.collection("revoked_jtis").document(jti).set({
        "revoked_at": now,
        "expires_at": jti_exp,
    })

    return now, duration


async def get_pending_oauth(db: AsyncClient, state_token: str) -> dict | None:
    """Returns the OAuth pending state, or None if not found / expired."""
    snap = await db.collection("oauth_pending").document(state_token).get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    if datetime.now(timezone.utc) > data.get("expires_at", datetime.min.replace(tzinfo=timezone.utc)):
        return None
    return data
