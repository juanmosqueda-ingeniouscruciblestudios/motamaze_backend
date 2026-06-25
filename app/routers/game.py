import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_settings, verify_jwt
from app.services.bq_streaming import stream_event, stream_events

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


class LivesGrantRequest(BaseModel):
    source: str                     # "iap" | "rewarded_ad_ssv" | "promo"
    session_id: str
    product_id: str | None = None   # required for source == "iap"
    reward_token: str | None = None # required for source == "rewarded_ad_ssv"
    ad_unit_id: str | None = None   # required for source == "rewarded_ad_ssv"
    promo_code: str | None = None   # required for source == "promo"


class LevelCompleteRequest(BaseModel):
    level_id: int
    score: int
    stars_earned: int
    duration_secs: int
    session_id: str


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


# ---------------------------------------------------------------------------
# POST /lives/grant  (DATA-002 ST-09)
# ---------------------------------------------------------------------------

@router.post("/lives/grant")
async def lives_grant(
    body: LivesGrantRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(verify_jwt),
    settings: Settings = Depends(get_settings),
):
    from fastapi import HTTPException

    valid_sources = {"iap", "rewarded_ad_ssv", "promo"}
    if body.source not in valid_sources:
        raise HTTPException(400, detail={"error_code": "LIVES_GRANT_INVALID_SOURCE", "message": f"source must be one of {sorted(valid_sources)}"})

    if body.source == "rewarded_ad_ssv" and (not body.reward_token or not body.ad_unit_id):
        raise HTTPException(400, detail={"error_code": "LIVES_GRANT_MISSING_FIELDS", "message": "reward_token and ad_unit_id required for rewarded_ad_ssv"})
    if body.source == "iap" and not body.product_id:
        raise HTTPException(400, detail={"error_code": "LIVES_GRANT_MISSING_FIELDS", "message": "product_id required for iap"})
    if body.source == "promo" and not body.promo_code:
        raise HTTPException(400, detail={"error_code": "LIVES_GRANT_MISSING_FIELDS", "message": "promo_code required for promo"})

    user_id = claims.get("uid", "")
    now = datetime.now(timezone.utc)

    # Determine BQ fields per source
    entitlement_type = "life_pack"
    quantity: int | None = 1

    if body.source == "rewarded_ad_ssv":
        # AdMob SSV token verification stub — GAME-002 will add cryptographic check
        background_tasks.add_task(
            stream_event, "ad_impressions",
            {
                "event_timestamp": now.isoformat(),
                "event_date": now.date().isoformat(),
                "user_id": user_id,
                "session_id": body.session_id,
                "platform": None,
                "app_version": None,
                "country": None,
                "ad_unit_id": body.ad_unit_id,
                "ad_type": "rewarded",
                "event_type": "reward_earned",
                "revenue_usd": None,
                "ad_network": "admob",
            },
            settings.gcp_project_id, settings.bq_dataset,
            row_id=f"ad_impression_{body.reward_token}",
        )
        entitlement_id = body.ad_unit_id
        source_bq = "rewarded_ad_ssv"
        granted_by = "admob_ssv"
        dedup_entitlement = f"entitlement_ssv_{body.reward_token}"

    elif body.source == "iap":
        pid = body.product_id
        if pid.startswith("lives_pack_"):
            try:
                quantity = int(pid.split("_")[-1])
            except ValueError:
                quantity = 0
            entitlement_type = "life_pack"
        elif pid == "no_ads":
            entitlement_type = "no_ads"
            quantity = None
        elif pid.startswith("skin_"):
            entitlement_type = "skin"
            quantity = None
        entitlement_id = pid
        source_bq = "iap"
        granted_by = "payment_verify"
        dedup_entitlement = f"entitlement_iap_{pid}_{body.session_id}"

    else:  # promo
        entitlement_id = body.promo_code
        source_bq = "promo_code"
        granted_by = "backend_promo"
        dedup_entitlement = f"entitlement_promo_{body.promo_code}_{user_id}"

    background_tasks.add_task(
        stream_event, "entitlement_grants",
        {
            "event_timestamp": now.isoformat(),
            "event_date": now.date().isoformat(),
            "user_id": user_id,
            "session_id": body.session_id,
            "platform": None,
            "app_version": None,
            "country": None,
            "entitlement_type": entitlement_type,
            "entitlement_id": entitlement_id,
            "source": source_bq,
            "granted_by": granted_by,
            "quantity": quantity,
        },
        settings.gcp_project_id, settings.bq_dataset,
        row_id=dedup_entitlement,
    )

    # GAME-002 will replace stub values with Firestore reads
    return {
        "granted": quantity or 1,
        "current_lives": None,
        "max_lives": None,
        "next_regen_at": None,
        "capped": False,
    }


# ---------------------------------------------------------------------------
# POST /progress/level-complete  (DATA-002 ST-11)
# ---------------------------------------------------------------------------

@router.post("/progress/level-complete")
async def level_complete(
    body: LevelCompleteRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(verify_jwt),
    settings: Settings = Depends(get_settings),
):
    from fastapi import HTTPException

    if not (1 <= body.level_id <= 30):
        raise HTTPException(400, detail={"error_code": "PROGRESS_INVALID_LEVEL", "message": "level_id must be between 1 and 30"})
    if not (1 <= body.stars_earned <= 3):
        raise HTTPException(400, detail={"error_code": "PROGRESS_INVALID_STARS", "message": "stars_earned must be between 1 and 3"})
    if body.score < 0:
        raise HTTPException(400, detail={"error_code": "PROGRESS_INVALID_SCORE", "message": "score must be >= 0"})

    user_id = claims.get("uid", "")
    now = datetime.now(timezone.utc)

    background_tasks.add_task(
        stream_event, "player_behavior",
        {
            "event_timestamp": now.isoformat(),
            "event_date": now.date().isoformat(),
            "user_id": user_id,
            "session_id": body.session_id,
            "event_name": "level_complete",
            "platform": None,
            "app_version": None,
            "country": None,
            "level_id": body.level_id,
            "score": body.score,
            "stars_earned": body.stars_earned,
            "duration_secs": body.duration_secs,
            "npc_type": None,
            "extra_json": None,
        },
        settings.gcp_project_id, settings.bq_dataset,
        row_id=f"level_complete_{body.session_id}_{body.level_id}_{body.score}",
    )

    # GAME-001 will replace stub values with Firestore reads/writes
    return {
        "level_id": body.level_id,
        "stars_earned": body.stars_earned,
        "best_score": body.score,
        "new_best": True,
        "next_level_unlocked": body.level_id + 1 if body.level_id < 30 else None,
        "highest_unlocked_level": body.level_id + 1 if body.level_id < 30 else 30,
        "total_stars": None,
        "season_stars_earned": None,
        "total_season_stars": None,
    }


# GET  /progress                — GAME-001
# GET  /lives                   — GAME-002
# POST /lives/spend             — GAME-002
# GET  /store/catalog           — GAME-003
# GET  /profile                 — GAME-004
# POST /profile/equip-skin      — GAME-004
