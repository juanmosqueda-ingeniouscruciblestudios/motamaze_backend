# T-402 (subtask 5) — Brazil store_age_signal reconciliation

| Field | Value |
|---|---|
| **Type** | Feature / Compliance |
| **Priority** | High — Digital ECA prohibits self-declared age in Brazil |
| **Status** | ✅ Done — 2026-07-22 |
| **Date** | 2026-07-22 |
| **Engine** | FastAPI backend (no client change this pass) |
| **Depends-on** | T-402 subtasks 1+2 (`8e475e6` — `store_age_signal` contract + Firestore fields), T-401 (DOB flow), T-400 (`consent_age_threshold`) |

---

## Description

Subtasks 1+2 only captured and stored the raw `store_age_signal` — nothing reacted to it. This
closes that loop: in Brazil, `store_age_signal` (Apple Declared Age Range / Google Play Age Signals)
must take priority over the self-declared DOB from T-401, with the DOB relegated to a secondary/
fallback signal there. **Every other country is untouched.**

**Acceptance criteria:**
- BR user with a parseable `store_age_signal` → `is_child`/`restricted_features`/`coppa_compliant`
  established at **login time** (not left `null` until a later `age-verify` call).
- BR user whose `is_child` was already decided by the signal → a subsequent DOB submission via
  `POST /auth/age-verify` must **not** override it.
- BR user with no signal (or an unparseable one) → identical to today's DOB-only flow.
- Every non-BR country → zero behavior change, zero new code path executed.

---

## Previous state (before this change)

`is_child` was set **only** by `POST /auth/age-verify`, purely from DOB, for every country including
Brazil — despite the architecture doc explicitly requiring store/OS signals as the deciding input in
BR (self-declaration prohibited under Digital ECA). `upsert_user()` (`app/services/auth_service.py`)
created every new user with `"is_child": None` unconditionally and never referenced
`store_age_signal` beyond storing it raw (subtasks 1+2). `age_verify` (`app/routers/auth.py`) always
computed `is_child = age < threshold` from the submitted DOB with no country-specific branch.

---

## Implementation details

### `app/services/geo_service.py` — two new functions

`store_age_signal_is_minor(signal, threshold)` — conservative parser, regex `^(\d+)(?:-(\d+))?\+?$`,
decision keyed on the band's **lower** bound (`"13-15"` → 13 < 18 → minor; `"18+"` → 18, not < 18 →
not a minor). Returns `None` for absent/unparseable input so the caller falls back to DOB rather than
guessing. Real Apple/Google band formats aren't confirmed by any doc found — documented as a known
gap in the function's own docstring and in `logic/age-assurance.md`.

`age_gate_update(is_child, now)` — extracted from what `age_verify` already built inline
(`consent.is_child`, `restricted_features`, conditionally `consent.coppa_compliant`), so both the DOB
path and the new BR-signal path produce byte-identical update shapes instead of two hand-maintained
copies.

### `app/services/auth_service.py` — `upsert_user()`

Computes `signal_is_minor = geo_service.store_age_signal_is_minor(store_age_signal, consent_age_threshold)` once, only when `country_code == "BR"`. **Create path:** `consent.is_child` seeded from
`signal_is_minor` instead of hardcoded `None`; `consent.coppa_compliant` becomes the one-liner
`signal_is_minor is False` (evaluates correctly for all three states: `None`→`False`, `True`→`False`,
`False`→`True` — matches `age_verify`'s existing adult-auto-compliant rule without a branch); a
top-level `restricted_features` key is added **only** when `signal_is_minor is not None`, so a non-BR
or signal-less BR creation is byte-identical to before. **Update path:** inside the existing
`if store_age_signal:` guard (subtask 1+2's non-clobber block), additionally merges
`geo_service.age_gate_update(signal_is_minor, now)` when parseable, and updates the local `is_child`
so the function's return value (fed into `LoginResponse.is_child`) is correct too.

### `app/routers/auth.py` — `POST /auth/age-verify`

Before building the DOB-derived update, checks `consent.get("country_code") == "BR"` and calls the
same `store_age_signal_is_minor` against the stored `consent.store_age_signal`. If it resolves
(not `None`), skips `age_gate_update(...)` entirely — only `consent.age_verified_at` is written — and
reassigns the local `is_child` to the signal's value so the **response** also reflects it, not the
just-computed (and in this case irrelevant) DOB-derived value.

**Bug caught and fixed during this same pass, before it shipped:** the first draft updated Firestore
correctly but still `return`ed `AgeVerifyResponse(is_child=is_child, ...)` using the DOB-derived local
variable — meaning a BR minor confirmed by signal, submitting a false "I'm 30" DOB, would have gotten
back `is_child: false` in the API response even though Firestore correctly kept `true`. Caught by
re-reading the return statement immediately after editing, before writing tests — fixed by
reassigning `is_child = signal_is_minor` in the skip branch.

---

## Testing

```bash
python -m pytest tests/test_geo_service.py tests/test_auth_service.py tests/test_age_verify_router.py -v
python -m pytest --ignore=tests/test_firestore_rules.py -q
```

New test files/additions:
- `tests/test_geo_service.py` (new file — this module had zero coverage before) — table-driven
  `store_age_signal_is_minor` (10 cases: ranges, `+`, bare numbers, `None`/empty/unparseable strings)
  + a threshold-genericity test + `age_gate_update` child/adult cases.
- `tests/test_auth_service.py` — 5 new: BR+minor-signal sets `is_child`/`restricted_features` at
  creation; BR+adult-signal sets `coppa_compliant` at creation; BR without a signal is unchanged;
  non-BR with a signal present never triggers reconciliation (captured raw, not acted on); a BR user
  who logs in first without a signal then later with one gets reconciled on the second login.
- `tests/test_age_verify_router.py` — 2 new: a BR user whose `is_child=True` was already established
  by a signal submits an adult DOB and `is_child` stays `True` (`age_verified_at` still updates); a BR
  user with no signal gets the unchanged Rama-1 DOB flow (adult → `coppa_compliant=True`).

---

## Results

```
======================== 41 passed in 2.40s =========================  (the 3 new/touched files, isolated)
======================== 88 passed in 11.56s ========================  (full suite, no regressions)
```

---

## Follow-ups / notes

- **Godot client (T-402 subtasks 6-8, Juan)** doesn't send `store_age_signal` yet — until it does,
  every BR user still falls into the Rama-1 DOB fallback this pass leaves untouched. No visible
  behavior change in production until the client ships.
- **Band format assumption is unverified against a real Apple/Google payload** — flagged in both
  `geo_service.store_age_signal_is_minor`'s docstring and `logic/age-assurance.md`. Revisit the regex
  once Juan has a real device payload to check it against.
- **Provisional pending final ANPD guidance** (same caveat as subtasks 1+2) — treat this build as
  something to revisit before scaling in Brazil, not a one-and-done compliance closure.
- New `logic/age-assurance.md` — first use of the `logic/` "current implementation" doc surface for
  the auth/consent system (previously only `gcp-infrastructure.md` and `admob-config.md` existed
  there). Consolidates T-400/T-401/T-402 age/consent logic into one current-state reference instead
  of it being scattered across three changelogs.
