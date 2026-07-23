"""Integration tests for POST /jobs/recalc-age-thresholds — T-404."""

from datetime import date

URL = "/jobs/recalc-age-thresholds"
JOB_HEADERS = {"X-CloudScheduler-JobName": "recalc-age-thresholds"}


async def test_recalc_requires_scheduler_header(client):
    resp = await client.post(URL)
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "JOBS_FORBIDDEN"


async def test_recalc_flips_aged_out_user_and_returns_summary(client, fake_db):
    # Birth month/year chosen so the user has definitely aged out by today,
    # regardless of when this test actually runs.
    old_year = date.today().year - 30
    fake_db.seed("users", "recalc-router-user", {
        "uid": "recalc-router-user",
        "consent": {
            "is_child": True,
            "birth_month": 1,
            "birth_year": old_year,
            "consent_age_threshold": 13,
        },
    })

    resp = await client.post(URL, headers=JOB_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["aged_out_count"] == 1
    assert body["aged_out_uids"] == ["recalc-router-user"]

    doc = (await fake_db.collection("users").document("recalc-router-user").get()).to_dict()
    assert doc["consent"]["is_child"] is False


async def test_recalc_no_eligible_users_is_a_noop(client, fake_db):
    fake_db.seed("users", "no-birth-fields-user", {
        "uid": "no-birth-fields-user",
        "consent": {"is_child": True},
    })

    resp = await client.post(URL, headers=JOB_HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {"aged_out_count": 0, "aged_out_uids": []}
