import logging
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from google.cloud.firestore import AsyncClient

from app.config import Settings
from app.dependencies import get_firestore_client, get_settings
from app.services import account_deletion_service, admob_api, reconcile_service
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
    """T-123 (ST-04): daily purge of accounts past their 30-day deletion
    grace period. Firestore purge only — BigQuery historical-table purge and
    the final account_deletions status="completed" update are ST-05, not
    yet wired in. This job marks status="processing" once Firestore is done."""
    if x_cloudscheduler_jobname is None:
        raise HTTPException(403, detail={"error_code": "JOBS_FORBIDDEN"})

    due_uids = await account_deletion_service.find_users_due_for_purge(db)
    purged = failed = 0

    for uid in due_uids:
        now = datetime.now(timezone.utc)
        try:
            tables_purged = await account_deletion_service.purge_user_firestore_data(db, uid, now)
        except Exception as exc:
            failed += 1
            logger.error("T-123 purge failed: uid=%s err=%s", uid, exc)
            continue

        purged += 1
        logger.info("T-123 purge: uid=%s tables=%s", uid, tables_purged)
        background_tasks.add_task(
            stream_event, "account_deletions",
            {
                "requested_at": now.isoformat(),
                "request_date": now.date().isoformat(),
                "user_id": uid,
                "platform": None,
                "request_source": "user_request",
                "status": "processing",
                "completed_at": None,
                "tables_purged": tables_purged,
                "notes": "firestore_purged_bq_pending",
            },
            settings.gcp_project_id, settings.bq_dataset,
            row_id=f"deletion_process_{uid}_{int(now.timestamp())}",
        )

    logger.info("T-123 purge run: due=%d purged=%d failed=%d", len(due_uids), purged, failed)
    return {"due": len(due_uids), "purged": purged, "failed": failed}
