# T-402 (subtasks 1+2) — store_age_signal contract + Firestore fields

| Field | Value |
|---|---|
| **Type** | Feature / Compliance |
| **Priority** | High — Digital ECA prohibits self-declared age in Brazil |
| **Status** | ✅ Done — 2026-07-22 |
| **Date** | 2026-07-22 |
| **Engine** | FastAPI backend |
| **Depends-on** | T-400 (`consent_age_threshold`), AUTH-004 (`LoginRequest`/`upsert_user` shape) |

---

## Description

First two backend subtasks of T-402 (Brazil age assurance). Brazil's Digital ECA prohibits
self-declared age — T-401's DOB flow isn't sufficient there on its own; the required mechanism is
Apple Declared Age Range API (iOS) / Google Play Age Signals API (Android), which return a raw age
band. This pass **only captures and stores** the raw signal — no interpretation or reconciliation
against DOB-based `is_child` (that's subtask 5, `T-402-br-age-signal-reconciliation.md`).

**Acceptance criteria:**
- `POST /auth/login` accepts two new optional fields: `store_age_signal`, `store_age_signal_source`.
- Both persisted on `users/{uid}.consent`, plus a `store_age_signal_captured_at` timestamp.
- A login without the signal never clobbers a previously-captured value.
- Documented in `REST-001` and `docs/DATA_MODEL.md`.

---

## Previous state (before this change)

`LoginRequest` had no age-signal fields at all — only `store_country_code`/`device_country_code`
(T-400, jurisdiction) and `display_name` (AUTH-004). `upsert_user()`'s `consent` map had no reserved
field for a store/OS age signal anywhere in the schema.

---

## Implementation details

### `app/routers/auth.py` — `LoginRequest`
Two new optional fields, same shape/place as the existing `store_country_code`: `store_age_signal:
str | None` (raw band, e.g. `"13-15"`, `"18+"` — explicitly **not normalized** here) and
`store_age_signal_source: str | None` (`"apple_declared_age_range"` | `"play_age_signals"`).

### `app/services/auth_service.py` — `upsert_user()`
Two new kwargs. Create path: writes `store_age_signal`/`store_age_signal_source`/
`store_age_signal_captured_at` (timestamp, `None` if no signal) into the initial `consent` map.
Update path: follows the exact truthy-guard pattern already used for `email`/`display_name`/
`photo_url` (AUTH-004) — only overwrites when the incoming value is truthy, so a login without the
signal never wipes a previously-captured one.

### `app/routers/auth.py` — login handler
Passes `store_age_signal=body.store_age_signal, store_age_signal_source=body.store_age_signal_source`
into the `upsert_user(...)` call.

### Docs
`docs/DATA_MODEL.md` — 3 new rows in the `users/{uid}.consent` table, plus backfilled several
already-shipped-but-undocumented fields found stale while editing the same table (`is_child`,
`country_code`, `consent_age_threshold`, `country_signal_mismatch`). `changelogs/REST-001-rest-api-
contract.md` — contract addition appended as a dated addendum (the original `/auth/login` table was
already stale re: T-400's fields, a pre-existing gap, not introduced by this change).

---

## Testing

```bash
python -m pytest tests/test_auth_router.py -v
python -m pytest --ignore=tests/test_firestore_rules.py -q
```

`tests/test_auth_router.py` — 3 new: signal present → persisted correctly with timestamp; signal
absent → fields stay `None` (no regression); repeat login omitting the signal → previously-stored
value is not clobbered.

---

## Results

```
======================== 10 passed ========================  (test_auth_router.py, isolated)
======================== 68 passed in 8.22s ================  (full suite, no regressions)
```

---

## Follow-ups / notes

- No reconciliation logic yet — nothing reads `store_age_signal` to affect `is_child`. Shipped
  separately as subtask 5 the same day (`T-402-br-age-signal-reconciliation.md`).
- Godot client (Juan) doesn't send these fields yet — zero visible behavior change until it does.
- Commit `8e475e6`.
