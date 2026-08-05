"""Integration tests for POST /jobs/recalc-achievement-rarities — T-447 ST-10."""

from app.services import bq_streaming

URL = "/jobs/recalc-achievement-rarities"

CATALOG = {
    "achievements": [
        {"achievement_id": "first_blood", "name": "First Blood", "rarity_tier": "COMMON"},
    ],
}


async def test_recalc_rarities_requires_scheduler_header(client):
    resp = await client.post(URL)
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "JOBS_FORBIDDEN"


async def test_recalc_rarities_writes_and_reports_summary(client, monkeypatch, fake_db, scheduler_headers):
    fake_db.seed("config", "achievements", CATALOG)
    fake_db.seed("achievement_progress", "user-1", {"unlocked": ["first_blood"]})
    fake_db.seed("achievement_progress", "user-2", {"unlocked": []})

    async def _fake_run_select(query, params):
        return [{"user_id": "user-1"}, {"user_id": "user-2"}]

    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select)

    resp = await client.post(URL, headers=scheduler_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["computed"] == ["first_blood"]
    assert body["total_players"] == 2

    rarity_doc = fake_db._collections["achievement_rarities"]["first_blood"]
    assert rarity_doc["unlocked_by"] == 1
    assert rarity_doc["rarity_percent"] == 50.0
    assert rarity_doc["rarity_tier"] == "COMMON"


async def test_recalc_rarities_no_active_players_skips_without_error(client, monkeypatch, fake_db, scheduler_headers):
    fake_db.seed("config", "achievements", CATALOG)

    async def _fake_run_select(query, params):
        return []

    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select)

    resp = await client.post(URL, headers=scheduler_headers)
    assert resp.status_code == 200
    assert resp.json() == {"computed": [], "total_players": 0, "skipped": "no_active_players"}
