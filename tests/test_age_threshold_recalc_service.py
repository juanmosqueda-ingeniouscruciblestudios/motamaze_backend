"""Unit tests for app/services/age_threshold_recalc_service.py — T-404.
Finds DOB-verified users who've crossed their country's age threshold
since verification and flips is_child to False."""

from datetime import datetime, timezone

from app.services import age_threshold_recalc_service

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)  # today = 2026-08-01


async def test_recalc_flips_aged_out_user(fake_db):
    # Born June 2013, threshold 13 -> aged out starting 2026-07-01, well
    # before "today" (2026-08-01).
    fake_db.seed("users", "aged-out-user", {
        "uid": "aged-out-user",
        "consent": {
            "is_child": True,
            "birth_month": 6,
            "birth_year": 2013,
            "consent_age_threshold": 13,
        },
        "restricted_features": {"leaderboard": True, "personalized_ads": True, "share_score": True},
    })

    aged_out = await age_threshold_recalc_service.find_and_recalc_aged_out_users(fake_db, now=NOW)
    assert aged_out == ["aged-out-user"]

    doc = (await fake_db.collection("users").document("aged-out-user").get()).to_dict()
    assert doc["consent"]["is_child"] is False
    assert doc["consent"]["coppa_compliant"] is True
    assert doc["restricted_features"] == {
        "leaderboard": False, "personalized_ads": False, "share_score": False,
    }


async def test_recalc_skips_user_not_yet_aged_out(fake_db):
    # Born June 2014, threshold 13 -> ages out 2027-07-01, still in the future.
    fake_db.seed("users", "still-child-user", {
        "uid": "still-child-user",
        "consent": {
            "is_child": True,
            "birth_month": 6,
            "birth_year": 2014,
            "consent_age_threshold": 13,
        },
    })

    aged_out = await age_threshold_recalc_service.find_and_recalc_aged_out_users(fake_db, now=NOW)
    assert aged_out == []

    doc = (await fake_db.collection("users").document("still-child-user").get()).to_dict()
    assert doc["consent"]["is_child"] is True  # untouched


async def test_recalc_skips_adults(fake_db):
    fake_db.seed("users", "already-adult", {
        "uid": "already-adult",
        "consent": {
            "is_child": False,
            "birth_month": 1,
            "birth_year": 1990,
            "consent_age_threshold": 13,
        },
    })

    aged_out = await age_threshold_recalc_service.find_and_recalc_aged_out_users(fake_db, now=NOW)
    assert aged_out == []


async def test_recalc_skips_br_store_signal_users_without_birth_fields(fake_db):
    # BR user whose is_child came from store_age_signal — no birth_month/
    # year exist (ST-01 never writes them in that branch), so this job
    # can't and shouldn't touch them, with no explicit country_code check.
    fake_db.seed("users", "br-signal-user", {
        "uid": "br-signal-user",
        "consent": {
            "is_child": True,
            "country_code": "BR",
            "consent_age_threshold": 18,
            "store_age_signal": "13-15",
        },
    })

    aged_out = await age_threshold_recalc_service.find_and_recalc_aged_out_users(fake_db, now=NOW)
    assert aged_out == []

    doc = (await fake_db.collection("users").document("br-signal-user").get()).to_dict()
    assert doc["consent"]["is_child"] is True  # untouched


async def test_recalc_is_idempotent_on_second_run(fake_db):
    fake_db.seed("users", "idempotent-user", {
        "uid": "idempotent-user",
        "consent": {
            "is_child": True,
            "birth_month": 6,
            "birth_year": 2013,
            "consent_age_threshold": 13,
        },
    })

    first = await age_threshold_recalc_service.find_and_recalc_aged_out_users(fake_db, now=NOW)
    assert first == ["idempotent-user"]

    second = await age_threshold_recalc_service.find_and_recalc_aged_out_users(fake_db, now=NOW)
    assert second == []  # is_child is already False — filtered out naturally


async def test_recalc_multiple_users_independent(fake_db):
    fake_db.seed("users", "user-a", {
        "uid": "user-a",
        "consent": {"is_child": True, "birth_month": 6, "birth_year": 2013, "consent_age_threshold": 13},
    })
    fake_db.seed("users", "user-b", {
        "uid": "user-b",
        "consent": {"is_child": True, "birth_month": 6, "birth_year": 2015, "consent_age_threshold": 13},
    })

    aged_out = await age_threshold_recalc_service.find_and_recalc_aged_out_users(fake_db, now=NOW)
    assert aged_out == ["user-a"]
