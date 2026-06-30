"""
INFRA-005 ST-03 — Firestore security rules smoke tests.

Strategy: Firebase Rules REST API (projects.test endpoint).
No emulator, no firebase-tools, no Firebase client SDK required.

The Firebase Rules API accepts a rules source + simulated requests and
returns whether each request would be ALLOWED or DENIED. We embed the
firestore.rules content inline so the tests are self-contained and also
validate the deployed ruleset independently.

Requirements:
  - Active gcloud session (gcloud auth login) OR GCLOUD_TOKEN env var
  - firebaserules.googleapis.com enabled on project (done in INFRA-005 ST-02)

Usage:
  pytest tests/test_firestore_rules.py -v
  # or:
  GCLOUD_TOKEN=$(gcloud auth print-access-token) pytest tests/test_firestore_rules.py -v
"""
import os
import pathlib
import subprocess

import httpx
import pytest

PROJECT = "motamaze"
RULES_API = "https://firebaserules.googleapis.com/v1"
REPO_ROOT = pathlib.Path(__file__).parent.parent
FIRESTORE_RULES = (REPO_ROOT / "firestore.rules").read_text()

COLLECTIONS = [
    "users",
    "sessions",
    "revoked_jtis",
    "progress",
    "lives",
    "entitlements",
    "season_progress",
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _get_token() -> str:
    if tok := os.getenv("GCLOUD_TOKEN"):
        return tok
    result = subprocess.run(
        "gcloud auth print-access-token",
        capture_output=True, text=True, check=True, shell=True,
    )
    return result.stdout.strip()


@pytest.fixture(scope="module")
def token():
    try:
        return _get_token()
    except Exception as e:
        pytest.skip(f"No gcloud token available: {e}")


@pytest.fixture(scope="module")
def api(token):
    with httpx.Client(
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-goog-user-project": PROJECT,
        },
        timeout=30,
    ) as client:
        yield client


def _run_rule_tests(api: httpx.Client, test_cases: list[dict]) -> list[dict]:
    """Call Firebase Rules projects.test endpoint with inline source."""
    resp = api.post(
        f"{RULES_API}/projects/{PROJECT}:test",
        json={
            "source": {"files": [{"name": "firestore.rules", "content": FIRESTORE_RULES}]},
            "testSuite": {"testCases": test_cases},
        },
    )
    resp.raise_for_status()
    return resp.json().get("testResults", [])


# ---------------------------------------------------------------------------
# Test: deny-all — authenticated Firebase user
# ---------------------------------------------------------------------------

class TestAuthenticatedUserDenied:
    """Authenticated Firebase users must be denied reads and writes on all collections."""

    def test_read_denied(self, api):
        cases = [
            {
                "expectation": "DENY",
                "request": {
                    "auth": {"uid": "test-uid-001", "token": {}},
                    "path": f"/databases/(default)/documents/{col}/test-doc",
                    "method": "get",
                },
            }
            for col in COLLECTIONS
        ]
        results = _run_rule_tests(api, cases)
        assert len(results) == len(COLLECTIONS)
        for col, result in zip(COLLECTIONS, results):
            assert result["state"] == "SUCCESS", (
                f"READ on '{col}': expected DENY but Firebase Rules returned {result['state']}. "
                f"Full result: {result}"
            )

    def test_write_create_denied(self, api):
        cases = [
            {
                "expectation": "DENY",
                "request": {
                    "auth": {"uid": "test-uid-001", "token": {}},
                    "path": f"/databases/(default)/documents/{col}/test-doc",
                    "method": "create",
                    "resource": {"data": {"uid": "test-uid-001"}},
                },
            }
            for col in COLLECTIONS
        ]
        results = _run_rule_tests(api, cases)
        assert len(results) == len(COLLECTIONS)
        for col, result in zip(COLLECTIONS, results):
            assert result["state"] == "SUCCESS", (
                f"WRITE on '{col}': expected DENY but Firebase Rules returned {result['state']}. "
                f"Full result: {result}"
            )

    def test_write_update_denied(self, api):
        cases = [
            {
                "expectation": "DENY",
                "request": {
                    "auth": {"uid": "test-uid-001", "token": {}},
                    "path": f"/databases/(default)/documents/{col}/test-doc",
                    "method": "update",
                    "resource": {"data": {"uid": "test-uid-001"}},
                },
            }
            for col in COLLECTIONS
        ]
        results = _run_rule_tests(api, cases)
        for col, result in zip(COLLECTIONS, results):
            assert result["state"] == "SUCCESS", (
                f"UPDATE on '{col}': expected DENY, got {result['state']}"
            )

    def test_delete_denied(self, api):
        cases = [
            {
                "expectation": "DENY",
                "request": {
                    "auth": {"uid": "test-uid-001", "token": {}},
                    "path": f"/databases/(default)/documents/{col}/test-doc",
                    "method": "delete",
                },
            }
            for col in COLLECTIONS
        ]
        results = _run_rule_tests(api, cases)
        for col, result in zip(COLLECTIONS, results):
            assert result["state"] == "SUCCESS", (
                f"DELETE on '{col}': expected DENY, got {result['state']}"
            )


# ---------------------------------------------------------------------------
# Test: deny-all — unauthenticated (no auth context)
# ---------------------------------------------------------------------------

class TestUnauthenticatedDenied:
    """Requests with no auth context must also be denied."""

    def test_unauthenticated_read_denied(self, api):
        cases = [
            {
                "expectation": "DENY",
                "request": {
                    "path": f"/databases/(default)/documents/{col}/test-doc",
                    "method": "get",
                },
            }
            for col in COLLECTIONS
        ]
        results = _run_rule_tests(api, cases)
        for col, result in zip(COLLECTIONS, results):
            assert result["state"] == "SUCCESS", (
                f"Unauthenticated READ on '{col}': expected DENY, got {result['state']}"
            )

    def test_unauthenticated_write_denied(self, api):
        cases = [
            {
                "expectation": "DENY",
                "request": {
                    "path": f"/databases/(default)/documents/{col}/test-doc",
                    "method": "create",
                    "resource": {"data": {"attack": "injection"}},
                },
            }
            for col in COLLECTIONS
        ]
        results = _run_rule_tests(api, cases)
        for col, result in zip(COLLECTIONS, results):
            assert result["state"] == "SUCCESS", (
                f"Unauthenticated WRITE on '{col}': expected DENY, got {result['state']}"
            )


# ---------------------------------------------------------------------------
# Test: verify deployed ruleset content (prod)
# ---------------------------------------------------------------------------

class TestDeployedRuleset:
    """Verify the deployed ruleset in production matches expected deny-all policy."""

    def test_deployed_rules_are_deny_all(self, api):
        release_resp = api.get(f"{RULES_API}/projects/{PROJECT}/releases/cloud.firestore")
        release_resp.raise_for_status()
        ruleset_name = release_resp.json()["rulesetName"]

        ruleset_resp = api.get(f"{RULES_API}/{ruleset_name}")
        ruleset_resp.raise_for_status()

        files = ruleset_resp.json()["source"]["files"]
        content = "\n".join(f["content"] for f in files)
        assert "allow read, write: if false" in content, (
            "Deployed rules do not contain deny-all policy ('allow read, write: if false' not found)"
        )

    def test_deployed_rules_have_no_permissive_clauses(self, api):
        release_resp = api.get(f"{RULES_API}/projects/{PROJECT}/releases/cloud.firestore")
        release_resp.raise_for_status()
        ruleset_name = release_resp.json()["rulesetName"]

        ruleset_resp = api.get(f"{RULES_API}/{ruleset_name}")
        ruleset_resp.raise_for_status()

        files = ruleset_resp.json()["source"]["files"]
        content = "\n".join(f["content"] for f in files)

        non_comment_lines = [
            line for line in content.splitlines()
            if not line.strip().startswith("//")
        ]
        permissive = [
            line for line in non_comment_lines
            if "allow" in line and "if false" not in line
        ]
        assert permissive == [], (
            f"Found unexpected permissive allow clauses in deployed rules: {permissive}"
        )
