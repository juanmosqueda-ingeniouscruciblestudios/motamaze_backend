"""Integration tests for the Remote Config integration in /lives endpoints
— T-244 (ST-02). GET /lives, POST /lives/spend, POST /lives/grant had zero
test coverage before this (a pre-existing gap, not introduced here) —
these tests are scoped to what T-244 touches (regen_interval_secs /
default_max_lives now coming from Remote Config), not full endpoint
coverage. See changelogs/T-244-*.md follow-ups."""

from app.services import jwt_service, remote_config_service

GET_URL = "/lives"


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
