# INFRA-007 — Cloud Run public access fix + real Cloud Scheduler auth on /jobs/*

| Field | Value |
|---|---|
| **Type** | Bug fix / Security |
| **Priority** | Critical — `X-CloudScheduler-JobName` was spoofable, Cloud Run IAM was the *only* real gate on 7 endpoints including `purge-deleted-accounts` and `recalc-age-thresholds` |
| **Status** | Done — ST-01–05 ✅. ST-06 (this doc) closes it out |
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
- [x] Run `--no-invoker-iam-check` in `motamaze-dev`, validate (ST-04)
- [x] Run `--no-invoker-iam-check` in `motamaze` (prod), validate (ST-05)

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

### ST-04 — `--no-invoker-iam-check` in DEV, validated

`gcloud run services update motamaze-backend --no-invoker-iam-check --project=motamaze-dev
--region=us-central1`. Four things checked live afterward:

1. `POST /jobs/recalc-level-stats` with no `Authorization` header, and with a garbage `Bearer` value
   — both `403 {"error_code":"JOBS_FORBIDDEN"}` from our own app (not Cloud Run's generic HTML 403
   page), confirming the request now reaches the app and our own check is what's rejecting it.
2. A real Cloud Scheduler force-run (`gcloud scheduler jobs run recalc-level-stats`) — **first
   attempt failed** (403, no exception detail logged — the original code silently swallowed it).
   Added exception/mismatch logging (commit `243b00c`) rather than guess. After that deployed, 3/3
   consecutive force-runs succeeded (200). No code path changed behavior between the two commits —
   almost certainly a cold-start hiccup fetching Google's certs on the instance that came up right
   after the Cloud Run service update, not a logic bug. Kept the logging permanently; silently
   swallowing the exception would have made this undiagnosable if it ever happens for real.
3. `GET /ogimg/healthcheck` (nonexistent token, falls back to the Cloudinary base image per T-440) —
   `302 → 200`, 0→1 redirect. Previously always 403 regardless of token validity. **This also
   unblocks T-CLO-4** (health monitor uptime check), paused since 2026-07-31 for this exact reason.
4. `GET /s/tokenquenoexiste` — `404 SHARE_TOKEN_NOT_FOUND` (our own app logic), not Cloud Run's 403.
   Confirms the share-preview endpoint genuinely resolves for unauthenticated callers now — the
   actual root problem this ticket exists to fix.

### ST-05 — `--no-invoker-iam-check` in PROD, validated (found and fixed a real bug)

`gcloud run services update motamaze-backend --no-invoker-iam-check --project=motamaze
--region=us-central1`. Same four checks as ST-04, plus one that ST-04's cold-start theory turned out
to be masking:

1. No-auth / garbage-`Bearer` on `/jobs/recalc-level-stats` — `403 JOBS_FORBIDDEN` from the app, as
   expected.
2. Real Cloud Scheduler force-run — **failed deterministically**, not intermittently like ST-04's
   first attempt. `recalc-level-stats` itself is `PAUSED` in prod (along with `purge-deleted-accounts`,
   `reconcile-ad-revenue`, `recalc-age-thresholds`, `recalc-achievement-rarities` — 5 of 8 jobs;
   separate, pre-existing finding, out of scope for this ticket), so `admob-daily-report` (`ENABLED`,
   idempotent — deterministic BQ row IDs, no user-data writes) was force-run instead. The app log
   (added in ST-04's `243b00c` logging) showed the real cause immediately:
   `Token has wrong audience https://motamaze-backend-ghubi2atbq-uc.a.run.app, expected one of
   ['https://motamaze-backend-qxc5bjtn4q-uc.a.run.app']` — the prod revision was checking against
   **dev's** Cloud Run URL.
   Root cause: `settings.cloud_run_service_url` (`app/config.py`) defaults to the dev URL, and
   `.github/workflows/cicd.yml`'s `env_vars` for both the `deploy-dev` and `deploy-prod` jobs (ST-03)
   never actually set `CLOUD_RUN_SERVICE_URL` — only `GCP_PROJECT_ID`/`ENVIRONMENT`. Dev passed ST-04
   purely by coincidence, because the hardcoded default happens to equal dev's real URL; prod has no
   such coincidence. This means ST-04's "cold-start" theory for the first failed force-run in dev is
   now suspect too, but unlike prod's failure it wasn't reproducible/deterministic and the audience
   check there was never actually wrong — left as-is, noted below.
   Fix, in two parts: (a) hot-patched prod immediately via
   `gcloud run services update motamaze-backend --project=motamaze --region=us-central1
   --update-env-vars="CLOUD_RUN_SERVICE_URL=https://motamaze-backend-ghubi2atbq-uc.a.run.app"` to
   validate ST-05 same-day; (b) added `CLOUD_RUN_SERVICE_URL` explicitly to both `env_vars` blocks in
   `cicd.yml` (dev and prod, each with its own URL) so the next CI/CD deploy doesn't silently drop the
   hot patch and regress prod back to the wrong audience. After the hot patch: 3/3 consecutive
   force-runs of `admob-daily-report` returned `200`.
3. `GET /ogimg/healthcheck` — `302 → 200` (was `403`). Same as dev; **T-CLO-4 is now unblocked in
   prod too**.
4. `GET /s/tokenquenoexiste` — `404 SHARE_TOKEN_NOT_FOUND` (was `403`). Confirms the actual root
   problem (broken public share previews) is fixed in prod, not just dev.

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

**DEV live validation (ST-04):**
```
POST /jobs/recalc-level-stats, no auth        -> 403 JOBS_FORBIDDEN (app-level)
POST /jobs/recalc-level-stats, garbage Bearer -> 403 JOBS_FORBIDDEN (app-level)
Cloud Scheduler force-run (real OIDC token)   -> 200 (3/3 after the logging fix deployed)
GET /ogimg/healthcheck                        -> 302 -> 200 (was 403)
GET /s/tokenquenoexiste                       -> 404 SHARE_TOKEN_NOT_FOUND (was 403)
GET /health                                   -> 200 (unchanged, already public)
```

**PROD live validation (ST-05):**
```
POST /jobs/recalc-level-stats, no auth        -> 403 JOBS_FORBIDDEN (app-level)
Cloud Scheduler force-run (admob-daily-report) -> 200 (3/3, after CLOUD_RUN_SERVICE_URL fix)
GET /ogimg/healthcheck                        -> 302 -> 200 (was 403)
GET /s/tokenquenoexiste                       -> 404 SHARE_TOKEN_NOT_FOUND (was 403)
GET /health                                   -> 200 (unchanged, already public)
```

---

## Follow-ups / notes

- **T-CLO-4 (OG image health monitor) is unblocked in both dev and prod** — it was paused 2026-07-31
  because the canary URL always 403'd regardless of the feature's actual correctness. Now false in
  both environments; ready to resume.
- **5 of 8 `/jobs/*` Cloud Scheduler jobs are `PAUSED` in prod**
  (`purge-deleted-accounts`, `reconcile-ad-revenue`, `recalc-age-thresholds`,
  `recalc-achievement-rarities`, `recalc-level-stats` — only `admob-daily-report`,
  `reconcile-purchases`, and the unrelated `maxmind-geolite2-weekly` are `ENABLED`). Found while
  picking a job to force-run for ST-05; not caused by or in scope for this ticket, but worth a
  separate ticket to confirm which of these are intentionally paused vs. an oversight — several
  (`purge-deleted-accounts`, `recalc-age-thresholds`) look like they should be running.
- **`admob-daily-report` and `reconcile-purchases` still have no dedicated test file** — pre-existing
  gap noted in `test_jobs_router.py`'s own docstring, unrelated to this ticket, not fixed here.
- **`gcloud org-policies` (V2 API) required enabling `orgpolicy.googleapis.com`** on the project —
  it was never used before. Left enabled; no cost, standard GCP API.
