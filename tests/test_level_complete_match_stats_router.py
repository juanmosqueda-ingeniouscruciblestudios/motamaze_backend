"""Integration tests for match_stats handling in POST /progress/level-complete
-- T-447 ST-01/ST-06. This endpoint had zero test coverage before this (a
pre-existing gap, not introduced here, same situation /lives/spend was in
per test_game_lives_router.py) -- scoped to what ST-06 touches (match_stats
parsing/validation and the season_match_stats write), not full endpoint
coverage of progress/season_progress bookkeeping."""

from app.services import jwt_service

URL = "/progress/level-complete"


def _auth_headers(test_settings, uid: str = "user-match-1") -> dict:
    token, _ = jwt_service.create_access_token(
        user_id=uid,
        provider="google",
        session_id="session-match-1",
        project_id=test_settings.gcp_project_id,
        secret_name=test_settings.jwt_secret_name,
        key_id=test_settings.jwt_key_id,
        issuer=test_settings.jwt_issuer,
    )
    return {"Authorization": f"Bearer {token}"}


def _match_stats(**overrides):
    base = {
        "won": True, "game_mode": "big_dig", "target_score": 10,
        "npcs": {"bola": 1, "mancha": 0, "huracan": 0, "zas": 0},
        "hits_taken": 0, "badsmell_hits": 0, "stuns_taken": 0, "frozen_secs": 0.0,
        "food_collected": 20, "max_food_deficit": 0, "final_gap": 0, "lead_changes": 0,
        "max_food_drought_secs": 5.0, "max_idle_secs": 2.0, "maze_coverage_pct": 60.0,
        "shift_reroutes": 0, "time_to_target_secs": 30.0, "round_duration_secs": 120.0,
    }
    base.update(overrides)
    return base


def _payload(level_id=1, uid_suffix="1", **ms_overrides):
    body = {
        "level_id": level_id, "score": 100, "stars_earned": 3,
        "duration_secs": 90, "session_id": f"session-match-{uid_suffix}",
    }
    if ms_overrides is not None:
        body["match_stats"] = _match_stats(**ms_overrides)
    return body


async def test_valid_match_stats_creates_season_match_stats(client, test_settings, fake_db):
    resp = await client.post(URL, json=_payload(), headers=_auth_headers(test_settings, "u-ms-1"))
    assert resp.status_code == 200

    doc = fake_db._collections["season_match_stats"]["u-ms-1"]
    assert doc["win_streak"] == {"count": 1, "level_ids": ["1"]}
    assert doc["qualifying_levels"]["1"]["mode"] == "big_dig"
    # no level_stats doc seeded -- snapshot should be None, not a KeyError
    assert doc["qualifying_levels"]["1"]["win_rate_snapshot"] is None


async def test_win_rate_snapshot_pulled_from_level_stats_when_present(client, test_settings, fake_db):
    fake_db.seed("level_stats", "1", {"win_rate": 55.5, "source": "measured"})

    resp = await client.post(URL, json=_payload(), headers=_auth_headers(test_settings, "u-ms-2"))
    assert resp.status_code == 200

    doc = fake_db._collections["season_match_stats"]["u-ms-2"]
    assert doc["qualifying_levels"]["1"]["win_rate_snapshot"] == 55.5


async def test_invalid_match_stats_skips_season_write_but_keeps_progress(client, test_settings, fake_db):
    # game_mode outside the known 8 -- fails REST-001 validation.
    payload = _payload(game_mode="not_a_real_mode")
    resp = await client.post(URL, json=payload, headers=_auth_headers(test_settings, "u-ms-3"))
    assert resp.status_code == 200  # progress registers regardless (REST-001)
    assert resp.json()["stars_earned"] == 3

    assert "u-ms-3" not in fake_db._collections.get("season_match_stats", {})


async def test_missing_match_stats_skips_season_write(client, test_settings, fake_db):
    body = {
        "level_id": 1, "score": 100, "stars_earned": 3,
        "duration_secs": 90, "session_id": "session-match-4",
    }
    resp = await client.post(URL, json=body, headers=_auth_headers(test_settings, "u-ms-4"))
    assert resp.status_code == 200
    assert "u-ms-4" not in fake_db._collections.get("season_match_stats", {})


async def test_loss_after_win_resets_streak_across_two_requests(client, test_settings, fake_db):
    headers = _auth_headers(test_settings, "u-ms-5")
    resp1 = await client.post(URL, json=_payload(level_id=1), headers=headers)
    assert resp1.status_code == 200

    resp2 = await client.post(URL, json=_payload(level_id=1, won=False), headers=headers)
    assert resp2.status_code == 200

    doc = fake_db._collections["season_match_stats"]["u-ms-5"]
    assert doc["win_streak"] == {"count": 0, "level_ids": []}
