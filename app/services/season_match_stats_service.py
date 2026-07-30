from datetime import datetime

from google.cloud.firestore import AsyncClient

# T-447 ST-06 (schema patched in ST-07 -- see notes below). Persists raw
# per-match facts only -- which facts satisfy a given achievement guard
# (hit-free? comeback? close win? mode coverage?) is decided by the
# evaluation engine (T-447 ST-07), not here. This mirrors the
# guard_notes-is-not-executable-data decision already made for
# config/achievements (ST-05): the 40 guards are heterogeneous and fixed, so
# pre-baking guard-specific aggregates into this schema would just be a
# rules DSL in disguise. This collection only ever answers "what happened,
# on which level, this season" -- never "does this satisfy achievement X".


async def apply_match(
    db: AsyncClient,
    uid: str,
    season_id: str,
    level_id: int,
    stars_earned: int,
    match_stats: dict,
    win_rate_snapshot: float | None,
    now: datetime,
) -> dict:
    """Call once per level-complete that carries a *validated* match_stats
    block. won comes from match_stats["won"] -- explicit, never inferred.

    win_streak: consecutive-attempt streak of *distinct* levels won, in the
    order first won, each entry carrying its win_rate_snapshot -- ST-07's
    4 streak-gated achievements (on_a_roll/hot_streak/relentless/unbreakable)
    each cap the streak at a different WR threshold, so the raw ordered list
    is stored here and each achievement computes its own trailing qualifying
    run at evaluation time (ST-07's _streak_length), rather than this
    service picking one threshold. Winning a level already in the current
    streak is a no-op (doesn't extend, doesn't reset) -- confirmed
    2026-07-29. Losing resets it to empty. A win on a level whose WR is
    *above* a given achievement's threshold also breaks that achievement's
    effective streak (confirmed 2026-07-30) -- handled at read time in
    ST-07, not by resetting this raw list (a different achievement with a
    looser threshold may still see that win as streak-continuing).

    qualifying_levels: one record per level_id, written only the FIRST time
    it's won this season -- later wins of the same level don't overwrite it.
    This preserves the win_rate_snapshot and match context from the win that
    actually earned it, consistent with DATA_MODEL's "WR vigente al momento
    de la partida" policy.

    three_star_levels: separate from qualifying_levels because the 3-star
    achievements (three_star_warrior, perfectionist) care about *when the
    level was first 3-starred*, which isn't necessarily the same match as
    the level's first win -- a player can win a level at 1-2 stars first and
    3-star it on a later replay. Gated on stars_earned == 3 alone (matching
    guard_notes, which states no separate win requirement), independent of
    match_stats.won. Same first-time-only policy as qualifying_levels, same
    reasoning. Carries its own npcs snapshot (perfect_champion needs
    Bola/Mancha presence on the specific match that earned the 3 stars,
    which may differ from qualifying_levels' first-win match).
    """
    ref = db.collection("season_match_stats").document(uid)
    snap = await ref.get()
    data = snap.to_dict() if snap.exists else None

    if data is not None and data.get("season_id") == season_id:
        streak = dict(data.get("win_streak") or {"count": 0, "levels": []})
        qualifying_levels = dict(data.get("qualifying_levels") or {})
        three_star_levels = dict(data.get("three_star_levels") or {})
    else:
        streak = {"count": 0, "levels": []}
        qualifying_levels = {}
        three_star_levels = {}

    level_key = str(level_id)
    won = bool(match_stats["won"])

    if not won:
        streak = {"count": 0, "levels": []}
    else:
        streak_levels = list(streak["levels"])
        if not any(entry["level_id"] == level_key for entry in streak_levels):
            streak_levels.append({"level_id": level_key, "win_rate_snapshot": win_rate_snapshot})
            streak = {"count": streak["count"] + 1, "levels": streak_levels}

        if level_key not in qualifying_levels:
            qualifying_levels[level_key] = {
                "mode": match_stats["game_mode"],
                "win_rate_snapshot": win_rate_snapshot,
                "npcs": dict(match_stats["npcs"]),
                "hits_taken": match_stats["hits_taken"],
                "badsmell_hits": match_stats["badsmell_hits"],
                "max_food_deficit": match_stats["max_food_deficit"],
                "final_gap": match_stats["final_gap"],
                "lead_changes": match_stats["lead_changes"],
                "maze_coverage_pct": match_stats["maze_coverage_pct"],
                "recorded_at": now,
            }

    if stars_earned == 3 and level_key not in three_star_levels:
        three_star_levels[level_key] = {
            "win_rate_snapshot": win_rate_snapshot,
            "npcs": dict(match_stats["npcs"]),
            "recorded_at": now,
        }

    payload = {
        "uid": uid,
        "season_id": season_id,
        "win_streak": streak,
        "qualifying_levels": qualifying_levels,
        "three_star_levels": three_star_levels,
        "updated_at": now,
    }
    await ref.set(payload)
    return payload
