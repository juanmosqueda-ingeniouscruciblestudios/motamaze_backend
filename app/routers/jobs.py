import logging
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException

from app.config import Settings
from app.dependencies import get_settings
from app.services import admob_api
from app.services.bq_streaming import stream_events

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
