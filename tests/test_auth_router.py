"""Integration tests for POST /auth/login and POST /auth/refresh (AUTH-004:
Sign in with Apple + the provider-persistence bug fix on refresh)."""

from datetime import timedelta

from app.services import auth_service, jwt_service
from tests.conftest import make_apple_token

LOGIN_URL = "/auth/login"
REFRESH_URL = "/auth/refresh"


def _decode(token: str, test_settings):
    return jwt_service.decode_access_token(
        token, test_settings.gcp_project_id, test_settings.jwt_secret_name, test_settings.jwt_issuer
    )


def _apple_login_body(id_token: str, **overrides) -> dict:
    body = {
        "provider": "apple",
        "id_token": id_token,
        "platform": "ios",
        "app_version": "1.0.0",
        "display_name": "Test Player",
    }
    body.update(overrides)
    return body


async def _mock_google(monkeypatch, sub="google-sub-1", email="g@example.com", name="G Player"):
    async def _fake_verify_google_token(token, client_id):
        return {"sub": sub, "email": email, "name": name, "picture": "https://example.com/p.png"}

    monkeypatch.setattr(auth_service, "verify_google_token", _fake_verify_google_token)


# ---------------------------------------------------------------------------
# 11-13: POST /auth/login (apple)
# ---------------------------------------------------------------------------


async def test_apple_login_new_user(client, fake_db, apple_signing_key):
    token = make_apple_token(apple_signing_key, sub="apple-sub-new")
    resp = await client.post(LOGIN_URL, json=_apple_login_body(token))

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_new_user"] is True

    user_doc = (await fake_db.collection("users").document("apple-sub-new").get()).to_dict()
    assert user_doc["provider"] == "apple"

    sessions = fake_db._collections.get("sessions", {})
    assert len(sessions) == 1
    session_doc = next(iter(sessions.values()))
    assert session_doc["provider"] == "apple"


async def test_apple_login_invalid_token(client):
    resp = await client.post(LOGIN_URL, json=_apple_login_body("not-a-valid-jwt"))
    assert resp.status_code == 401
    assert resp.json()["detail"]["error_code"] == "AUTH_TOKEN_INVALID"


async def test_apple_login_expired_token(client, apple_signing_key):
    token = make_apple_token(apple_signing_key, exp_delta=timedelta(minutes=-5))
    resp = await client.post(LOGIN_URL, json=_apple_login_body(token))
    assert resp.status_code == 401
    assert resp.json()["detail"]["error_code"] == "AUTH_TOKEN_EXPIRED"


# ---------------------------------------------------------------------------
# 14: refresh regression — the actual bug-fix proof
# ---------------------------------------------------------------------------


async def test_refresh_preserves_apple_provider(client, test_settings, apple_signing_key):
    token = make_apple_token(apple_signing_key, sub="apple-sub-refresh")
    login_resp = await client.post(LOGIN_URL, json=_apple_login_body(token))
    refresh_token = login_resp.json()["refresh_token"]

    refresh_resp = await client.post(REFRESH_URL, json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 200

    claims = _decode(refresh_resp.json()["access_token"], test_settings)
    assert claims["provider"] == "apple"  # previously hardcoded to "google" — the bug this fixes


# ---------------------------------------------------------------------------
# 15: chained refresh keeps propagating the correct provider
# ---------------------------------------------------------------------------


async def test_chained_refresh_preserves_google_provider(client, test_settings, monkeypatch):
    await _mock_google(monkeypatch)
    login_resp = await client.post(LOGIN_URL, json={
        "provider": "google", "id_token": "irrelevant-mocked", "platform": "android", "app_version": "1.0.0",
    })
    refresh_token = login_resp.json()["refresh_token"]

    first = await client.post(REFRESH_URL, json={"refresh_token": refresh_token})
    assert _decode(first.json()["access_token"], test_settings)["provider"] == "google"

    second = await client.post(REFRESH_URL, json={"refresh_token": first.json()["refresh_token"]})
    assert _decode(second.json()["access_token"], test_settings)["provider"] == "google"


# ---------------------------------------------------------------------------
# 16: pre-migration session (no `provider` field) falls back gracefully
# ---------------------------------------------------------------------------


async def test_refresh_falls_back_for_pre_migration_session(client, fake_db, test_settings, monkeypatch):
    await _mock_google(monkeypatch)
    login_resp = await client.post(LOGIN_URL, json={
        "provider": "google", "id_token": "irrelevant-mocked", "platform": "android", "app_version": "1.0.0",
    })
    refresh_token = login_resp.json()["refresh_token"]
    session_id, _ = jwt_service.extract_session_and_secret(refresh_token)

    # Simulate a session doc created before AUTH-004 shipped.
    ref = fake_db.collection("sessions").document(session_id)
    data = (await ref.get()).to_dict()
    del data["provider"]
    await ref.set(data)

    resp = await client.post(REFRESH_URL, json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert _decode(resp.json()["access_token"], test_settings)["provider"] == "google"


# ---------------------------------------------------------------------------
# 17: existing google login path still works unchanged (regression guard)
# ---------------------------------------------------------------------------


async def test_google_login_still_works(client, fake_db, monkeypatch):
    await _mock_google(monkeypatch, sub="google-sub-regress", email="reg@example.com", name="Regress Player")
    resp = await client.post(LOGIN_URL, json={
        "provider": "google", "id_token": "irrelevant-mocked", "platform": "android", "app_version": "1.0.0",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_new_user"] is True

    doc = (await fake_db.collection("users").document("google-sub-regress").get()).to_dict()
    assert doc["provider"] == "google"
    assert doc["email"] == "reg@example.com"
    assert doc["display_name"] == "Regress Player"
