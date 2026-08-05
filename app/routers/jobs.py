import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from google.auth.transport import requests as google_requests
from google.cloud.firestore import AsyncClient
from google.oauth2 import id_token as google_id_token

from app.config import Settings
from app.dependencies import get_firestore_client, get_settings
from app.services import (
    account_deletion_service,
    achievement_rarities_service,
    admob_api,
    ad_revenue_reconciliation_service,
    age_threshold_recalc_service,
    level_stats_service,
    reconcile_service,
)
from app.services.bq_streaming import stream_event, stream_events

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

_PUBLISHER_ID = "pub-9121176819960949"
_SCHEDULER_SA_NAME = "game-api-backend"


def _verify_scheduler_oidc_sync(token: str, audience: str) -> dict:
    # Fetches Google's public certs over HTTPS and validates signature, exp,
    # and aud in one call -- same library/pattern as auth_service.verify_google_token.
    return google_id_token.verify_oauth2_token(token, google_requests.Request(), audience=audience)


async def _verify_scheduler_oidc(token: str, audience: str) -> dict:
    return await asyncio.to_thread(_verify_scheduler_oidc_sync, token, audience)


async def verify_cloud_scheduler_oidc(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    """INFRA-007. Cloud Run IAM (--no-invoker-iam-check removed the domain-wide
    default, only game-api-backend's own identity can reach these URLs at all)
    is the primary auth layer. This is defense in depth on top of it: the old
    check here only confirmed the client SENT an X-CloudScheduler-JobName
    header -- any caller could set that themselves, so Cloud Run IAM was the
    *only* real gate on 7 endpoints including purge-deleted-accounts (destroys
    user data) and recalc-age-thresholds (COPPA child flags).

    This verifies the Authorization: Bearer token Cloud Scheduler attaches is
    genuinely Google-signed, unexpired, carries this exact Cloud Run service
    as its audience (settings.cloud_run_service_url — must match every
    /jobs/* scheduler job's own --oidc-token-audience, confirmed identical
    across all of them per environment), and — the part a bare signature
    check would miss — was issued to our own scheduler-invoking service
    account specifically, not just any authenticated Google identity that
    happened to reach this URL.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(403, detail={"error_code": "JOBS_FORBIDDEN"})
    token = authorization.removeprefix("Bearer ").strip()

    try:
        claims = await _verify_scheduler_oidc(token, settings.cloud_run_service_url)
    except Exception as exc:
        logger.warning("Scheduler OIDC verification failed: %s", exc)
        raise HTTPException(403, detail={"error_code": "JOBS_FORBIDDEN"})

    expected_email = f"{_SCHEDULER_SA_NAME}@{settings.gcp_project_id}.iam.gserviceaccount.com"
    if claims.get("email") != expected_email or not claims.get("email_verified"):
        logger.warning(
            "Scheduler OIDC email mismatch: got %s (verified=%s), expected %s",
            claims.get("email"), claims.get("email_verified"), expected_email,
        )
        raise HTTPException(403, detail={"error_code": "JOBS_FORBIDDEN"})


@router.post("/admob-daily-report", dependencies=[Depends(verify_cloud_scheduler_oidc)])
async def run_admob_daily_report(
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
):
    report_date = date.today() - timedelta(days=1)

    try:
        rows = await admob_api.fetch_network_report(
            settings.gcp_project_id, _PUBLISHER_ID, report_date
        )
    except RuntimeError as exc:
        logger.error("AdMob fetch failed: %s", exc)
        raise HTTPException(502, detail={"error_code": "ADMOB_FETCH_FAILED", "detail": str(exc)})

    if rows:
        row_ids = [
            f"admob_{report_date.isoformat()}_{r['ad_unit_id']}_{r['country']}"
            for r in rows
        ]
        background_tasks.add_task(
            stream_events,
            "admob_daily_report",
            rows,
            settings.gcp_project_id,
            settings.bq_dataset,
            row_ids=row_ids,
        )

    logger.info("AdMob report %s: %d rows queued", report_date, len(rows))
    return {"report_date": report_date.isoformat(), "rows_queued": len(rows)}


@router.post("/reconcile-ad-revenue", dependencies=[Depends(verify_cloud_scheduler_oidc)])
async def run_reconcile_ad_revenue(
    settings: Settings = Depends(get_settings),
):
    """T-302: compares our own ad_impressions counts against AdMob's
    Reporting API (admob_daily_report) for yesterday, per ad_unit, and flags
    discrepancies past DISCREPANCY_THRESHOLD_PERCENT. Must be scheduled to
    run AFTER admob-daily-report — it reads admob_daily_report for the same
    report_date, and that table is only populated by the other job."""
    report_date = date.today() - timedelta(days=1)
    results = await ad_revenue_reconciliation_service.reconcile_ad_revenue(
        settings.gcp_project_id, settings.bq_dataset, report_date
    )
    flagged = [r for r in results if r["flagged"]]
    for r in flagged:
        logger.warning("T-302 ad revenue discrepancy: %s", r)

    logger.info(
        "T-302 reconcile %s: %d ad units checked, %d flagged",
        report_date, len(results), len(flagged),
    )
    return {
        "report_date": report_date.isoformat(),
        "ad_units_checked": len(results),
        "flagged": len(flagged),
        "results": results,
    }


@router.post("/reconcile-purchases", dependencies=[Depends(verify_cloud_scheduler_oidc)])
async def run_reconcile_purchases(
    settings: Settings = Depends(get_settings),
    db: AsyncClient = Depends(get_firestore_client),
):
    ack_result = await reconcile_service.reconcile_pending_acks(
        settings.play_package_name, db, settings
    )
    refund_result = await reconcile_service.detect_refunds(
        settings.play_package_name, db, settings
    )

    logger.info("PAY-002 reconcile: ack=%s refunds=%s", ack_result, refund_result)
    return {"pending_acks": ack_result, "refunds": refund_result}


@router.post("/purge-deleted-accounts", dependencies=[Depends(verify_cloud_scheduler_oidc)])
async def run_purge_deleted_accounts(
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    db: AsyncClient = Depends(get_firestore_client),
):
    """T-123 (ST-04/ST-05): daily purge of accounts past their 30-day
    deletion grace period — BigQuery historical tables first, Firestore
    second. That order is deliberate, not arbitrary: purge_user_firestore_data
    deletes users/{uid} last (it's the "does this account still exist" flag
    that find_users_due_for_purge scans for), so if the BQ purge throws,
    the Firestore side never runs and this uid is picked up again next run —
    both purges are idempotent (re-deleting/re-anonymizing already-purged
    rows is a no-op), so a retry after a partial failure is always safe.
    Reversing this order would orphan a user whose Firestore doc was already
    gone but whose BQ purge failed, with no way to retry it."""
    due_uids = await account_deletion_service.find_users_due_for_purge(db)
    purged = failed = 0

    for uid in due_uids:
        now = datetime.now(timezone.utc)
        try:
            bq_tables = await account_deletion_service.purge_user_bigquery_data(
                settings.gcp_project_id, settings.bq_dataset, uid
            )
            fs_tables = await account_deletion_service.purge_user_firestore_data(db, uid, now)
        except Exception as exc:
            failed += 1
            logger.error("T-123 purge failed: uid=%s err=%s", uid, exc)
            background_tasks.add_task(
                stream_event, "account_deletions",
                {
                    "requested_at": now.isoformat(),
                    "request_date": now.date().isoformat(),
                    "user_id": uid,
                    "platform": None,
                    "request_source": "user_request",
                    "status": "failed",
                    "completed_at": None,
                    "tables_purged": [],
                    "notes": str(exc)[:500],
                },
                settings.gcp_project_id, settings.bq_dataset,
                row_id=f"deletion_failed_{uid}_{int(now.timestamp())}",
            )
            continue

        purged += 1
        tables_purged = bq_tables + fs_tables
        completed_at = datetime.now(timezone.utc)
        logger.info("T-123 purge completed: uid=%s tables=%s", uid, tables_purged)
        background_tasks.add_task(
            stream_event, "account_deletions",
            {
                "requested_at": now.isoformat(),
                "request_date": now.date().isoformat(),
                "user_id": uid,
                "platform": None,
                "request_source": "user_request",
                "status": "completed",
                "completed_at": completed_at.isoformat(),
                "tables_purged": tables_purged,
                "notes": "purge_complete",
            },
            settings.gcp_project_id, settings.bq_dataset,
            row_id=f"deletion_complete_{uid}_{int(now.timestamp())}",
        )

    logger.info("T-123 purge run: due=%d purged=%d failed=%d", len(due_uids), purged, failed)
    return {"due": len(due_uids), "purged": purged, "failed": failed}


@router.post("/recalc-age-thresholds", dependencies=[Depends(verify_cloud_scheduler_oidc)])
async def run_recalc_age_thresholds(
    db: AsyncClient = Depends(get_firestore_client),
):
    """T-404: monthly recalc — flips is_child to False for DOB-verified
    users who've crossed their country's age threshold since verification.
    Brazil store-signal users are out of scope (no stored birth_month/year
    to recalc from) — see age_threshold_recalc_service for why that's
    sufficient without an explicit country_code check."""
    aged_out = await age_threshold_recalc_service.find_and_recalc_aged_out_users(db)

    logger.info("T-404 recalc: %d users aged out: %s", len(aged_out), aged_out)
    return {"aged_out_count": len(aged_out), "aged_out_uids": aged_out}


@router.post("/recalc-level-stats", dependencies=[Depends(verify_cloud_scheduler_oidc)])
async def run_recalc_level_stats(
    settings: Settings = Depends(get_settings),
    db: AsyncClient = Depends(get_firestore_client),
):
    """T-447 ST-04: recomputes level_stats/{level_id}.win_rate from
    player_behavior (life_spent = attempts, level_complete = wins) over a
    trailing window. Levels under level_stats_service.MIN_SAMPLE_SIZE
    attempts are left untouched — see docs/DATA_MODEL.md#level_stats for why
    an absent/stale WR fails the 26 dependent achievement guards closed
    instead of granting them for free."""
    result = await level_stats_service.recalc_level_stats(
        db, settings.gcp_project_id, settings.bq_dataset
    )
    logger.info("T-447 ST-04 level_stats recalc: %s", result)
    return result


@router.post("/recalc-achievement-rarities", dependencies=[Depends(verify_cloud_scheduler_oidc)])
async def run_recalc_achievement_rarities(
    settings: Settings = Depends(get_settings),
    db: AsyncClient = Depends(get_firestore_client),
):
    """T-447 ST-10: recomputes achievement_rarities/{achievement_id} from
    the players active in the trailing window (achievement_rarities_service
    -- see its module docstring for why total_players and unlocked_by are
    both scoped to that same active-uid set). GET /achievements (ST-09)
    only reads these documents; no BQ query in the request path."""
    result = await achievement_rarities_service.recalc_achievement_rarities(
        db, settings.gcp_project_id, settings.bq_dataset
    )
    logger.info("T-447 ST-10 achievement rarities recalc: %s", result)
    return result
