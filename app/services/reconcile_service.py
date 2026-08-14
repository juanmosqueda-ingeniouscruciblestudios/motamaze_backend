import hashlib
import logging
from datetime import datetime, timedelta, timezone

from google.cloud.firestore import ArrayUnion, AsyncClient

from app.config import Settings
from app.services import play_api, store_service

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
        return "season_pass", "consumable"  # see payments.py's _infer_entitlement (2026-08-14)
    return None, None


async def revoke_entitlement(
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
            skins = store_service.normalize_skins(snap.to_dict())
            entry = skins.get(product_id)
            # Only revoke what was bought. The same skin can also arrive from
            # the Season Pass free track or a leaderboard prize (T-243) — a
            # refund has no claim on those, and stripping one would punish the
            # player for a purchase made on top of something they had earned.
            if entry and entry.get("source") == store_service.SKIN_SOURCE_PURCHASE:
                # update() rather than set(merge=True): merging a map can only
                # add or overwrite keys, never drop one, and merge=False would
                # take the rest of the document (no_ads, life_packs_total) with
                # it. Replacing the whole skins field is what actually removes.
                await db.collection("entitlements").document(uid).update({
                    "skins": {sid: e for sid, e in skins.items() if sid != product_id},
                    "updated_at": now,
                })
                # Drop it from the profile too if it was the equipped look —
                # the client applies equipped_skin at boot, so otherwise the
                # player keeps wearing a skin they were refunded for.
                user_snap = await db.collection("users").document(uid).get()
                if user_snap.exists and (user_snap.to_dict() or {}).get("equipped_skin") == product_id:
                    await db.collection("users").document(uid).update({"equipped_skin": None})
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

        await revoke_entitlement(db, uid, entitlement_type, product_id, now)
        await db.collection("purchases").document(token_hash).set(
            {"voided": True, "voided_at": now}, merge=True
        )
        revoked += 1
        logger.info("PAY-002 refund revoked: uid=%s product=%s", uid, product_id)

    return {"voided_checked": len(voided), "revoked": revoked, "skipped": skipped}
