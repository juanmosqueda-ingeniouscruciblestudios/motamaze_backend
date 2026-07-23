from datetime import date

from google.cloud import bigquery

from app.services import bq_streaming

# Starting point, not tuned against real traffic yet — ad-network impression
# counting legitimately diverges a few % from a client's own count (timezone
# edges, ad-blockers, timing windows). Revisit once real data exists.
DISCREPANCY_THRESHOLD_PERCENT = 10.0


def _discrepancy_percent(admob_count: int, our_count: int) -> float | None:
    """None means "nothing to compare" (AdMob reported zero impressions for
    this ad_unit that day) rather than 0% or 100% — either would misleadingly
    imply a real comparison happened."""
    if admob_count == 0:
        return None
    return abs(admob_count - our_count) / admob_count * 100


async def reconcile_ad_revenue(
    project_id: str, dataset_id: str, report_date: date
) -> list[dict]:
    """Compares our own logged ad_impressions counts against AdMob's own
    Reporting API numbers (admob_daily_report) for one day, per ad_unit.

    Known, deliberate gap (not a bug in this function): ad_impressions is
    only populated today for rewarded-ad completions
    (POST /lives/grant -> app/routers/game.py) — interstitial and banner
    impressions aren't logged anywhere server-side yet (that requires
    AdMob's per-impression revenue callback wired in Godot, or a Firebase
    Analytics BigQuery export, neither of which exists today). Those
    ad_units will show ~100% discrepancy here until that client-side work
    ships — that's expected and documented, not something for this
    function to hide or work around. See logic/ad-revenue-reconciliation.md.
    """
    admob_rows = await bq_streaming.run_select(
        f"""
        SELECT ad_unit_id,
               SUM(impressions) AS admob_impressions,
               SUM(estimated_earnings_micros) AS admob_earnings_micros
        FROM `{project_id}.{dataset_id}.admob_daily_report`
        WHERE report_date = @report_date
        GROUP BY ad_unit_id
        """,
        [bigquery.ScalarQueryParameter("report_date", "DATE", report_date.isoformat())],
    )
    our_rows = await bq_streaming.run_select(
        f"""
        SELECT ad_unit_id, COUNT(*) AS our_impressions
        FROM `{project_id}.{dataset_id}.ad_impressions`
        WHERE event_date = @report_date
        GROUP BY ad_unit_id
        """,
        [bigquery.ScalarQueryParameter("report_date", "DATE", report_date.isoformat())],
    )
    our_by_unit = {row["ad_unit_id"]: row["our_impressions"] for row in our_rows}

    results = []
    for row in admob_rows:
        ad_unit_id = row["ad_unit_id"]
        admob_count = row["admob_impressions"] or 0
        our_count = our_by_unit.get(ad_unit_id, 0)
        discrepancy_pct = _discrepancy_percent(admob_count, our_count)
        results.append({
            "ad_unit_id": ad_unit_id,
            "admob_impressions": admob_count,
            "admob_earnings_micros": row["admob_earnings_micros"] or 0,
            "our_impressions": our_count,
            "discrepancy_percent": discrepancy_pct,
            "flagged": discrepancy_pct is not None and discrepancy_pct > DISCREPANCY_THRESHOLD_PERCENT,
        })
    return results
