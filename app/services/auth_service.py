import asyncio
import json
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from cachetools import TTLCache
from google.auth.transport import requests as google_requests
from google.cloud.firestore import AsyncClient
from google.oauth2 import id_token as google_id_token
from jose import ExpiredSignatureError, JWTError, jwk
from jose import jwt as jose_jwt

from app.services import geo_service, jwt_service


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


_APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
_APPLE_ISSUER = "https://appleid.apple.com"
_apple_jwks_cache: TTLCache = TTLCache(maxsize=1, ttl=3600)


async def _get_apple_jwks() -> list[dict]:
    if "keys" in _apple_jwks_cache:
        return _apple_jwks_cache["keys"]

    def _fetch() -> list[dict]:
        with urllib.request.urlopen(_APPLE_JWKS_URL, timeout=5) as r:
            return json.loads(r.read())["keys"]

    keys = await asyncio.to_thread(_fetch)
    _apple_jwks_cache["keys"] = keys
    return keys


async def verify_apple_token(token: str, audience: str) -> dict:
    """Verifies an Apple `identity_token` (JWT) against Apple's published JWKS.
    Mirrors verify_google_token's error contract: raises ValueError whose message
    contains 'expired' iff the failure was expiry (app/routers/auth.py branches on
    this to pick AUTH_TOKEN_EXPIRED vs AUTH_TOKEN_INVALID)."""
    try:
        header = jose_jwt.get_unverified_header(token)
    except JWTError:
        raise ValueError("Malformed Apple identity_token")

    kid = header.get("kid")
    keys = await _get_apple_jwks()
    key_data = next((k for k in keys if k.get("kid") == kid), None)
    if key_data is None:
        # Same pattern as leaderboard.py's App Check JWKS handling: clear and let
        # the *next* request refresh, avoids hammering Apple's JWKS mid-request.
        _apple_jwks_cache.clear()
        raise ValueError("Unknown Apple signing key (kid) — JWKS refreshed")

    public_key = jwk.construct(key_data)
    try:
        claims = jose_jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=_APPLE_ISSUER,
            options={"leeway": 30},
        )
    except ExpiredSignatureError:
        raise ValueError("Apple identity_token has expired")
    except JWTError as exc:
        raise ValueError(f"Apple identity_token verification failed: {exc}")

    return claims


async def upsert_user(
    db: AsyncClient,
    sub: str,
    email: str,
    display_name: str,
    photo_url: str | None,
    provider: str,
    country_code: str | None = None,
    consent_age_threshold: int = 13,
    country_signal_mismatch: bool = False,
    store_age_signal: str | None = None,
    store_age_signal_source: str | None = None,
) -> tuple[str, bool, bool | None]:
    now = datetime.now(timezone.utc)
    ref = db.collection("users").document(sub)
    snap = await ref.get()
    is_new = not snap.exists

    # T-402: in Brazil, a store/OS age-band signal outranks the DOB flow
    # (T-401) — Digital ECA prohibits self-declaration as the deciding
    # signal there. None for every other country (or an unparseable/absent
    # signal), which leaves DOB as the sole determinant, unchanged.
    signal_is_minor = None
    if country_code == "BR":
        signal_is_minor = geo_service.store_age_signal_is_minor(store_age_signal, consent_age_threshold)

    if is_new:
        doc_payload: dict = {
            "uid": sub,
            "provider": provider,
            "email": email,
            "display_name": display_name,
            "photo_url": photo_url,
            "created_at": now,
            "updated_at": now,
            "equipped_skin": None,
            "delete_requested_at": None,
            "consent": {
                # (signal_is_minor is False) is True only when the signal
                # confirmed an adult — mirrors age_verify's adult-auto-compliant
                # rule; stays False (default) when signal_is_minor is None/True.
                "coppa_compliant": signal_is_minor is False,
                "gdpr_consent": None,
                "ccpa_opt_out": False,
                "age_verified_at": None,
                "is_child": signal_is_minor,
                "country_code": country_code,
                "consent_age_threshold": consent_age_threshold,
                "country_signal_mismatch": country_signal_mismatch,
                # T-402 (Brazil): raw, unnormalized — see LoginRequest comment in auth.py
                "store_age_signal": store_age_signal,
                "store_age_signal_source": store_age_signal_source,
                "store_age_signal_captured_at": now if store_age_signal else None,
            },
        }
        if signal_is_minor is not None:
            doc_payload["restricted_features"] = {
                "leaderboard": signal_is_minor,
                "personalized_ads": signal_is_minor,
                "share_score": signal_is_minor,
            }
        await ref.set(doc_payload)
        return sub, True, signal_is_minor
    else:
        existing = snap.to_dict() or {}
        existing_provider = existing.get("provider")
        if existing_provider and existing_provider != provider:
            # Structurally near-impossible (Google sub is numeric, Apple sub is
            # alphanumeric-with-dots) — but if it ever happens, fail loudly
            # instead of silently merging two different humans' accounts.
            raise ValueError("AUTH_PROVIDER_MISMATCH")

        is_child: bool | None = (existing.get("consent") or {}).get("is_child")
        update: dict = {
            "updated_at": now,
            "consent.country_code": country_code,
            "consent.consent_age_threshold": consent_age_threshold,
            "consent.country_signal_mismatch": country_signal_mismatch,
        }
        if not existing_provider:
            # Backfill for docs created before multi-provider support shipped.
            update["provider"] = provider
        # Apple only returns `name` to the client on the FIRST authorization, and
        # `email`/`photo_url` can legitimately be blank on later logins for either
        # provider — never clobber a previously-stored value with a blank.
        if email:
            update["email"] = email
        if display_name:
            update["display_name"] = display_name
        if photo_url:
            update["photo_url"] = photo_url
        # T-402: only overwrite when this login actually provided a signal —
        # a login without it (non-BR user, or a pre-T-402 client) must never
        # clobber a previously-captured value.
        if store_age_signal:
            update["consent.store_age_signal"] = store_age_signal
            update["consent.store_age_signal_source"] = store_age_signal_source
            update["consent.store_age_signal_captured_at"] = now
            if signal_is_minor is not None:
                update.update(geo_service.age_gate_update(signal_is_minor, now))
                is_child = signal_is_minor

        await ref.update(update)
        return sub, False, is_child


async def create_session(
    db: AsyncClient,
    uid: str,
    session_id: str,
    token_hash: str,
    provider: str,
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
        "provider": provider,
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
