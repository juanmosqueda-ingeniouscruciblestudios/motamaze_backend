import asyncio
import json
import urllib.request
from datetime import datetime, timezone
from typing import Annotated

from cachetools import TTLCache
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from google.cloud.firestore import AsyncClient
from jose import JWTError
from jose import jwk
from jose import jwt as jose_jwt
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_firestore_client, get_settings, verify_jwt
from app.services.bq_streaming import stream_event

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])

_APPCHECK_JWKS_URL = "https://firebaseappcheck.googleapis.com/v1/jwks"
_appcheck_jwks_cache: TTLCache = TTLCache(maxsize=1, ttl=3600)


async def _get_appcheck_jwks() -> list[dict]:
    if "keys" in _appcheck_jwks_cache:
        return _appcheck_jwks_cache["keys"]

    def _fetch() -> list[dict]:
        with urllib.request.urlopen(_APPCHECK_JWKS_URL, timeout=5) as r:
            return json.loads(r.read())["keys"]

    keys = await asyncio.to_thread(_fetch)
    _appcheck_jwks_cache["keys"] = keys
    return keys


async def verify_app_check(
    x_firebase_appcheck: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    """Dependency: verifies Firebase App Check token (mandatory for leaderboard writes).

    Already platform-agnostic — no iOS-specific code needed here (T-443/AUTH-IOS
    review, 2026-07-18). App Check itself is the platform abstraction: the client
    SDK exchanges a platform-specific attestation (Play Integrity on Android,
    App Attest/DeviceCheck on iOS) for this same Firebase-issued JWT format, so
    the backend never sees a raw Play Integrity or App Attest token — only ever
    this normalized token, verified identically regardless of platform. The
    remaining iOS work is client-side (T-IOS-8: Godot App Check SDK + App Attest
    provider) plus registering a "MotaMaze iOS" app in Firebase Console → App
    Check (today only "MotaMaze Android" exists — see
    changelogs/T-443-leaderboard-backend.md).
    """
    if not x_firebase_appcheck:
        raise HTTPException(
            401,
            detail={
                "error_code": "LEADERBOARD_APPCHECK_MISSING",
                "message": "X-Firebase-AppCheck header required",
            },
        )
    try:
        header = jose_jwt.get_unverified_header(x_firebase_appcheck)
        kid = header.get("kid")
        keys = await _get_appcheck_jwks()
        key_data = next((k for k in keys if k.get("kid") == kid), None)
        if not key_data:
            _appcheck_jwks_cache.clear()
            raise JWTError("Unknown App Check kid — JWKS refreshed")
        public_key = jwk.construct(key_data)
        decoded = jose_jwt.decode(
            x_firebase_appcheck,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
            issuer=f"https://firebaseappcheck.googleapis.com/{settings.firebase_project_number}",
        )
        aud = decoded.get("aud", [])
        if isinstance(aud, str):
            aud = [aud]
        if f"projects/{settings.firebase_project_number}" not in aud:
            raise JWTError("Invalid App Check audience")
    except (JWTError, Exception):
        raise HTTPException(
            401,
            detail={
                "error_code": "LEADERBOARD_APPCHECK_MISSING",
                "message": "Invalid App Check token",
            },
        )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ScoreSubmitRequest(BaseModel):
    season_id: str
    score: int


# ---------------------------------------------------------------------------
# POST /leaderboard/score  (T-443)
# ---------------------------------------------------------------------------

@router.post("/score", dependencies=[Depends(verify_app_check)])
async def submit_score(
    body: ScoreSubmitRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(verify_jwt),
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
    if body.season_id != settings.active_season_id:
        raise HTTPException(404, detail={"error_code": "SEASON_NOT_ACTIVE"})

    user_id = claims.get("uid", "")
    now = datetime.now(timezone.utc)

    # Check restricted_features — children excluded from leaderboard (T-401 sets this field)
    user_snap = await db.collection("users").document(user_id).get()
    if user_snap.exists and user_snap.to_dict().get("restricted_features", False):
        raise HTTPException(403, detail={"error_code": "LEADERBOARD_RESTRICTED"})

    display_name = ""
    if user_snap.exists:
        display_name = user_snap.to_dict().get("display_name", "") or ""

    # Authoritative score: read season_stars from Firestore, ignore body.score
    season_snap = await db.collection("season_progress").document(user_id).get()
    if season_snap.exists:
        sd = season_snap.to_dict()
        season_stars = (
            sd.get("season_stars", 0)
            if sd.get("season_id") == settings.active_season_id
            else 0
        )
    else:
        season_stars = 0

    anomaly = body.score != season_stars

    # Read current leaderboard entry and update only if score improved
    score_ref = (
        db.collection("leaderboards")
        .document(settings.active_season_id)
        .collection("scores")
        .document(user_id)
    )
    score_snap = await score_ref.get()
    existing_stars = score_snap.to_dict().get("season_stars", 0) if score_snap.exists else 0

    updated = season_stars > existing_stars
    if updated:
        await score_ref.set({
            "uid": user_id,
            "display_name": display_name,
            "season_stars": season_stars,
            "updated_at": now,
        })

    # Approximate rank: count players with strictly higher score
    current = season_stars if updated else existing_stars
    count_result = await (
        db.collection("leaderboards")
        .document(settings.active_season_id)
        .collection("scores")
        .where("season_stars", ">", current)
        .count()
        .get()
    )
    rank = count_result[0][0].value + 1

    # BQ: log every score submit with anomaly flag for fraud detection
    background_tasks.add_task(
        stream_event,
        "player_behavior",
        {
            "event_timestamp": now.isoformat(),
            "event_date": now.date().isoformat(),
            "user_id": user_id,
            "session_id": claims.get("sid", ""),
            "event_name": "leaderboard_score_submit",
            "platform": None,
            "app_version": None,
            "country": None,
            "level_id": None,
            "score": season_stars,
            "stars_earned": None,
            "duration_secs": None,
            "npc_type": None,
            "extra_json": json.dumps({
                "client_score": body.score,
                "anomaly": anomaly,
                "updated": updated,
            }),
        },
        settings.gcp_project_id,
        settings.bq_dataset,
        row_id=f"lb_score_{user_id}_{now.timestamp():.0f}",
    )

    return {"updated": updated, "rank": rank, "season_stars": season_stars}


# ---------------------------------------------------------------------------
# GET /leaderboard  (T-443)
# ---------------------------------------------------------------------------

@router.get("")
async def get_leaderboard(
    type: str = "global",
    season_id: str | None = None,
    claims: dict = Depends(verify_jwt),
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
    if type not in ("global", "weekly"):
        raise HTTPException(400, detail={"error_code": "LEADERBOARD_INVALID_TYPE"})

    target_season = season_id or settings.active_season_id
    user_id = claims.get("uid", "")
    now = datetime.now(timezone.utc)

    # Season metadata (name, prizes) from root leaderboard doc
    season_doc = await db.collection("leaderboards").document(target_season).get()
    if not season_doc.exists:
        raise HTTPException(404, detail={"error_code": "SEASON_NOT_FOUND"})

    season_data = season_doc.to_dict()
    season_name = season_data.get("name", target_season)
    top3_prizes = season_data.get("top3_prizes", [])

    # Top 100 scores descending
    score_docs = await (
        db.collection("leaderboards")
        .document(target_season)
        .collection("scores")
        .order_by("season_stars", direction="DESCENDING")
        .limit(100)
        .get()
    )

    top_players = []
    player_rank_obj = None
    player_in_top = False

    for i, doc in enumerate(score_docs):
        data = doc.to_dict()
        entry = {
            "rank": i + 1,
            "user_id": data.get("uid", doc.id),
            "display_name": data.get("display_name", ""),
            "season_points": data.get("season_stars", 0),
        }
        top_players.append(entry)
        if doc.id == user_id:
            player_rank_obj = entry
            player_in_top = True

    # If player not in top 100, find their rank separately
    if not player_in_top:
        player_doc = await (
            db.collection("leaderboards")
            .document(target_season)
            .collection("scores")
            .document(user_id)
            .get()
        )
        if player_doc.exists:
            pd = player_doc.to_dict()
            p_stars = pd.get("season_stars", 0)
            count_result = await (
                db.collection("leaderboards")
                .document(target_season)
                .collection("scores")
                .where("season_stars", ">", p_stars)
                .count()
                .get()
            )
            player_rank_obj = {
                "rank": count_result[0][0].value + 1,
                "user_id": user_id,
                "display_name": pd.get("display_name", ""),
                "season_points": p_stars,
            }
        else:
            player_rank_obj = {
                "rank": None,
                "user_id": user_id,
                "display_name": "",
                "season_points": 0,
            }

    return JSONResponse(
        content={
            "season_id": target_season,
            "season_name": season_name,
            "leaderboard_type": type,
            "top_players": top_players,
            "player_rank": player_rank_obj,
            "top3_prizes": top3_prizes,
            "cached_at": now.isoformat(),
        },
        headers={"Cache-Control": "public, max-age=300"},
    )
