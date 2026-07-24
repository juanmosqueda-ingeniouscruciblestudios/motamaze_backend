import asyncio
import json
import logging
import urllib.error
import urllib.request
from typing import Callable, TypeVar

import google.auth
import google.auth.transport.requests
from cachetools import TTLCache

logger = logging.getLogger(__name__)

_REMOTE_CONFIG_URL = "https://firebaseremoteconfig.googleapis.com/v1/projects/{project_id}/remoteConfig"
_SCOPES = ["https://www.googleapis.com/auth/firebase.remoteconfig"]

# 5 min — same TTL family as jwt_service's key cache. Long enough to avoid
# hammering the Remote Config API on every request (some endpoints read
# these values on every call), short enough that a console change still
# takes effect within a few minutes without a redeploy.
_TEMPLATE_CACHE_TTL = 300
_template_cache: TTLCache = TTLCache(maxsize=2, ttl=_TEMPLATE_CACHE_TTL)

T = TypeVar("T")


def _fetch_template_sync(project_id: str) -> dict:
    # Application Default Credentials — the Cloud Run service account
    # locally, or `gcloud auth application-default login` in dev. No new
    # dependency: google-auth is already used elsewhere (BigQuery,
    # Firestore clients rely on it implicitly); this just requests an
    # explicit token with the Remote Config scope for a raw REST call,
    # same pattern as admob_api.py's OAuth + urllib.request pattern —
    # deliberately not the firebase-admin SDK (a new dependency, would
    # need approval per CLAUDE.md).
    credentials, _ = google.auth.default(scopes=_SCOPES)
    credentials.refresh(google.auth.transport.requests.Request())
    url = _REMOTE_CONFIG_URL.format(project_id=project_id)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {credentials.token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Remote Config API {exc.code}: {body}")


async def _get_template(project_id: str) -> dict | None:
    cached = _template_cache.get(project_id)
    if cached is not None:
        return cached
    try:
        template = await asyncio.to_thread(_fetch_template_sync, project_id)
        _template_cache[project_id] = template
        return template
    except Exception as exc:
        # A Remote Config outage (or missing IAM grant, or no template
        # published yet) must never break gameplay — log and let the
        # caller's fallback take over.
        logger.warning("remote_config: template fetch failed, using fallback defaults: %s", exc)
        return None


async def get_value(project_id: str, key: str, default: T, cast: Callable[[str], T] = str) -> T:
    """Reads one Remote Config parameter's *default* value (not a
    condition-specific override — the server has no per-request device/app
    context to evaluate conditions against, unlike the client SDKs; that's
    a deliberate scope boundary, not an oversight).

    Never raises. Falls back to `default` if: the template fetch failed,
    the key isn't in the published template yet, or the value can't be
    cast to the expected type — a bad/missing Remote Config parameter must
    never break the caller.
    """
    template = await _get_template(project_id)
    if template is None:
        return default

    param = (template.get("parameters") or {}).get(key)
    if not param:
        return default

    raw = (param.get("defaultValue") or {}).get("value")
    if raw is None:
        return default

    try:
        return cast(raw)
    except (ValueError, TypeError):
        logger.warning("remote_config: key=%s value=%r failed cast, using fallback", key, raw)
        return default
