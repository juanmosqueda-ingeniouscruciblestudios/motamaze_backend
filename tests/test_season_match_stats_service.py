"""Unit tests for season_match_stats_service.apply_match — T-447 ST-06."""

from datetime import datetime, timezone

from app.services import season_match_stats_service

NOW = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)


def _match_stats(won=True, mode="big_dig", **overrides):
    base = {
        "won": won, "game_mode": mode,
        "npcs": {"bola": 1, "mancha": 0, "huracan": 0, "zas": 0},
        "hits_taken": 0, "badsmell_hits": 0, "max_food_deficit": 0,
        "final_gap": 0, "lead_changes": 0, "maze_coverage_pct": 50.0,
    }
    base.update(overrides)
    return base


async def test_first_win_creates_streak_and_qualifying_entry(fake_db):
    await season_match_stats_service.apply_match(
        fake_db, "u1", "season_001", 1, _match_stats(), win_rate_snapshot=42.0, now=NOW,
    )
    doc = fake_db._collections["season_match_stats"]["u1"]
    assert doc["win_streak"] == {"count": 1, "level_ids": ["1"]}
    assert doc["qualifying_levels"]["1"]["win_rate_snapshot"] == 42.0
    assert doc["qualifying_levels"]["1"]["mode"] == "big_dig"


async def test_winning_a_new_level_extends_streak(fake_db):
    await season_match_stats_service.apply_match(fake_db, "u1", "season_001", 1, _match_stats(), 42.0, NOW)
    await season_match_stats_service.apply_match(fake_db, "u1", "season_001", 2, _match_stats(), 30.0, NOW)

    doc = fake_db._collections["season_match_stats"]["u1"]
    assert doc["win_streak"] == {"count": 2, "level_ids": ["1", "2"]}
    assert set(doc["qualifying_levels"]) == {"1", "2"}


async def test_repeating_a_won_level_is_a_streak_noop(fake_db):
    await season_match_stats_service.apply_match(fake_db, "u1", "season_001", 1, _match_stats(), 42.0, NOW)
    await season_match_stats_service.apply_match(fake_db, "u1", "season_001", 1, _match_stats(hits_taken=3), 99.0, NOW)

    doc = fake_db._collections["season_match_stats"]["u1"]
    assert doc["win_streak"] == {"count": 1, "level_ids": ["1"]}
    # first-win snapshot is kept, not overwritten by the second (worse) win
    assert doc["qualifying_levels"]["1"]["hits_taken"] == 0
    assert doc["qualifying_levels"]["1"]["win_rate_snapshot"] == 42.0


async def test_losing_resets_the_streak_even_on_a_repeated_level(fake_db):
    await season_match_stats_service.apply_match(fake_db, "u1", "season_001", 1, _match_stats(), 42.0, NOW)
    await season_match_stats_service.apply_match(fake_db, "u1", "season_001", 2, _match_stats(), 30.0, NOW)
    await season_match_stats_service.apply_match(fake_db, "u1", "season_001", 1, _match_stats(won=False), None, NOW)

    doc = fake_db._collections["season_match_stats"]["u1"]
    assert doc["win_streak"] == {"count": 0, "level_ids": []}
    # qualifying_levels is never pruned by a loss -- already-earned facts stick
    assert set(doc["qualifying_levels"]) == {"1", "2"}


async def test_new_season_resets_streak_and_qualifying_levels(fake_db):
    await season_match_stats_service.apply_match(fake_db, "u1", "season_001", 1, _match_stats(), 42.0, NOW)
    await season_match_stats_service.apply_match(fake_db, "u1", "season_002", 5, _match_stats(), 10.0, NOW)

    doc = fake_db._collections["season_match_stats"]["u1"]
    assert doc["season_id"] == "season_002"
    assert doc["win_streak"] == {"count": 1, "level_ids": ["5"]}
    assert set(doc["qualifying_levels"]) == {"5"}
