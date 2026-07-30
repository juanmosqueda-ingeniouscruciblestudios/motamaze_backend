"""Unit tests for season_match_stats_service.apply_match — T-447 ST-06
(win_streak/qualifying_levels), patched in ST-07 to add per-entry WR
snapshots to the streak and a separate three_star_levels map."""

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


async def _apply(fake_db, uid, season_id, level_id, match_stats, win_rate_snapshot, now, stars_earned=0):
    await season_match_stats_service.apply_match(
        fake_db, uid, season_id, level_id, stars_earned, match_stats, win_rate_snapshot, now,
    )


async def test_first_win_creates_streak_and_qualifying_entry(fake_db):
    await _apply(fake_db, "u1", "season_001", 1, _match_stats(), 42.0, NOW)

    doc = fake_db._collections["season_match_stats"]["u1"]
    assert doc["win_streak"] == {"count": 1, "levels": [{"level_id": "1", "win_rate_snapshot": 42.0}]}
    assert doc["qualifying_levels"]["1"]["win_rate_snapshot"] == 42.0
    assert doc["qualifying_levels"]["1"]["mode"] == "big_dig"


async def test_winning_a_new_level_extends_streak(fake_db):
    await _apply(fake_db, "u1", "season_001", 1, _match_stats(), 42.0, NOW)
    await _apply(fake_db, "u1", "season_001", 2, _match_stats(), 30.0, NOW)

    doc = fake_db._collections["season_match_stats"]["u1"]
    assert doc["win_streak"]["count"] == 2
    assert [e["level_id"] for e in doc["win_streak"]["levels"]] == ["1", "2"]
    assert [e["win_rate_snapshot"] for e in doc["win_streak"]["levels"]] == [42.0, 30.0]
    assert set(doc["qualifying_levels"]) == {"1", "2"}


async def test_repeating_a_won_level_is_a_streak_noop(fake_db):
    await _apply(fake_db, "u1", "season_001", 1, _match_stats(), 42.0, NOW)
    await _apply(fake_db, "u1", "season_001", 1, _match_stats(hits_taken=3), 99.0, NOW)

    doc = fake_db._collections["season_match_stats"]["u1"]
    assert doc["win_streak"] == {"count": 1, "levels": [{"level_id": "1", "win_rate_snapshot": 42.0}]}
    # first-win snapshot is kept, not overwritten by the second (worse) win
    assert doc["qualifying_levels"]["1"]["hits_taken"] == 0
    assert doc["qualifying_levels"]["1"]["win_rate_snapshot"] == 42.0


async def test_losing_resets_the_streak_even_on_a_repeated_level(fake_db):
    await _apply(fake_db, "u1", "season_001", 1, _match_stats(), 42.0, NOW)
    await _apply(fake_db, "u1", "season_001", 2, _match_stats(), 30.0, NOW)
    await _apply(fake_db, "u1", "season_001", 1, _match_stats(won=False), None, NOW)

    doc = fake_db._collections["season_match_stats"]["u1"]
    assert doc["win_streak"] == {"count": 0, "levels": []}
    # qualifying_levels is never pruned by a loss -- already-earned facts stick
    assert set(doc["qualifying_levels"]) == {"1", "2"}


async def test_new_season_resets_streak_and_qualifying_levels(fake_db):
    await _apply(fake_db, "u1", "season_001", 1, _match_stats(), 42.0, NOW)
    await _apply(fake_db, "u1", "season_002", 5, _match_stats(), 10.0, NOW)

    doc = fake_db._collections["season_match_stats"]["u1"]
    assert doc["season_id"] == "season_002"
    assert doc["win_streak"]["count"] == 1
    assert [e["level_id"] for e in doc["win_streak"]["levels"]] == ["5"]
    assert set(doc["qualifying_levels"]) == {"5"}
    assert doc["three_star_levels"] == {}


async def test_three_star_clear_recorded_independent_of_qualifying_levels(fake_db):
    # 1-star win first (creates qualifying_levels[1], no three_star entry)...
    await _apply(fake_db, "u1", "season_001", 1, _match_stats(), 42.0, NOW, stars_earned=1)
    doc = fake_db._collections["season_match_stats"]["u1"]
    assert doc["three_star_levels"] == {}
    assert doc["qualifying_levels"]["1"]["win_rate_snapshot"] == 42.0

    # ...then a later 3-star replay at a different WR snapshot records the
    # 3-star fact WITHOUT touching the already-recorded qualifying_levels entry.
    await _apply(fake_db, "u1", "season_001", 1, _match_stats(), 20.0, NOW, stars_earned=3)
    doc = fake_db._collections["season_match_stats"]["u1"]
    assert doc["three_star_levels"]["1"]["win_rate_snapshot"] == 20.0
    assert doc["qualifying_levels"]["1"]["win_rate_snapshot"] == 42.0  # unchanged


async def test_three_star_only_recorded_once_per_level(fake_db):
    await _apply(fake_db, "u1", "season_001", 1, _match_stats(), 42.0, NOW, stars_earned=3)
    await _apply(fake_db, "u1", "season_001", 1, _match_stats(), 5.0, NOW, stars_earned=3)

    doc = fake_db._collections["season_match_stats"]["u1"]
    assert doc["three_star_levels"]["1"]["win_rate_snapshot"] == 42.0
