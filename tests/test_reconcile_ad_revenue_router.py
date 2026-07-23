"""Integration tests for POST /jobs/reconcile-ad-revenue — T-302."""

from datetime import date, timedelta

from app.services import bq_streaming

URL = "/jobs/reconcile-ad-revenue"
JOB_HEADERS = {"X-CloudScheduler-JobName": "reconcile-ad-revenue"}


async def test_reconcile_ad_revenue_requires_scheduler_header(client):
    resp = await client.post(URL)
    assert resp.status_code == 403
    assert resp.json()["detail"]["error_code"] == "JOBS_FORBIDDEN"


async def test_reconcile_ad_revenue_returns_summary_and_flags(client, monkeypatch):
    async def _fake_run_select(query, params):
        if "admob_daily_report" in query:
            return [
                {"ad_unit_id": "rewarded-1", "admob_impressions": 100, "admob_earnings_micros": 500000},
                {"ad_unit_id": "interstitial-1", "admob_impressions": 50, "admob_earnings_micros": 200000},
            ]
        return [{"ad_unit_id": "rewarded-1", "our_impressions": 97}]

    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select)

    resp = await client.post(URL, headers=JOB_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ad_units_checked"] == 2
    assert body["flagged"] == 1  # interstitial-1: 0 logged vs 50 reported

    flagged_units = [r["ad_unit_id"] for r in body["results"] if r["flagged"]]
    assert flagged_units == ["interstitial-1"]


async def test_reconcile_ad_revenue_no_data_is_a_noop(client, monkeypatch):
    async def _fake_run_select(query, params):
        return []

    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select)

    resp = await client.post(URL, headers=JOB_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_date"] == (date.today() - timedelta(days=1)).isoformat()
    assert body["ad_units_checked"] == 0
    assert body["flagged"] == 0
    assert body["results"] == []
