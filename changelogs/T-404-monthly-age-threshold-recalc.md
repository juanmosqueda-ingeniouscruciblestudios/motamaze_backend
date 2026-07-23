# T-404 — Monthly recalc Cloud Function (age threshold crossing, per-user country)

| Field | Value |
|---|---|
| **Type** | Feature / Compliance |
| **Priority** | High — closes a documented-but-never-implemented gap in the age-assurance system |
| **Status** | In Progress — ST-01–05 ✅. ST-06 (Cloud Scheduler dev + validate) pending |
| **Date** | 2026-07-23 |
| **Engine** | FastAPI backend + Cloud Scheduler (not created yet — see Follow-ups) |
| **Depends-on** | T-401 (DOB flow ✅), T-402 (BR store-signal reconciliation ✅) |

---

## Description

A user's `is_child` is set once, at DOB verification, and never re-evaluated — but people age. This
ticket closes that gap: a monthly job detects when a DOB-verified user has crossed their country's
`consent_age_threshold` since verification, and flips them to adult without requiring re-verification.

**Acceptance criteria (original ticket title: "age threshold crossing, per-user country"):**
- [x] Detect threshold crossings per-user, using each user's own `consent_age_threshold` (never
  hardcoded to 13)
- [x] Flip `is_child`/`restricted_features`/`coppa_compliant` for users who've crossed
- [x] No new client (Godot) work required
- [ ] Cloud Scheduler live (dev — ST-06, next)

---

## Previous state (before this change)

The architecture doc specified the exact design from the start (line 1140): *"Store birth_month +
birth_year only for annual recalculation. Never write birth_day to any database."* This was never
implemented. `POST /auth/age-verify` (T-401) already parsed the client's full DOB (`date.fromisoformat(body.dob)`)
to compute `age`, then discarded it entirely after use — nothing was ever persisted for a later
recalc to work from. No recalc logic, pure function, or job existed anywhere in the codebase.

---

## Implementation details

### ST-01 — `app/routers/auth.py`, `age_verify()`
Added `consent.birth_month`/`consent.birth_year` to the existing `update` dict, derived from
`dob.month`/`dob.year` — no new client data needed, the full DOB was already in hand. **Only written
in the DOB-decides branch** (`signal_is_minor is None`), never in the BR-store-signal branch:
presence of these fields must mean "is_child is DOB-derived," so ST-03's job can rely on that alone
without also cross-checking `country_code`. Written for both children and adults verified by DOB, not
just children.

### ST-02 — `app/services/geo_service.py`, `has_aged_out()`
Pure function: `has_aged_out(birth_month, birth_year, threshold, today) -> bool`. Since only
month+year are stored, the exact crossing date within that month is unknown — resolved
conservatively (same protect-first bias as `store_age_signal_is_minor`): the user stays classified
as a minor through the last day of their birth month, flipping to "aged out" only once the following
month starts. December correctly rolls into January of the following year.

### ST-03 — `app/services/age_threshold_recalc_service.py` (new) + `app/routers/jobs.py`
`find_and_recalc_aged_out_users()`: full `users` collection scan filtered in Python (same MVP-scale
reasoning as T-123's `find_users_due_for_purge` — avoids a composite index and a query needing
multiple simultaneous filters). Filters to `consent.is_child == True` with `birth_month`/`birth_year`
present — confirmed in implementation that this presence check alone is sufficient to exclude Brazil
store-signal users, no explicit `country_code` check needed (see ST-01's design). Applies
`geo_service.age_gate_update(False, now)` to anyone `has_aged_out()` returns `True` for — same helper
already used by `age-verify` and `upsert_user`, so the update shape is identical regardless of which
signal decided it. New `POST /jobs/recalc-age-thresholds`, same `X-CloudScheduler-JobName`
header-check pattern as the rest of `/jobs`. Naturally idempotent: once `is_child` flips to `False`,
the same filter excludes the user from every future run — no separate dedup marker needed.

### ST-04 — Test gap review
Reviewed coverage across ST-01–03 (same exercise as T-123's ST-06) and found a real gap: every test
that actually exercised `has_aged_out()` through the recalc service used `threshold=13` — nothing
confirmed the service reads a non-default threshold (e.g. Brazil's 18) from Firestore rather than
accidentally hardcoding 13. Added three tests: non-default threshold respected, a legacy doc with no
`is_child` field is skipped (not crashed on), and a missing `consent_age_threshold` defaults to 13
rather than erroring.

### Docs
`docs/DATA_MODEL.md` — `birth_month`/`birth_year` added to the `consent` field table, two new rows in
the `users/{uid}` endpoints table (`POST /auth/age-verify` was missing from that table entirely —
added it while here; `POST /jobs/recalc-age-thresholds`). Also corrected a stale T-402 note that
still said reconciliation logic didn't exist, superseded the same day it was written. New
`logic/age-threshold-recalc.md` — links to `logic/age-assurance.md` rather than duplicating its
per-country threshold table and the DOB-vs-signal branch explanation.

---

## Testing

```bash
python -m pytest --ignore=tests/test_firestore_rules.py -q
```

New test files: `tests/test_age_threshold_recalc_service.py` (9 cases), `tests/test_recalc_age_thresholds_router.py`
(3 cases). Extended: `tests/test_age_verify_router.py` (+2: birth fields persisted with day excluded;
BR-signal branch persists none), `tests/test_geo_service.py` (+7: `has_aged_out` boundary cases).

---

## Results

```
======================== 155 passed ========================  (full suite, no regressions across ST-01–04)
```

---

## Follow-ups / notes

- **ST-06 (Cloud Scheduler, dev + validate) not done yet** — next in the subtask sequence. Will
  follow the same pattern as T-123/T-302: create in `motamaze-dev`, force-run, confirm 200 in Cloud
  Run logs, leave prod promotion as a separate tracked subtask.
- **Scope limited to DOB-verified users (Rama 1)** — Brazil users verified via `store_age_signal`
  (Rama 2, a band not an exact date) have no `birth_month`/`birth_year` and are out of scope for this
  job entirely. Documented in `logic/age-threshold-recalc.md`, not an oversight.
- **Up to ~1 month of lag is possible** between a user's real birthday and when this system reflects
  it — a deliberate trade-off from only storing month+year (data minimization), not a bug.
- **No client (Godot) work required for this ticket** — the DOB was already collected and sent by
  the client since T-401; this ticket only changed what the backend does with data it already had.
