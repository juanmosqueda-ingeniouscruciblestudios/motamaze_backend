from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_settings, verify_jwt
from app.services.bq_streaming import stream_event

router = APIRouter(prefix="/payments", tags=["payments"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_entitlement(product_id: str) -> tuple[str, str, int | None]:
    """Returns (entitlement_type, product_type, quantity) from product_id."""
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
    return "life_pack", "consumable", 0


def _bq_purchase_row(
    now: datetime,
    user_id: str,
    session_id: str,
    platform: str,
    product_id: str,
    product_type: str,
    purchase_token: str,
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
        "order_id": None,
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
# POST /payments/android/verify  (DATA-002 ST-08)
# ---------------------------------------------------------------------------

@router.post("/android/verify")
async def android_verify(
    body: AndroidVerifyRequest,
    background_tasks: BackgroundTasks,
    claims: dict = Depends(verify_jwt),
    settings: Settings = Depends(get_settings),
):
    user_id = claims.get("uid", "")
    now = datetime.now(timezone.utc)
    entitlement_type, product_type, quantity = _infer_entitlement(body.product_id)

    # PAY-001 will replace this stub with Play Developer API: purchases.products.get()
    verification_status = "verified"
    grant_status = "granted"

    background_tasks.add_task(
        stream_event, "purchase_events",
        _bq_purchase_row(
            now, user_id, body.session_id, "android",
            body.product_id, product_type, body.purchase_token,
            verification_status, grant_status,
        ),
        settings.gcp_project_id, settings.bq_dataset,
        row_id=f"purchase_android_{body.purchase_token}",
    )
    background_tasks.add_task(
        stream_event, "entitlement_grants",
        _bq_entitlement_row(
            now, user_id, body.session_id, "android",
            entitlement_type, body.product_id, quantity,
        ),
        settings.gcp_project_id, settings.bq_dataset,
        row_id=f"entitlement_android_{body.purchase_token}",
    )

    return {
        "order_id": None,  # populated by Play API in PAY-001
        "product_id": body.product_id,
        "product_type": product_type,
        "verification_status": verification_status,
        "grant_status": grant_status,
        "entitlement": {
            "type": entitlement_type,
            "quantity": quantity,
            "current_lives": None,  # PAY-001 will read from Firestore
        },
    }


# ---------------------------------------------------------------------------
# POST /payments/ios/verify  (DATA-002 ST-08)
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

    # PAY-001 will replace this stub with App Store Server API call + JWS verification
    verification_status = "verified"
    grant_status = "granted"

    background_tasks.add_task(
        stream_event, "purchase_events",
        _bq_purchase_row(
            now, user_id, body.session_id, "ios",
            body.product_id, product_type, body.transaction_id,
            verification_status, grant_status,
        ),
        settings.gcp_project_id, settings.bq_dataset,
        row_id=f"purchase_ios_{body.transaction_id}",
    )
    background_tasks.add_task(
        stream_event, "entitlement_grants",
        _bq_entitlement_row(
            now, user_id, body.session_id, "ios",
            entitlement_type, body.product_id, quantity,
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
            "current_lives": None,  # PAY-001 will read from Firestore
        },
    }


# POST /payments/android/refund-notification  — PAY-001
# POST /payments/ios/refund-notification      — PAY-001
