import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_settings, verify_jwt
from app.services.bq_streaming import stream_events

router = APIRouter(tags=["game"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class BehaviorEvent(BaseModel):
    event_name: str
    platform: str
    app_version: str
    country: str | None = None
    level_id: int | None = None
    score: int | None = None
    stars_earned: int | None = None
    duration_secs: int | None = None
    npc_type: str | None = None
    extra_json: str | None = None


class BehaviorBatchRequest(BaseModel):
    events: list[BehaviorEvent]


# ---------------------------------------------------------------------------
# POST /events/behavior  (DATA-002 ST-07)
# ---------------------------------------------------------------------------

@router.post("/events/behavior", status_code=204)
async def events_behavior(
    body: BehaviorBatchRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(verify_jwt),
    settings: Settings = Depends(get_settings),
):
    if not body.events:
        return Response(status_code=204)

    user_id = claims.get("uid", "")
    session_id = claims.get("sid", "")
    now = datetime.now(timezone.utc)
    batch_id = str(uuid.uuid4())

    rows = []
    row_ids = []
    for i, evt in enumerate(body.events):
        rows.append({
            "event_timestamp": now.isoformat(),
            "event_date": now.date().isoformat(),
            "user_id": user_id,
            "session_id": session_id,
            "event_name": evt.event_name,
            "platform": evt.platform,
            "app_version": evt.app_version,
            "country": evt.country or "",
            "level_id": evt.level_id,
            "score": evt.score,
            "stars_earned": evt.stars_earned,
            "duration_secs": evt.duration_secs,
            "npc_type": evt.npc_type,
            "extra_json": evt.extra_json,
        })
        row_ids.append(f"behavior_{session_id}_{batch_id}_{i}")

    background_tasks.add_task(
        stream_events, "player_behavior",
        rows, settings.gcp_project_id, settings.bq_dataset,
        row_ids=row_ids,
    )

    return Response(status_code=204)


# GET  /progress                — GAME-001
# POST /progress/level-complete — GAME-001
# GET  /lives                   — GAME-002
# POST /lives/spend             — GAME-002
# POST /lives/grant             — GAME-002
# GET  /store/catalog           — GAME-003
# GET  /profile                 — GAME-004
# POST /profile/equip-skin      — GAME-004
