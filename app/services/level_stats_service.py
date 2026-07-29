from datetime import date, datetime, timedelta, timezone

from google.cloud import bigquery
from google.cloud.firestore import AsyncClient

from app.services import bq_streaming

# T-447 ST-04. Formula and thresholds per docs/DATA_MODEL.md#level_stats.
WINDOW_DAYS = 30
MIN_SAMPLE_SIZE = 100


async def fetch_window_counts(
    project_id: str, dataset_id: str, as_of: date | None = None
) -> list[dict]:
    """wins (level_complete) / attempts (life_spent) per level_id over a
    trailing window. attempts is intents *started*, not resolved — see
    DATA_MODEL for why life_spent was chosen over instrumenting level_fail,
    and why that makes "spend on level start, not on loss" load-bearing."""
    end = as_of or datetime.now(timezone.utc).date()
    start = end - timedelta(days=WINDOW_DAYS)

    return await bq_streaming.run_select(
        f"""
        SELECT level_id,
               COUNTIF(event_name = 'level_complete') AS wins,
               COUNTIF(event_name = 'life_spent')     AS attempts
        FROM `{project_id}.{dataset_id}.player_behavior`
        WHERE level_id IS NOT NULL
          AND event_date BETWEEN @start_date AND @end_date
        GROUP BY level_id
        """,
        [
            bigquery.ScalarQueryParameter("start_date", "DATE", start.isoformat()),
            bigquery.ScalarQueryParameter("end_date", "DATE", end.isoformat()),
        ],
    )


async def recalc_level_stats(db: AsyncClient, project_id: str, dataset_id: str) -> dict:
    """Writes level_stats/{level_id} with source="measured" for every level
    that cleared MIN_SAMPLE_SIZE attempts in the window. Levels below the
    threshold are left untouched (not zeroed, not overwritten) — an
    absent/stale document means WR-gated guards fail closed, per
    DATA_MODEL's "WR ausente = guard no evaluable" policy. This never
    downgrades a level from measured back to simulated; it only ever
    promotes forward when there's enough signal."""
    rows = await fetch_window_counts(project_id, dataset_id)
    now = datetime.now(timezone.utc)
    updated: list[str] = []
    skipped_low_sample: list[str] = []

    for row in rows:
        attempts = row.get("attempts") or 0
        level_id = str(row["level_id"])
        if attempts < MIN_SAMPLE_SIZE:
            skipped_low_sample.append(level_id)
            continue

        wins = row.get("wins") or 0
        win_rate = wins / attempts * 100
        await db.collection("level_stats").document(level_id).set({
            "level_id": level_id,
            "win_rate": win_rate,
            "source": "measured",
            "sample_size": attempts,
            "computed_at": now,
        })
        updated.append(level_id)

    return {"updated": updated, "skipped_low_sample": skipped_low_sample}
