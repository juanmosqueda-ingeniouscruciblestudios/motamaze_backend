import asyncio
import json
import urllib.error
import urllib.request
from datetime import date

import google.auth.transport.requests
from google.cloud import secretmanager
from google.oauth2.credentials import Credentials

_ADMOB_BASE = "https://admob.googleapis.com/v1"
_TOKEN_URI = "https://oauth2.googleapis.com/token"

_cached_creds: Credentials | None = None


def _read_secret(sm_client: secretmanager.SecretManagerServiceClient, project_id: str, name: str) -> str:
    path = f"projects/{project_id}/secrets/{name}/versions/latest"
    resp = sm_client.access_secret_version(request={"name": path})
    return resp.payload.data.decode("utf-8").strip()


def _load_creds_from_sm(project_id: str) -> Credentials:
    sm = secretmanager.SecretManagerServiceClient()
    return Credentials(
        token=None,
        refresh_token=_read_secret(sm, project_id, "admob-oauth-refresh-token"),
        client_id=_read_secret(sm, project_id, "admob-oauth-client-id"),
        client_secret=_read_secret(sm, project_id, "admob-oauth-client-secret"),
        token_uri=_TOKEN_URI,
    )


def _get_access_token(project_id: str) -> str:
    global _cached_creds
    if _cached_creds is None:
        _cached_creds = _load_creds_from_sm(project_id)
    if not _cached_creds.valid:
        try:
            _cached_creds.refresh(google.auth.transport.requests.Request())
        except Exception:
            # Credentials may have been rotated in Secret Manager — re-read and retry once.
            _cached_creds = _load_creds_from_sm(project_id)
            _cached_creds.refresh(google.auth.transport.requests.Request())
    return _cached_creds.token


def _build_report_spec(publisher_id: str, report_date: date) -> dict:
    d = {"year": report_date.year, "month": report_date.month, "day": report_date.day}
    return {
        "reportSpec": {
            "dateRange": {"startDate": d, "endDate": d},
            "dimensions": ["DATE", "AD_UNIT", "COUNTRY", "FORMAT"],
            "metrics": ["ESTIMATED_EARNINGS", "IMPRESSIONS", "CLICKS", "IMPRESSION_RPM"],
            "localizationSettings": {"currencyCode": "USD"},
        }
    }


def _parse_rows(items: list, report_date: date) -> list[dict]:
    rows = []
    for item in items:
        if "row" not in item:
            continue
        row = item["row"]
        dim = row.get("dimensionValues", {})
        met = row.get("metricValues", {})

        earnings = met.get("ESTIMATED_EARNINGS", {})
        impressions = met.get("IMPRESSIONS", {})
        clicks = met.get("CLICKS", {})
        rpm = met.get("IMPRESSION_RPM", {})

        rows.append({
            "report_date":               report_date.isoformat(),
            "ad_unit_id":                dim.get("AD_UNIT", {}).get("value", ""),
            "ad_format":                 dim.get("FORMAT", {}).get("value", "").lower(),
            "country":                   dim.get("COUNTRY", {}).get("value", ""),
            "estimated_earnings_micros": int(earnings.get("microsValue", 0)),
            "impressions":               int(impressions.get("integerValue", 0)),
            "clicks":                    int(clicks.get("integerValue", 0)),
            "impression_rpm":            float(rpm.get("doubleValue", 0.0)),
        })
    return rows


def _fetch_sync(project_id: str, publisher_id: str, report_date: date) -> list[dict]:
    token = _get_access_token(project_id)
    url = f"{_ADMOB_BASE}/accounts/{publisher_id}/networkReport:generate"
    payload = json.dumps(_build_report_spec(publisher_id, report_date)).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            items = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AdMob API {exc.code}: {body}")
    return _parse_rows(items, report_date)


async def fetch_network_report(project_id: str, publisher_id: str, report_date: date) -> list[dict]:
    return await asyncio.to_thread(_fetch_sync, project_id, publisher_id, report_date)
