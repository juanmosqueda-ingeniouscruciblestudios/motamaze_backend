import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from google.auth.exceptions import TransportError
from google.auth.transport import requests as google_requests
from google.cloud.firestore import AsyncClient
from google.oauth2 import id_token as google_id_token


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
    token_hash: str,
    platform: str | None,
    os_version: str | None,
    app_version: str | None,
) -> str:
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    device: dict | None = {}
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
    return session_id
