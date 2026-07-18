"""Unit tests for app/services/auth_service.py — Apple token verification and
the multi-provider upsert_user()/create_session() changes (AUTH-004)."""

from datetime import timedelta

import pytest

from app.services import auth_service
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
    uid, is_new, is_child = await auth_service.upsert_user(
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
    uid, is_new, _ = await auth_service.upsert_user(
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
    uid, is_new, _ = await auth_service.upsert_user(
        fake_db, "legacy-sub", "old@example.com", "Old User", None, "google"
    )
    assert is_new is False
    doc = (await fake_db.collection("users").document(uid).get()).to_dict()
    assert doc["provider"] == "google"


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
