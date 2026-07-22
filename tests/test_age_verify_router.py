"""Tests for POST /auth/age-verify — committed evidence for T-406 ST-02
(coppa_compliant auto-activation) and T-401 ST-01. Mirrors the 20 scenarios
manually verified and recorded in changelogs/T-406-iarc-content-rating.md
(2026-07-16) — that run was never checked into the test suite; this is.
"""

from datetime import date, timedelta

import pytest

from app.services import jwt_service

URL = "/auth/age-verify"


def _dob_for_age(n: int) -> str:
    """DOB string that makes the endpoint's age formula compute exactly `n`,
    regardless of what day the suite actually runs on."""
    today = date.today()
    return today.replace(year=today.year - n).isoformat()


def _auth_headers(test_settings, uid: str) -> dict:
    token, _ = jwt_service.create_access_token(
        user_id=uid,
        provider="google",
        session_id=f"session-{uid}",
        project_id=test_settings.gcp_project_id,
        secret_name=test_settings.jwt_secret_name,
        key_id=test_settings.jwt_key_id,
        issuer=test_settings.jwt_issuer,
    )
    return {"Authorization": f"Bearer {token}"}


def _seed_user(fake_db, uid: str, consent_age_threshold: int):
    fake_db.seed("users", uid, {
        "uid": uid,
        "consent": {"consent_age_threshold": consent_age_threshold},
    })


# ---------------------------------------------------------------------------
# Adults — auto-compliant (US/MX/AR thresholds, per T-400/T-407)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,age,threshold",
    [
        ("adult_us", 26, 13),
        ("adult_mx", 18, 18),   # exact threshold, boundary — still adult
        ("adult_ar", 16, 16),   # exact threshold, boundary — still adult
        ("boundary_13_threshold_13", 13, 13),  # age NOT < threshold -> adult
    ],
)
async def test_age_verify_adult_auto_compliant(client, fake_db, test_settings, label, age, threshold):
    uid = f"user-{label}"
    _seed_user(fake_db, uid, threshold)

    resp = await client.post(
        URL, json={"dob": _dob_for_age(age)}, headers=_auth_headers(test_settings, uid)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_child"] is False

    doc = (await fake_db.collection("users").document(uid).get()).to_dict()
    assert doc["consent"]["is_child"] is False
    assert doc["consent"]["coppa_compliant"] is True
    assert doc["restricted_features"] == {
        "leaderboard": False, "personalized_ads": False, "share_score": False,
    }


# ---------------------------------------------------------------------------
# Children — coppa_compliant NOT set (gated on T-401 ST-03 VPC email flow)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,age,threshold",
    [
        ("child_us", 10, 13),
        ("child_ar", 14, 16),
        ("child_pe_exact", 13, 14),  # age < threshold by exactly 1 -> child
    ],
)
async def test_age_verify_child_not_auto_compliant(client, fake_db, test_settings, label, age, threshold):
    uid = f"user-{label}"
    _seed_user(fake_db, uid, threshold)

    resp = await client.post(
        URL, json={"dob": _dob_for_age(age)}, headers=_auth_headers(test_settings, uid)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_child"] is True

    doc = (await fake_db.collection("users").document(uid).get()).to_dict()
    assert doc["consent"]["is_child"] is True
    assert "coppa_compliant" not in doc["consent"]
    assert doc["restricted_features"] == {
        "leaderboard": True, "personalized_ads": True, "share_score": True,
    }


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


async def test_age_verify_invalid_dob_format(client, fake_db, test_settings):
    uid = "user-bad-dob"
    _seed_user(fake_db, uid, 13)
    resp = await client.post(URL, json={"dob": "not-a-date"}, headers=_auth_headers(test_settings, uid))
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "AGE_VERIFY_INVALID_DOB"


async def test_age_verify_future_dob_rejected(client, fake_db, test_settings):
    uid = "user-future-dob"
    _seed_user(fake_db, uid, 13)
    future = (date.today() + timedelta(days=1)).isoformat()
    resp = await client.post(URL, json={"dob": future}, headers=_auth_headers(test_settings, uid))
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "AGE_VERIFY_INVALID_DOB"


async def test_age_verify_implausible_age_rejected(client, fake_db, test_settings):
    uid = "user-implausible-dob"
    _seed_user(fake_db, uid, 13)
    resp = await client.post(
        URL, json={"dob": _dob_for_age(121)}, headers=_auth_headers(test_settings, uid)
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "AGE_VERIFY_INVALID_DOB"


async def test_age_verify_user_not_found(client, test_settings):
    resp = await client.post(
        URL, json={"dob": _dob_for_age(30)}, headers=_auth_headers(test_settings, "user-does-not-exist")
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error_code"] == "USER_NOT_FOUND"


# ---------------------------------------------------------------------------
# T-402: Brazil store_age_signal outranks DOB (subtask 5)
# ---------------------------------------------------------------------------


async def test_age_verify_br_signal_already_minor_dob_cannot_override(client, fake_db, test_settings):
    # Simulates: login already reconciled is_child=True from store_age_signal
    # (as upsert_user now does). An adult-claiming DOB must NOT flip it.
    uid = "user-br-signal-minor"
    fake_db.seed("users", uid, {
        "uid": uid,
        "consent": {
            "consent_age_threshold": 18,
            "country_code": "BR",
            "store_age_signal": "13-15",
            "is_child": True,
        },
        "restricted_features": {"leaderboard": True, "personalized_ads": True, "share_score": True},
    })

    resp = await client.post(
        URL, json={"dob": _dob_for_age(30)}, headers=_auth_headers(test_settings, uid)
    )
    assert resp.status_code == 200
    assert resp.json()["is_child"] is True  # signal wins, not the adult DOB

    doc = (await fake_db.collection("users").document(uid).get()).to_dict()
    assert doc["consent"]["is_child"] is True
    assert doc["consent"].get("coppa_compliant") is not True  # never flipped by DOB
    assert doc["consent"]["age_verified_at"] is not None  # still recorded


async def test_age_verify_br_without_signal_dob_flow_unchanged(client, fake_db, test_settings):
    # BR user, but no store_age_signal yet (pre-T-402 client) — Rama 1
    # (DOB-only) behavior must be identical to every other country.
    uid = "user-br-no-signal"
    fake_db.seed("users", uid, {
        "uid": uid,
        "consent": {"consent_age_threshold": 18, "country_code": "BR"},
    })

    resp = await client.post(
        URL, json={"dob": _dob_for_age(30)}, headers=_auth_headers(test_settings, uid)
    )
    assert resp.status_code == 200
    assert resp.json()["is_child"] is False

    doc = (await fake_db.collection("users").document(uid).get()).to_dict()
    assert doc["consent"]["coppa_compliant"] is True
