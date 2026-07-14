import asyncio
import base64
import hashlib
import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from google.cloud.firestore import ArrayUnion, AsyncClient
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_firestore_client, get_settings, verify_jwt
from app.services import play_api, reconcile_service
from app.services.bq_streaming import stream_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

_REGEN_INTERVAL_SECS = 1800
_DEFAULT_MAX_LIVES = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_entitlement(product_id: str) -> tuple[str | None, str | None, int | None]:
    """Returns (entitlement_type, product_type, quantity) or (None, None, None) if unknown."""
    if product_id.startswith("lives_pack_"):
        try:
            qty = int(product_id.split("_")[-1])
        except ValueError:
            qty = 0
        return "life_pack", "consumable", qty
    if product_id == "no_ads":
        return "no_ads", "non_consumable", None
    if product_id.startswith("skin_"):
        return "skin", "non_consumable", None
    if product_id == "season_pass_gold":
        return "season_pass", "non_consumable", None
    return None, None, None


async def _grant_lives_iap(db: AsyncClient, user_id: str, quantity: int, now: datetime) -> int:
    """Grants lives from IAP purchase. Returns new current_lives count."""
    lives_ref = db.collection("lives").document(user_id)
    snap = await lives_ref.get()
    if snap.exists:
        data = snap.to_dict()
        count = data.get("count", 0)
        max_lives = data.get("max_lives", _DEFAULT_MAX_LIVES)
        last_regen_at = data.get("last_regen_at", now)
    else:
        count, max_lives, last_regen_at = 0, _DEFAULT_MAX_LIVES, now

    actual = min(quantity, max_lives - count)
    new_count = count + actual
    next_regen = (
        None if new_count >= max_lives
        else last_regen_at + timedelta(seconds=_REGEN_INTERVAL_SECS)
    )

    await lives_ref.set({
        "uid": user_id,
        "count": new_count,
        "max_lives": max_lives,
        "last_regen_at": last_regen_at,
        "next_regen_at": next_regen,
        "updated_at": now,
    }, merge=True)
    return new_count


def _bq_purchase_row(
    now: datetime,
    user_id: str,
    session_id: str,
    platform: str,
    product_id: str,
    product_type: str,
    purchase_token: str,
    order_id: str | None,
    verification_status: str,
    grant_status: str,
) -> dict:
    return {
        "event_timestamp": now.isoformat(),
        "event_date": now.date().isoformat(),
        "user_id": user_id,
        "session_id": session_id,
        "platform": platform,
        "app_version": None,
        "country": None,
        "product_id": product_id,
        "product_type": product_type,
        "purchase_token": purchase_token,
        "order_id": order_id,
        "price_usd": None,
        "currency_code": None,
        "verification_status": verification_status,
        "grant_status": grant_status,
    }


def _bq_entitlement_row(
    now: datetime,
    user_id: str,
    session_id: str,
    platform: str,
    entitlement_type: str,
    product_id: str,
    quantity: int | None,
) -> dict:
    return {
        "event_timestamp": now.isoformat(),
        "event_date": now.date().isoformat(),
        "user_id": user_id,
        "session_id": session_id,
        "platform": platform,
        "app_version": None,
        "country": None,
        "entitlement_type": entitlement_type,
        "entitlement_id": product_id,
        "source": "iap",
        "granted_by": "payment_verify",
        "quantity": quantity,
    }


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class AndroidVerifyRequest(BaseModel):
    purchase_token: str
    product_id: str
    session_id: str


class IosVerifyRequest(BaseModel):
    transaction_id: str
    product_id: str
    session_id: str


# ---------------------------------------------------------------------------
# POST /payments/android/verify
# ---------------------------------------------------------------------------

@router.post("/android/verify")
async def android_verify(
    body: AndroidVerifyRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(verify_jwt),
    settings: Settings = Depends(get_settings),
    db: AsyncClient = Depends(get_firestore_client),
):
    user_id = claims.get("uid", "")
    now = datetime.now(timezone.utc)
    token_hash = hashlib.sha256(body.purchase_token.encode()).hexdigest()

    entitlement_type, product_type, quantity = _infer_entitlement(body.product_id)
    if entitlement_type is None:
        raise HTTPException(400, detail={"error_code": "PAY_PRODUCT_NOT_FOUND"})

    # Call Play Developer API
    try:
        purchase = await play_api.get_product_purchase(
            settings.play_package_name, body.product_id, body.purchase_token
        )
    except play_api.PlayAPIError as e:
        if e.http_status >= 500:
            raise HTTPException(503, detail={"error_code": "PAY_STORE_UNAVAILABLE"})
        raise HTTPException(402, detail={"error_code": "PAY_VERIFICATION_FAILED"})
    except Exception:
        raise HTTPException(503, detail={"error_code": "PAY_STORE_UNAVAILABLE"})

    purchase_state = purchase.get("purchaseState", 0)
    order_id = purchase.get("orderId")

    # PENDING purchase — client must retry later
    if purchase_state == 2:
        return JSONResponse(status_code=202, content={
            "order_id": None,
            "product_id": body.product_id,
            "verification_status": "pending",
            "grant_status": "pending",
            "message": "Purchase is pending approval. Retry when payment is confirmed.",
        })

    # CANCELLED / invalid
    if purchase_state == 1:
        raise HTTPException(402, detail={"error_code": "PAY_VERIFICATION_FAILED"})

    # PURCHASED (purchaseState == 0)

    # Idempotency: already processed by a previous request
    already_done = (
        (product_type == "consumable" and purchase.get("consumptionState", 0) == 1)
        or (product_type == "non_consumable" and purchase.get("acknowledgementState", 0) == 1)
    )

    if already_done:
        current_lives = None
        if entitlement_type == "life_pack":
            snap = await db.collection("lives").document(user_id).get()
            current_lives = snap.to_dict().get("count", 0) if snap.exists else 0

        await db.collection("purchases").document(token_hash).set({
            "uid": user_id,
            "product_id": body.product_id,
            "product_type": product_type,
            "order_id": order_id,
            "purchase_token": body.purchase_token,
            "acknowledged": True,
            "acknowledged_at": now,
            "created_at": now,
        }, merge=True)

        background_tasks.add_task(
            stream_event, "purchase_events",
            _bq_purchase_row(
                now, user_id, body.session_id, "android",
                body.product_id, product_type, token_hash,
                order_id, "verified", "already_granted",
            ),
            settings.gcp_project_id, settings.bq_dataset,
            row_id=f"purchase_android_{token_hash}",
        )

        return {
            "order_id": order_id,
            "product_id": body.product_id,
            "product_type": product_type,
            "verification_status": "verified",
            "grant_status": "already_granted",
            "entitlement": {
                "type": entitlement_type,
                "quantity": quantity,
                "current_lives": current_lives,
            },
        }

    # Grant entitlement in Firestore
    current_lives = None
    if entitlement_type == "life_pack" and quantity:
        current_lives = await _grant_lives_iap(db, user_id, quantity, now)
    elif entitlement_type == "no_ads":
        await db.collection("entitlements").document(user_id).set(
            {"no_ads": True, "updated_at": now}, merge=True
        )
    elif entitlement_type == "skin":
        await db.collection("entitlements").document(user_id).set(
            {"skins": ArrayUnion([body.product_id]), "updated_at": now}, merge=True
        )
    elif entitlement_type == "season_pass":
        await db.collection("season_progress").document(user_id).set(
            {"has_gold_pass": True, "season_id": settings.active_season_id, "updated_at": now},
            merge=True,
        )

    # Write purchase record so PAY-002 reconciliation job can find un-acknowledged tokens.
    await db.collection("purchases").document(token_hash).set({
        "uid": user_id,
        "product_id": body.product_id,
        "product_type": product_type,
        "order_id": order_id,
        "purchase_token": body.purchase_token,
        "acknowledged": False,
        "created_at": now,
    }, merge=True)

    # Acknowledge or consume via Play API (non-fatal if this call fails — PAY-002 reconciles)
    try:
        if product_type == "consumable":
            await play_api.consume_product_purchase(
                settings.play_package_name, body.product_id, body.purchase_token
            )
        else:
            await play_api.acknowledge_product_purchase(
                settings.play_package_name, body.product_id, body.purchase_token
            )
        await db.collection("purchases").document(token_hash).set(
            {"acknowledged": True, "acknowledged_at": now}, merge=True
        )
    except Exception:
        pass

    # BQ streaming (background)
    background_tasks.add_task(
        stream_event, "purchase_events",
        _bq_purchase_row(
            now, user_id, body.session_id, "android",
            body.product_id, product_type, token_hash,
            order_id, "verified", "granted",
        ),
        settings.gcp_project_id, settings.bq_dataset,
        row_id=f"purchase_android_{token_hash}",
    )
    background_tasks.add_task(
        stream_event, "entitlement_grants",
        _bq_entitlement_row(
            now, user_id, body.session_id, "android",
            entitlement_type, body.product_id, quantity,
        ),
        settings.gcp_project_id, settings.bq_dataset,
        row_id=f"entitlement_android_{token_hash}",
    )

    return {
        "order_id": order_id,
        "product_id": body.product_id,
        "product_type": product_type,
        "verification_status": "verified",
        "grant_status": "granted",
        "entitlement": {
            "type": entitlement_type,
            "quantity": quantity,
            "current_lives": current_lives,
        },
    }


# ---------------------------------------------------------------------------
# POST /payments/ios/verify  (DATA-002 ST-08 — stub, iOS en PAY-001 fase 2)
# ---------------------------------------------------------------------------

@router.post("/ios/verify")
async def ios_verify(
    body: IosVerifyRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(verify_jwt),
    settings: Settings = Depends(get_settings),
):
    user_id = claims.get("uid", "")
    now = datetime.now(timezone.utc)
    entitlement_type, product_type, quantity = _infer_entitlement(body.product_id)

    # PAY-001 phase 2: replace with App Store Server API call + JWS verification
    verification_status = "verified"
    grant_status = "granted"

    background_tasks.add_task(
        stream_event, "purchase_events",
        _bq_purchase_row(
            now, user_id, body.session_id, "ios",
            body.product_id, product_type or "unknown", body.transaction_id,
            None, verification_status, grant_status,
        ),
        settings.gcp_project_id, settings.bq_dataset,
        row_id=f"purchase_ios_{body.transaction_id}",
    )
    background_tasks.add_task(
        stream_event, "entitlement_grants",
        _bq_entitlement_row(
            now, user_id, body.session_id, "ios",
            entitlement_type or "unknown", body.product_id, quantity,
        ),
        settings.gcp_project_id, settings.bq_dataset,
        row_id=f"entitlement_ios_{body.transaction_id}",
    )

    return {
        "transaction_id": body.transaction_id,
        "product_id": body.product_id,
        "product_type": product_type,
        "verification_status": verification_status,
        "grant_status": grant_status,
        "entitlement": {
            "type": entitlement_type,
            "quantity": quantity,
            "current_lives": None,
        },
    }


# ---------------------------------------------------------------------------
# PAY-003 helpers
# ---------------------------------------------------------------------------

async def _verify_pubsub_oidc(token: str, expected_email: str) -> bool:
    """Verify a Pub/Sub push OIDC bearer token via Google's tokeninfo endpoint."""
    url = (
        "https://oauth2.googleapis.com/tokeninfo?id_token="
        + urllib.parse.quote(token, safe="")
    )

    def _fetch() -> bool:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                info = json.loads(r.read())
            return (
                info.get("email") == expected_email
                and info.get("email_verified") in ("true", True)
            )
        except Exception:
            return False

    return await asyncio.to_thread(_fetch)


# ---------------------------------------------------------------------------
# POST /payments/android/refund-notification  (T-254 / PAY-003)
# ---------------------------------------------------------------------------

@router.post("/android/refund-notification")
async def android_refund_notification(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    db: AsyncClient = Depends(get_firestore_client),
):
    # 1. Verify Pub/Sub OIDC bearer token
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(401, detail={"error_code": "RTDN_AUTH_MISSING"})

    oidc_token = auth_header[7:]
    if not await _verify_pubsub_oidc(oidc_token, settings.pubsub_rtdn_sa_email):
        raise HTTPException(401, detail={"error_code": "RTDN_AUTH_INVALID"})

    # 2. Parse Pub/Sub push envelope
    try:
        body_json = await request.json()
        data_b64 = body_json.get("message", {}).get("data", "")
    except Exception:
        logger.warning("T-254 RTDN: malformed Pub/Sub envelope")
        return Response(status_code=204)

    if not data_b64:
        return Response(status_code=204)

    # 3. Decode and parse DeveloperNotification JSON
    try:
        notification = json.loads(base64.b64decode(data_b64).decode("utf-8"))
    except Exception:
        logger.warning("T-254 RTDN: base64/JSON decode failed")
        return Response(status_code=204)

    voided = notification.get("voidedPurchaseNotification")
    if not voided:
        return Response(status_code=204)

    purchase_token = voided.get("purchaseToken", "")
    if not purchase_token:
        return Response(status_code=204)

    # 4. Hash token → look up Firestore doc
    token_hash = hashlib.sha256(purchase_token.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    try:
        doc = await db.collection("purchases").document(token_hash).get()
    except Exception as exc:
        logger.error("T-254 RTDN: Firestore lookup failed: %s", exc)
        return Response(status_code=204)

    if not doc.exists:
        logger.warning("T-254 RTDN: purchase not found for token ...%s", purchase_token[-8:])
        return Response(status_code=204)

    data = doc.to_dict()

    # 5. Idempotency guard
    if data.get("voided"):
        return Response(status_code=204)

    uid = data.get("uid", "")
    product_id = data.get("product_id", "")
    entitlement_type, _, _ = _infer_entitlement(product_id)

    # 6. Revoke entitlement
    if uid and entitlement_type:
        try:
            await reconcile_service.revoke_entitlement(db, uid, entitlement_type, product_id, now)
        except Exception as exc:
            logger.error("T-254 RTDN: revoke_entitlement failed uid=%s: %s", uid, exc)

    # 7. Mark purchase as voided
    try:
        await db.collection("purchases").document(token_hash).set(
            {"voided": True, "voided_at": now}, merge=True
        )
    except Exception as exc:
        logger.error("T-254 RTDN: voided flag write failed: %s", exc)

    # 8. BQ log (background — non-critical)
    background_tasks.add_task(
        stream_event,
        "purchase_events",
        _bq_purchase_row(
            now, uid, "", "android",
            product_id, data.get("product_type", ""),
            token_hash, data.get("order_id"),
            "refunded", "revoked",
        ),
        settings.gcp_project_id,
        settings.bq_dataset,
        row_id=f"refund_android_{token_hash}",
    )

    logger.info("T-254 RTDN: revoked uid=%s product=%s", uid, product_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# POST /payments/ios/refund-notification  (T-254 / PAY-003 — stub, iOS post-MVP)
# ---------------------------------------------------------------------------

@router.post("/ios/refund-notification")
async def ios_refund_notification(request: Request):
    # PAY-003 phase 2: Apple ASSN v2 JWS chain verification — iOS out of MVP scope
    return Response(status_code=204)
