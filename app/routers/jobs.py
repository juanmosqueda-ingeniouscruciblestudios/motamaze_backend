import logging
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from google.cloud.firestore import AsyncClient

from app.config import Settings
from app.dependencies import get_firestore_client, get_settings
from app.services import account_deletion_service, admob_api, ad_revenue_reconciliation_service, reconcile_service
from app.services.bq_streaming import stream_event, stream_events

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

_PUBLISHER_ID = "pub-9121176819960949"


@router.post("/admob-daily-report")
async def run_admob_daily_report(
    background_tasks: BackgroundTasks,
    x_cloudscheduler_jobname: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
):
    # Cloud Run IAM is the primary auth layer; this header is belt-and-suspenders.
    if x_cloudscheduler_jobname is None:
        raise HTTPException(403, detail={"error_code": "JOBS_FORBIDDEN"})

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


@router.post("/reconcile-ad-revenue")
async def run_reconcile_ad_revenue(
    x_cloudscheduler_jobname: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
):
    """T-302: compares our own ad_impressions counts against AdMob's
    Reporting API (admob_daily_report) for yesterday, per ad_unit, and flags
    discrepancies past DISCREPANCY_THRESHOLD_PERCENT. Must be scheduled to
    run AFTER admob-daily-report — it reads admob_daily_report for the same
    report_date, and that table is only populated by the other job."""
    if x_cloudscheduler_jobname is None:
        raise HTTPException(403, detail={"error_code": "JOBS_FORBIDDEN"})

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


@router.post("/reconcile-purchases")
async def run_reconcile_purchases(
    x_cloudscheduler_jobname: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
    db: AsyncClient = Depends(get_firestore_client),
):
    if x_cloudscheduler_jobname is None:
        raise HTTPException(403, detail={"error_code": "JOBS_FORBIDDEN"})

    ack_result = await reconcile_service.reconcile_pending_acks(
        settings.play_package_name, db, settings
    )
    refund_result = await reconcile_service.detect_refunds(
        settings.play_package_name, db, settings
    )

    logger.info("PAY-002 reconcile: ack=%s refunds=%s", ack_result, refund_result)
    return {"pending_acks": ack_result, "refunds": refund_result}


@router.post("/purge-deleted-accounts")
async def run_purge_deleted_accounts(
    background_tasks: BackgroundTasks,
    x_cloudscheduler_jobname: Annotated[str | None, Header()] = None,
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
    if x_cloudscheduler_jobname is None:
        raise HTTPException(403, detail={"error_code": "JOBS_FORBIDDEN"})

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
