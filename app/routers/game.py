import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from google.cloud.firestore import AsyncClient, async_transactional
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_firestore_client, get_settings, verify_jwt
from app.services import (
    achievements_engine,
    remote_config_service,
    season_match_stats_service,
    season_points_service,
    store_service,
)
from app.services.bq_streaming import stream_event, stream_events

router = APIRouter(tags=["game"])

# T-447 ST-06: the 8 shipping modes (docs/game_modes.md in motamaze-project,
# WIN_CONDITION grouping there is coarser than this — this is the per-mode
# slug match_stats.game_mode actually carries).
GAME_MODES = frozenset({
    "big_dig", "first_bite", "huracans_friends", "whole_gangs_here",
    "deep_run", "watch_the_walls", "hot_floor", "the_chase",
})

# T-244: fallback defaults, used when Remote Config is unreachable or the
# parameter isn't published yet — see _resolve_lives_config(). No longer
# read directly anywhere else in this file.
REGEN_INTERVAL_SECS = 1800  # 30 minutes
DEFAULT_MAX_LIVES = 5


async def _resolve_lives_config(settings: Settings) -> tuple[int, int]:
    """(regen_interval_secs, default_max_lives) — Remote Config values with
    the module constants above as fallback (T-244)."""
    regen_interval_secs = await remote_config_service.get_value(
        settings.gcp_project_id, "regen_interval_secs", REGEN_INTERVAL_SECS, cast=int
    )
    default_max_lives = await remote_config_service.get_value(
        settings.gcp_project_id, "default_max_lives", DEFAULT_MAX_LIVES, cast=int
    )
    return regen_interval_secs, default_max_lives


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


class LivesSpendRequest(BaseModel):
    session_id: str
    # T-447 ST-03: optional so older clients keep working — level_stats'
    # win-rate denominator (life_spent) is unusable per-level without it.
    # See docs/DATA_MODEL.md#level_stats.
    level_id: int | None = None


class EquipSkinRequest(BaseModel):
    skin_id: str


class LivesGrantRequest(BaseModel):
    source: str                     # "iap" | "rewarded_ad_ssv" | "promo"
    session_id: str
    product_id: str | None = None   # required for source == "iap"
    reward_token: str | None = None # required for source == "rewarded_ad_ssv"
    ad_unit_id: str | None = None   # required for source == "rewarded_ad_ssv"
    promo_code: str | None = None   # required for source == "promo"


class MatchStatsNpcs(BaseModel):
    bola: int = 0
    mancha: int = 0
    huracan: int = 0
    zas: int = 0


class MatchStats(BaseModel):
    """T-447 ST-01/ST-06. Deliberately no Field(ge=0)/range constraints here:
    REST-001 says a match_stats that fails validation drops achievement
    evaluation for that match WITHOUT rejecting the level-complete request —
    a 422 from pydantic would do exactly the rejection this is meant to
    avoid. See _is_match_stats_valid for the actual range/consistency rules,
    checked after parsing succeeds."""
    won: bool
    game_mode: str
    target_score: int
    npcs: MatchStatsNpcs
    hits_taken: int
    badsmell_hits: int
    stuns_taken: int
    frozen_secs: float
    food_collected: int
    max_food_deficit: int
    final_gap: int
    lead_changes: int
    max_food_drought_secs: float
    max_idle_secs: float
    maze_coverage_pct: float
    shift_reroutes: int
    time_to_target_secs: float
    round_duration_secs: float


def _is_match_stats_valid(ms: MatchStats) -> bool:
    """REST-001 §match_stats "Validaciones server-side"."""
    counters = (
        ms.hits_taken, ms.food_collected, ms.lead_changes, ms.shift_reroutes,
        ms.stuns_taken, ms.badsmell_hits, ms.max_food_deficit, ms.final_gap,
    )
    if any(c < 0 for c in counters):
        return False
    if not (0 <= ms.maze_coverage_pct <= 100):
        return False
    if ms.game_mode not in GAME_MODES:
        return False
    if ms.round_duration_secs <= 0:
        return False
    time_fields = (ms.frozen_secs, ms.max_idle_secs, ms.max_food_drought_secs, ms.time_to_target_secs)
    if any(t < 0 or t > ms.round_duration_secs for t in time_fields):
        return False
    return True


class LevelCompleteRequest(BaseModel):
    level_id: int
    score: int
    stars_earned: int
    duration_secs: int
    session_id: str
    match_stats: MatchStats | None = None


# ---------------------------------------------------------------------------
# Lives helpers
# ---------------------------------------------------------------------------

def _apply_regen(
    count: int, max_lives: int, last_regen_at: datetime, now: datetime, regen_interval_secs: int,
) -> tuple[int, datetime]:
    """Returns (new_count, new_last_regen_at). Advances last_regen_at by whole intervals."""
    if count >= max_lives:
        return count, last_regen_at
    elapsed = (now - last_regen_at).total_seconds()
    lives_to_add = int(elapsed // regen_interval_secs)
    if lives_to_add == 0:
        return count, last_regen_at
    new_count = min(count + lives_to_add, max_lives)
    new_last = last_regen_at + timedelta(seconds=lives_to_add * regen_interval_secs)
    return new_count, new_last


def _next_regen_dt(
    count: int, max_lives: int, last_regen_at: datetime, regen_interval_secs: int,
) -> datetime | None:
    if count >= max_lives:
        return None
    return last_regen_at + timedelta(seconds=regen_interval_secs)


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
# GET /lives  (T-220 / GAME-002)
# ---------------------------------------------------------------------------

@router.get("/lives")
async def get_lives(
    claims: dict = Depends(verify_jwt),
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
    user_id = claims.get("uid", "")
    now = datetime.now(timezone.utc)
    regen_interval_secs, default_max_lives = await _resolve_lives_config(settings)
    lives_ref = db.collection("lives").document(user_id)
    snap = await lives_ref.get()

    if not snap.exists:
        await lives_ref.set({
            "uid": user_id,
            "count": default_max_lives,
            "max_lives": default_max_lives,
            "last_regen_at": now,
            "next_regen_at": None,
            "updated_at": now,
        })
        return {
            "current_lives": default_max_lives,
            "max_lives": default_max_lives,
            "next_regen_at": None,
            "regen_interval_secs": regen_interval_secs,
        }

    data = snap.to_dict()
    count = data.get("count", default_max_lives)
    max_lives = data.get("max_lives", default_max_lives)
    last_regen_at = data["last_regen_at"]

    new_count, new_last = _apply_regen(count, max_lives, last_regen_at, now, regen_interval_secs)
    next_regen = _next_regen_dt(new_count, max_lives, new_last, regen_interval_secs)

    if new_count != count:
        await lives_ref.update({
            "count": new_count,
            "last_regen_at": new_last,
            "next_regen_at": next_regen,
            "updated_at": now,
        })

    return {
        "current_lives": new_count,
        "max_lives": max_lives,
        "next_regen_at": next_regen.isoformat() if next_regen else None,
        "regen_interval_secs": regen_interval_secs,
    }


# ---------------------------------------------------------------------------
# POST /lives/spend  (T-220 / GAME-002)
# ---------------------------------------------------------------------------

@async_transactional
async def _spend_txn(
    txn, lives_ref, user_id: str, now: datetime, regen_interval_secs: int, default_max_lives: int,
):
    """Firestore transaction: apply regen + decrement. Raises HTTPException on 0 lives."""
    snap = await lives_ref.get(transaction=txn)
    if not snap.exists:
        new_count = default_max_lives - 1
        next_r = _next_regen_dt(new_count, default_max_lives, now, regen_interval_secs)
        txn.set(lives_ref, {
            "uid": user_id,
            "count": new_count,
            "max_lives": default_max_lives,
            "last_regen_at": now,
            "next_regen_at": next_r,
            "updated_at": now,
        })
        return new_count, next_r

    data = snap.to_dict()
    count = data.get("count", default_max_lives)
    max_lives = data.get("max_lives", default_max_lives)
    last_regen = data["last_regen_at"]

    new_count, new_last = _apply_regen(count, max_lives, last_regen, now, regen_interval_secs)
    if new_count == 0:
        raise HTTPException(400, detail={"error_code": "LIVES_INSUFFICIENT", "message": "No lives remaining"})

    new_count -= 1
    next_r = _next_regen_dt(new_count, max_lives, new_last, regen_interval_secs)
    txn.update(lives_ref, {
        "count": new_count,
        "last_regen_at": new_last,
        "next_regen_at": next_r,
        "updated_at": now,
    })
    return new_count, next_r


@router.post("/lives/spend")
async def lives_spend(
    body: LivesSpendRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(verify_jwt),
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
    if body.level_id is not None and not (1 <= body.level_id <= 30):
        raise HTTPException(400, detail={"error_code": "LIVES_INVALID_LEVEL", "message": "level_id must be between 1 and 30"})

    user_id = claims.get("uid", "")
    now = datetime.now(timezone.utc)
    regen_interval_secs, default_max_lives = await _resolve_lives_config(settings)
    lives_ref = db.collection("lives").document(user_id)

    remaining, next_regen = await _spend_txn(
        db.transaction(), lives_ref, user_id, now, regen_interval_secs, default_max_lives
    )

    background_tasks.add_task(
        stream_event, "player_behavior",
        {
            "event_timestamp": now.isoformat(),
            "event_date": now.date().isoformat(),
            "user_id": user_id,
            "session_id": body.session_id,
            "event_name": "life_spent",
            "platform": None, "app_version": None, "country": None,
            "level_id": body.level_id, "score": None, "stars_earned": None,
            "duration_secs": None, "npc_type": None, "extra_json": None,
        },
        settings.gcp_project_id, settings.bq_dataset,
        row_id=f"life_spent_{body.session_id}_{now.timestamp():.0f}",
    )

    return {
        "remaining_lives": remaining,
        "next_regen_at": next_regen.isoformat() if next_regen else None,
    }


# ---------------------------------------------------------------------------
# POST /lives/grant  (T-220 / GAME-002 — completes DATA-002 ST-09 stub)
# ---------------------------------------------------------------------------

@router.post("/lives/grant")
async def lives_grant(
    body: LivesGrantRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(verify_jwt),
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
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
    regen_interval_secs, default_max_lives = await _resolve_lives_config(settings)

    entitlement_type = "life_pack"
    quantity: int | None = 1

    if body.source == "rewarded_ad_ssv":
        background_tasks.add_task(
            stream_event, "ad_impressions",
            {
                "event_timestamp": now.isoformat(),
                "event_date": now.date().isoformat(),
                "user_id": user_id,
                "session_id": body.session_id,
                "platform": None, "app_version": None, "country": None,
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
            "platform": None, "app_version": None, "country": None,
            "entitlement_type": entitlement_type,
            "entitlement_id": entitlement_id,
            "source": source_bq,
            "granted_by": granted_by,
            "quantity": quantity,
        },
        settings.gcp_project_id, settings.bq_dataset,
        row_id=dedup_entitlement,
    )

    # --- Firestore: grant lives ---
    actual_granted = 0
    capped = False
    current_lives = default_max_lives
    max_lives = default_max_lives
    next_regen: datetime | None = None

    if quantity is not None and quantity > 0:
        lives_ref = db.collection("lives").document(user_id)
        lives_snap = await lives_ref.get()

        if not lives_snap.exists:
            actual_granted = min(quantity, default_max_lives)
            capped = actual_granted < quantity
            new_count = actual_granted
            await lives_ref.set({
                "uid": user_id,
                "count": new_count,
                "max_lives": default_max_lives,
                "last_regen_at": now,
                "next_regen_at": _next_regen_dt(new_count, default_max_lives, now, regen_interval_secs),
                "updated_at": now,
            })
            next_regen = _next_regen_dt(new_count, default_max_lives, now, regen_interval_secs)
            current_lives = new_count
        else:
            ld = lives_snap.to_dict()
            count = ld.get("count", default_max_lives)
            max_lives = ld.get("max_lives", default_max_lives)
            last_regen_at = ld["last_regen_at"]

            count, last_regen_at = _apply_regen(count, max_lives, last_regen_at, now, regen_interval_secs)
            actual_granted = min(quantity, max_lives - count)
            capped = actual_granted < quantity
            new_count = count + actual_granted
            next_regen = _next_regen_dt(new_count, max_lives, last_regen_at, regen_interval_secs)
            await lives_ref.update({
                "count": new_count,
                "last_regen_at": last_regen_at,
                "next_regen_at": next_regen,
                "updated_at": now,
            })
            current_lives = new_count

        # Update entitlements.life_packs_total for IAP life packs
        if body.source == "iap" and entitlement_type == "life_pack" and actual_granted > 0:
            ent_ref = db.collection("entitlements").document(user_id)
            ent_snap = await ent_ref.get()
            if ent_snap.exists:
                current_total = ent_snap.to_dict().get("life_packs_total", 0)
                await ent_ref.update({"life_packs_total": current_total + 1, "updated_at": now})
            else:
                await ent_ref.set({
                    "uid": user_id, "no_ads": False, "skins": [],
                    "life_packs_total": 1, "updated_at": now,
                })

    return {
        "granted": actual_granted,
        "current_lives": current_lives,
        "max_lives": max_lives,
        "next_regen_at": next_regen.isoformat() if next_regen else None,
        "capped": capped,
    }


# ---------------------------------------------------------------------------
# GET /progress  (T-210 / GAME-001)
# ---------------------------------------------------------------------------

@router.get("/progress")
async def get_progress(
    claims: dict = Depends(verify_jwt),
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
    user_id = claims.get("uid", "")

    progress_snap, season_snap = await asyncio.gather(
        db.collection("progress").document(user_id).get(),
        db.collection("season_progress").document(user_id).get(),
    )

    if progress_snap.exists:
        prog = progress_snap.to_dict()
        levels = prog.get("levels", {})
        best_level = prog.get("best_level", 0)
        total_stars = sum(v.get("stars", 0) for v in levels.values())
    else:
        levels = {}
        best_level = 0
        total_stars = 0

    season_stars = 0
    if season_snap.exists:
        sd = season_snap.to_dict()
        if sd.get("season_id") == settings.active_season_id:
            season_stars = sd.get("season_stars", 0)

    return {
        "best_level": best_level,
        "highest_unlocked_level": min(best_level + 1, 30),
        "total_stars": total_stars,
        "levels": levels,
        "season_id": settings.active_season_id,
        "season_stars": season_stars,
    }


# ---------------------------------------------------------------------------
# POST /progress/level-complete  (T-210 / GAME-001 — completes DATA-002 ST-11 stub)
# ---------------------------------------------------------------------------

@router.post("/progress/level-complete")
async def level_complete(
    body: LevelCompleteRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(verify_jwt),
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
    if not (1 <= body.level_id <= 30):
        raise HTTPException(400, detail={"error_code": "PROGRESS_INVALID_LEVEL", "message": "level_id must be between 1 and 30"})
    if not (1 <= body.stars_earned <= 3):
        raise HTTPException(400, detail={"error_code": "PROGRESS_INVALID_STARS", "message": "stars_earned must be between 1 and 3"})
    if body.score < 0:
        raise HTTPException(400, detail={"error_code": "PROGRESS_INVALID_SCORE", "message": "score must be >= 0"})

    user_id = claims.get("uid", "")
    now = datetime.now(timezone.utc)
    level_key = f"level_{body.level_id}"

    # --- Read progress/{uid} ---
    progress_ref = db.collection("progress").document(user_id)
    progress_snap = await progress_ref.get()

    if not progress_snap.exists:
        if body.level_id != 1:
            raise HTTPException(403, detail={"error_code": "PROGRESS_LEVEL_LOCKED", "message": "Complete earlier levels first"})
        existing_best_level = 0
        existing_level_data: dict = {}
        existing_total_stars = 0
    else:
        prog = progress_snap.to_dict()
        existing_best_level = prog.get("best_level", 0)
        if body.level_id > existing_best_level + 1:
            raise HTTPException(403, detail={"error_code": "PROGRESS_LEVEL_LOCKED", "message": "Complete earlier levels first"})
        existing_level_data = prog.get("levels", {}).get(level_key, {})
        existing_total_stars = sum(v.get("stars", 0) for v in prog.get("levels", {}).values())

    existing_stars     = existing_level_data.get("stars", 0)
    existing_score     = existing_level_data.get("best_score", 0)
    existing_completed = existing_level_data.get("completed_at")

    new_stars     = max(existing_stars, body.stars_earned)
    new_score     = max(existing_score, body.score)
    stars_delta   = max(0, body.stars_earned - existing_stars)
    new_best_level = max(existing_best_level, body.level_id)
    newly_unlocked = body.level_id > existing_best_level
    new_best      = (not existing_completed) or (body.score > existing_score)
    total_stars   = existing_total_stars - existing_stars + new_stars

    # --- Write progress/{uid} ---
    level_doc = {
        "stars": new_stars,
        "best_score": new_score,
        "completed_at": existing_completed or now,
    }
    if not progress_snap.exists:
        await progress_ref.set({
            "uid": user_id,
            "best_level": new_best_level,
            "levels": {level_key: level_doc},
            "updated_at": now,
        })
    else:
        await progress_ref.update({
            f"levels.{level_key}": level_doc,
            "best_level": new_best_level,
            "updated_at": now,
        })

    # --- Read season_progress/{uid} (write deferred to after achievement
    # evaluation -- T-447 ST-08 needs achievement_bonus_points from
    # newly_unlocked_achievements before it can write the final totals) ---
    season_ref = db.collection("season_progress").document(user_id)
    season_snap = await season_ref.get()
    season_snap_data = season_snap.to_dict() if season_snap.exists else None
    level_key_str = str(body.level_id)

    if season_snap_data is not None and season_snap_data.get("season_id") == settings.active_season_id:
        existing_season_stars = season_snap_data.get("season_stars", 0)
        existing_levels_cleared_ids: list[str] = list(season_snap_data.get("levels_cleared_ids", []))
        existing_achievement_bonus_points = season_snap_data.get("achievement_bonus_points", 0)
    else:
        # No doc yet, or a stale season_id -- T-447 ST-08 fix: the stale
        # case used to leave season_id un-persisted forever (the old
        # .update() never wrote it), so every subsequent call re-detected
        # "stale" and re-baselined from 0, silently discarding everything
        # accumulated since the real reset. Writing season_id below on every
        # branch (not just doc creation) closes that.
        existing_season_stars = 0
        existing_levels_cleared_ids = []
        existing_achievement_bonus_points = 0

    total_season_stars = existing_season_stars + stars_delta
    levels_cleared_ids = list(existing_levels_cleared_ids)
    if level_key_str not in levels_cleared_ids:
        levels_cleared_ids.append(level_key_str)

    # --- T-447 ST-06/ST-07: season_match_stats/{uid} + achievement guards ---
    # A missing/invalid match_stats block means no achievement evaluation
    # for this match at all (REST-001) -- that includes streak/qualifying-
    # level tracking, not just guard evaluation itself.
    newly_unlocked_achievements: list[str] = []
    if body.match_stats is not None and _is_match_stats_valid(body.match_stats):
        level_stats_snap = await db.collection("level_stats").document(str(body.level_id)).get()
        win_rate_snapshot = level_stats_snap.to_dict().get("win_rate") if level_stats_snap.exists else None
        match_stats_dict = body.match_stats.model_dump()
        season_match_stats = await season_match_stats_service.apply_match(
            db, user_id, settings.active_season_id, body.level_id, body.stars_earned,
            match_stats_dict, win_rate_snapshot, now,
        )
        newly_unlocked_achievements = await achievements_engine.evaluate_achievements(
            db, user_id, body.level_id, body.stars_earned, match_stats_dict,
            win_rate_snapshot, total_season_stars, season_match_stats, now,
        )

    # --- T-447 ST-08: achievement_bonus + season_points, then write season_progress ---
    achievement_bonus_points = existing_achievement_bonus_points
    if newly_unlocked_achievements:
        catalog_snap = await db.collection("config").document("achievements").get()
        catalog = (catalog_snap.to_dict() or {}).get("achievements") or []
        points_by_id = {a["achievement_id"]: a["points"] for a in catalog}
        achievement_bonus_points += sum(points_by_id.get(aid, 0) for aid in newly_unlocked_achievements)

    season_reset = season_snap_data is None or season_snap_data.get("season_id") != settings.active_season_id
    season_changed = (
        season_reset or stars_delta > 0
        or level_key_str not in existing_levels_cleared_ids
        or achievement_bonus_points != existing_achievement_bonus_points
    )
    if season_changed:
        season_payload = {
            "season_id": settings.active_season_id,
            "season_stars": total_season_stars,
            "levels_cleared_ids": levels_cleared_ids,
            "achievement_bonus_points": achievement_bonus_points,
            "updated_at": now,
        }
        if season_snap_data is None:
            await season_ref.set({
                "uid": user_id,
                "has_gold_pass": False,
                "free_rewards_claimed": [],
                "gold_rewards_claimed": [],
                **season_payload,
            })
        else:
            await season_ref.update(season_payload)

    season_points = season_points_service.compute_season_points(
        total_season_stars, len(levels_cleared_ids), achievement_bonus_points,
    )

    # --- BQ streaming (background, unchanged from DATA-002 ST-11) ---
    background_tasks.add_task(
        stream_event, "player_behavior",
        {
            "event_timestamp": now.isoformat(),
            "event_date": now.date().isoformat(),
            "user_id": user_id,
            "session_id": body.session_id,
            "event_name": "level_complete",
            "platform": None, "app_version": None, "country": None,
            "level_id": body.level_id,
            "score": body.score,
            "stars_earned": body.stars_earned,
            "duration_secs": body.duration_secs,
            "npc_type": None, "extra_json": None,
        },
        settings.gcp_project_id, settings.bq_dataset,
        row_id=f"level_complete_{body.session_id}_{body.level_id}_{body.score}",
    )

    return {
        "level_id":             body.level_id,
        "stars_earned":         body.stars_earned,
        "best_score":           new_score,
        "new_best":             new_best,
        "next_level_unlocked":  new_best_level + 1 if newly_unlocked and new_best_level < 30 else None,
        "highest_unlocked_level": min(new_best_level + 1, 30),
        "total_stars":          total_stars,
        "season_stars_earned":  stars_delta,
        "total_season_stars":   total_season_stars,
        "achievements_unlocked": newly_unlocked_achievements,
        "achievement_bonus_points": achievement_bonus_points,
        "season_points":        season_points,
    }


# ---------------------------------------------------------------------------
# GET /store/catalog  (GAME-003 / T-240)
# ---------------------------------------------------------------------------

@router.get("/store/catalog")
async def get_store_catalog(
    claims: dict = Depends(verify_jwt),
    db: AsyncClient = Depends(get_firestore_client),
):
    user_id = claims.get("uid", "")
    now = datetime.now(timezone.utc)

    catalog_snap = await db.collection("config").document("catalog").get()
    catalog = catalog_snap.to_dict() or {"products": [], "catalog_version": None}

    # Top-level collection, not nested under config/catalog — Firestore
    # subcollections would need "promotions" to itself be a document under
    # "config" first, which the architecture doc's config/promotions/{id}
    # shorthand doesn't actually require; a flat collection is simpler and
    # matches every other collection in this codebase (users, entitlements,
    # purchases, etc. are all top-level too).
    promo_docs = await db.collection("promotions").get()
    promotions = [d.to_dict() for d in promo_docs]

    user_snap = await db.collection("users").document(user_id).get()
    user_data = user_snap.to_dict() or {}
    created_at = user_data.get("created_at", now)

    entitlements_snap = await db.collection("entitlements").document(user_id).get()
    entitlements = entitlements_snap.to_dict() or {}
    has_paid = bool(
        entitlements.get("no_ads")
        or entitlements.get("skins")
        or entitlements.get("life_packs_total")
    )

    session_docs = await (
        db.collection("sessions")
        .where("uid", "==", user_id)
        .order_by("started_at", direction="DESCENDING")
        .limit(1)
        .get()
    )
    last_session_at = None
    for s in session_docs:
        last_session_at = s.to_dict().get("started_at")

    user_segment = store_service.resolve_user_segment(created_at, last_session_at, has_paid, now)
    owned = store_service.owned_product_ids(entitlements, catalog["products"])
    products = store_service.resolve_catalog_products(
        catalog["products"], promotions, owned, user_segment, now
    )

    return {
        "catalog_version": catalog.get("catalog_version"),
        "products": products,
    }


# ---------------------------------------------------------------------------
# POST /profile/equip-skin  (GAME-005 / T-243)
# ---------------------------------------------------------------------------

# "skin_default" and null are the same thing (decision 2026-07-28): the client
# may send either name for the free default look, and it persists as null.
# If a distinct default skin is ever introduced, only this constant's stored
# value changes — the endpoint contract stays put.
DEFAULT_SKIN_ID = "skin_default"


@router.post("/profile/equip-skin")
async def equip_skin(
    body: EquipSkinRequest,
    claims: dict = Depends(verify_jwt),
    db: AsyncClient = Depends(get_firestore_client),
):
    user_id = claims.get("uid", "")
    user_ref = db.collection("users").document(user_id)

    # The default look deliberately skips both checks below. It isn't a catalog
    # product, and gating it on ownership would strand a player who never bought
    # a skin: they could never go back to the plain look.
    if body.skin_id == DEFAULT_SKIN_ID:
        await user_ref.update({"equipped_skin": None})
        return {"skin_id": DEFAULT_SKIN_ID, "equipped": True}

    # Ownership is the authority on existence, not the catalog: skins also
    # arrive from the Season Pass free track and the leaderboard top-3, and
    # those never appear as sellable products. Checking the catalog first would
    # reject a legitimately earned skin with SKIN_NOT_FOUND (T-243).
    entitlements_snap = await db.collection("entitlements").document(user_id).get()
    if body.skin_id not in store_service.owned_skin_ids(entitlements_snap.to_dict() or {}):
        catalog_snap = await db.collection("config").document("catalog").get()
        products = (catalog_snap.to_dict() or {}).get("products") or []
        if body.skin_id in store_service.catalog_skin_ids(products):
            # A real skin, on sale, that this player has not acquired.
            raise HTTPException(403, detail={"error_code": "SKIN_NOT_OWNED", "message": f"{body.skin_id} has not been acquired"})
        raise HTTPException(400, detail={"error_code": "SKIN_NOT_FOUND", "message": f"{body.skin_id} is not a known skin"})

    # update(), not set(merge=True): a valid JWT implies the profile exists, so
    # merge would only ever paper over an anomaly by recreating a document
    # holding nothing but equipped_skin. That case is reachable — T-123's purge
    # job deletes users/{uid} while an access token may still be within its
    # 15-minute TTL — and an orphan profile is worse than the error.
    await user_ref.update({"equipped_skin": body.skin_id})
    return {"skin_id": body.skin_id, "equipped": True}
