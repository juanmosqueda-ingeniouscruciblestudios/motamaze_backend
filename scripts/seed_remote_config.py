#!/usr/bin/env python3
"""
scripts/seed_remote_config.py

Publishes/updates the Firebase Remote Config parameters that
app/services/remote_config_service.py reads (T-244). Idempotent — GETs the
current template (preserving anything else already published), merges in
PARAMETERS below, PUTs it back with the fetched etag.

Values below match the CURRENT hardcoded fallback constants in
app/routers/game.py (REGEN_INTERVAL_SECS=1800, DEFAULT_MAX_LIVES=5) — this
run makes them live-tunable with NO behavior change, not a balance change.
Edit PARAMETERS and re-run to actually change gameplay behavior.

Usage:
    gcloud auth application-default login --project motamaze-dev   # or motamaze for prod
    python scripts/seed_remote_config.py --project motamaze-dev
"""

import argparse
import json
import urllib.error
import urllib.request

import google.auth
import google.auth.transport.requests

_REMOTE_CONFIG_URL = "https://firebaseremoteconfig.googleapis.com/v1/projects/{project_id}/remoteConfig"
_SCOPES = ["https://www.googleapis.com/auth/firebase.remoteconfig"]

# Matches app/routers/game.py's REGEN_INTERVAL_SECS / DEFAULT_MAX_LIVES
# fallback constants exactly — see module docstring.
PARAMETERS = {
    "regen_interval_secs": "1800",
    "default_max_lives": "5",
}


def _authed_request(method: str, url: str, headers: dict, body: bytes | None = None):
    credentials, _ = google.auth.default(scopes=_SCOPES)
    credentials.refresh(google.auth.transport.requests.Request())
    auth_headers = {**headers, "Authorization": f"Bearer {credentials.token}"}
    # User ADC (gcloud auth application-default login) has no project of its
    # own — Google bills/quota-checks it against whatever's in
    # quota_project_id, but that only applies if we send it explicitly; the
    # google.auth.transport wrappers do this via before_request(), raw
    # urllib doesn't. Without it, GCP silently checks quota against the
    # gcloud CLI's OWN project instead and returns a misleading
    # SERVICE_DISABLED 403. Not needed for the deployed Cloud Run service
    # (its service-account credentials are already tied to their own
    # project), only for this kind of local admin script.
    if getattr(credentials, "quota_project_id", None):
        auth_headers["X-Goog-User-Project"] = credentials.quota_project_id
    req = urllib.request.Request(url, data=body, headers=auth_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.headers
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Remote Config API {exc.code} on {method} {url}: {body_text}")


def main(project: str) -> None:
    url = _REMOTE_CONFIG_URL.format(project_id=project)
    template, resp_headers = _authed_request("GET", url, {})
    # No prior template published yet (first-ever publish) -> no ETag comes
    # back at all; "*" means "no version to match, create unconditionally".
    etag = resp_headers.get("ETag") or "*"

    parameters = template.get("parameters") or {}
    for key, value in PARAMETERS.items():
        parameters[key] = {"defaultValue": {"value": value}}
    template["parameters"] = parameters

    body = json.dumps(template).encode("utf-8")
    _authed_request(
        "PUT", url, {"Content-Type": "application/json; UTF8", "If-Match": etag}, body=body
    )

    print(f"Remote Config published in project={project}:")
    for key, value in PARAMETERS.items():
        print(f"  {key} = {value}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, choices=["motamaze-dev", "motamaze"])
    args = parser.parse_args()
    main(args.project)
