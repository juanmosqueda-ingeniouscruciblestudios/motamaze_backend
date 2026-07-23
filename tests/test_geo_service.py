"""Tests for app/services/geo_service.py — T-402's store_age_signal_is_minor()
parser and the shared age_gate_update() helper. Previously zero coverage for
this module (consent_age_threshold/resolve_country were only ever exercised
indirectly through the auth router tests)."""

from datetime import date, datetime, timezone

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


# ---------------------------------------------------------------------------
# T-404: has_aged_out — conservative month-precision threshold crossing
# ---------------------------------------------------------------------------


def test_has_aged_out_true_on_first_day_of_month_after_birth_month():
    # Born June 2013, threshold 13 -> turns 13 sometime in June 2026;
    # conservatively "aged out" starts July 1, 2026, not before.
    assert geo_service.has_aged_out(6, 2013, 13, date(2026, 7, 1)) is True


def test_has_aged_out_false_one_day_before_boundary():
    assert geo_service.has_aged_out(6, 2013, 13, date(2026, 6, 30)) is False


def test_has_aged_out_false_still_within_birth_month():
    # Even on their actual (unknown) birthday, we don't flip them yet —
    # protected through the whole month by design.
    assert geo_service.has_aged_out(6, 2013, 13, date(2026, 6, 15)) is False


def test_has_aged_out_false_well_before_threshold_year():
    assert geo_service.has_aged_out(6, 2013, 13, date(2020, 1, 1)) is False


def test_has_aged_out_true_well_after_threshold_year():
    assert geo_service.has_aged_out(6, 2013, 13, date(2030, 1, 1)) is True


def test_has_aged_out_december_birth_month_rolls_into_next_year():
    # Born December 2012, threshold 13 -> turns 13 in December 2025;
    # aged out starts January 1, 2026, not December 2025.
    assert geo_service.has_aged_out(12, 2012, 13, date(2025, 12, 31)) is False
    assert geo_service.has_aged_out(12, 2012, 13, date(2026, 1, 1)) is True


def test_has_aged_out_respects_country_threshold_not_hardcoded():
    # Same birth date, BR threshold (18) crosses much later than US (13).
    assert geo_service.has_aged_out(3, 2013, 13, date(2026, 4, 1)) is True   # US-like
    assert geo_service.has_aged_out(3, 2013, 18, date(2026, 4, 1)) is False  # BR-like
