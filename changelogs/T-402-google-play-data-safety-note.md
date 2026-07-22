# T-402 (subtask 9) — Google Play Data Safety: store_age_signal note

| Field | Value |
|---|---|
| **Type** | Documentation / Compliance |
| **Priority** | Medium — required before Play Console re-submission, not before soft launch |
| **Status** | ✅ Done — 2026-07-22 |
| **Date** | 2026-07-22 |
| **Engine** | N/A (docs only) |
| **Depends-on** | T-402 subtasks 1+2 (`8e475e6`), subtask 5 (`1bdd8ff`) |

---

## Description

The last backend-owned piece of T-402: reflect the new `store_age_signal` data collection (shipped
in subtasks 1+2/5) in `docs/GOOGLE_PLAY_DATA_SAFETY.md`, and flag it as provisional pending final
ANPD guidance before scaling in Brazil. Everything else remaining on T-402 is Godot client work
(Juan) — this closes Saul's side of the ticket entirely.

**Acceptance criteria:**
- `docs/GOOGLE_PLAY_DATA_SAFETY.md` documents the `store_age_signal` collection and the reasoning
  for whether it needs a new Data Safety row.
- A provisional/ANPD-pending note is present, consistent with `logic/age-assurance.md` and
  `docs/DATA_MODEL.md`'s existing caveats.
- Consistent with the doc's own two-stage submission rule: don't describe a practice that isn't
  live in production yet.

---

## Previous state (before this change)

`docs/GOOGLE_PLAY_DATA_SAFETY.md` had zero mentions of `store_age_signal`, Age Signals, Declared Age
Range, ANPD, or Brazil — it predates T-402 entirely (last data-collection change tracked was T-311's
Tenjin correction, 2026-07-21).

---

## Implementation details

Followed the doc's existing Part 1B convention (two-stage submission — same pattern already used for
AdMob/Crashlytics/Tenjin): a new data source doesn't get declared in Part 1 until the client actually
ships it. The Godot Android client doesn't call Google Play's Age Signals API yet, so no real signal
reaches the backend in production — Part 1 (today's submission) is correctly left unchanged.

Added a new Part 1B section ("When the Godot Android client ships the Play Age Signals API call")
covering: (1) no new Data Safety row is needed — the existing "Other info (age/consent status)" row
already covers it, same category as the pre-existing DOB-based collection; (2) `Shared` stays `No` —
the signal flows from Google's own API into the app, MotaMaze doesn't forward it anywhere (verified
against `app/services/auth_service.py`/`geo_service.py`); (3) scope is Brazil-only, gated by
`country_code == "BR"`, backed by an explicit regression test
(`test_upsert_user_non_br_signal_never_triggers_reconciliation`); (4) explicitly out of scope: Apple's
Declared Age Range API (iOS) — this document only covers Google Play, per its own header.

Also added a matching bullet to Part 2's pre-submission checklist (same citation style as the
existing Cloudinary/profile-photo bullets — reasoned from shipped code, not a guess) and a tracking
line in the "Keep in sync" list at the bottom for when the Godot ticket ships.

The ANPD-provisional caveat mirrors the language already used in `logic/age-assurance.md` and
`docs/DATA_MODEL.md` — no new legal position taken here, just cross-referenced.

---

## Testing

Documentation-only change — no code touched, no automated tests apply. Verification was manual:
confirmed every code reference cited in the new section (`store_age_signal_is_minor`, `age_gate_update`,
the `country_code == "BR"` gate, the named regression test) against the actual shipped code in
`app/services/auth_service.py` and `app/services/geo_service.py` before writing the doc text.

---

## Results

Doc renders correctly; all internal cross-references (`logic/age-assurance.md`, `docs/DATA_MODEL.md`,
the named test) point at files/tests that exist as of commit `1bdd8ff`.

---

## Follow-ups / notes

- **This closes Saul's backend scope on T-402.** Everything left on the parent ticket is Godot client
  work (Apple Declared Age Range integration, Play Age Signals integration, sending the signal at
  login, fallback handling) — owned by Juan.
- Re-open this doc section once the Godot Android client ships the Play Age Signals API call, to
  re-verify the "no new row needed" reasoning against real shipped behavior — tracked in the doc's
  own "Keep in sync" checklist.
- Still provisional pending final ANPD guidance — same open item as the rest of T-402, not resolved
  by this pass.
