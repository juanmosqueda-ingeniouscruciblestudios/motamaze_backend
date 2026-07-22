"""Unit tests for app/services/auth_service.py — Apple token verification and
the multi-provider upsert_user()/create_session() changes (AUTH-004)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services import auth_service, jwt_service
from tests.conftest import make_apple_token

APPLE_AUD = "com.ingeniouscruciblestudios.motamaze"


# ---------------------------------------------------------------------------
# verify_apple_token
# ---------------------------------------------------------------------------


async def test_verify_apple_token_valid(apple_signing_key):
    token = make_apple_token(apple_signing_key, sub="apple-sub-abc.123")
    claims = await auth_service.verify_apple_token(token, APPLE_AUD)
    assert claims["sub"] == "apple-sub-abc.123"
    assert claims["email"] == "player@example.com"


async def test_verify_apple_token_expired(apple_signing_key):
    token = make_apple_token(apple_signing_key, exp_delta=timedelta(minutes=-5))
    with pytest.raises(ValueError, match="(?i)expired"):
        await auth_service.verify_apple_token(token, APPLE_AUD)


async def test_verify_apple_token_wrong_audience(apple_signing_key):
    token = make_apple_token(apple_signing_key, aud="com.someoneelse.otherapp")
    with pytest.raises(ValueError):
        await auth_service.verify_apple_token(token, APPLE_AUD)


async def test_verify_apple_token_unknown_kid(apple_signing_key):
    token = make_apple_token(apple_signing_key, kid="a-kid-not-in-jwks")
    with pytest.raises(ValueError, match="Unknown Apple signing key"):
        await auth_service.verify_apple_token(token, APPLE_AUD)


async def test_verify_apple_token_forged_signature(
    apple_signing_key, apple_signing_key_untrusted
):
    # Signed by a key whose public JWK was never published — but its `kid`
    # matches the trusted key's kid, so it passes the lookup and must fail on
    # signature verification instead.
    token = make_apple_token(
        apple_signing_key,
        kid=apple_signing_key["kid"],
        signing_pem=apple_signing_key_untrusted["private_pem"],
    )
    with pytest.raises(ValueError):
        await auth_service.verify_apple_token(token, APPLE_AUD)


# ---------------------------------------------------------------------------
# upsert_user
# ---------------------------------------------------------------------------


async def test_upsert_user_new_apple_user(fake_db):
    uid, is_new, is_child, _ = await auth_service.upsert_user(
        fake_db, "apple-sub-1", "p@example.com", "Player One", None, "apple"
    )
    assert is_new is True
    assert is_child is None
    doc = (await fake_db.collection("users").document(uid).get()).to_dict()
    assert doc["provider"] == "apple"
    assert doc["email"] == "p@example.com"
    assert doc["photo_url"] is None


async def test_upsert_user_repeat_apple_login_blank_fields_preserved(fake_db):
    await auth_service.upsert_user(
        fake_db, "apple-sub-2", "p2@example.com", "Player Two", None, "apple"
    )
    # Second login: Apple gives no name (and simulate a blank email edge case too).
    uid, is_new, _, _ = await auth_service.upsert_user(
        fake_db, "apple-sub-2", "", "", None, "apple"
    )
    assert is_new is False
    doc = (await fake_db.collection("users").document(uid).get()).to_dict()
    assert doc["email"] == "p2@example.com"
    assert doc["display_name"] == "Player Two"


async def test_upsert_user_provider_mismatch_raises(fake_db):
    await auth_service.upsert_user(
        fake_db, "shared-sub", "g@example.com", "G Player", None, "google"
    )
    with pytest.raises(ValueError, match="AUTH_PROVIDER_MISMATCH"):
        await auth_service.upsert_user(
            fake_db, "shared-sub", "a@example.com", "A Player", None, "apple"
        )


async def test_upsert_user_legacy_doc_backfills_provider(fake_db):
    # Simulate a doc created before AUTH-004 shipped: no `provider` field.
    fake_db.seed("users", "legacy-sub", {
        "uid": "legacy-sub",
        "email": "old@example.com",
        "display_name": "Old User",
        "photo_url": None,
        "consent": {},
    })
    uid, is_new, _, _ = await auth_service.upsert_user(
        fake_db, "legacy-sub", "old@example.com", "Old User", None, "google"
    )
    assert is_new is False
    doc = (await fake_db.collection("users").document(uid).get()).to_dict()
    assert doc["provider"] == "google"


# ---------------------------------------------------------------------------
# T-402: BR store_age_signal reconciliation (subtask 5)
# ---------------------------------------------------------------------------


async def test_upsert_user_br_signal_minor_sets_is_child_at_creation(fake_db):
    uid, is_new, is_child, _ = await auth_service.upsert_user(
        fake_db, "br-minor-1", "p@example.com", "Player", None, "google",
        country_code="BR", consent_age_threshold=18,
        store_age_signal="13-15", store_age_signal_source="play_age_signals",
    )
    assert is_new is True
    assert is_child is True  # returned value already reflects the signal

    doc = (await fake_db.collection("users").document(uid).get()).to_dict()
    assert doc["consent"]["is_child"] is True
    assert doc["consent"]["coppa_compliant"] is False
    assert doc["restricted_features"] == {
        "leaderboard": True, "personalized_ads": True, "share_score": True,
    }


async def test_upsert_user_br_signal_adult_sets_coppa_compliant_at_creation(fake_db):
    uid, is_new, is_child, _ = await auth_service.upsert_user(
        fake_db, "br-adult-1", "p@example.com", "Player", None, "google",
        country_code="BR", consent_age_threshold=18,
        store_age_signal="18+", store_age_signal_source="play_age_signals",
    )
    assert is_child is False

    doc = (await fake_db.collection("users").document(uid).get()).to_dict()
    assert doc["consent"]["is_child"] is False
    assert doc["consent"]["coppa_compliant"] is True
    assert doc["restricted_features"]["leaderboard"] is False


async def test_upsert_user_br_without_signal_unchanged(fake_db):
    # No store_age_signal sent (e.g. pre-T-402 client, or platform didn't
    # return one) — falls back to today's DOB-only flow, is_child stays None.
    uid, is_new, is_child, _ = await auth_service.upsert_user(
        fake_db, "br-no-signal-1", "p@example.com", "Player", None, "google",
        country_code="BR", consent_age_threshold=18,
    )
    assert is_child is None
    doc = (await fake_db.collection("users").document(uid).get()).to_dict()
    assert doc["consent"]["is_child"] is None
    assert "restricted_features" not in doc


async def test_upsert_user_non_br_signal_never_triggers_reconciliation(fake_db):
    # Regression guard: a store_age_signal present for a NON-Brazil user must
    # be captured (raw) but must never drive is_child — DOB (T-401) remains
    # the sole determinant everywhere except BR.
    uid, is_new, is_child, _ = await auth_service.upsert_user(
        fake_db, "mx-user-1", "p@example.com", "Player", None, "google",
        country_code="MX", consent_age_threshold=18,
        store_age_signal="13-15", store_age_signal_source="play_age_signals",
    )
    assert is_child is None
    doc = (await fake_db.collection("users").document(uid).get()).to_dict()
    assert doc["consent"]["store_age_signal"] == "13-15"  # still captured raw
    assert doc["consent"]["is_child"] is None  # but not acted on
    assert "restricted_features" not in doc


async def test_upsert_user_br_signal_reconciles_on_repeat_login_too(fake_db):
    # First login: no signal yet (matches today's client not sending it).
    await auth_service.upsert_user(
        fake_db, "br-later-signal", "p@example.com", "Player", None, "google",
        country_code="BR", consent_age_threshold=18,
    )
    # Second login: client updated, now sends the signal.
    uid, is_new, is_child, _ = await auth_service.upsert_user(
        fake_db, "br-later-signal", "p@example.com", "Player", None, "google",
        country_code="BR", consent_age_threshold=18,
        store_age_signal="13-15", store_age_signal_source="play_age_signals",
    )
    assert is_new is False
    assert is_child is True
    doc = (await fake_db.collection("users").document(uid).get()).to_dict()
    assert doc["consent"]["is_child"] is True
    assert doc["restricted_features"]["share_score"] is True


# ---------------------------------------------------------------------------
# T-123: deletion_pending flag from upsert_user
# ---------------------------------------------------------------------------


async def test_upsert_user_new_user_deletion_pending_false(fake_db):
    uid, is_new, is_child, deletion_pending = await auth_service.upsert_user(
        fake_db, "new-user-1", "p@example.com", "Player", None, "google"
    )
    assert deletion_pending is False


async def test_upsert_user_existing_user_with_pending_deletion(fake_db):
    fake_db.seed("users", "deleting-user", {
        "uid": "deleting-user",
        "provider": "google",
        "email": "d@example.com",
        "display_name": "Deleting Player",
        "photo_url": None,
        "delete_requested_at": datetime.now(timezone.utc),
        "consent": {},
    })
    uid, is_new, is_child, deletion_pending = await auth_service.upsert_user(
        fake_db, "deleting-user", "d@example.com", "Deleting Player", None, "google"
    )
    assert is_new is False
    assert deletion_pending is True


async def test_upsert_user_existing_user_without_pending_deletion(fake_db):
    fake_db.seed("users", "normal-user", {
        "uid": "normal-user",
        "provider": "google",
        "email": "n@example.com",
        "display_name": "Normal Player",
        "photo_url": None,
        "delete_requested_at": None,
        "consent": {},
    })
    uid, is_new, is_child, deletion_pending = await auth_service.upsert_user(
        fake_db, "normal-user", "n@example.com", "Normal Player", None, "google"
    )
    assert deletion_pending is False


# ---------------------------------------------------------------------------
# create_session / consume_refresh_session
# ---------------------------------------------------------------------------


async def test_create_session_persists_provider(fake_db):
    await auth_service.create_session(
        fake_db, "uid-1", "session-1", "hash-1", "apple", "ios", "17.0", "1.0.0"
    )
    doc = (await fake_db.collection("sessions").document("session-1").get()).to_dict()
    assert doc["provider"] == "apple"
    assert doc["device"]["platform"] == "ios"


# ---------------------------------------------------------------------------
# T-123: consume_refresh_session blocks pending-deletion accounts
# ---------------------------------------------------------------------------


async def test_consume_refresh_session_rejects_pending_deletion(fake_db):
    fake_db.seed("users", "deleting-user-2", {
        "uid": "deleting-user-2",
        "delete_requested_at": datetime.now(timezone.utc),
    })
    token_hash = jwt_service.hash_refresh_token("secret-abc")
    fake_db.seed("sessions", "session-del", {
        "session_id": "session-del",
        "uid": "deleting-user-2",
        "token_hash": token_hash,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
    })
    with pytest.raises(ValueError, match="AUTH_ACCOUNT_DELETION_PENDING"):
        await auth_service.consume_refresh_session(fake_db, "session-del.secret-abc")

    # Session must survive the rejected attempt — not consumed/deleted.
    assert (await fake_db.collection("sessions").document("session-del").get()).exists


async def test_consume_refresh_session_allows_normal_user(fake_db):
    fake_db.seed("users", "normal-user-2", {"uid": "normal-user-2", "delete_requested_at": None})
    token_hash = jwt_service.hash_refresh_token("secret-xyz")
    fake_db.seed("sessions", "session-ok", {
        "session_id": "session-ok",
        "uid": "normal-user-2",
        "token_hash": token_hash,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
    })
    uid, session = await auth_service.consume_refresh_session(fake_db, "session-ok.secret-xyz")
    assert uid == "normal-user-2"
