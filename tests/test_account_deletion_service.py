"""Unit tests for app/services/account_deletion_service.py — T-123 (ST-04):
finding accounts past their 30-day grace period and purging their Firestore
data (hard-delete most collections, anonymize purchases, users/{uid} last)."""

from datetime import datetime, timedelta, timezone

from app.services import account_deletion_service

NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# find_users_due_for_purge
# ---------------------------------------------------------------------------


async def test_find_users_due_for_purge_past_grace_period(fake_db):
    fake_db.seed("users", "due-user", {
        "uid": "due-user",
        "delete_requested_at": NOW - timedelta(days=31),
    })
    due = await account_deletion_service.find_users_due_for_purge(fake_db, now=NOW)
    assert due == ["due-user"]


async def test_find_users_due_for_purge_within_grace_period_excluded(fake_db):
    fake_db.seed("users", "recent-request", {
        "uid": "recent-request",
        "delete_requested_at": NOW - timedelta(days=5),
    })
    due = await account_deletion_service.find_users_due_for_purge(fake_db, now=NOW)
    assert due == []


async def test_find_users_due_for_purge_no_pending_deletion_excluded(fake_db):
    fake_db.seed("users", "normal-user", {"uid": "normal-user", "delete_requested_at": None})
    due = await account_deletion_service.find_users_due_for_purge(fake_db, now=NOW)
    assert due == []


async def test_find_users_due_for_purge_exact_boundary_included(fake_db):
    # Exactly 30 days — <= cutoff, so it's included (not "31 days minimum").
    fake_db.seed("users", "boundary-user", {
        "uid": "boundary-user",
        "delete_requested_at": NOW - timedelta(days=30),
    })
    due = await account_deletion_service.find_users_due_for_purge(fake_db, now=NOW)
    assert due == ["boundary-user"]


# ---------------------------------------------------------------------------
# purge_user_firestore_data
# ---------------------------------------------------------------------------


async def _seed_full_user(fake_db, uid: str):
    fake_db.seed("users", uid, {"uid": uid, "delete_requested_at": NOW - timedelta(days=31)})
    fake_db.seed("progress", uid, {"uid": uid, "best_level": 5})
    fake_db.seed("lives", uid, {"uid": uid, "count": 3})
    fake_db.seed("entitlements", uid, {"no_ads": True, "skins": ["skin_gold"]})
    fake_db.seed("season_progress", uid, {"uid": uid, "season_stars": 100})
    fake_db.seed("achievement_progress", uid, {"uid": uid, "unlocked": ["first_level"]})
    fake_db.seed("sessions", f"{uid}-session-1", {"uid": uid, "session_id": f"{uid}-session-1"})
    fake_db.seed("purchases", f"{uid}-purchase-1", {"uid": uid, "product_id": "no_ads", "amount": 299})


async def test_purge_hard_deletes_uid_keyed_collections(fake_db):
    await _seed_full_user(fake_db, "purge-user-1")
    await account_deletion_service.purge_user_firestore_data(fake_db, "purge-user-1", now=NOW)

    for collection in ["progress", "lives", "entitlements", "season_progress", "achievement_progress"]:
        assert not (await fake_db.collection(collection).document("purge-user-1").get()).exists

    assert not (await fake_db.collection("users").document("purge-user-1").get()).exists


async def test_purge_deletes_sessions_by_uid(fake_db):
    await _seed_full_user(fake_db, "purge-user-2")
    await account_deletion_service.purge_user_firestore_data(fake_db, "purge-user-2", now=NOW)

    assert not (await fake_db.collection("sessions").document("purge-user-2-session-1").get()).exists


async def test_purge_anonymizes_purchases_instead_of_deleting(fake_db):
    await _seed_full_user(fake_db, "purge-user-3")
    await account_deletion_service.purge_user_firestore_data(fake_db, "purge-user-3", now=NOW)

    doc = (await fake_db.collection("purchases").document("purge-user-3-purchase-1").get()).to_dict()
    assert doc is not None  # still exists — anonymized, not deleted
    assert doc["uid"] is None
    assert doc["anonymized_at"] == NOW
    assert doc["product_id"] == "no_ads"  # transaction data preserved for audit


async def test_purge_returns_tables_touched(fake_db):
    await _seed_full_user(fake_db, "purge-user-4")
    touched = await account_deletion_service.purge_user_firestore_data(fake_db, "purge-user-4", now=NOW)

    assert set(touched) == {
        "progress", "lives", "entitlements", "season_progress",
        "achievement_progress", "sessions", "purchases", "users",
    }


async def test_purge_skips_missing_collections_gracefully(fake_db):
    # Minimal user — no progress/lives/purchases/etc ever created.
    fake_db.seed("users", "minimal-user", {
        "uid": "minimal-user", "delete_requested_at": NOW - timedelta(days=31),
    })
    touched = await account_deletion_service.purge_user_firestore_data(fake_db, "minimal-user", now=NOW)
    assert touched == ["users"]
