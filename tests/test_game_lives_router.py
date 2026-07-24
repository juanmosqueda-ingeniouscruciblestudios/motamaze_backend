"""Integration tests for the Remote Config integration in /lives endpoints
— T-244 (ST-02). GET /lives, POST /lives/spend, POST /lives/grant had zero
test coverage before this (a pre-existing gap, not introduced here) —
these tests are scoped to what T-244 touches (regen_interval_secs /
default_max_lives now coming from Remote Config), not full endpoint
coverage. See changelogs/T-244-*.md follow-ups."""

from app.services import jwt_service, remote_config_service

GET_URL = "/lives"
SPEND_URL = "/lives/spend"
GRANT_URL = "/lives/grant"


def _auth_headers(test_settings, uid: str = "user-lives-1") -> dict:
    token, _ = jwt_service.create_access_token(
        user_id=uid,
        provider="google",
        session_id="session-lives-1",
        project_id=test_settings.gcp_project_id,
        secret_name=test_settings.jwt_secret_name,
        key_id=test_settings.jwt_key_id,
        issuer=test_settings.jwt_issuer,
    )
    return {"Authorization": f"Bearer {token}"}


async def test_get_lives_uses_fallback_defaults_when_remote_config_unset(client, test_settings):
    # The autouse _patch_remote_config fixture simulates "no template
    # published" -- must fall back to the module constants (1800s, 5 lives).
    resp = await client.get(GET_URL, headers=_auth_headers(test_settings))
    assert resp.status_code == 200
    body = resp.json()
    assert body["regen_interval_secs"] == 1800
    assert body["max_lives"] == 5


async def test_get_lives_uses_remote_config_value_when_published(client, test_settings, monkeypatch):
    def _fake_fetch(project_id):
        return {
            "parameters": {
                "regen_interval_secs": {"defaultValue": {"value": "900"}},
                "default_max_lives": {"defaultValue": {"value": "8"}},
            }
        }

    monkeypatch.setattr(remote_config_service, "_fetch_template_sync", _fake_fetch)

    resp = await client.get(GET_URL, headers=_auth_headers(test_settings, "user-lives-2"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["regen_interval_secs"] == 900
    assert body["max_lives"] == 8


# ---------------------------------------------------------------------------
# T-244 (ST-03): /lives/grant and /lives/spend also migrated — ST-02 only
# directly tested GET /lives, these were unverified until now
# ---------------------------------------------------------------------------


def _fake_fetch(regen=None, max_lives=None):
    params = {}
    if regen is not None:
        params["regen_interval_secs"] = {"defaultValue": {"value": str(regen)}}
    if max_lives is not None:
        params["default_max_lives"] = {"defaultValue": {"value": str(max_lives)}}
    return lambda project_id: {"parameters": params}


async def test_lives_grant_caps_at_remote_config_max_not_hardcoded_default(
    client, test_settings, monkeypatch
):
    # RC says max is 3 (smaller than the 5-life fallback) -- a new user
    # requesting a 5-pack must be capped at 3, not 5, proving the endpoint
    # actually uses the resolved value in its capping arithmetic.
    monkeypatch.setattr(remote_config_service, "_fetch_template_sync", _fake_fetch(max_lives=3))

    resp = await client.post(
        GRANT_URL,
        json={"source": "iap", "session_id": "sess-grant-1", "product_id": "lives_pack_5"},
        headers=_auth_headers(test_settings, "user-lives-grant-1"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["max_lives"] == 3
    assert body["current_lives"] == 3
    assert body["granted"] == 3
    assert body["capped"] is True


# NOTE: POST /lives/spend is NOT covered here. It's wrapped in
# @async_transactional (google.cloud.firestore) and FakeFirestoreClient
# (tests/conftest.py) has no .transaction() support at all -- faithfully
# faking Firestore's real transaction lifecycle (begin/commit/rollback +
# retry, all tied to the real client's gRPC stub) is a separate, larger
# undertaking than T-244's scope. This is a pre-existing gap (the endpoint
# had zero tests before this ticket either), flagged as a follow-up, not
# silently worked around. _spend_txn shares the exact same _apply_regen/
# _next_regen_dt helpers that GET /lives already proves work correctly
# with Remote-Config-resolved values above -- the untested part is
# Firestore's transaction wrapping itself, not the T-244 change.


async def test_lives_grant_partial_remote_config_only_one_key_published(
    client, test_settings, monkeypatch
):
    # Only default_max_lives is published -- regen_interval_secs must still
    # fall back cleanly, not error, not silently use the wrong key.
    monkeypatch.setattr(remote_config_service, "_fetch_template_sync", _fake_fetch(max_lives=10))

    resp = await client.post(
        GRANT_URL,
        json={"source": "promo", "session_id": "sess-grant-2", "promo_code": "WELCOME"},
        headers=_auth_headers(test_settings, "user-lives-grant-2"),
    )
    assert resp.status_code == 200
    assert resp.json()["max_lives"] == 10  # published value used
    # (regen_interval_secs isn't in this response, but the fallback not
    # raising is itself the point of this test.)
