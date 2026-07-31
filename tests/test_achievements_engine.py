"""Tests for achievements_engine — T-447 ST-07, extended to full 40-guard
coverage in ST-11. Covers the registry itself, the shared helpers
(_streak_length is the one with real logic worth testing directly), all 40
guards (one true + one false case each, varying a single condition), and
the evaluate_achievements orchestrator's own behavior (skip-if-unlocked,
multi-unlock, persistence).

ST-07 originally shipped a representative subset per structural category,
reasoning that testing all 40 "would just re-transcribe project_spec.md
into assertions". ST-11 revisits that: each guard is independent boolean
logic hand-transcribed from guard_notes, and a mistake in any one of them
(wrong operator, wrong threshold, AND where it should be OR) is exactly the
kind of bug a representative-sample strategy misses for the other 28 --
it's not spec-restating, it's the only thing that would actually catch a
transcription error in an untested guard."""

from datetime import datetime, timezone

from app.services import achievements_engine as eng
from scripts.seed_achievements import ACHIEVEMENTS

NOW = datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc)


def _ms(won=True, mode="big_dig", **overrides):
    base = {
        "won": won, "game_mode": mode, "target_score": 10,
        "npcs": {"bola": 0, "mancha": 0, "huracan": 0, "zas": 0},
        "hits_taken": 0, "badsmell_hits": 0, "stuns_taken": 0, "frozen_secs": 0.0,
        "food_collected": 0, "max_food_deficit": 0, "final_gap": 0, "lead_changes": 0,
        "max_food_drought_secs": 0.0, "max_idle_secs": 0.0, "maze_coverage_pct": 0.0,
        "shift_reroutes": 0, "time_to_target_secs": 0.0, "round_duration_secs": 120.0,
    }
    base.update(overrides)
    return base


def _ctx(**overrides):
    base = dict(
        level_id=1, stars_earned=1, match_stats=_ms(), win_rate_snapshot=None,
        season_stars=0, streak_levels=[], qualifying_levels={}, three_star_levels={},
        season_points=None,
    )
    base.update(overrides)
    return eng.GuardContext(**base)


# --- registry --------------------------------------------------------------


def test_guards_registry_matches_seeded_achievement_ids():
    assert set(eng.GUARDS) == {a["achievement_id"] for a in ACHIEVEMENTS}
    assert len(eng.GUARDS) == 40


# --- _streak_length ----------------------------------------------------


def test_streak_length_counts_trailing_entries_under_threshold():
    levels = [
        {"level_id": "1", "win_rate_snapshot": 50.0},
        {"level_id": "2", "win_rate_snapshot": 40.0},
        {"level_id": "3", "win_rate_snapshot": 30.0},
    ]
    assert eng._streak_length(levels, 70) == 3


def test_streak_length_stops_at_first_entry_over_threshold_from_the_end():
    levels = [
        {"level_id": "1", "win_rate_snapshot": 30.0},
        {"level_id": "2", "win_rate_snapshot": 90.0},  # too easy for this achievement
        {"level_id": "3", "win_rate_snapshot": 30.0},
    ]
    # only the trailing run counts -- the easy win at index 1 breaks it for
    # this achievement, level 1's earlier qualifying win doesn't carry over
    assert eng._streak_length(levels, 70) == 1


def test_streak_length_treats_missing_wr_as_disqualifying():
    levels = [
        {"level_id": "1", "win_rate_snapshot": 30.0},
        {"level_id": "2", "win_rate_snapshot": None},
    ]
    assert eng._streak_length(levels, 70) == 0


# --- single-match guards -------------------------------------------------


def test_first_blood_requires_a_win():
    assert eng.GUARDS["first_blood"](_ctx(match_stats=_ms(won=True))) is True
    assert eng.GUARDS["first_blood"](_ctx(match_stats=_ms(won=False))) is False


def test_star_born_requires_three_stars_this_match():
    assert eng.GUARDS["star_born"](_ctx(stars_earned=3)) is True
    assert eng.GUARDS["star_born"](_ctx(stars_earned=2)) is False


def test_double_threat_requires_both_npcs_and_zero_hits():
    ok = _ctx(match_stats=_ms(won=True, hits_taken=0, badsmell_hits=0, npcs={"bola": 1, "mancha": 1, "huracan": 0, "zas": 0}))
    assert eng.GUARDS["double_threat"](ok) is True

    missing_mancha = _ctx(match_stats=_ms(won=True, hits_taken=0, badsmell_hits=0, npcs={"bola": 1, "mancha": 0, "huracan": 0, "zas": 0}))
    assert eng.GUARDS["double_threat"](missing_mancha) is False


def test_speedy_requires_first_bite_mode_even_though_guard_notes_omit_it():
    base = dict(won=True, game_mode="first_bite", target_score=10, round_duration_secs=120.0, time_to_target_secs=50.0)
    ok = _ctx(match_stats=_ms(**base), win_rate_snapshot=55.0)
    assert eng.GUARDS["speedy"](ok) is True

    wrong_mode = _ctx(match_stats=_ms(**{**base, "game_mode": "big_dig"}), win_rate_snapshot=55.0)
    assert eng.GUARDS["speedy"](wrong_mode) is False


# --- streak guards -------------------------------------------------------


def test_on_a_roll_needs_two_qualifying_consecutive_wins():
    levels = [{"level_id": "1", "win_rate_snapshot": 75.0}, {"level_id": "2", "win_rate_snapshot": 60.0}]
    assert eng.GUARDS["on_a_roll"](_ctx(streak_levels=levels)) is True

    levels_short = levels[:1]
    assert eng.GUARDS["on_a_roll"](_ctx(streak_levels=levels_short)) is False


def test_unbreakable_and_relentless_use_different_thresholds_on_same_streak():
    # 7 entries all under 40 -- satisfies relentless (7 @ WR<=40) but not
    # unbreakable (needs 10 @ WR<=60, only has 7 entries total)
    levels = [{"level_id": str(i), "win_rate_snapshot": 35.0} for i in range(7)]
    assert eng.GUARDS["relentless"](_ctx(streak_levels=levels)) is True
    assert eng.GUARDS["unbreakable"](_ctx(streak_levels=levels)) is False


# --- qualifying-count guards -----------------------------------------------


def test_ghost_counts_distinct_hit_free_qualifying_levels():
    qualifying = {
        str(i): {"hits_taken": 0, "win_rate_snapshot": 45.0, "npcs": {"bola": 1, "mancha": 0, "huracan": 0, "zas": 0}}
        for i in range(5)
    }
    assert eng.GUARDS["ghost"](_ctx(qualifying_levels=qualifying)) is True
    assert eng.GUARDS["ghost"](_ctx(qualifying_levels=dict(list(qualifying.items())[:4]))) is False


def test_ghost_excludes_levels_without_bola_or_mancha():
    qualifying = {
        str(i): {"hits_taken": 0, "win_rate_snapshot": 45.0, "npcs": {"bola": 0, "mancha": 0, "huracan": 1, "zas": 0}}
        for i in range(5)
    }
    assert eng.GUARDS["ghost"](_ctx(qualifying_levels=qualifying)) is False


def test_all_modes_needs_all_eight_distinct_modes_under_threshold():
    modes = ["big_dig", "first_bite", "huracans_friends", "whole_gangs_here",
             "deep_run", "watch_the_walls", "hot_floor", "the_chase"]
    qualifying = {str(i): {"mode": m, "win_rate_snapshot": 75.0} for i, m in enumerate(modes)}
    assert eng.GUARDS["all_modes"](_ctx(qualifying_levels=qualifying)) is True

    qualifying.pop("0")
    assert eng.GUARDS["all_modes"](_ctx(qualifying_levels=qualifying)) is False


# --- three-star guards -----------------------------------------------------


def test_three_star_warrior_needs_20_total_and_10_hard():
    easy = {str(i): {"win_rate_snapshot": 80.0} for i in range(10)}
    hard = {str(i): {"win_rate_snapshot": 40.0} for i in range(10, 20)}
    assert eng.GUARDS["three_star_warrior"](_ctx(three_star_levels={**easy, **hard})) is True
    assert eng.GUARDS["three_star_warrior"](_ctx(three_star_levels=easy)) is False  # 10 total, none hard enough combo


def test_perfect_champion_needs_wr_and_npc_together():
    ok = {str(i): {"win_rate_snapshot": 15.0, "npcs": {"bola": 1, "mancha": 0, "huracan": 0, "zas": 0}} for i in range(10)}
    assert eng.GUARDS["perfect_champion"](_ctx(three_star_levels=ok)) is True

    no_npc = {str(i): {"win_rate_snapshot": 15.0, "npcs": {"bola": 0, "mancha": 0, "huracan": 1, "zas": 0}} for i in range(10)}
    assert eng.GUARDS["perfect_champion"](_ctx(three_star_levels=no_npc)) is False


# --- remaining COMMON guards (T-447 ST-11) --------------------------------


def test_never_give_up_needs_comeback_and_wr_and_npc():
    ok = _ctx(match_stats=_ms(won=True, max_food_deficit=5, npcs={"bola": 0, "mancha": 0, "huracan": 1, "zas": 0}), win_rate_snapshot=60.0)
    assert eng.GUARDS["never_give_up"](ok) is True

    too_small_deficit = _ctx(match_stats=_ms(won=True, max_food_deficit=4, npcs={"bola": 0, "mancha": 0, "huracan": 1, "zas": 0}), win_rate_snapshot=60.0)
    assert eng.GUARDS["never_give_up"](too_small_deficit) is False


def test_always_moving_needs_level_11_plus_and_food_mode():
    ok = _ctx(level_id=11, match_stats=_ms(won=True, max_idle_secs=5, mode="big_dig"), win_rate_snapshot=70.0)
    assert eng.GUARDS["always_moving"](ok) is True

    too_low_level = _ctx(level_id=10, match_stats=_ms(won=True, max_idle_secs=5, mode="big_dig"), win_rate_snapshot=70.0)
    assert eng.GUARDS["always_moving"](too_low_level) is False


def test_hot_streak_needs_three_qualifying_consecutive_wins():
    levels = [{"level_id": str(i), "win_rate_snapshot": 70.0} for i in range(3)]
    assert eng.GUARDS["hot_streak"](_ctx(streak_levels=levels)) is True
    assert eng.GUARDS["hot_streak"](_ctx(streak_levels=levels[:2])) is False


def test_big_eater_needs_food_and_food_mode_and_two_npcs():
    ok = _ctx(match_stats=_ms(food_collected=25, mode="big_dig", npcs={"huracan": 1, "zas": 1, "bola": 0, "mancha": 0}))
    assert eng.GUARDS["big_eater"](ok) is True

    not_enough_food = _ctx(match_stats=_ms(food_collected=24, mode="big_dig", npcs={"huracan": 1, "zas": 1, "bola": 0, "mancha": 0}))
    assert eng.GUARDS["big_eater"](not_enough_food) is False


def test_stars_75_needs_season_stars_threshold():
    assert eng.GUARDS["stars_75"](_ctx(season_stars=75)) is True
    assert eng.GUARDS["stars_75"](_ctx(season_stars=74)) is False


def test_full_house_needs_five_whole_gangs_here_levels():
    qualifying = {str(i): {"mode": "whole_gangs_here", "win_rate_snapshot": 70.0} for i in range(5)}
    assert eng.GUARDS["full_house"](_ctx(qualifying_levels=qualifying)) is True
    assert eng.GUARDS["full_house"](_ctx(qualifying_levels=dict(list(qualifying.items())[:4]))) is False


def test_zas_chaser_needs_three_zas_levels_under_wr():
    qualifying = {str(i): {"npcs": {"zas": 1}, "win_rate_snapshot": 50.0} for i in range(3)}
    assert eng.GUARDS["zas_chaser"](_ctx(qualifying_levels=qualifying)) is True
    assert eng.GUARDS["zas_chaser"](_ctx(qualifying_levels=dict(list(qualifying.items())[:2]))) is False


# --- remaining UNCOMMON guards (T-447 ST-11) --------------------------------


def test_stink_proof_needs_level_11_plus_and_no_badsmell_hits():
    ok = _ctx(level_id=11, match_stats=_ms(won=True, badsmell_hits=0, npcs={"mancha": 1, "bola": 0, "huracan": 0, "zas": 0}), win_rate_snapshot=70.0)
    assert eng.GUARDS["stink_proof"](ok) is True

    got_hit = _ctx(level_id=11, match_stats=_ms(won=True, badsmell_hits=1, npcs={"mancha": 1, "bola": 0, "huracan": 0, "zas": 0}), win_rate_snapshot=70.0)
    assert eng.GUARDS["stink_proof"](got_hit) is False


def test_comeback_king_needs_three_deficit_comebacks():
    qualifying = {str(i): {"max_food_deficit": 5, "win_rate_snapshot": 60.0, "npcs": {"huracan": 1, "zas": 0}} for i in range(3)}
    assert eng.GUARDS["comeback_king"](_ctx(qualifying_levels=qualifying)) is True
    assert eng.GUARDS["comeback_king"](_ctx(qualifying_levels=dict(list(qualifying.items())[:2]))) is False


def test_maze_master_needs_90_pct_coverage_in_food_mode():
    ok = _ctx(level_id=11, match_stats=_ms(won=True, maze_coverage_pct=90.0, mode="big_dig"), win_rate_snapshot=70.0)
    assert eng.GUARDS["maze_master"](ok) is True

    not_enough_coverage = _ctx(level_id=11, match_stats=_ms(won=True, maze_coverage_pct=89.0, mode="big_dig"), win_rate_snapshot=70.0)
    assert eng.GUARDS["maze_master"](not_enough_coverage) is False


def test_bola_dancer_needs_zero_stuns_with_bola_present():
    ok = _ctx(match_stats=_ms(won=True, stuns_taken=0, npcs={"bola": 1, "mancha": 0, "huracan": 0, "zas": 0}), win_rate_snapshot=60.0)
    assert eng.GUARDS["bola_dancer"](ok) is True

    got_stunned = _ctx(match_stats=_ms(won=True, stuns_taken=1, npcs={"bola": 1, "mancha": 0, "huracan": 0, "zas": 0}), win_rate_snapshot=60.0)
    assert eng.GUARDS["bola_dancer"](got_stunned) is False


def test_daredevil_needs_frozen_time_with_mancha_present():
    ok = _ctx(match_stats=_ms(won=True, frozen_secs=1.0, npcs={"mancha": 1, "bola": 0, "huracan": 0, "zas": 0}), win_rate_snapshot=60.0)
    assert eng.GUARDS["daredevil"](ok) is True

    never_frozen = _ctx(match_stats=_ms(won=True, frozen_secs=0.0, npcs={"mancha": 1, "bola": 0, "huracan": 0, "zas": 0}), win_rate_snapshot=60.0)
    assert eng.GUARDS["daredevil"](never_frozen) is False


def test_hungry_hungry_needs_two_npcs_and_short_food_drought():
    ok = _ctx(match_stats=_ms(won=True, max_food_drought_secs=20.0, mode="big_dig", npcs={"bola": 1, "mancha": 1, "huracan": 0, "zas": 0}), win_rate_snapshot=60.0)
    assert eng.GUARDS["hungry_hungry"](ok) is True

    only_one_npc = _ctx(match_stats=_ms(won=True, max_food_drought_secs=20.0, mode="big_dig", npcs={"bola": 1, "mancha": 0, "huracan": 0, "zas": 0}), win_rate_snapshot=60.0)
    assert eng.GUARDS["hungry_hungry"](only_one_npc) is False


def test_thriller_needs_three_close_comeback_wins():
    qualifying = {str(i): {"final_gap": 3, "lead_changes": 2, "win_rate_snapshot": 60.0, "npcs": {"huracan": 1, "zas": 0}} for i in range(3)}
    assert eng.GUARDS["thriller"](_ctx(qualifying_levels=qualifying)) is True
    assert eng.GUARDS["thriller"](_ctx(qualifying_levels=dict(list(qualifying.items())[:2]))) is False


# --- remaining RARE guards (T-447 ST-11) --------------------------------


def test_wall_dodger_needs_five_reroutes_in_watch_the_walls():
    ok = _ctx(match_stats=_ms(won=True, shift_reroutes=5, mode="watch_the_walls"))
    assert eng.GUARDS["wall_dodger"](ok) is True

    not_enough_reroutes = _ctx(match_stats=_ms(won=True, shift_reroutes=4, mode="watch_the_walls"))
    assert eng.GUARDS["wall_dodger"](not_enough_reroutes) is False


def test_deep_survivor_needs_hit_free_deep_run():
    ok = _ctx(match_stats=_ms(won=True, mode="deep_run", hits_taken=0, npcs={"bola": 1, "mancha": 0, "huracan": 0, "zas": 0}))
    assert eng.GUARDS["deep_survivor"](ok) is True

    got_hit = _ctx(match_stats=_ms(won=True, mode="deep_run", hits_taken=1, npcs={"bola": 1, "mancha": 0, "huracan": 0, "zas": 0}))
    assert eng.GUARDS["deep_survivor"](got_hit) is False


def test_speedster_needs_90s_remaining_and_wr_at_most_50():
    ok = _ctx(match_stats=_ms(won=True, mode="first_bite", round_duration_secs=120.0, time_to_target_secs=30.0), win_rate_snapshot=50.0)
    assert eng.GUARDS["speedster"](ok) is True

    wr_too_high = _ctx(match_stats=_ms(won=True, mode="first_bite", round_duration_secs=120.0, time_to_target_secs=30.0), win_rate_snapshot=51.0)
    assert eng.GUARDS["speedster"](wr_too_high) is False


def test_outrun_the_swarm_needs_five_no_lead_change_huracans_friends():
    qualifying = {str(i): {"mode": "huracans_friends", "lead_changes": 0} for i in range(5)}
    assert eng.GUARDS["outrun_the_swarm"](_ctx(qualifying_levels=qualifying)) is True
    assert eng.GUARDS["outrun_the_swarm"](_ctx(qualifying_levels=dict(list(qualifying.items())[:4]))) is False


def test_clean_sweep_season_needs_ten_hit_free_levels():
    qualifying = {str(i): {"hits_taken": 0, "win_rate_snapshot": 50.0, "npcs": {"bola": 1, "mancha": 0}} for i in range(10)}
    assert eng.GUARDS["clean_sweep_season"](_ctx(qualifying_levels=qualifying)) is True
    assert eng.GUARDS["clean_sweep_season"](_ctx(qualifying_levels=dict(list(qualifying.items())[:9]))) is False


def test_perfectionist_needs_20_total_and_8_hard():
    easy = {str(i): {"win_rate_snapshot": 80.0} for i in range(12)}
    hard = {str(i): {"win_rate_snapshot": 40.0} for i in range(12, 20)}
    assert eng.GUARDS["perfectionist"](_ctx(three_star_levels={**easy, **hard})) is True

    only_seven_hard = {str(i): {"win_rate_snapshot": 80.0} for i in range(13)}
    only_seven_hard.update({str(i): {"win_rate_snapshot": 40.0} for i in range(13, 20)})
    assert eng.GUARDS["perfectionist"](_ctx(three_star_levels=only_seven_hard)) is False


# --- remaining EPIC guards (T-447 ST-11) --------------------------------


def test_manchas_nightmare_needs_ten_hit_free_mancha_levels():
    qualifying = {str(i): {"badsmell_hits": 0, "npcs": {"mancha": 1}, "win_rate_snapshot": 40.0} for i in range(10)}
    assert eng.GUARDS["manchas_nightmare"](_ctx(qualifying_levels=qualifying)) is True
    assert eng.GUARDS["manchas_nightmare"](_ctx(qualifying_levels=dict(list(qualifying.items())[:9]))) is False


def test_full_roster_zero_scars_needs_all_four_npcs_and_no_hits():
    ok = _ctx(match_stats=_ms(won=True, hits_taken=0, npcs={"bola": 1, "mancha": 1, "huracan": 1, "zas": 1}))
    assert eng.GUARDS["full_roster_zero_scars"](ok) is True

    missing_zas = _ctx(match_stats=_ms(won=True, hits_taken=0, npcs={"bola": 1, "mancha": 1, "huracan": 1, "zas": 0}))
    assert eng.GUARDS["full_roster_zero_scars"](missing_zas) is False


def test_speed_legend_needs_100s_remaining_no_wr_gate():
    ok = _ctx(match_stats=_ms(won=True, mode="first_bite", round_duration_secs=120.0, time_to_target_secs=20.0))
    assert eng.GUARDS["speed_legend"](ok) is True

    not_fast_enough = _ctx(match_stats=_ms(won=True, mode="first_bite", round_duration_secs=120.0, time_to_target_secs=21.0))
    assert eng.GUARDS["speed_legend"](not_fast_enough) is False


def test_survivors_gauntlet_needs_15_hit_free_levels():
    qualifying = {str(i): {"hits_taken": 0, "win_rate_snapshot": 50.0, "npcs": {"bola": 1, "mancha": 0}} for i in range(15)}
    assert eng.GUARDS["survivors_gauntlet"](_ctx(qualifying_levels=qualifying)) is True
    assert eng.GUARDS["survivors_gauntlet"](_ctx(qualifying_levels=dict(list(qualifying.items())[:14]))) is False


def test_the_hard_way_needs_three_star_low_wr_hit_npc():
    ok = _ctx(stars_earned=3, win_rate_snapshot=20.0, match_stats=_ms(npcs={"bola": 1, "mancha": 0, "huracan": 0, "zas": 0}))
    assert eng.GUARDS["the_hard_way"](ok) is True

    wr_too_high = _ctx(stars_earned=3, win_rate_snapshot=21.0, match_stats=_ms(npcs={"bola": 1, "mancha": 0, "huracan": 0, "zas": 0}))
    assert eng.GUARDS["the_hard_way"](wr_too_high) is False


# --- remaining LEGENDARY guards (T-447 ST-11) --------------------------------


def test_invincible_needs_ten_hit_free_levels_under_25_wr():
    qualifying = {str(i): {"hits_taken": 0, "win_rate_snapshot": 25.0, "npcs": {"bola": 1, "mancha": 0}} for i in range(10)}
    assert eng.GUARDS["invincible"](_ctx(qualifying_levels=qualifying)) is True
    assert eng.GUARDS["invincible"](_ctx(qualifying_levels=dict(list(qualifying.items())[:9]))) is False


def test_flawless_needs_twenty_hit_free_levels_under_40_wr():
    qualifying = {str(i): {"hits_taken": 0, "win_rate_snapshot": 40.0, "npcs": {"bola": 1, "mancha": 0}} for i in range(20)}
    assert eng.GUARDS["flawless"](_ctx(qualifying_levels=qualifying)) is True
    assert eng.GUARDS["flawless"](_ctx(qualifying_levels=dict(list(qualifying.items())[:19]))) is False


def test_apex_predator_needs_five_full_roster_hit_free_levels():
    qualifying = {str(i): {"hits_taken": 0, "npcs": {"bola": 1, "mancha": 1, "huracan": 1, "zas": 1}} for i in range(5)}
    assert eng.GUARDS["apex_predator"](_ctx(qualifying_levels=qualifying)) is True
    assert eng.GUARDS["apex_predator"](_ctx(qualifying_levels=dict(list(qualifying.items())[:4]))) is False


# --- season_points not yet available (ST-08) --------------------------


def test_seasonal_legend_fails_closed_when_season_points_is_none():
    assert eng.GUARDS["seasonal_legend"](_ctx(season_points=None)) is False


def test_seasonal_legend_unlocks_once_season_points_is_wired():
    assert eng.GUARDS["seasonal_legend"](_ctx(season_points=4000)) is True
    assert eng.GUARDS["seasonal_legend"](_ctx(season_points=3999)) is False


# --- evaluate_achievements orchestrator -----------------------------------


async def test_evaluate_achievements_unlocks_and_persists(fake_db):
    unlocked = await eng.evaluate_achievements(
        fake_db, "u1", level_id=1, stars_earned=1, match_stats=_ms(won=True),
        win_rate_snapshot=None, season_stars=0, season_match_stats={}, now=NOW,
    )
    assert "first_blood" in unlocked

    doc = fake_db._collections["achievement_progress"]["u1"]
    assert "first_blood" in doc["unlocked"]
    assert doc["unlock_timestamps"]["first_blood"] == NOW


async def test_evaluate_achievements_skips_already_unlocked(fake_db):
    fake_db.seed("achievement_progress", "u1", {"unlocked": ["first_blood"], "unlock_timestamps": {}})

    unlocked = await eng.evaluate_achievements(
        fake_db, "u1", level_id=1, stars_earned=1, match_stats=_ms(won=True),
        win_rate_snapshot=None, season_stars=0, season_match_stats={}, now=NOW,
    )
    assert "first_blood" not in unlocked


async def test_evaluate_achievements_can_unlock_multiple_at_once(fake_db):
    # won + 3 stars in one match -> first_blood AND star_born together
    unlocked = await eng.evaluate_achievements(
        fake_db, "u1", level_id=1, stars_earned=3, match_stats=_ms(won=True),
        win_rate_snapshot=None, season_stars=0, season_match_stats={}, now=NOW,
    )
    assert set(unlocked) >= {"first_blood", "star_born"}


async def test_evaluate_achievements_returns_empty_when_nothing_unlocks(fake_db):
    unlocked = await eng.evaluate_achievements(
        fake_db, "u1", level_id=1, stars_earned=1, match_stats=_ms(won=False),
        win_rate_snapshot=None, season_stars=0, season_match_stats={}, now=NOW,
    )
    assert unlocked == []
    assert "u1" not in fake_db._collections.get("achievement_progress", {})
