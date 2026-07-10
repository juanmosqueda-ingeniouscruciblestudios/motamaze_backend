import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import google.auth
import google.auth.transport.requests

_SCOPES = ["https://www.googleapis.com/auth/androidpublisher"]
_BASE = "https://androidpublisher.googleapis.com/androidpublisher/v3"

_credentials = None


class PlayAPIError(Exception):
    def __init__(self, http_status: int, error_body: dict):
        self.http_status = http_status
        self.error_body = error_body


def _get_token() -> str:
    global _credentials
    if _credentials is None:
        _credentials, _ = google.auth.default(scopes=_SCOPES)
    if not _credentials.valid:
        _credentials.refresh(google.auth.transport.requests.Request())
    return _credentials.token


def _do_get(url: str) -> dict:
    token = _get_token()
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise PlayAPIError(e.code, json.loads(e.read() or b"{}"))


def _do_post(url: str) -> None:
    token = _get_token()
    req = urllib.request.Request(
        url,
        data=b"",
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Length": "0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        raise PlayAPIError(e.code, json.loads(e.read() or b"{}"))


async def get_product_purchase(pkg: str, product_id: str, purchase_token: str) -> dict:
    url = f"{_BASE}/applications/{pkg}/purchases/products/{product_id}/tokens/{purchase_token}"
    return await asyncio.to_thread(_do_get, url)


async def acknowledge_product_purchase(pkg: str, product_id: str, purchase_token: str) -> None:
    url = (
        f"{_BASE}/applications/{pkg}/purchases/products"
        f"/{product_id}/tokens/{purchase_token}:acknowledge"
    )
    await asyncio.to_thread(_do_post, url)


async def consume_product_purchase(pkg: str, product_id: str, purchase_token: str) -> None:
    url = (
        f"{_BASE}/applications/{pkg}/purchases/products"
        f"/{product_id}/tokens/{purchase_token}:consume"
    )
    await asyncio.to_thread(_do_post, url)


def _do_list_voided(url: str) -> list[dict]:
    token = _get_token()
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("voidedPurchases", [])
    except urllib.error.HTTPError as e:
        raise PlayAPIError(e.code, json.loads(e.read() or b"{}"))


async def list_voided_purchases(pkg: str, start: datetime, end: datetime) -> list[dict]:
    """Returns voided purchases between start and end (UTC datetimes)."""
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    params = urllib.parse.urlencode({"startTime": start_ms, "endTime": end_ms, "maxResults": 1000})
    url = f"{_BASE}/applications/{pkg}/purchases/voidedpurchases?{params}"
    return await asyncio.to_thread(_do_list_voided, url)
