"""T-447 ST-10: recomputes achievement_rarities/{achievement_id} on a 24h
Cloud Scheduler cadence (app/routers/jobs.py). GET /achievements (ST-09)
only ever reads these documents -- no BigQuery query in the request path.

Population basis (2026-07-31, interpretive decision): DATA_MODEL.md defines
rarity_percent = unlocked_by / total_players * 100, with total_players =
"jugadores activos al momento del cálculo". achievement_progress is
cumulative and never reset (DATA_MODEL's TTL table) -- it holds unlocks
from every player who's ever played, including long-churned ones. Naively
dividing an all-time unlocked_by by a *recent-window* total_players would
let rarity_percent exceed 100% for any achievement most active players
already cleared long ago. Instead both sides of the fraction are scoped to
the SAME population: the uids active in the trailing window. unlocked_by
counts only unlocks among those uids, so rarity_percent is always in
[0, 100] and genuinely answers "what fraction of today's active players
have this".
"""

from collections import Counter
from datetime import date, datetime, timedelta, timezone

from google.cloud import bigquery
from google.cloud.firestore import AsyncClient

from app.services import bq_streaming

# Mirrors level_stats_service.WINDOW_DAYS's "trailing window = current
# signal" reasoning, kept as its own constant -- per-level difficulty and
# account-wide rarity are different questions and shouldn't be forced to
# move together if one is retuned later.
ACTIVE_WINDOW_DAYS = 30

# DATA_MODEL.md#achievement_rarities tier thresholds, checked high to low
# so each entry's ">=" is that tier's inclusive lower bound.
_TIERS = (
    (50, "COMMON"),
    (20, "UNCOMMON"),
    (8, "RARE"),
    (4, "EPIC"),
)


def compute_rarity_tier(rarity_percent: float) -> str:
    for threshold, tier in _TIERS:
        if rarity_percent >= threshold:
            return tier
    return "LEGENDARY"


async def fetch_active_uids(
    project_id: str, dataset_id: str, as_of: date | None = None
) -> list[str]:
    """Distinct user_id with any player_behavior event in the trailing
    ACTIVE_WINDOW_DAYS."""
    end = as_of or datetime.now(timezone.utc).date()
    start = end - timedelta(days=ACTIVE_WINDOW_DAYS)

    rows = await bq_streaming.run_select(
        f"""
        SELECT DISTINCT user_id
        FROM `{project_id}.{dataset_id}.player_behavior`
        WHERE user_id IS NOT NULL
          AND event_date BETWEEN @start_date AND @end_date
        """,
        [
            bigquery.ScalarQueryParameter("start_date", "DATE", start.isoformat()),
            bigquery.ScalarQueryParameter("end_date", "DATE", end.isoformat()),
        ],
    )
    return [row["user_id"] for row in rows]


async def count_unlocks_among(db: AsyncClient, uids: list[str]) -> dict[str, int]:
    """achievement_id -> how many of the given uids have it in
    achievement_progress/{uid}.unlocked. Reads one doc per uid (mirrors
    jobs.py's run_purge_deleted_accounts loop) rather than scanning the
    whole achievement_progress collection -- see module docstring for why
    the tally must stay scoped to this specific uid set."""
    counts: Counter[str] = Counter()
    for uid in uids:
        snap = await db.collection("achievement_progress").document(uid).get()
        data = snap.to_dict() or {}
        counts.update(data.get("unlocked") or [])
    return dict(counts)


async def recalc_achievement_rarities(
    db: AsyncClient, project_id: str, dataset_id: str
) -> dict:
    """Writes achievement_rarities/{achievement_id} for every achievement in
    config/achievements. Skips the whole run (leaves existing rarity docs
    untouched) when the active window has zero players -- a percent against
    a zero denominator is missing signal, not a real "nobody's unlocked
    this" result, same philosophy as level_stats_service's MIN_SAMPLE_SIZE
    skip."""
    catalog_snap = await db.collection("config").document("achievements").get()
    catalog = (catalog_snap.to_dict() or {}).get("achievements") or []

    active_uids = await fetch_active_uids(project_id, dataset_id)
    total_players = len(active_uids)
    if total_players == 0:
        return {"computed": [], "total_players": 0, "skipped": "no_active_players"}

    unlocked_by = await count_unlocks_among(db, active_uids)
    now = datetime.now(timezone.utc)

    computed: list[str] = []
    for entry in catalog:
        achievement_id = entry["achievement_id"]
        unlocked_count = unlocked_by.get(achievement_id, 0)
        rarity_percent = unlocked_count / total_players * 100
        await db.collection("achievement_rarities").document(achievement_id).set({
            "achievement_id": achievement_id,
            "total_players": total_players,
            "unlocked_by": unlocked_count,
            "rarity_percent": rarity_percent,
            "rarity_tier": compute_rarity_tier(rarity_percent),
            "computed_at": now,
        })
        computed.append(achievement_id)

    return {"computed": computed, "total_players": total_players}
