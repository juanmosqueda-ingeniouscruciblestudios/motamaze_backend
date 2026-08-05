# INFRA-007 — Cloud Run public access fix + real Cloud Scheduler auth on /jobs/*

| Field | Value |
|---|---|
| **Type** | Bug fix / Security |
| **Priority** | Critical — `X-CloudScheduler-JobName` was spoofable, Cloud Run IAM was the *only* real gate on 7 endpoints including `purge-deleted-accounts` and `recalc-age-thresholds` |
| **Status** | In Progress — ST-01–03 ✅ (this pass). ST-04/05 (flip the Cloud Run invoker flag in DEV/PROD) and ST-06 (docs, in progress) remain |
| **Date** | 2026-08-05 |
| **Depends-on** | None — no external blockers |

---

## Description

Found 2026-07-31: the entire `motamaze-backend` Cloud Run service was inaccessible without an
identity token, because the org policy `constraints/iam.allowedPolicyMemberDomains` blocks `allUsers`
as an IAM member — `--allow-unauthenticated` silently fails. That broke `GET /s/{token}` and
`GET /ogimg/{token}` (T-440's public share-preview endpoints social crawlers hit) in production.

Juan's 2026-08-03 retarget (email, verified against the actual code before acting on it): don't
fight the org policy. `gcloud run services update motamaze-backend --no-invoker-iam-check` removes
the invoker IAM check at the project level (`roles/run.admin`, which Saul already has via
`roles/owner` — confirmed, no new grant needed) — domain-restricted sharing never has to apply. But
flipping that flag makes the service reachable by anyone, and `app/routers/jobs.py`'s only real
check was `if x_cloudscheduler_jobname is None: 403` — any caller could set that header themselves.
Cloud Run IAM was the sole real gate on 7 endpoints, two of which are genuinely dangerous unguarded:
`purge-deleted-accounts` (destroys user data) and `recalc-age-thresholds` (COPPA child flags).

**Acceptance criteria:**
- [x] Confirm `constraints/run.managed.requireInvokerIam` doesn't block the fix (ST-01)
- [x] Audit every router's auth coverage, confirm `jobs.py` is the only real gap (ST-02)
- [x] Replace the spoofable header check with real Cloud Scheduler OIDC verification (ST-03)
- [ ] Run `--no-invoker-iam-check` in `motamaze-dev`, validate (ST-04)
- [ ] Run `--no-invoker-iam-check` in `motamaze` (prod), validate (ST-05)

---

## Previous state (before this change)

```python
@router.post("/admob-daily-report")
async def run_admob_daily_report(
    background_tasks: BackgroundTasks,
    x_cloudscheduler_jobname: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
):
    # Cloud Run IAM is the primary auth layer; this header is belt-and-suspenders.
    if x_cloudscheduler_jobname is None:
        raise HTTPException(403, detail={"error_code": "JOBS_FORBIDDEN"})
```

Repeated identically across all 7 `/jobs/*` endpoints. The header is never validated against
anything — any HTTP client sending `X-CloudScheduler-JobName: anything` passes.

---

## Implementation details

### ST-01 — Confirm the org policy doesn't block the fix

`gcloud org-policies describe constraints/run.managed.requireInvokerIam --project=motamaze
--effective` → `enforce: false`. Not enforced at project or org level. The Organization Policy API
itself was disabled on the project (`orgpolicy.googleapis.com`) — enabled it (read-only in intent,
low-risk, reversible) to run this check. Confirms the `--no-invoker-iam-check` step (ST-04/05) needs
zero Juan/org-admin involvement.

### ST-02 — Full router audit

| Router | Guarded | Detail |
|---|---|---|
| `game.py` | 9/9 | All `Depends(verify_jwt)` |
| `leaderboard.py` | 2/2 | All `Depends(verify_jwt)` (+ App Check on the write) |
| `auth.py` | 6/9 | 3 intentionally public: `login`, `refresh`, `parental-consent/verify` |
| `social.py` | 1/3 | `share/create` guarded; `/s/{token}`, `/ogimg/{token}` intentionally public (T-440, social crawlers) |
| `payments.py` | 2/4 | `android/verify`/`ios/verify` guarded via `verify_jwt`; the 2 refund-notification webhooks use their own OIDC/JWS verification (`_verify_pubsub_oidc`, Apple JWS chain) — real auth, just not `verify_jwt` |
| `well_known.py`, `health.py` | 0/3 | Intentionally public (JWKS, health checks) |
| **`jobs.py`** | **0/7 real** | Only checks header presence — the confirmed gap |

### ST-03 — Real Cloud Scheduler OIDC verification

`app/routers/jobs.py`, new `verify_cloud_scheduler_oidc` FastAPI dependency, applied to all 7
`/jobs/*` routes via `dependencies=[Depends(verify_cloud_scheduler_oidc)]` (same shape as
`leaderboard.py`'s `verify_app_check`). Uses `google.oauth2.id_token.verify_oauth2_token` — the same
library/pattern `auth_service.verify_google_token` already uses for Google Sign-In — which fetches
Google's public certs and validates signature, expiry, and `aud` in one call:

```python
def _verify_scheduler_oidc_sync(token: str, audience: str) -> dict:
    return google_id_token.verify_oauth2_token(token, google_requests.Request(), audience=audience)
```

Two checks, both required (matching Juan's spec — signature/audience alone isn't enough, since any
authenticated Google identity could otherwise pass):
1. **Audience** — `settings.cloud_run_service_url`, a new setting. Verified via `gcloud scheduler
   jobs list --format="table(httpTarget.oidcToken.audience)"` that every existing `/jobs/*` Cloud
   Scheduler job (5 in dev, 6 in prod) already uses the exact same audience per environment before
   hardcoding it — hardening this without checking first would have broken every real job silently.
2. **Service account identity** — `claims["email"] == f"game-api-backend@{settings.gcp_project_id}
   .iam.gserviceaccount.com"` and `email_verified`. Also confirmed identical across every existing
   scheduler job. Derived from the already-existing `settings.gcp_project_id`, not a new hardcoded
   value — correct per environment automatically.

Both failure modes return the same `403 JOBS_FORBIDDEN` as before (missing header, bad signature,
wrong audience, wrong SA — same error code, no detail leaked about which check failed).

---

## Testing

```bash
python -m pytest -q
```

`tests/test_jobs_scheduler_auth.py` (new) — exercises every branch of `verify_cloud_scheduler_oidc`
directly: missing header, non-Bearer header, verification failure, wrong SA email, unverified email,
valid token accepted, and that the audience is actually forwarded (not silently skipped). The 5
existing `/jobs/*` test files (`test_jobs_router.py`,
`test_recalc_{achievement_rarities,age_thresholds,level_stats}_router.py`,
`test_reconcile_ad_revenue_router.py`) were updated from the old `X-CloudScheduler-JobName` header to
the new `Authorization: Bearer` flow via a shared `scheduler_headers` fixture
(`tests/conftest.py`) that monkeypatches `jobs._verify_scheduler_oidc` so tests never hit Google's
real cert endpoint.

---

## Results

```
355 passed
```

Full suite, no regressions across any router.

---

## Follow-ups / notes

- **ST-04/ST-05 not done in this pass** — flipping `--no-invoker-iam-check` in dev then prod, each
  followed by a live validation (confirm `/jobs/*` still rejects unauthenticated calls, confirm
  `/s/{token}`/`/ogimg/{token}` now resolve publicly). Deliberately sequenced after ST-03 lands, not
  before — flipping the flag first would have left the service publicly reachable with only the
  spoofable header as protection.
- **`admob-daily-report` and `reconcile-purchases` still have no dedicated test file** — pre-existing
  gap noted in `test_jobs_router.py`'s own docstring, unrelated to this ticket, not fixed here.
- **`gcloud org-policies` (V2 API) required enabling `orgpolicy.googleapis.com`** on the project —
  it was never used before. Left enabled; no cost, standard GCP API.
