"""T-447 ST-09: merges config/achievements (static catalog), achievement_progress/{uid}
(per-player unlock state) and achievement_rarities/{achievement_id} (BigQuery-measured
rarity, ST-10) into the shape GET /achievements returns.

Pure — all three inputs are already-read data, no Firestore access here. Mirrors
store_service.resolve_catalog_products' split between I/O (router) and merge logic
(service).
"""

# T-447 ST-10 (rarity job) hasn't shipped yet, so achievement_rarities is empty in
# practice today -- every achievement falls back to its static rarity_tier with no
# measured rarity_percent. Once the job runs, a real doc simply takes over per
# achievement_id; no code change needed here.
def _resolve_rarity(entry: dict, rarity_doc: dict | None) -> tuple[str, float | None]:
    if rarity_doc is not None:
        return rarity_doc["rarity_tier"], rarity_doc["rarity_percent"]
    return entry["rarity_tier"], None


def build_achievements_response(
    catalog: list[dict],
    progress: dict,
    rarities: dict[str, dict],
) -> list[dict]:
    """progress = achievement_progress/{uid}.to_dict() (or {} if never written).
    rarities = {achievement_id: achievement_rarities/{achievement_id}.to_dict()},
    only containing achievements the rarity job has already computed."""
    unlocked = set(progress.get("unlocked") or [])
    unlock_timestamps = progress.get("unlock_timestamps") or {}

    result = []
    for entry in catalog:
        achievement_id = entry["achievement_id"]
        rarity, rarity_percent = _resolve_rarity(entry, rarities.get(achievement_id))
        result.append({
            "achievement_id": achievement_id,
            "title": entry["name"],
            "description": entry["description"],
            # No icon asset pipeline confirmed yet (2026-07-30) -- badge_{achievement_id}
            # is the naming convention REST-001's own examples imply
            # (badge_first_level / first_level), applied literally to the real 40 IDs.
            "icon_id": f"badge_{achievement_id}",
            "rarity": rarity,
            "rarity_percent": rarity_percent,
            "unlocked": achievement_id in unlocked,
            "unlocked_at": unlock_timestamps.get(achievement_id),
            # achievement_progress.progress is deliberately unpopulated since ST-07
            # (DATA_MODEL.md) -- always null until that follow-up lands.
            "progress": None,
        })
    return result
