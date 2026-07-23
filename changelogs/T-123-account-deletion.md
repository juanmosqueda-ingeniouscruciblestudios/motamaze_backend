# T-123 — DELETE /auth/account: full erase + BigQuery deletion queue

| Field | Value |
|---|---|
| **Type** | Feature / Compliance |
| **Priority** | Critical — GDPR Art.17 + Apple App Store Review 5.1.1 (store-compliance gate, more urgent now that DEC-L confirmed iOS simultaneous launch) |
| **Status** | ✅ Done — 2026-07-22 |
| **Date** | 2026-07-22 |
| **Engine** | FastAPI backend + Cloud Scheduler (dev only — prod promotion pending) |
| **Depends-on** | T-120 (login), T-300 (BigQuery tables) — both already Done |

---

## Description

`DELETE /auth/account` had a partial implementation since 2026-06-25 (commit `62250da`, shipped as
DATA-002 ST-10): it marked `delete_requested_at` and queued a `pending` row in BigQuery, but nothing
ever purged any data — the DATA-002 changelog explicitly deferred that to a separate ticket
("COMP-001") that was never created as its own Monday item; this ticket is that work. Zero test
coverage existed for the endpoint before this pass either.

**Acceptance criteria (final, after two decisions made with the user on 2026-07-22 — see Previous
state below for what changed from the initial plan):**
- 30-day grace period, cancelable — not immediate Firestore erasure.
- `purchases`/BigQuery `purchase_events` anonymized (uid stripped/hashed), not deleted — financial
  audit retention (GDPR Art.17(3)(b)).
- Every other uid-keyed collection/table fully deleted after the grace period.
- No silent partial state — every outcome (success or failure) recorded in `account_deletions`.

---

## Previous state (before this change)

`DELETE /auth/account` (`app/routers/auth.py`) existed and worked exactly as commit `62250da` left
it: 409 if a deletion was already pending, marks `users/{uid}.delete_requested_at`, revokes the
*current* session only, queues one `account_deletions` BQ row with `status="pending"`. Nothing else
in the codebase ever read `delete_requested_at` — a second device stayed fully functional
indefinitely (`POST /auth/refresh` never checked it), no data was ever purged, and the
`account_deletions.status` field never moved past `"pending"`.

The architecture doc (`motamaze-project/rnd_research/2026-06-04_motamaze-architecture-final.md`,
line 1264) specified *"immediately deletes Firestore user document and sessions; queues BigQuery
deletion (30-day window)"* — i.e. immediate Firestore erasure, no grace period. That was superseded
by an explicit decision with the user on 2026-07-22, made when this ticket's subtasks were first
scoped: **a 30-day grace period with cancellation**, matching how most major platforms handle
account deletion (locked/restricted state, reversible until the window closes) rather than
irreversible immediate erasure. The architecture doc itself is corrected as part of this ticket (see
Follow-ups) — it was never updated to match, a documentation gap, not a re-litigated decision.

The other decision made the same day: `purchases`/`purchase_events` are **anonymized, not deleted**
(GDPR Art.17(3)(b), legal-obligation exception for financial/accounting records) — this shaped the
purge design from the start rather than being a mid-implementation change.

---

## Implementation details

Delivered across 6 subtasks (ST-01 through ST-06), each committed and pushed separately — see the
commit list below. Full design rationale lives in `logic/account-deletion.md`; this section
summarizes what changed per file.

### `app/services/auth_service.py`
- `upsert_user()` return signature extended to a 4-tuple — added `deletion_pending: bool`, computed
  from `existing.get("delete_requested_at") is not None` in the existing-user branch (always `False`
  for new users). Surfaced so login can inform the client without an extra Firestore read.
- `consume_refresh_session()` now checks `users/{uid}.delete_requested_at` after token-hash
  verification, before consuming the session: raises `ValueError("AUTH_ACCOUNT_DELETION_PENDING")`
  if set, and — unlike every other rejection path in this function — leaves the session **un**consumed
  (not deleted), since the whole point is the session should remain usable *if* the user cancels.

### `app/routers/auth.py`
- `LoginResponse.deletion_pending: bool = False` — new field, passed through from `upsert_user()`.
  **Login is deliberately never blocked** by a pending deletion — see the design note in
  `logic/account-deletion.md` for why (it's the only path to reach `cancel-deletion`).
- New `POST /auth/account/cancel-deletion`: authenticated, clears `delete_requested_at`
  synchronously (the field checked everywhere else), queues a `status="cancelled"` BQ row
  (best-effort). 404 `AUTH_NO_PENDING_DELETION` / 404 `USER_NOT_FOUND` for the two ways there's
  nothing to cancel.

### `app/services/account_deletion_service.py` (new file)
- `find_users_due_for_purge()` — full `users` collection scan filtered in Python (MVP scale,
  sidesteps a composite index and a Firestore inequality query against a mostly-`None` field).
- `purge_user_firestore_data()` — hard-deletes `progress`/`lives`/`entitlements`/`season_progress`/
  `achievement_progress`/`sessions`, anonymizes `purchases` (`uid: null`, `anonymized_at`), deletes
  `users/{uid}` last. Returns the collections touched.
- `purge_user_bigquery_data()` — hard-deletes `login_events`/`session_durations`/`player_behavior`/
  `ad_impressions`/`entitlement_grants`, anonymizes `purchase_events` (`user_id` → deterministic
  SHA-256 hash — the column is `NOT NULL`, so nulling it out isn't an option). Same file, same
  service layer as the Firestore purge — one place for "what happens to a deleted user's data."

### `app/services/bq_streaming.py`
- `run_dml()` — new. First DML (UPDATE/DELETE) surface in this codebase; every prior BigQuery
  interaction was append-only streaming inserts. Wraps the blocking
  `bigquery.Client().query().result()` via `asyncio.to_thread`. Unlike `stream_event`, errors
  **propagate** instead of being logged-and-swallowed — the caller needs to know a purge failed.

### `app/routers/jobs.py`
- New `POST /jobs/purge-deleted-accounts`, same `X-CloudScheduler-JobName` header-check pattern as
  `reconcile-purchases`. Runs BigQuery purge **before** Firestore purge — deliberate ordering (not
  arbitrary): Firestore deletes `users/{uid}` last, and that's the same field
  `find_users_due_for_purge()` scans for, so a BigQuery failure with Firestore purged first would
  orphan the user with no way to retry. Both purges are idempotent, so retrying after any partial
  failure is always safe. Writes a final `status="completed"` (with `tables_purged`) or
  `status="failed"` (with the exception message in `notes`) row per user.

### Infra
- Cloud Scheduler job `purge-deleted-accounts` created in `motamaze-dev` (schedule `0 7 * * *` UTC),
  `roles/run.invoker` granted to `game-api-backend@motamaze-dev.iam.gserviceaccount.com` on the dev
  Cloud Run service (IAM policy was empty — Cloud Scheduler had never been used against dev before).
  Force-run validated end-to-end: first attempt 403 before IAM propagated, second attempt 200,
  confirmed in Cloud Run request logs. **Production promotion is a separate, tracked subtask** — see
  Follow-ups.

### Docs
`docs/DATA_MODEL.md` — `delete_requested_at` description, `users/{uid}` endpoints table, TTL table
(`users`/`sessions` rows), and a new anonymization note on `purchases/{doc_id}`. New
`logic/account-deletion.md` — full current-state reference for the whole flow.

---

## Testing

```bash
python -m pytest --ignore=tests/test_firestore_rules.py -q
```

New/touched test files across the 6 subtasks: `tests/test_auth_service.py`, `tests/test_auth_router.py`,
`tests/test_account_deletion_service.py` (new), `tests/test_jobs_router.py` (new — first coverage
for `/jobs` at all), `tests/conftest.py` (extended `_patch_bq_streaming` to cover
`app.routers.jobs.stream_event`, which had no test coverage before this ticket and would otherwise
attempt a real BigQuery call in every test).

Coverage highlights: grace-period access cutoff (login open + flagged, refresh blocked, regression
for unaffected users); cancellation (clears state, reactivates refresh, 404s for both "nothing to
cancel" and "already purged"); the original `DELETE /auth/account` endpoint itself (202, 409,
session revocation, BQ row shape — zero coverage before this ticket); Firestore purge (collection
selection, anonymization vs. deletion, tables-touched reporting, idempotency on a second run);
BigQuery purge (table selection, anonymization vs. deletion, deterministic hashing, zero-affected-
rows not mis-reported, error propagation); the job endpoint's BQ-before-Firestore ordering and its
retry-safety on a partial failure; the actual `account_deletions` row content for both `completed`
and `failed` outcomes, not just the response summary.

---

## Results

```
======================== 126 passed ========================  (full suite, no regressions across 6 subtasks)
```

Cloud Scheduler force-run (dev): first attempt `403` (IAM not yet propagated), second attempt `200`
— confirmed via `gcloud logging read` against `motamaze-backend` (dev Cloud Run service).

---

## Follow-ups / notes

- **Production Cloud Scheduler promotion — separate tracked subtask**
  (`Backend: promover Cloud Scheduler de purge-deleted-accounts de DEV a PROD`, Monday item
  `12604774083`). Requires the endpoint deployed to prod (manual-approval gate, not just push to
  `main`) before `gcloud scheduler jobs create` against `--project=motamaze`. Real risk this
  subtask exists to prevent: if forgotten, no account deletion would ever actually process in
  production.
- **Architecture doc correction** (`motamaze-project/rnd_research/2026-06-04_motamaze-architecture-final.md`):
  line 1264's "immediately deletes" description is now wrong — corrected as part of this ticket's
  docs pass. Also resolves risk item P0-3 ("DELETE /auth/account not yet implemented"), now
  genuinely implemented. **Push to `motamaze-project` is still blocked by a 403 permissions error**
  (Juan needs to grant write access) — committed locally, queued behind the other pending commits
  in that repo.
- **BigQuery streaming-buffer restriction not validated against a real case.** DML on rows inserted
  in roughly the last 90 minutes can fail — not expected to matter 30 days out, but untested against
  an actual buffered row.
- **Client (Godot) has no UI for any of this yet** — `deletion_pending`, the cancel-deletion call,
  and the delete-account call itself are all backend-only today. Separate client-side tickets
  already exist (`Main menu... account deletion UI`, `Wire account-deletion UI to DELETE
  /auth/account`), not part of this ticket's scope.
