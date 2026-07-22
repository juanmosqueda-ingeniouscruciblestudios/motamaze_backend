"""Integration tests for POST /auth/login and POST /auth/refresh (AUTH-004:
Sign in with Apple + the provider-persistence bug fix on refresh)."""

from datetime import datetime, timedelta, timezone

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


# ---------------------------------------------------------------------------
# T-402: store_age_signal contract (subtasks 1+2 — capture/store only, no
# reconciliation logic yet)
# ---------------------------------------------------------------------------


async def test_login_persists_store_age_signal(client, fake_db, apple_signing_key):
    token = make_apple_token(apple_signing_key, sub="apple-sub-br")
    resp = await client.post(LOGIN_URL, json=_apple_login_body(
        token,
        store_age_signal="13-15",
        store_age_signal_source="apple_declared_age_range",
    ))
    assert resp.status_code == 200

    doc = (await fake_db.collection("users").document("apple-sub-br").get()).to_dict()
    consent = doc["consent"]
    assert consent["store_age_signal"] == "13-15"
    assert consent["store_age_signal_source"] == "apple_declared_age_range"
    assert consent["store_age_signal_captured_at"] is not None


async def test_login_without_store_age_signal_leaves_fields_none(client, fake_db, apple_signing_key):
    token = make_apple_token(apple_signing_key, sub="apple-sub-non-br")
    resp = await client.post(LOGIN_URL, json=_apple_login_body(token))
    assert resp.status_code == 200

    doc = (await fake_db.collection("users").document("apple-sub-non-br").get()).to_dict()
    consent = doc["consent"]
    assert consent["store_age_signal"] is None
    assert consent["store_age_signal_source"] is None
    assert consent["store_age_signal_captured_at"] is None


async def test_login_repeat_does_not_clobber_store_age_signal(client, fake_db, apple_signing_key):
    first_token = make_apple_token(apple_signing_key, sub="apple-sub-repeat")
    await client.post(LOGIN_URL, json=_apple_login_body(
        first_token,
        store_age_signal="18+",
        store_age_signal_source="apple_declared_age_range",
    ))

    # Second login (e.g. app relaunch) omits the signal — must NOT wipe it out.
    second_token = make_apple_token(apple_signing_key, sub="apple-sub-repeat")
    resp = await client.post(LOGIN_URL, json=_apple_login_body(second_token))
    assert resp.status_code == 200

    doc = (await fake_db.collection("users").document("apple-sub-repeat").get()).to_dict()
    consent = doc["consent"]
    assert consent["store_age_signal"] == "18+"
    assert consent["store_age_signal_source"] == "apple_declared_age_range"


# ---------------------------------------------------------------------------
# T-123: grace-period access cutoff (login stays open, refresh is blocked)
# ---------------------------------------------------------------------------


async def test_login_surfaces_deletion_pending_flag(client, fake_db, apple_signing_key):
    # Seed an existing user with a pending deletion — login must still
    # succeed (so the client can reach cancel-deletion) but flag it.
    fake_db.seed("users", "apple-sub-deleting", {
        "uid": "apple-sub-deleting",
        "provider": "apple",
        "email": "d@example.com",
        "display_name": "Deleting Player",
        "photo_url": None,
        "delete_requested_at": datetime.now(timezone.utc),
        "consent": {},
    })
    token = make_apple_token(apple_signing_key, sub="apple-sub-deleting")
    resp = await client.post(LOGIN_URL, json=_apple_login_body(token))
    assert resp.status_code == 200
    assert resp.json()["deletion_pending"] is True


async def test_login_without_pending_deletion_flag_is_false(client, fake_db, apple_signing_key):
    token = make_apple_token(apple_signing_key, sub="apple-sub-not-deleting")
    resp = await client.post(LOGIN_URL, json=_apple_login_body(token))
    assert resp.status_code == 200
    assert resp.json()["deletion_pending"] is False


async def test_refresh_rejects_pending_deletion(client, fake_db, apple_signing_key):
    token = make_apple_token(apple_signing_key, sub="apple-sub-refresh-deleting")
    login_resp = await client.post(LOGIN_URL, json=_apple_login_body(token))
    refresh_token = login_resp.json()["refresh_token"]

    # Deletion requested after login (e.g. via DELETE /auth/account on another device).
    await fake_db.collection("users").document("apple-sub-refresh-deleting").update(
        {"delete_requested_at": datetime.now(timezone.utc)}
    )

    resp = await client.post(REFRESH_URL, json={"refresh_token": refresh_token})
    assert resp.status_code == 401
    assert resp.json()["detail"]["error_code"] == "AUTH_ACCOUNT_DELETION_PENDING"


# ---------------------------------------------------------------------------
# T-123 (subtask 3): POST /auth/account/cancel-deletion
# ---------------------------------------------------------------------------

CANCEL_URL = "/auth/account/cancel-deletion"


async def test_cancel_deletion_clears_pending_state(client, fake_db, apple_signing_key):
    token = make_apple_token(apple_signing_key, sub="apple-sub-cancel")
    login_resp = await client.post(LOGIN_URL, json=_apple_login_body(token))
    access_token = login_resp.json()["access_token"]

    del_resp = await client.delete("/auth/account", headers={"Authorization": f"Bearer {access_token}"})
    assert del_resp.status_code == 202
    doc = (await fake_db.collection("users").document("apple-sub-cancel").get()).to_dict()
    assert doc["delete_requested_at"] is not None

    # DELETE /auth/account revoked that access token — re-login for a fresh
    # one (login stays open with a pending deletion, subtask 1).
    token2 = make_apple_token(apple_signing_key, sub="apple-sub-cancel")
    relogin_resp = await client.post(LOGIN_URL, json=_apple_login_body(token2))
    assert relogin_resp.json()["deletion_pending"] is True
    new_access_token = relogin_resp.json()["access_token"]

    cancel_resp = await client.post(CANCEL_URL, headers={"Authorization": f"Bearer {new_access_token}"})
    assert cancel_resp.status_code == 200

    doc2 = (await fake_db.collection("users").document("apple-sub-cancel").get()).to_dict()
    assert doc2["delete_requested_at"] is None


async def test_cancel_deletion_reactivates_refresh(client, fake_db, apple_signing_key):
    token = make_apple_token(apple_signing_key, sub="apple-sub-reactivate")
    login_resp = await client.post(LOGIN_URL, json=_apple_login_body(token))
    await client.delete(
        "/auth/account", headers={"Authorization": f"Bearer {login_resp.json()['access_token']}"}
    )

    token2 = make_apple_token(apple_signing_key, sub="apple-sub-reactivate")
    relogin_resp = await client.post(LOGIN_URL, json=_apple_login_body(token2))
    new_access_token = relogin_resp.json()["access_token"]
    new_refresh_token = relogin_resp.json()["refresh_token"]

    cancel_resp = await client.post(CANCEL_URL, headers={"Authorization": f"Bearer {new_access_token}"})
    assert cancel_resp.status_code == 200

    # Refresh was blocked while deletion was pending (previous test class) —
    # confirm cancelling actually lifts that cutoff, not just the flag.
    refresh_resp = await client.post(REFRESH_URL, json={"refresh_token": new_refresh_token})
    assert refresh_resp.status_code == 200


async def test_cancel_deletion_without_pending_deletion_404(client, apple_signing_key):
    token = make_apple_token(apple_signing_key, sub="apple-sub-no-pending")
    login_resp = await client.post(LOGIN_URL, json=_apple_login_body(token))
    access_token = login_resp.json()["access_token"]

    resp = await client.post(CANCEL_URL, headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 404
    assert resp.json()["detail"]["error_code"] == "AUTH_NO_PENDING_DELETION"


async def test_cancel_deletion_user_not_found(client, test_settings):
    token, _ = jwt_service.create_access_token(
        user_id="ghost-user", provider="google", session_id="ghost-session",
        project_id=test_settings.gcp_project_id, secret_name=test_settings.jwt_secret_name,
        key_id=test_settings.jwt_key_id, issuer=test_settings.jwt_issuer,
    )
    resp = await client.post(CANCEL_URL, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404
    assert resp.json()["detail"]["error_code"] == "USER_NOT_FOUND"
