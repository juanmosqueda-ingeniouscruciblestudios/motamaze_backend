import secrets
import string
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from google.cloud.firestore import AsyncClient
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_firestore_client, get_settings, verify_jwt

router = APIRouter(tags=["social"])

_BASE62 = string.ascii_letters + string.digits  # 62 chars → 62^12 ≈ 3.2×10²¹ tokens


def _generate_token(length: int = 12) -> str:
    return "".join(secrets.choice(_BASE62) for _ in range(length))


def _og_image_url(settings: Settings, score: int, level_reached: int) -> str:
    cloud = settings.cloudinary_cloud_name
    base  = settings.cloudinary_share_image_id
    score_layer = f"l_text:Fredoka@google_90_700:{score}%20pts,co_white,g_center,y_-60"
    level_layer = f"l_text:Fredoka@google_55_500:Nivel%20{level_reached},co_white,g_center,y_40"
    # f_auto,q_auto as the final chained component (right before the public_id)
    # controls the delivery encoding of the fully-composited image (base +
    # both text overlays) — auto-selects WebP/AVIF per the requester's Accept
    # header and an auto-tuned quality level. Without this, Cloudinary served
    # the untransformed base PNG (~1.2MB) instead of the <600KB WebP the spec
    # calls for (found during T-440 ST-02 integration testing, 2026-07-21).
    delivery = "f_auto,q_auto"
    return (
        f"https://res.cloudinary.com/{cloud}/image/upload"
        f"/{score_layer}/{level_layer}/{delivery}/{base}"
    )


def _og_proxy_url(settings: Settings, token: str) -> str:
    return f"{settings.share_base_url}/ogimg/{token}"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ShareCreateRequest(BaseModel):
    score: int
    level_reached: int
    season_id: str


# ---------------------------------------------------------------------------
# POST /share/create  (T-440)
# ---------------------------------------------------------------------------

@router.post("/share/create")
async def share_create(
    body: ShareCreateRequest,
    claims: dict = Depends(verify_jwt),
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
    if not (1 <= body.level_reached <= 30):
        raise HTTPException(
            400,
            detail={"error_code": "SHARE_INVALID_LEVEL", "message": "level_reached must be between 1 and 30"},
        )
    if body.score < 0:
        raise HTTPException(
            400,
            detail={"error_code": "SHARE_INVALID_SCORE", "message": "score must be >= 0"},
        )
    if not body.season_id:
        raise HTTPException(
            404,
            detail={"error_code": "SEASON_NOT_ACTIVE", "message": "season_id is required"},
        )

    user_id = claims.get("uid", "")
    now = datetime.now(timezone.utc)

    # Social-001 will derive expires_at from active season document
    expires_at = datetime(2026, 9, 14, 23, 59, 59, tzinfo=timezone.utc)

    # Collision retry — 62^12 space makes this virtually unreachable
    for _ in range(3):
        token = _generate_token()
        doc_ref = db.collection("shares").document(token)
        snap = await doc_ref.get()
        if not snap.exists:
            break

    # T-210: validate score/level against server-side progression record when available
    og_image_url = _og_image_url(settings, body.score, body.level_reached)
    og_proxy     = _og_proxy_url(settings, token)

    # T-311: replace with Tenjin tracking link
    # share_url = tenjin_create_link(deeplink_url=f"{settings.share_base_url}/s/{token}")
    share_url = f"{settings.share_base_url}/s/{token}"

    await doc_ref.set({
        "uid":           user_id,
        "score":         body.score,
        "level_reached": body.level_reached,
        "season_id":     body.season_id,
        "created_at":    now,
        "expires_at":    expires_at,
        "og_image_url":  og_image_url,
        "share_url":     share_url,
    })

    return {
        "share_url":    share_url,
        "token":        token,
        "og_image_url": og_proxy,
        "expires_at":   expires_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# GET /s/{token}  (T-440 — public, returns HTML for OG previews)
# ---------------------------------------------------------------------------

@router.get("/s/{token}", response_class=HTMLResponse)
async def share_view(
    token: str,
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
    snap = await db.collection("shares").document(token).get()
    if not snap.exists:
        raise HTTPException(
            404,
            detail={"error_code": "SHARE_TOKEN_NOT_FOUND", "message": "Share not found"},
        )

    data = snap.to_dict()
    expires_at = data.get("expires_at")
    if expires_at and expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            404,
            detail={"error_code": "SHARE_TOKEN_NOT_FOUND", "message": "Share has expired"},
        )

    score     = data.get("score", 0)
    level     = data.get("level_reached", 1)
    share_url = data.get("share_url", f"{settings.share_base_url}/s/{token}")
    og_proxy  = _og_proxy_url(settings, token)

    title       = f"¡Llegué al nivel {level} en MotaMaze! ⭐ {score} pts"
    description = "¿Puedes superarme? Descarga MotaMaze y a ver quién llega más lejos."

    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta property="og:title"        content="{title}" />
  <meta property="og:description"  content="{description}" />
  <meta property="og:image"        content="{og_proxy}" />
  <meta property="og:url"          content="{share_url}" />
  <meta property="og:type"         content="website" />
  <meta name="twitter:card"        content="summary_large_image" />
  <meta name="twitter:title"       content="{title}" />
  <meta name="twitter:description" content="{description}" />
  <meta name="twitter:image"       content="{og_proxy}" />
  <title>{title}</title>
</head>
<body>
  <script>window.location = "motamaze://share/{token}";</script>
  <p><a href="https://play.google.com/store/apps/details?id=com.ingeniouscruciblestudios.motamaze">Descargar MotaMaze</a></p>
</body>
</html>""")


# ---------------------------------------------------------------------------
# GET /ogimg/{token}  (T-440 — public redirect proxy, eliminates Cloudinary lock-in)
# ---------------------------------------------------------------------------

@router.get("/ogimg/{token}")
async def og_image_redirect(
    token: str,
    db: AsyncClient = Depends(get_firestore_client),
    settings: Settings = Depends(get_settings),
):
    fallback = (
        f"https://res.cloudinary.com/{settings.cloudinary_cloud_name}"
        f"/image/upload/{settings.cloudinary_share_image_id}"
    )
    snap = await db.collection("shares").document(token).get()
    if not snap.exists:
        return RedirectResponse(url=fallback, status_code=302)
    og_url = snap.to_dict().get("og_image_url") or fallback
    return RedirectResponse(url=og_url, status_code=302)


# GET  /leaderboard             — T-443
# POST /leaderboard/score       — T-443
# GET  /season                  — Social-001
# POST /season/claim-reward     — Social-001
# GET  /achievements            — Social-002
