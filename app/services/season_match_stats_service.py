from datetime import datetime

from google.cloud.firestore import AsyncClient

# T-447 ST-06. Persists raw per-match facts only -- which facts satisfy a
# given achievement guard (hit-free? comeback? close win? mode coverage?) is
# decided by the evaluation engine (T-447 ST-07), not here. This mirrors the
# guard_notes-is-not-executable-data decision already made for config/achievements
# (ST-05): the 40 guards are heterogeneous and fixed, so pre-baking
# guard-specific aggregates into this schema would just be a rules DSL in
# disguise. This collection only ever answers "what happened, on which
# level, this season" -- never "does this satisfy achievement X".


async def apply_match(
    db: AsyncClient,
    uid: str,
    season_id: str,
    level_id: int,
    match_stats: dict,
    win_rate_snapshot: float | None,
    now: datetime,
) -> None:
    """Call once per level-complete that carries a *validated* match_stats
    block. won comes from match_stats["won"] -- explicit, never inferred.

    win_streak: consecutive-attempt streak of *distinct* levels won, in the
    order first won. Winning a level already in the current streak is a
    no-op (doesn't extend, doesn't reset) -- confirmed 2026-07-29, repeating
    a level you've already banked shouldn't cost you the streak. Losing
    resets it to empty.

    qualifying_levels: one record per level_id, written only the FIRST time
    it's won this season -- later wins of the same level don't overwrite it.
    This preserves the win_rate_snapshot and match context from the win that
    actually earned it, consistent with DATA_MODEL's "WR vigente al momento
    de la partida" policy (an achievement's WR gate is evaluated against the
    difficulty *as measured when that win happened*, not re-checked later).
    """
    ref = db.collection("season_match_stats").document(uid)
    snap = await ref.get()
    data = snap.to_dict() if snap.exists else None

    if data is not None and data.get("season_id") == season_id:
        streak = dict(data.get("win_streak") or {"count": 0, "level_ids": []})
        qualifying_levels = dict(data.get("qualifying_levels") or {})
    else:
        streak = {"count": 0, "level_ids": []}
        qualifying_levels = {}

    level_key = str(level_id)
    won = bool(match_stats["won"])

    if not won:
        streak = {"count": 0, "level_ids": []}
    else:
        streak_levels = list(streak["level_ids"])
        if level_key not in streak_levels:
            streak_levels.append(level_key)
            streak = {"count": streak["count"] + 1, "level_ids": streak_levels}

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

    await ref.set({
        "uid": uid,
        "season_id": season_id,
        "win_streak": streak,
        "qualifying_levels": qualifying_levels,
        "updated_at": now,
    })
