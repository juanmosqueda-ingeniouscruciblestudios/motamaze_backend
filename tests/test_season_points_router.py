"""Integration tests for season_points bookkeeping in POST /progress/level-complete
-- T-447 ST-08. Covers season_progress's new levels_cleared_ids/
achievement_bonus_points fields, the season_points formula in the response,
and the season-reset bug fix (season_id now actually persists on every
write, not just doc creation -- see game.py's ST-08 comment)."""

from app.config import Settings
from app.dependencies import get_settings
from app.main import app
from app.services import jwt_service
from scripts.seed_achievements import ACHIEVEMENTS

URL = "/progress/level-complete"


def _auth_headers(test_settings, uid: str) -> dict:
    token, _ = jwt_service.create_access_token(
        user_id=uid, provider="google", session_id=f"session-{uid}",
        project_id=test_settings.gcp_project_id, secret_name=test_settings.jwt_secret_name,
        key_id=test_settings.jwt_key_id, issuer=test_settings.jwt_issuer,
    )
    return {"Authorization": f"Bearer {token}"}


def _payload(level_id, stars_earned=1, session_id="s1", with_match_stats=False):
    body = {
        "level_id": level_id, "score": 100, "stars_earned": stars_earned,
        "duration_secs": 60, "session_id": session_id,
    }
    if with_match_stats:
        body["match_stats"] = {
            "won": True, "game_mode": "big_dig", "target_score": 10,
            "npcs": {"bola": 0, "mancha": 0, "huracan": 0, "zas": 0},
            "hits_taken": 0, "badsmell_hits": 0, "stuns_taken": 0, "frozen_secs": 0.0,
            "food_collected": 0, "max_food_deficit": 0, "final_gap": 0, "lead_changes": 0,
            "max_food_drought_secs": 0.0, "max_idle_secs": 0.0, "maze_coverage_pct": 0.0,
            "shift_reroutes": 0, "time_to_target_secs": 0.0, "round_duration_secs": 120.0,
        }
    return body


async def test_season_points_formula_without_match_stats(client, test_settings, fake_db):
    resp = await client.post(URL, json=_payload(1, stars_earned=3), headers=_auth_headers(test_settings, "u-sp-1"))
    assert resp.status_code == 200
    body = resp.json()
    # 3 stars * 3 + 1 level_cleared * 5 + 0 bonus (no match_stats -> no achievements)
    assert body["total_season_stars"] == 3
    assert body["achievement_bonus_points"] == 0
    assert body["season_points"] == 3 * 3 + 1 * 5 + 0
    assert body["achievements_unlocked"] == []


async def test_levels_cleared_does_not_double_count_repeats(client, test_settings, fake_db):
    headers = _auth_headers(test_settings, "u-sp-2")
    await client.post(URL, json=_payload(1, stars_earned=1, session_id="a"), headers=headers)
    resp = await client.post(URL, json=_payload(1, stars_earned=2, session_id="b"), headers=headers)

    doc = fake_db._collections["season_progress"]["u-sp-2"]
    assert doc["levels_cleared_ids"] == ["1"]
    body = resp.json()
    # season_stars: 2 (best of 1,2) ; levels_cleared: 1 (not 2, same level)
    assert body["total_season_stars"] == 2
    assert body["season_points"] == 2 * 3 + 1 * 5


async def test_achievement_bonus_added_to_season_points(client, test_settings, fake_db):
    fake_db.seed("config", "achievements", {"achievements": ACHIEVEMENTS, "catalog_version": "2026-07-30"})
    first_blood_pts = next(a["points"] for a in ACHIEVEMENTS if a["achievement_id"] == "first_blood")
    star_born_pts = next(a["points"] for a in ACHIEVEMENTS if a["achievement_id"] == "star_born")

    resp = await client.post(
        URL, json=_payload(1, stars_earned=3, with_match_stats=True),
        headers=_auth_headers(test_settings, "u-sp-3"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["achievements_unlocked"]) >= {"first_blood", "star_born"}
    assert body["achievement_bonus_points"] == first_blood_pts + star_born_pts
    assert body["season_points"] == 3 * 3 + 1 * 5 + (first_blood_pts + star_born_pts)

    doc = fake_db._collections["season_progress"]["u-sp-3"]
    assert doc["achievement_bonus_points"] == first_blood_pts + star_born_pts


async def test_achievement_bonus_not_re_added_on_second_match(client, test_settings, fake_db):
    fake_db.seed("config", "achievements", {"achievements": ACHIEVEMENTS, "catalog_version": "2026-07-30"})
    headers = _auth_headers(test_settings, "u-sp-4")

    resp1 = await client.post(URL, json=_payload(1, stars_earned=3, session_id="a", with_match_stats=True), headers=headers)
    bonus_after_first = resp1.json()["achievement_bonus_points"]
    assert bonus_after_first > 0

    # second match: already unlocked, nothing new -> bonus unchanged
    resp2 = await client.post(URL, json=_payload(2, stars_earned=1, session_id="b", with_match_stats=True), headers=headers)
    assert resp2.json()["achievement_bonus_points"] == bonus_after_first
    assert resp2.json()["achievements_unlocked"] == []


async def test_season_reset_persists_new_season_id_and_does_not_regress_on_next_call(client, test_settings, fake_db):
    """Regression test for the pre-existing bug this ST fixed: season_id
    used to never get written back, so every call after a season boundary
    re-detected "stale" and re-baselined from 0 forever, discarding
    progress accumulated since the real reset."""
    headers = _auth_headers(test_settings, "u-sp-5")
    await client.post(URL, json=_payload(1, stars_earned=2, session_id="a"), headers=headers)

    season_2_settings = Settings(**{**test_settings.model_dump(), "active_season_id": "season_002"})
    app.dependency_overrides[get_settings] = lambda: season_2_settings

    # level_id must stay sequential (highest_unlocked_level + 1) -- the
    # progress-lock check is independent of season_id and unaffected by it.
    resp1 = await client.post(URL, json=_payload(2, stars_earned=1, session_id="b"), headers=headers)
    assert resp1.json()["total_season_stars"] == 1  # reset, not 3

    resp2 = await client.post(URL, json=_payload(3, stars_earned=2, session_id="c"), headers=headers)
    # if season_id persisted correctly, this ACCUMULATES on top of the
    # season_002 call above (1 + 2 = 3) instead of re-resetting to 2
    assert resp2.json()["total_season_stars"] == 3

    doc = fake_db._collections["season_progress"]["u-sp-5"]
    assert doc["season_id"] == "season_002"
    assert doc["levels_cleared_ids"] == ["2", "3"]

    app.dependency_overrides[get_settings] = lambda: test_settings
