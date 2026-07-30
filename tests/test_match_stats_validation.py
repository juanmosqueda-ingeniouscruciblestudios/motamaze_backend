"""Unit tests for game._is_match_stats_valid — T-447 ST-01/ST-06 (REST-001
"Validaciones server-side"). Pydantic itself only enforces types (no
Field(ge=0)/range constraints, deliberately -- see MatchStats docstring), so
these value-range rules are the actual gate."""

from app.routers.game import MatchStats, MatchStatsNpcs, _is_match_stats_valid


def _stats(**overrides) -> MatchStats:
    base = dict(
        won=True, game_mode="big_dig", target_score=10,
        npcs=MatchStatsNpcs(), hits_taken=0, badsmell_hits=0, stuns_taken=0,
        frozen_secs=0.0, food_collected=10, max_food_deficit=0, final_gap=0,
        lead_changes=0, max_food_drought_secs=0.0, max_idle_secs=0.0,
        maze_coverage_pct=50.0, shift_reroutes=0, time_to_target_secs=10.0,
        round_duration_secs=120.0,
    )
    base.update(overrides)
    return MatchStats(**base)


def test_baseline_stats_are_valid():
    assert _is_match_stats_valid(_stats()) is True


def test_negative_counter_is_invalid():
    assert _is_match_stats_valid(_stats(hits_taken=-1)) is False


def test_coverage_above_100_is_invalid():
    assert _is_match_stats_valid(_stats(maze_coverage_pct=101.0)) is False


def test_coverage_below_0_is_invalid():
    assert _is_match_stats_valid(_stats(maze_coverage_pct=-0.1)) is False


def test_unknown_game_mode_is_invalid():
    assert _is_match_stats_valid(_stats(game_mode="dodge_burrow")) is False


def test_zero_round_duration_is_invalid():
    assert _is_match_stats_valid(_stats(round_duration_secs=0)) is False


def test_time_field_exceeding_round_duration_is_invalid():
    assert _is_match_stats_valid(_stats(round_duration_secs=60.0, time_to_target_secs=61.0)) is False


def test_time_field_equal_to_round_duration_is_valid():
    assert _is_match_stats_valid(_stats(round_duration_secs=60.0, time_to_target_secs=60.0)) is True


def test_negative_time_field_is_invalid():
    assert _is_match_stats_valid(_stats(frozen_secs=-0.5)) is False
