"""Integration test for POST /jobs/purge-deleted-accounts — T-123 (ST-04).
The rest of /jobs (admob-daily-report, reconcile-purchases) has no test
coverage yet; out of scope here, only the new endpoint is covered."""

from datetime import datetime, timedelta, timezone

PURGE_URL = "/jobs/purge-deleted-accounts"
JOB_HEADERS = {"X-CloudScheduler-JobName": "purge-deleted-accounts"}


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
