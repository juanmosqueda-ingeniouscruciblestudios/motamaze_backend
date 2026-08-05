"""Tests for verify_cloud_scheduler_oidc (INFRA-007) -- the real auth gate on
/jobs/*, replacing the old spoofable X-CloudScheduler-JobName header check.
Exercised against one representative endpoint (recalc-level-stats); all 7
/jobs/* endpoints share the exact same dependency, so this isn't
endpoint-specific behavior."""

from app.routers import jobs
from app.services import bq_streaming

URL = "/jobs/recalc-level-stats"


async def _fake_run_select(query, params):
    return []


def _patch_bq(monkeypatch):
    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select)


async def test_missing_authorization_header_rejected(client, fake_db, monkeypatch):
    _patch_bq(monkeypatch)
    resp = await client.post(URL)
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "JOBS_FORBIDDEN"


async def test_non_bearer_authorization_rejected(client, fake_db, monkeypatch):
    _patch_bq(monkeypatch)
    resp = await client.post(URL, headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "JOBS_FORBIDDEN"


async def test_token_that_fails_google_verification_rejected(client, fake_db, monkeypatch):
    _patch_bq(monkeypatch)

    async def _fake_verify_fails(token, audience):
        raise ValueError("Token expired")

    monkeypatch.setattr(jobs, "_verify_scheduler_oidc", _fake_verify_fails)

    resp = await client.post(URL, headers={"Authorization": "Bearer expired-token"})
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "JOBS_FORBIDDEN"


async def test_valid_token_wrong_service_account_email_rejected(client, fake_db, monkeypatch, test_settings):
    _patch_bq(monkeypatch)

    async def _fake_verify_wrong_sa(token, audience):
        return {"email": "someone-else@evil-project.iam.gserviceaccount.com", "email_verified": True}

    monkeypatch.setattr(jobs, "_verify_scheduler_oidc", _fake_verify_wrong_sa)

    resp = await client.post(URL, headers={"Authorization": "Bearer token-for-wrong-sa"})
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "JOBS_FORBIDDEN"


async def test_valid_token_email_not_verified_rejected(client, fake_db, monkeypatch, test_settings):
    _patch_bq(monkeypatch)

    async def _fake_verify_unverified(token, audience):
        return {
            "email": f"game-api-backend@{test_settings.gcp_project_id}.iam.gserviceaccount.com",
            "email_verified": False,
        }

    monkeypatch.setattr(jobs, "_verify_scheduler_oidc", _fake_verify_unverified)

    resp = await client.post(URL, headers={"Authorization": "Bearer unverified-token"})
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "JOBS_FORBIDDEN"


async def test_valid_token_correct_sa_email_accepted(client, fake_db, monkeypatch, scheduler_headers):
    _patch_bq(monkeypatch)
    resp = await client.post(URL, headers=scheduler_headers)
    assert resp.status_code == 200


async def test_audience_is_passed_through_to_verification(client, fake_db, monkeypatch, test_settings):
    """Confirms the dependency actually forwards settings.cloud_run_service_url
    as the audience to verify against, rather than skipping/hardcoding it."""
    _patch_bq(monkeypatch)
    captured = {}

    async def _fake_verify_capture(token, audience):
        captured["audience"] = audience
        return {
            "email": f"game-api-backend@{test_settings.gcp_project_id}.iam.gserviceaccount.com",
            "email_verified": True,
        }

    monkeypatch.setattr(jobs, "_verify_scheduler_oidc", _fake_verify_capture)

    resp = await client.post(URL, headers={"Authorization": "Bearer some-token"})
    assert resp.status_code == 200
    assert captured["audience"] == test_settings.cloud_run_service_url
