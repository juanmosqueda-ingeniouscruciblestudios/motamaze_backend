"""Unit tests for app/services/achievements_catalog_service.py — T-447 ST-09.
Pure -- no Firestore I/O, callers supply already-read data."""

from datetime import datetime, timezone

from app.services.achievements_catalog_service import build_achievements_response

NOW = datetime(2026, 7, 30, tzinfo=timezone.utc)

FIRST_BLOOD = {
    "achievement_id": "first_blood", "name": "First Blood", "description": "Win your first match",
    "rarity_tier": "COMMON", "points": 25,
}
MAZE_MASTER = {
    "achievement_id": "maze_master", "name": "Maze Master", "description": "Cover 90% of the maze",
    "rarity_tier": "UNCOMMON", "points": 75,
}
CATALOG = [FIRST_BLOOD, MAZE_MASTER]


def test_unlocked_achievement_has_timestamp_and_flag():
    progress = {"unlocked": ["first_blood"], "unlock_timestamps": {"first_blood": NOW}}
    result = build_achievements_response(CATALOG, progress, {})
    by_id = {r["achievement_id"]: r for r in result}
    assert by_id["first_blood"]["unlocked"] is True
    assert by_id["first_blood"]["unlocked_at"] == NOW
    assert by_id["maze_master"]["unlocked"] is False
    assert by_id["maze_master"]["unlocked_at"] is None


def test_empty_progress_all_locked():
    result = build_achievements_response(CATALOG, {}, {})
    assert all(r["unlocked"] is False and r["unlocked_at"] is None for r in result)


def test_progress_always_null_pending_st07_followup():
    result = build_achievements_response(CATALOG, {}, {})
    assert all(r["progress"] is None for r in result)


def test_title_and_description_come_from_catalog_name():
    result = build_achievements_response(CATALOG, {}, {})
    by_id = {r["achievement_id"]: r for r in result}
    assert by_id["first_blood"]["title"] == "First Blood"
    assert by_id["first_blood"]["description"] == "Win your first match"


def test_icon_id_derived_from_achievement_id():
    result = build_achievements_response(CATALOG, {}, {})
    by_id = {r["achievement_id"]: r for r in result}
    assert by_id["first_blood"]["icon_id"] == "badge_first_blood"


def test_rarity_falls_back_to_static_tier_without_measured_data():
    # T-447 ST-10 (rarity job) hasn't run for this achievement yet.
    result = build_achievements_response(CATALOG, {}, {})
    by_id = {r["achievement_id"]: r for r in result}
    assert by_id["first_blood"]["rarity"] == "COMMON"
    assert by_id["first_blood"]["rarity_percent"] is None


def test_rarity_uses_measured_data_when_present():
    rarities = {"first_blood": {"rarity_tier": "RARE", "rarity_percent": 12.5}}
    result = build_achievements_response(CATALOG, {}, rarities)
    by_id = {r["achievement_id"]: r for r in result}
    # Measured tier can diverge from the static one -- measured wins.
    assert by_id["first_blood"]["rarity"] == "RARE"
    assert by_id["first_blood"]["rarity_percent"] == 12.5
    # Achievement without a rarity doc still falls back independently.
    assert by_id["maze_master"]["rarity"] == "UNCOMMON"
    assert by_id["maze_master"]["rarity_percent"] is None
