"""Tests for POST /leaderboard/score and GET /leaderboard — previously zero
coverage. Focus: the App Check anti-cheat gate (verify_app_check), and proof
that it's already platform-agnostic (no Play Integrity vs App Attest/DeviceCheck
branching needed for iOS — see the comment on verify_app_check itself)."""

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt as jose_jwt

from app.routers import leaderboard
from app.services import jwt_service
from tests.conftest import _gen_keypair, _public_jwk

SCORE_URL = "/leaderboard/score"
GET_URL = "/leaderboard"


def _auth_headers(test_settings, uid: str = "user-lb-1") -> dict:
    token, _ = jwt_service.create_access_token(
        user_id=uid,
        provider="google",
        session_id="session-lb-1",
        project_id=test_settings.gcp_project_id,
        secret_name=test_settings.jwt_secret_name,
        key_id=test_settings.jwt_key_id,
        issuer=test_settings.jwt_issuer,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def appcheck_signing_key():
    private_key, private_pem = _gen_keypair()
    kid = "test-appcheck-kid-1"
    return {"private_pem": private_pem, "kid": kid, "jwk": _public_jwk(private_key, kid)}


@pytest.fixture(autouse=True)
def _patch_appcheck_jwks(monkeypatch, appcheck_signing_key):
    async def _fake_jwks():
        return [appcheck_signing_key["jwk"]]

    monkeypatch.setattr(leaderboard, "_get_appcheck_jwks", _fake_jwks)


def _make_appcheck_token(
    signing_key: dict,
    test_settings,
    *,
    aud: list[str] | None = None,
    exp_delta: timedelta = timedelta(hours=1),
    kid: str | None = None,
    signing_pem: str | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "iss": f"https://firebaseappcheck.googleapis.com/{test_settings.firebase_project_number}",
        "aud": aud if aud is not None else [f"projects/{test_settings.firebase_project_number}"],
        "sub": "app:1:ios:com.ingeniouscruciblestudios.motamaze",
        "iat": now,
        "exp": now + exp_delta,
    }
    return jose_jwt.encode(
        claims,
        signing_pem or signing_key["private_pem"],
        algorithm="RS256",
        headers={"kid": kid or signing_key["kid"]},
    )


async def _seed_active_season(fake_db, test_settings, uid: str, season_stars: int):
    fake_db.seed("season_progress", uid, {
        "uid": uid, "season_id": test_settings.active_season_id, "season_stars": season_stars,
    })


# ---------------------------------------------------------------------------
# App Check gate — platform-agnostic by construction
# ---------------------------------------------------------------------------


async def test_submit_score_missing_appcheck_header(client, test_settings):
    resp = await client.post(
        SCORE_URL,
        json={"season_id": test_settings.active_season_id, "score": 10},
        headers=_auth_headers(test_settings),
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error_code"] == "LEADERBOARD_APPCHECK_MISSING"


async def test_submit_score_valid_appcheck_token_accepted_regardless_of_claimed_platform(
    client, fake_db, test_settings, appcheck_signing_key
):
    """A valid App Check token carries no platform marker the backend checks —
    proof that Android (Play Integrity) and iOS (App Attest/DeviceCheck) tokens
    are accepted identically, since Firebase itself normalizes them before we
    ever see one."""
    await _seed_active_season(fake_db, test_settings, "user-lb-1", 50)
    token = _make_appcheck_token(appcheck_signing_key, test_settings)

    resp = await client.post(
        SCORE_URL,
        json={"season_id": test_settings.active_season_id, "score": 50},
        headers={**_auth_headers(test_settings), "X-Firebase-AppCheck": token},
    )
    assert resp.status_code == 200
    assert resp.json()["season_stars"] == 50


async def test_submit_score_wrong_audience_rejected(client, test_settings, appcheck_signing_key):
    token = _make_appcheck_token(appcheck_signing_key, test_settings, aud=["projects/some-other-project"])
    resp = await client.post(
        SCORE_URL,
        json={"season_id": test_settings.active_season_id, "score": 10},
        headers={**_auth_headers(test_settings), "X-Firebase-AppCheck": token},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error_code"] == "LEADERBOARD_APPCHECK_MISSING"


async def test_submit_score_unknown_kid_rejected(client, test_settings, appcheck_signing_key):
    token = _make_appcheck_token(appcheck_signing_key, test_settings, kid="a-kid-not-in-jwks")
    resp = await client.post(
        SCORE_URL,
        json={"season_id": test_settings.active_season_id, "score": 10},
        headers={**_auth_headers(test_settings), "X-Firebase-AppCheck": token},
    )
    assert resp.status_code == 401


async def test_submit_score_forged_signature_rejected(client, test_settings, appcheck_signing_key):
    _, untrusted_pem = _gen_keypair()
    token = _make_appcheck_token(appcheck_signing_key, test_settings, signing_pem=untrusted_pem)
    resp = await client.post(
        SCORE_URL,
        json={"season_id": test_settings.active_season_id, "score": 10},
        headers={**_auth_headers(test_settings), "X-Firebase-AppCheck": token},
    )
    assert resp.status_code == 401


async def test_submit_score_expired_token_rejected(client, test_settings, appcheck_signing_key):
    token = _make_appcheck_token(appcheck_signing_key, test_settings, exp_delta=timedelta(minutes=-5))
    resp = await client.post(
        SCORE_URL,
        json={"season_id": test_settings.active_season_id, "score": 10},
        headers={**_auth_headers(test_settings), "X-Firebase-AppCheck": token},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Business logic — score authority + child restriction
# ---------------------------------------------------------------------------


async def test_submit_score_ignores_client_score_uses_server_authority(
    client, fake_db, test_settings, appcheck_signing_key
):
    await _seed_active_season(fake_db, test_settings, "user-lb-2", 75)
    token = _make_appcheck_token(appcheck_signing_key, test_settings)

    resp = await client.post(
        SCORE_URL,
        json={"season_id": test_settings.active_season_id, "score": 999999},
        headers={**_auth_headers(test_settings, uid="user-lb-2"), "X-Firebase-AppCheck": token},
    )
    assert resp.status_code == 200
    # Server-authoritative season_stars (75), not the client-submitted score (999999)
    assert resp.json()["season_stars"] == 75


async def test_submit_score_restricted_child_forbidden(
    client, fake_db, test_settings, appcheck_signing_key
):
    fake_db.seed("users", "user-lb-child", {"restricted_features": True})
    token = _make_appcheck_token(appcheck_signing_key, test_settings)

    resp = await client.post(
        SCORE_URL,
        json={"season_id": test_settings.active_season_id, "score": 10},
        headers={**_auth_headers(test_settings, uid="user-lb-child"), "X-Firebase-AppCheck": token},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "LEADERBOARD_RESTRICTED"


async def test_get_leaderboard_season_not_found(client, test_settings):
    resp = await client.get(
        GET_URL,
        params={"season_id": "season_does_not_exist"},
        headers=_auth_headers(test_settings),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error_code"] == "SEASON_NOT_FOUND"
