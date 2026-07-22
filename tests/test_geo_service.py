"""Tests for app/services/geo_service.py — T-402's store_age_signal_is_minor()
parser and the shared age_gate_update() helper. Previously zero coverage for
this module (consent_age_threshold/resolve_country were only ever exercised
indirectly through the auth router tests)."""

from datetime import datetime, timezone

import pytest

from app.services import geo_service

BR_THRESHOLD = 18  # geo_service.consent_age_threshold("BR")


@pytest.mark.parametrize(
    "signal,expected",
    [
        ("13-15", True),
        ("16-17", True),
        ("18+", False),
        ("18-24", False),
        ("17", True),
        ("18", False),
        (None, None),
        ("", None),
        ("unknown", None),
        ("adult", None),
    ],
)
def test_store_age_signal_is_minor(signal, expected):
    assert geo_service.store_age_signal_is_minor(signal, BR_THRESHOLD) == expected


def test_store_age_signal_is_minor_respects_threshold_not_hardcoded_18():
    # Same band, different threshold — confirms the function is generic,
    # not secretly hardcoded to Brazil's 18.
    assert geo_service.store_age_signal_is_minor("14-16", 13) is False
    assert geo_service.store_age_signal_is_minor("14-16", 15) is True


def test_age_gate_update_child():
    now = datetime.now(timezone.utc)
    update = geo_service.age_gate_update(True, now)
    assert update["consent.is_child"] is True
    assert update["restricted_features"] == {
        "leaderboard": True, "personalized_ads": True, "share_score": True,
    }
    assert "consent.coppa_compliant" not in update


def test_age_gate_update_adult():
    now = datetime.now(timezone.utc)
    update = geo_service.age_gate_update(False, now)
    assert update["consent.is_child"] is False
    assert update["restricted_features"] == {
        "leaderboard": False, "personalized_ads": False, "share_score": False,
    }
    assert update["consent.coppa_compliant"] is True
