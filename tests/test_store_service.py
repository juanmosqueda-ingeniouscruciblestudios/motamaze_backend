"""Unit tests for app/services/store_service.py — T-240 audience segmentation.
resolve_user_segment() is pure — no Firestore I/O, caller supplies already-
read values."""

from datetime import datetime, timedelta, timezone

from app.services.store_service import resolve_user_segment

NOW = datetime(2026, 7, 24, tzinfo=timezone.utc)


def test_non_payer_takes_priority_over_everything():
    # New AND never paid AND no recent session -> non_payer wins, not new.
    created_at = NOW - timedelta(days=1)
    last_session = NOW - timedelta(days=20)
    assert resolve_user_segment(created_at, last_session, False, NOW) == "non_payer"


def test_lapsed_when_last_session_past_window():
    created_at = NOW - timedelta(days=100)
    last_session = NOW - timedelta(days=14)  # exactly at the boundary
    assert resolve_user_segment(created_at, last_session, True, NOW) == "lapsed"


def test_not_lapsed_one_day_before_window():
    created_at = NOW - timedelta(days=100)
    last_session = NOW - timedelta(days=13)
    assert resolve_user_segment(created_at, last_session, True, NOW) == "all"


def test_missing_last_session_is_not_treated_as_lapsed():
    # No session on record at all -- absence of data isn't evidence of
    # lapsing, must not be mislabeled as lapsed.
    created_at = NOW - timedelta(days=100)
    assert resolve_user_segment(created_at, None, True, NOW) == "all"


def test_new_user_within_window():
    created_at = NOW - timedelta(days=3)  # exactly at the boundary
    last_session = NOW  # active just now, not lapsed
    assert resolve_user_segment(created_at, last_session, True, NOW) == "new"


def test_not_new_one_day_after_window():
    created_at = NOW - timedelta(days=4)
    last_session = NOW
    assert resolve_user_segment(created_at, last_session, True, NOW) == "all"


def test_lapsed_takes_priority_over_new():
    # Both conditions technically true is contradictory in practice (a
    # 1-day-old account can't have a 14-day-old last session), but the
    # priority order must still hold if it ever happens.
    created_at = NOW - timedelta(days=1)
    last_session = NOW - timedelta(days=15)
    assert resolve_user_segment(created_at, last_session, True, NOW) == "lapsed"


def test_all_fallback_for_established_active_payer():
    created_at = NOW - timedelta(days=200)
    last_session = NOW - timedelta(hours=1)
    assert resolve_user_segment(created_at, last_session, True, NOW) == "all"
