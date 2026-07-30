"""T-447 ST-07: the 40 achievement guards, as Python predicates over
GuardContext -- see config/achievements' guard_notes (ST-05) and
season_match_stats (ST-06) for why this is code, not data.

Interpretive decisions baked into these predicates, beyond a literal
transcription of project_spec.md's "Guards / Conditions" column:

- Streak guards (on_a_roll, hot_streak, relentless, unbreakable) use
  _streak_length: the trailing run of the current win_streak whose entries
  all have win_rate_snapshot <= the achievement's own threshold. A win on a
  level *above* that threshold breaks the run for THIS achievement (even
  though it doesn't reset season_match_stats.win_streak itself, which has
  no threshold of its own) -- confirmed 2026-07-30. A missing WR snapshot
  is treated the same as exceeding the threshold (fail closed, matching
  DATA_MODEL's "WR ausente = guard no evaluable").
- speedy/speedster/speed_legend structurally only make sense in first_bite
  (time_to_target_secs/target_score are meaningless outside a race-to-target
  mode) -- game_mode == "first_bite" is enforced even where guard_notes
  doesn't spell it out, matching speedster/speed_legend's own guard_notes,
  which do.
- "Food mode" (always_moving, maze_master, hungry_hungry, big_eater) means
  game_mode != "deep_run" -- deep_run is the only mode with FOOD_COUNT=0, so
  guard_notes' "(not deep_run)" parenthetical is read as the full exclusion
  rule, not an example.
- seasonal_legend needs season_points, which doesn't exist until T-447 ST-08
  wires the season_points formula. ctx.season_points is None until then, and
  the guard fails closed on None -- same fail-closed reasoning as an absent
  WR, not a bug.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from google.cloud.firestore import AsyncClient

_HIT_NPCS = ("bola", "mancha")


@dataclass
class GuardContext:
    level_id: int
    stars_earned: int
    match_stats: dict
    win_rate_snapshot: float | None
    season_stars: int
    streak_levels: list[dict]
    qualifying_levels: dict[str, dict]
    three_star_levels: dict[str, dict]
    season_points: float | None = None  # None until ST-08


def _streak_length(levels: list[dict], wr_threshold: float) -> int:
    count = 0
    for entry in reversed(levels):
        wr = entry.get("win_rate_snapshot")
        if wr is None or wr > wr_threshold:
            break
        count += 1
    return count


def _count(records: dict, predicate: Callable[[dict], bool]) -> int:
    return sum(1 for rec in records.values() if predicate(rec))


def _npc_present(npcs: dict, *names: str) -> bool:
    return any(npcs.get(n, 0) >= 1 for n in names)


def _wr_at_most(rec: dict, threshold: float) -> bool:
    wr = rec.get("win_rate_snapshot")
    return wr is not None and wr <= threshold


# --- COMMON ------------------------------------------------------------

def _first_blood(ctx: GuardContext) -> bool:
    return ctx.match_stats["won"]


def _on_a_roll(ctx: GuardContext) -> bool:
    return _streak_length(ctx.streak_levels, 80) >= 2


def _star_born(ctx: GuardContext) -> bool:
    return ctx.stars_earned == 3


def _never_give_up(ctx: GuardContext) -> bool:
    ms = ctx.match_stats
    return (
        ms["won"] and ms["max_food_deficit"] >= 5
        and ctx.win_rate_snapshot is not None and ctx.win_rate_snapshot <= 60
        and _npc_present(ms["npcs"], "huracan", "zas")
    )


def _always_moving(ctx: GuardContext) -> bool:
    ms = ctx.match_stats
    return (
        ms["won"] and ms["max_idle_secs"] <= 5 and ms["game_mode"] != "deep_run"
        and ctx.level_id >= 11
        and ctx.win_rate_snapshot is not None and ctx.win_rate_snapshot <= 70
    )


def _hot_streak(ctx: GuardContext) -> bool:
    return _streak_length(ctx.streak_levels, 70) >= 3


def _big_eater(ctx: GuardContext) -> bool:
    ms = ctx.match_stats
    return (
        ms["food_collected"] >= 25 and ms["game_mode"] != "deep_run"
        and (ms["npcs"].get("huracan", 0) + ms["npcs"].get("zas", 0)) >= 2
    )


def _stars_75(ctx: GuardContext) -> bool:
    return ctx.season_stars >= 75


def _full_house(ctx: GuardContext) -> bool:
    return _count(
        ctx.qualifying_levels,
        lambda r: r["mode"] == "whole_gangs_here" and _wr_at_most(r, 70),
    ) >= 5


def _zas_chaser(ctx: GuardContext) -> bool:
    return _count(
        ctx.qualifying_levels,
        lambda r: r["npcs"].get("zas", 0) >= 1 and _wr_at_most(r, 50),
    ) >= 3


# --- UNCOMMON ------------------------------------------------------------

def _speedy(ctx: GuardContext) -> bool:
    ms = ctx.match_stats
    remaining = ms["round_duration_secs"] - ms["time_to_target_secs"]
    return (
        ms["won"] and ms["game_mode"] == "first_bite" and remaining >= 60
        and ms["target_score"] >= 10
        and ctx.win_rate_snapshot is not None and ctx.win_rate_snapshot <= 60
    )


def _stink_proof(ctx: GuardContext) -> bool:
    ms = ctx.match_stats
    return (
        ms["won"] and ms["badsmell_hits"] == 0 and ms["npcs"].get("mancha", 0) >= 1
        and ctx.level_id >= 11
        and ctx.win_rate_snapshot is not None and ctx.win_rate_snapshot <= 70
    )


def _comeback_king(ctx: GuardContext) -> bool:
    return _count(
        ctx.qualifying_levels,
        lambda r: r["max_food_deficit"] >= 5 and _wr_at_most(r, 60)
        and _npc_present(r["npcs"], "huracan", "zas"),
    ) >= 3


def _maze_master(ctx: GuardContext) -> bool:
    ms = ctx.match_stats
    return (
        ms["won"] and ms["maze_coverage_pct"] >= 90 and ctx.level_id >= 11
        and ms["game_mode"] != "deep_run"
        and ctx.win_rate_snapshot is not None and ctx.win_rate_snapshot <= 70
    )


def _bola_dancer(ctx: GuardContext) -> bool:
    ms = ctx.match_stats
    return (
        ms["won"] and ms["stuns_taken"] == 0 and ms["npcs"].get("bola", 0) >= 1
        and ctx.win_rate_snapshot is not None and ctx.win_rate_snapshot <= 60
    )


def _daredevil(ctx: GuardContext) -> bool:
    ms = ctx.match_stats
    return (
        ms["won"] and ms["frozen_secs"] > 0 and ms["npcs"].get("mancha", 0) >= 1
        and ctx.win_rate_snapshot is not None and ctx.win_rate_snapshot <= 60
    )


def _hungry_hungry(ctx: GuardContext) -> bool:
    ms = ctx.match_stats
    total_npcs = sum(ms["npcs"].values())
    return (
        ms["won"] and ms["max_food_drought_secs"] <= 20 and ms["game_mode"] != "deep_run"
        and total_npcs >= 2
        and ctx.win_rate_snapshot is not None and ctx.win_rate_snapshot <= 60
    )


def _all_modes(ctx: GuardContext) -> bool:
    modes = {r["mode"] for r in ctx.qualifying_levels.values() if _wr_at_most(r, 80)}
    return len(modes) >= 8


def _thriller(ctx: GuardContext) -> bool:
    return _count(
        ctx.qualifying_levels,
        lambda r: r["final_gap"] <= 3 and r["lead_changes"] >= 2 and _wr_at_most(r, 60)
        and _npc_present(r["npcs"], "huracan", "zas"),
    ) >= 3


def _three_star_warrior(ctx: GuardContext) -> bool:
    total = len(ctx.three_star_levels)
    hard = _count(ctx.three_star_levels, lambda r: _wr_at_most(r, 50))
    return total >= 20 and hard >= 10


# --- RARE ------------------------------------------------------------

def _wall_dodger(ctx: GuardContext) -> bool:
    ms = ctx.match_stats
    return ms["won"] and ms["shift_reroutes"] >= 5 and ms["game_mode"] == "watch_the_walls"


def _ghost(ctx: GuardContext) -> bool:
    return _count(
        ctx.qualifying_levels,
        lambda r: r["hits_taken"] == 0 and _wr_at_most(r, 50) and _npc_present(r["npcs"], *_HIT_NPCS),
    ) >= 5


def _deep_survivor(ctx: GuardContext) -> bool:
    ms = ctx.match_stats
    return (
        ms["won"] and ms["game_mode"] == "deep_run" and ms["hits_taken"] == 0
        and _npc_present(ms["npcs"], *_HIT_NPCS)
    )


def _speedster(ctx: GuardContext) -> bool:
    ms = ctx.match_stats
    remaining = ms["round_duration_secs"] - ms["time_to_target_secs"]
    return (
        ms["won"] and ms["game_mode"] == "first_bite" and remaining >= 90
        and ctx.win_rate_snapshot is not None and ctx.win_rate_snapshot <= 50
    )


def _outrun_the_swarm(ctx: GuardContext) -> bool:
    return _count(
        ctx.qualifying_levels,
        lambda r: r["mode"] == "huracans_friends" and r["lead_changes"] == 0,
    ) >= 5


def _clean_sweep_season(ctx: GuardContext) -> bool:
    return _count(
        ctx.qualifying_levels,
        lambda r: r["hits_taken"] == 0 and _wr_at_most(r, 50) and _npc_present(r["npcs"], *_HIT_NPCS),
    ) >= 10


def _perfectionist(ctx: GuardContext) -> bool:
    total = len(ctx.three_star_levels)
    hard = _count(ctx.three_star_levels, lambda r: _wr_at_most(r, 40))
    return total >= 20 and hard >= 8


def _double_threat(ctx: GuardContext) -> bool:
    ms = ctx.match_stats
    return (
        ms["won"] and ms["hits_taken"] == 0 and ms["badsmell_hits"] == 0
        and ms["npcs"].get("bola", 0) >= 1 and ms["npcs"].get("mancha", 0) >= 1
    )


# --- EPIC ------------------------------------------------------------

def _manchas_nightmare(ctx: GuardContext) -> bool:
    return _count(
        ctx.qualifying_levels,
        lambda r: r["badsmell_hits"] == 0 and r["npcs"].get("mancha", 0) >= 1 and _wr_at_most(r, 40),
    ) >= 10


def _full_roster_zero_scars(ctx: GuardContext) -> bool:
    ms = ctx.match_stats
    return (
        ms["won"] and ms["hits_taken"] == 0
        and all(ms["npcs"].get(n, 0) >= 1 for n in ("bola", "mancha", "huracan", "zas"))
    )


def _speed_legend(ctx: GuardContext) -> bool:
    ms = ctx.match_stats
    remaining = ms["round_duration_secs"] - ms["time_to_target_secs"]
    return ms["won"] and ms["game_mode"] == "first_bite" and remaining >= 100


def _survivors_gauntlet(ctx: GuardContext) -> bool:
    return _count(
        ctx.qualifying_levels,
        lambda r: r["hits_taken"] == 0 and _wr_at_most(r, 50) and _npc_present(r["npcs"], *_HIT_NPCS),
    ) >= 15


def _the_hard_way(ctx: GuardContext) -> bool:
    return (
        ctx.stars_earned == 3
        and ctx.win_rate_snapshot is not None and ctx.win_rate_snapshot <= 20
        and _npc_present(ctx.match_stats["npcs"], *_HIT_NPCS)
    )


def _relentless(ctx: GuardContext) -> bool:
    return _streak_length(ctx.streak_levels, 40) >= 7


# --- LEGENDARY ------------------------------------------------------------

def _unbreakable(ctx: GuardContext) -> bool:
    return _streak_length(ctx.streak_levels, 60) >= 10


def _invincible(ctx: GuardContext) -> bool:
    return _count(
        ctx.qualifying_levels,
        lambda r: r["hits_taken"] == 0 and _wr_at_most(r, 25) and _npc_present(r["npcs"], *_HIT_NPCS),
    ) >= 10


def _flawless(ctx: GuardContext) -> bool:
    return _count(
        ctx.qualifying_levels,
        lambda r: r["hits_taken"] == 0 and _wr_at_most(r, 40) and _npc_present(r["npcs"], *_HIT_NPCS),
    ) >= 20


def _apex_predator(ctx: GuardContext) -> bool:
    return _count(
        ctx.qualifying_levels,
        lambda r: r["hits_taken"] == 0
        and all(r["npcs"].get(n, 0) >= 1 for n in ("bola", "mancha", "huracan", "zas")),
    ) >= 5


def _seasonal_legend(ctx: GuardContext) -> bool:
    return ctx.season_points is not None and ctx.season_points >= 4000


def _perfect_champion(ctx: GuardContext) -> bool:
    return _count(
        ctx.three_star_levels,
        lambda r: _wr_at_most(r, 20) and _npc_present(r["npcs"], *_HIT_NPCS),
    ) >= 10


GUARDS: dict[str, Callable[[GuardContext], bool]] = {
    "first_blood": _first_blood,
    "on_a_roll": _on_a_roll,
    "star_born": _star_born,
    "never_give_up": _never_give_up,
    "always_moving": _always_moving,
    "hot_streak": _hot_streak,
    "big_eater": _big_eater,
    "stars_75": _stars_75,
    "full_house": _full_house,
    "zas_chaser": _zas_chaser,
    "speedy": _speedy,
    "stink_proof": _stink_proof,
    "comeback_king": _comeback_king,
    "maze_master": _maze_master,
    "bola_dancer": _bola_dancer,
    "daredevil": _daredevil,
    "hungry_hungry": _hungry_hungry,
    "all_modes": _all_modes,
    "thriller": _thriller,
    "three_star_warrior": _three_star_warrior,
    "wall_dodger": _wall_dodger,
    "ghost": _ghost,
    "deep_survivor": _deep_survivor,
    "speedster": _speedster,
    "outrun_the_swarm": _outrun_the_swarm,
    "clean_sweep_season": _clean_sweep_season,
    "perfectionist": _perfectionist,
    "double_threat": _double_threat,
    "manchas_nightmare": _manchas_nightmare,
    "full_roster_zero_scars": _full_roster_zero_scars,
    "speed_legend": _speed_legend,
    "survivors_gauntlet": _survivors_gauntlet,
    "the_hard_way": _the_hard_way,
    "relentless": _relentless,
    "unbreakable": _unbreakable,
    "invincible": _invincible,
    "flawless": _flawless,
    "apex_predator": _apex_predator,
    "seasonal_legend": _seasonal_legend,
    "perfect_champion": _perfect_champion,
}


async def evaluate_achievements(
    db: AsyncClient,
    uid: str,
    level_id: int,
    stars_earned: int,
    match_stats: dict,
    win_rate_snapshot: float | None,
    season_stars: int,
    season_match_stats: dict,
    now: datetime,
    season_points: float | None = None,
) -> list[str]:
    """Call once per level-complete, AFTER season_match_stats_service.apply_match
    has already run for this match (season_match_stats must reflect it —
    streak/qualifying_levels/three_star_levels are all read post-update, not
    pre-update, since several guards need to see the level_id that was just
    won as part of the season history they're counting over).

    Only ever called when match_stats is present and validated (REST-001) --
    same gate as season_match_stats_service.apply_match. Returns the
    achievement_ids newly unlocked by this call (empty if none).

    Does not populate achievement_progress.progress (numeric progress toward
    locked achievements, e.g. "6 of 20 three-star levels") -- most guards
    are boolean compounds, not a single "N of M" counter, so a generic
    progress fraction isn't well-defined for all 40. Deliberately deferred,
    not an oversight; unlocked/unlock_timestamps correctness doesn't depend
    on it.
    """
    ref = db.collection("achievement_progress").document(uid)
    snap = await ref.get()
    data = snap.to_dict() if snap.exists else {}
    unlocked = set(data.get("unlocked") or [])

    ctx = GuardContext(
        level_id=level_id,
        stars_earned=stars_earned,
        match_stats=match_stats,
        win_rate_snapshot=win_rate_snapshot,
        season_stars=season_stars,
        streak_levels=(season_match_stats.get("win_streak") or {}).get("levels", []),
        qualifying_levels=season_match_stats.get("qualifying_levels") or {},
        three_star_levels=season_match_stats.get("three_star_levels") or {},
        season_points=season_points,
    )

    newly_unlocked = [
        achievement_id
        for achievement_id, guard in GUARDS.items()
        if achievement_id not in unlocked and guard(ctx)
    ]
    if not newly_unlocked:
        return []

    unlock_timestamps = dict(data.get("unlock_timestamps") or {})
    for achievement_id in newly_unlocked:
        unlock_timestamps[achievement_id] = now

    await ref.set({
        "uid": uid,
        "unlocked": sorted(unlocked | set(newly_unlocked)),
        "unlock_timestamps": unlock_timestamps,
        "updated_at": now,
    }, merge=True)

    return newly_unlocked
