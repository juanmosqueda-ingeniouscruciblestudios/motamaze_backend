"""Integration tests for POST /jobs/recalc-level-stats — T-447 ST-04."""

from app.services import bq_streaming

URL = "/jobs/recalc-level-stats"


async def test_recalc_level_stats_requires_scheduler_header(client):
    resp = await client.post(URL)
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "JOBS_FORBIDDEN"


async def test_recalc_level_stats_writes_and_reports_summary(client, monkeypatch, fake_db, scheduler_headers):
    async def _fake_run_select(query, params):
        return [
            {"level_id": 11, "wins": 30, "attempts": 100},
            {"level_id": 12, "wins": 5, "attempts": 20},
        ]

    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select)

    resp = await client.post(URL, headers=scheduler_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == ["11"]
    assert body["skipped_low_sample"] == ["12"]
    assert fake_db._collections["level_stats"]["11"]["win_rate"] == 30.0
    assert "12" not in fake_db._collections.get("level_stats", {})
