"""Integration test for POST /jobs/purge-deleted-accounts — T-123 (ST-04,
BigQuery purge added in ST-05). The rest of /jobs (admob-daily-report,
reconcile-purchases) has no test coverage yet; out of scope here, only the
new endpoint is covered."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services import bq_streaming

PURGE_URL = "/jobs/purge-deleted-accounts"
JOB_HEADERS = {"X-CloudScheduler-JobName": "purge-deleted-accounts"}


@pytest.fixture(autouse=True)
def _no_real_bigquery_dml(monkeypatch):
    """purge_user_bigquery_data calls bq_streaming.run_dml, which would
    otherwise hit real BigQuery — every test in this file gets a no-op
    default (0 rows affected); individual tests override for specific
    behavior (failure simulation, etc)."""
    async def _noop(query, params):
        return 0

    monkeypatch.setattr(bq_streaming, "run_dml", _noop)


async def test_purge_job_requires_scheduler_header(client):
    resp = await client.post(PURGE_URL)
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "JOBS_FORBIDDEN"


async def test_purge_job_purges_due_users_and_skips_others(client, fake_db):
    now = datetime.now(timezone.utc)
    fake_db.seed("users", "due-for-purge", {
        "uid": "due-for-purge", "delete_requested_at": now - timedelta(days=31),
    })
    fake_db.seed("progress", "due-for-purge", {"uid": "due-for-purge", "best_level": 3})
    fake_db.seed("users", "within-grace-period", {
        "uid": "within-grace-period", "delete_requested_at": now - timedelta(days=5),
    })
    fake_db.seed("users", "normal-user", {"uid": "normal-user", "delete_requested_at": None})

    resp = await client.post(PURGE_URL, headers=JOB_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"due": 1, "purged": 1, "failed": 0}

    assert not (await fake_db.collection("users").document("due-for-purge").get()).exists
    assert not (await fake_db.collection("progress").document("due-for-purge").get()).exists
    assert (await fake_db.collection("users").document("within-grace-period").get()).exists
    assert (await fake_db.collection("users").document("normal-user").get()).exists


async def test_purge_job_no_due_users_is_a_noop(client, fake_db):
    fake_db.seed("users", "normal-user-2", {"uid": "normal-user-2", "delete_requested_at": None})
    resp = await client.post(PURGE_URL, headers=JOB_HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {"due": 0, "purged": 0, "failed": 0}


async def test_purge_job_runs_bigquery_before_firestore(client, fake_db, monkeypatch):
    now = datetime.now(timezone.utc)
    fake_db.seed("users", "bq-then-fs-user", {
        "uid": "bq-then-fs-user", "delete_requested_at": now - timedelta(days=31),
    })

    async def _fake_run_dml(query, params):
        return 1

    monkeypatch.setattr(bq_streaming, "run_dml", _fake_run_dml)

    resp = await client.post(PURGE_URL, headers=JOB_HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {"due": 1, "purged": 1, "failed": 0}
    assert not (await fake_db.collection("users").document("bq-then-fs-user").get()).exists


async def test_purge_job_bigquery_failure_leaves_firestore_untouched_for_retry(client, fake_db, monkeypatch):
    # BQ purge fails -> Firestore purge must NOT run, so the user is still
    # found by find_users_due_for_purge on the next run (see jobs.py's
    # ordering rationale: users/{uid} is the flag that query scans for).
    now = datetime.now(timezone.utc)
    fake_db.seed("users", "bq-fails-user", {
        "uid": "bq-fails-user", "delete_requested_at": now - timedelta(days=31),
    })

    async def _fake_run_dml_fails(query, params):
        raise RuntimeError("BQ transient error")

    monkeypatch.setattr(bq_streaming, "run_dml", _fake_run_dml_fails)

    resp = await client.post(PURGE_URL, headers=JOB_HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {"due": 1, "purged": 0, "failed": 1}

    # Untouched — still exists, still due, retryable next run.
    doc = (await fake_db.collection("users").document("bq-fails-user").get()).to_dict()
    assert doc is not None
    assert doc["delete_requested_at"] is not None
