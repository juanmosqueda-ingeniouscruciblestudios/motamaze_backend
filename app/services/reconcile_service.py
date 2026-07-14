import hashlib
import logging
from datetime import datetime, timedelta, timezone

from google.cloud.firestore import ArrayUnion, AsyncClient

from app.config import Settings
from app.services import play_api

logger = logging.getLogger(__name__)

_PENDING_ACK_WINDOW_HOURS = 23
_DEFAULT_MAX_LIVES = 5


def _infer_entitlement(product_id: str) -> tuple[str | None, str | None]:
    """Returns (entitlement_type, product_type) for a known product_id."""
    if product_id.startswith("lives_pack_"):
        return "life_pack", "consumable"
    if product_id == "no_ads":
        return "no_ads", "non_consumable"
    if product_id.startswith("skin_"):
        return "skin", "non_consumable"
    if product_id == "season_pass_gold":
        return "season_pass", "non_consumable"
    return None, None


async def _revoke_entitlement(
    db: AsyncClient,
    uid: str,
    entitlement_type: str,
    product_id: str,
    now: datetime,
) -> None:
    if entitlement_type == "no_ads":
        await db.collection("entitlements").document(uid).set(
            {"no_ads": False, "updated_at": now}, merge=True
        )
    elif entitlement_type == "skin":
        snap = await db.collection("entitlements").document(uid).get()
        if snap.exists:
            skins = snap.to_dict().get("skins", [])
            skins = [s for s in skins if s != product_id]
            await db.collection("entitlements").document(uid).set(
                {"skins": skins, "updated_at": now}, merge=True
            )
    elif entitlement_type == "season_pass":
        await db.collection("season_progress").document(uid).set(
            {"has_gold_pass": False, "updated_at": now}, merge=True
        )
    # life_pack is consumable — already consumed, nothing to revoke in Firestore


async def reconcile_pending_acks(pkg: str, db: AsyncClient, settings: Settings) -> dict:
    """Retry acknowledge/consume for purchases where it failed at verify time."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_PENDING_ACK_WINDOW_HOURS)
    docs = await (
        db.collection("purchases")
        .where("acknowledged", "==", False)
        .where("created_at", "<", cutoff)
        .get()
    )

    retried = fixed = failed = 0
    for doc in docs:
        data = doc.to_dict()
        # doc.id is now SHA-256 hash; raw purchaseToken is stored as a field
        purchase_token = data.get("purchase_token") or doc.id
        product_id = data.get("product_id", "")
        product_type = data.get("product_type", "")
        retried += 1
        now = datetime.now(timezone.utc)
        try:
            if product_type == "consumable":
                await play_api.consume_product_purchase(pkg, product_id, purchase_token)
            else:
                await play_api.acknowledge_product_purchase(pkg, product_id, purchase_token)
            await db.collection("purchases").document(doc.id).set(
                {"acknowledged": True, "acknowledged_at": now}, merge=True
            )
            fixed += 1
            logger.info("PAY-002 ack fixed: token=...%s product=%s", purchase_token[-8:], product_id)
        except Exception as exc:
            failed += 1
            logger.warning("PAY-002 ack retry failed: token=...%s err=%s", purchase_token[-8:], exc)

    return {"retried": retried, "fixed": fixed, "failed": failed}


async def detect_refunds(pkg: str, db: AsyncClient, settings: Settings) -> dict:
    """Check Play voidedpurchases for the past 24h and revoke entitlements."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=1)

    try:
        voided = await play_api.list_voided_purchases(pkg, start, now)
    except play_api.PlayAPIError as exc:
        logger.error("PAY-002 voidedpurchases fetch failed: %s", exc)
        return {"voided_checked": 0, "revoked": 0, "error": str(exc)}

    revoked = skipped = 0
    for vp in voided:
        token = vp.get("purchaseToken")
        if not token:
            continue

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        doc = await db.collection("purchases").document(token_hash).get()
        if not doc.exists:
            skipped += 1
            logger.warning("PAY-002 voided token not in purchases: ...%s", token[-8:])
            continue

        data = doc.to_dict()
        uid = data.get("uid")
        product_id = data.get("product_id", "")
        entitlement_type, _ = _infer_entitlement(product_id)

        if not uid or not entitlement_type:
            skipped += 1
            continue

        if data.get("voided"):
            skipped += 1
            continue

        await _revoke_entitlement(db, uid, entitlement_type, product_id, now)
        await db.collection("purchases").document(token_hash).set(
            {"voided": True, "voided_at": now}, merge=True
        )
        revoked += 1
        logger.info("PAY-002 refund revoked: uid=%s product=%s", uid, product_id)

    return {"voided_checked": len(voided), "revoked": revoked, "skipped": skipped}
