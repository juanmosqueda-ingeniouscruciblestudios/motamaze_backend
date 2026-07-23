"""Unit tests for app/services/ad_revenue_reconciliation_service.py — T-302.
Compares our own ad_impressions counts against AdMob's Reporting API
(admob_daily_report) per ad_unit and flags discrepancies."""

from datetime import date

from app.services import ad_revenue_reconciliation_service, bq_streaming

REPORT_DATE = date(2026, 8, 24)


def _fake_run_select(admob_rows, our_rows):
    calls = {"n": 0}

    async def _run_select(query, params):
        calls["n"] += 1
        if "admob_daily_report" in query:
            return admob_rows
        return our_rows

    return _run_select


async def test_reconcile_matches_within_threshold_not_flagged(monkeypatch):
    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select(
        admob_rows=[{"ad_unit_id": "rewarded-1", "admob_impressions": 100, "admob_earnings_micros": 500000}],
        our_rows=[{"ad_unit_id": "rewarded-1", "our_impressions": 95}],
    ))

    results = await ad_revenue_reconciliation_service.reconcile_ad_revenue(
        "motamaze-dev", "motamaze_analytics", REPORT_DATE
    )
    assert len(results) == 1
    row = results[0]
    assert row["admob_impressions"] == 100
    assert row["our_impressions"] == 95
    assert row["discrepancy_percent"] == 5.0
    assert row["flagged"] is False


async def test_reconcile_flags_large_discrepancy(monkeypatch):
    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select(
        admob_rows=[{"ad_unit_id": "interstitial-1", "admob_impressions": 200, "admob_earnings_micros": 800000}],
        our_rows=[],  # nothing logged for this ad_unit — the documented client gap
    ))

    results = await ad_revenue_reconciliation_service.reconcile_ad_revenue(
        "motamaze-dev", "motamaze_analytics", REPORT_DATE
    )
    row = results[0]
    assert row["our_impressions"] == 0
    assert row["discrepancy_percent"] == 100.0
    assert row["flagged"] is True


async def test_reconcile_zero_admob_impressions_not_compared(monkeypatch):
    # AdMob reported nothing for this ad_unit that day — nothing to compare,
    # not a 0% or 100% discrepancy (either would be misleading).
    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select(
        admob_rows=[{"ad_unit_id": "banner-1", "admob_impressions": 0, "admob_earnings_micros": 0}],
        our_rows=[],
    ))

    results = await ad_revenue_reconciliation_service.reconcile_ad_revenue(
        "motamaze-dev", "motamaze_analytics", REPORT_DATE
    )
    row = results[0]
    assert row["discrepancy_percent"] is None
    assert row["flagged"] is False


async def test_reconcile_multiple_ad_units_independent(monkeypatch):
    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select(
        admob_rows=[
            {"ad_unit_id": "rewarded-1", "admob_impressions": 100, "admob_earnings_micros": 500000},
            {"ad_unit_id": "interstitial-1", "admob_impressions": 300, "admob_earnings_micros": 900000},
        ],
        our_rows=[
            {"ad_unit_id": "rewarded-1", "our_impressions": 98},
        ],
    ))

    results = await ad_revenue_reconciliation_service.reconcile_ad_revenue(
        "motamaze-dev", "motamaze_analytics", REPORT_DATE
    )
    assert len(results) == 2
    by_unit = {r["ad_unit_id"]: r for r in results}
    assert by_unit["rewarded-1"]["flagged"] is False
    assert by_unit["interstitial-1"]["flagged"] is True  # 0 logged vs 300 reported


async def test_reconcile_no_admob_data_returns_empty(monkeypatch):
    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select(admob_rows=[], our_rows=[]))

    results = await ad_revenue_reconciliation_service.reconcile_ad_revenue(
        "motamaze-dev", "motamaze_analytics", REPORT_DATE
    )
    assert results == []
