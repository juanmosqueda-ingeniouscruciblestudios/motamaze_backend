# T-447 — Achievement unlock tracking + season-points bonus

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | High — blocks the Achievements client screen (Godot, separate ticket) |
| **Status** | ✅ Done (backend scope) — ST-01, ST-04–ST-12 ✅. ST-02/ST-03 (Godot client, Juan) still open |
| **Date** | 2026-07-31 |
| **Engine** | FastAPI backend (no client work in this ticket's backend scope) |
| **Depends-on** | T-210 (progress backend ✅), T-443 (leaderboard backend ✅) — season_points is deliberately NOT wired into leaderboard ranking yet, see ST-08 below |

---

## Description

40 achievements (`motamaze-project/docs/project_spec.md` §Achievements), each gated by a guard
condition over match/season stats (win rate, streaks, hit-free counts, maze coverage, comebacks,
NPC presence). Unlocking one contributes a rarity-tiered points bonus to `season_points`. Not a
simple unlock flag — evaluating the guards requires new per-match and per-season stat tracking
that didn't exist before this ticket, plus a win-rate signal for the 26 of 40 guards gated on it.

**Acceptance criteria:**
- [x] Client can send match-outcome detail (`match_stats`) that the guards need
- [x] Win rate per level exists and is used as guard input, absent WR fails guards closed
- [x] 40 achievement definitions seeded, keyed by a stable `achievement_id`
- [x] Per-match and per-season aggregate facts persisted (streaks, qualifying levels, 3-star levels)
- [x] All 40 guards evaluated on `POST /progress/level-complete`, unlocks persisted
- [x] `season_points` formula implemented, achievement bonus included
- [x] `GET /achievements` returns unlocked state + progress + rarity
- [x] Rarity computed on a 24h cadence from active players, not live per-request
- [x] Full test coverage across guards, aggregates, formula, and endpoints
- [x] Documented in `DATA_MODEL.md`, `REST-001`, this changelog, `logic/achievements.md`

---

## Previous state (before this change)

Ticket created 2026-07-14 — no prior implementation existed. `POST /progress/level-complete`
carried five fields (`level_id`, `score`, `stars_earned`, `duration_secs`, `session_id`); none of
the match detail the 40 guards need (game mode, win/loss, hits, NPCs present, maze coverage, idle
time, food collected, lead changes, food droughts, time to target, frozen time, shift reroutes,
stuns) arrived at all. Win rate per level existed nowhere in the data model. Only 2 of the 40
achievements were even theoretically evaluable from data the backend already had.

---

## Implementation details

### ST-01 — `match_stats` contract (`db29191`)
Defines `match_stats` as an optional nested block on `POST /progress/level-complete` rather than
flat fields — an un-updated client omits the whole block, progress still records, nothing gets
evaluated. Absent must never read as satisfied, or old clients get achievements for free. Each of
the 18 fields mapped to which achievements consume it. `badsmell_hits` kept separate from
`hits_taken` (one achievement needs both at zero); `round_duration_secs` kept separate from the
existing `duration_secs` (First Bite achievements need time *remaining* = round duration minus
time to target). NPC presence is counts, not booleans — some guards need `n_huracan + n_zas >= 2`,
others need all four NPCs present at once. Documented in REST-001.

### ST-04 — `level_stats` win-rate source (`9c789f1`, `e68ff04`, `f8c9bf4`, `96c5cda`)
26 of 40 guards gate on win rate; nothing measured it. `level_stats/{level_id}.win_rate` defined
as resolved-attempts-based, but `level_fail` turned out to never be emitted by the client — instead
of standing up a whole new event, `POST /lives/spend` already streams `life_spent` on every attempt
(`player_behavior`), so `wins/attempts = level_complete / life_spent` reuses an event that already
exists. Denominator is therefore *attempts started*, not *attempts resolved* — abandonment counts
as a non-win, accepted knowingly (defensible for difficulty; can't distinguish a real loss from a
walk-away, revisit once production data shows the gap). Rests on the assumption that exactly one
life is spent per attempt, at attempt *start* (spending on loss would be exploitable — a player
who sees they're about to lose could quit before the result lands and keep the life); backend can't
observe which the client actually does, flagged pending Juan's confirmation (2026-08-03).

`level_stats_service.recalc_level_stats` (job, `POST /jobs/recalc-level-stats`, Cloud Scheduler
24h): trailing 30-day window, only writes a level once it clears `MIN_SAMPLE_SIZE=100` attempts in
the window, never downgrades `measured` back to `simulated`. An absent/stale document is the
intended way for WR-gated guards to fail closed, not a bug. `level_id` also threaded through
`POST /lives/spend` (optional, 1–30 validated) — the actual field the whole win-rate calculation
depends on; the client actually *sending* it is the separate, still-open Godot ticket (current
Monday **ST-03**, Juan).

### ST-05 — `config/achievements` seed (`f7a33ae`)
`scripts/seed_achievements.py`, same idempotent-seed pattern as `seed_store_catalog.py`. One
Firestore doc, static display fields (`name`, `description`, `rarity_tier`, `points`) for all 40,
sourced from `project_spec.md`'s achievement table. `achievement_id` is a new human-readable slug
(project_spec's own numeric IDs are non-contiguous, not meant to be player- or log-facing); `spec_id`
kept alongside for traceability. Guard conditions captured as `guard_notes` text only, not
executable data — 40 fixed, heterogeneous conditions that only change via a code deploy don't
justify a rules DSL; the real logic is Python predicates in the evaluation engine (ST-07).
`tests/test_seed_achievements_data.py` validates the list itself (40 unique IDs, rarity
counts/points match project_spec's table, 9,800 total points) — no Firestore I/O, same reasoning as
`seed_store_catalog.py` staying untested at the I/O layer.

### ST-06 — `season_match_stats` aggregates (`9d473c0`)
`MatchStats` Pydantic model (18 fields) added to `LevelCompleteRequest`, plus
`_is_match_stats_valid` implementing REST-001's server-side validation. Deliberately no
`Field(ge=0)` constraints on the model — a 422 would reject the whole request, but an invalid
`match_stats` must drop achievement evaluation without rejecting progress; validation runs as a
plain function after parsing, gating whether the new write happens at all.

New `season_match_stats/{uid}` + `season_match_stats_service.apply_match`:
- **`win_streak`**: distinct-level consecutive wins, each entry carrying its own WR snapshot.
  Re-winning an already-counted level is a no-op (doesn't extend, doesn't reset); any loss resets
  to empty, even on a repeated level.
- **`qualifying_levels`**: one record per level, written only on that level's *first* win this
  season — later replays don't overwrite it, preserving the WR/context from the win that actually
  earned it.
- **`three_star_levels`**: separate from `qualifying_levels` because the two 3-star achievements
  care about when a level was first *3-starred*, which can be a later replay than its first win.

Stores raw facts only, no achievement-specific flags (`is_hit_free`, `is_comeback`, ...) — same
guard_notes-is-not-data reasoning as ST-05. Deciding what satisfies a given guard is ST-07's job.

### ST-07 — Evaluation engine (`1213540`)
`app/services/achievements_engine.py` — 40 Python predicates over a `GuardContext`, indexed in
`GUARDS` by `achievement_id`. `evaluate_achievements()` runs once per level-complete, only when
`match_stats` is present and valid (same gate as ST-06), filters `GUARDS` against
`achievement_progress/{uid}.unlocked` before evaluating (no re-evaluating already-unlocked
achievements), and persists newly-unlocked IDs + timestamps with `merge=True`.

Notable interpretive decisions (full reasoning in the module docstring): streak guards
(`on_a_roll`/`hot_streak`/`relentless`/`unbreakable`) use a per-achievement trailing run of the
streak whose entries are all under *that achievement's own* WR threshold — a win above threshold
breaks the run for that achievement without resetting the raw streak itself, since a looser-
threshold achievement may still count it. A missing WR snapshot is treated as disqualifying,
matching "WR ausente = guard no evaluable". `speedy`/`speedster`/`speed_legend` require
`game_mode == "first_bite"` even where `guard_notes` doesn't spell it out (time-to-target is
meaningless outside that mode). `seasonal_legend` (`season_points >= 4000`) fails closed on
`season_points is None`, since that value didn't exist until ST-08. Deliberately does **not**
populate `achievement_progress.progress` (numeric "N of M" progress toward locked achievements) —
most guards are boolean compounds without a well-defined fraction; flagged as a follow-up, not a
blocking gap.

### ST-08 — `season_points` formula (`f2da509`)
`app/services/season_points_service.py`: `season_points = season_stars*3 + levels_cleared*5 +
achievement_bonus_points`. Discovered mid-implementation that `season_progress` didn't track
*which* levels had been cleared this season (needed for the `levels_cleared` term) — added
`levels_cleared_ids`. `achievement_bonus_points` accumulates points from `config/achievements` for
every achievement unlocked this call, added to `season_progress` once and never re-added on
subsequent matches. Fixed a pre-existing bug found in the process: `season_id` was never written
back on non-creation writes, so every request after a season boundary re-detected "stale" and
re-baselined from zero forever — regression-tested.

**Deliberately not wired into `leaderboard.py`'s ranking** — `leaderboards/{season}/scores` still
orders by raw `season_stars`. Touching the leaderboard's stored field, its query filters, and
`POST /leaderboard/score`'s "authoritative score" logic together is separate, larger scope, decided
against for this ST. Flagged as a known gap in `DATA_MODEL.md#season_progress`, not silently left
inconsistent.

### ST-09 — `GET /achievements` (`4c6f938`)
`app/services/achievements_catalog_service.py` (pure merge, mirrors
`store_service.resolve_catalog_products`) + the router in `game.py`. Merges
`config/achievements` (catalog) + `achievement_progress/{uid}` (unlock state) +
`achievement_rarities/{achievement_id}` (measured rarity, ST-10) into REST-001's response shape.

Two interim/interpretive decisions: **`icon_id`** is derived as `badge_{achievement_id}` — no badge
asset pipeline existed yet, so this adopts the naming pattern REST-001's own examples already
implied. **`rarity`/`rarity_percent`** fall back to `config/achievements`' static `rarity_tier`
with `rarity_percent: null` for any achievement the rarity job (ST-10) hasn't computed yet — reads
the full `achievement_rarities` collection in one `get()` (mirrors `/store/catalog`'s `promotions`
read) rather than one lookup per achievement. `progress` stays `null` throughout, per ST-07's
decision.

### ST-10 — Rarity job (`daaaa06`)
`app/services/achievement_rarities_service.py` + `POST /jobs/recalc-achievement-rarities` (Cloud
Scheduler, 24h). **Key correctness decision:** `total_players` and `unlocked_by` are scoped to the
*same* population — BigQuery `player_behavior` distinct `user_id`s active in the trailing 30 days —
rather than pairing that recent-window `total_players` against an all-time `achievement_progress`
tally. `achievement_progress` is cumulative and never resets, so an all-time `unlocked_by` divided
by a recent-window `total_players` could push `rarity_percent` past 100% for any achievement most
churned players already cleared. Instead, the job fetches the active-uid set from BigQuery first,
then counts unlocks only among those same uids (one `achievement_progress/{uid}` read per active
uid — same loop shape as `jobs.py`'s `run_purge_deleted_accounts`), guaranteeing
`rarity_percent ∈ [0, 100]`. Skips the whole run (leaves existing docs untouched) when the active
window has zero players — insufficient signal, not a real "nobody unlocked this" result, same
philosophy as `level_stats_service`'s `MIN_SAMPLE_SIZE` skip.

*Cloud Scheduler itself not yet created in GCP* — tracked separately, see Follow-ups.

### ST-11 — Test coverage review (`26609f4`)
Reviewed coverage across the whole ticket (guards, `season_match_stats_service`,
`season_points_service`, the level-complete/achievements/rarity endpoints). One real,
self-acknowledged gap found: `achievements_engine.py`'s 40-guard `GUARDS` registry had direct tests
for only 12 (ST-07 shipped a representative sample per structural category, reasoning that testing
all 40 would just re-transcribe `project_spec.md` into assertions). Revisited: each guard is
independently hand-transcribed logic, so a representative sample can't catch a transcription bug
(wrong operator, wrong threshold, AND where it should be OR) in any of the other 28 — that's not
spec-restating, it's the only thing that would catch it. Added one true + one false case per
remaining guard. No comparable gap found elsewhere.

### ST-12 — Documentation (this changelog)
This file, `logic/achievements.md`, the `changelogs/README.md` row, and the
`docs/IMPLEMENTATION.md` section. `DATA_MODEL.md` and `REST-001` were kept current incrementally
during ST-07/ST-09/ST-10 rather than deferred here — this pass only fixed two stale `T-447 ST-03`
references left over from a subtask renumbering (now `ST-04`), confirmed no other drift.

---

## Testing

```bash
python -m pytest -q
```

New/extended test files across the ticket: `tests/test_seed_achievements_data.py`,
`tests/test_level_stats_service.py`, `tests/test_recalc_level_stats_router.py`,
`tests/test_season_match_stats_service.py`, `tests/test_achievements_engine.py`,
`tests/test_season_points_service.py`, `tests/test_season_points_router.py`,
`tests/test_achievements_catalog_service.py`, `tests/test_achievements_router.py`,
`tests/test_achievement_rarities_service.py`, `tests/test_recalc_achievement_rarities_router.py`,
`tests/test_level_complete_match_stats_router.py`.

---

## Results

```
336 passed, 8 skipped
```

40/40 achievement guards individually covered (registry-completeness check:
`set(GUARDS) == {seeded achievement_ids}`, `len(GUARDS) == 40`). No regressions across any ST.

---

## Follow-ups / notes

- **Cloud Scheduler jobs not created in GCP yet** for `recalc-level-stats` (ST-04) and
  `recalc-achievement-rarities` (ST-10) — both endpoints are implemented and tested but don't
  auto-run. Tracked in a separate Infra/DevOps ticket with two subtasks (created 2026-07-31),
  same "build the job" / "schedule the job" split already used for `recalc-age-thresholds`.
- **`season_points` not wired into leaderboard ranking** — `GET /leaderboard` still orders by raw
  `season_stars`. Known gap, see ST-08 above and `DATA_MODEL.md#season_progress`.
- **`achievement_progress.progress` (numeric "N of M") never populated** — all achievements return
  `progress: null` in `GET /achievements`. Deferred since ST-07; doesn't affect unlock correctness,
  only a UI nice-to-have.
- **`icon_id` is a naming convention (`badge_{achievement_id}`), not a real asset reference** —
  pending an actual badge asset pipeline.
- **Win-rate data is currently empty in every environment** — `level_stats` only gets written once
  either real production volume clears `MIN_SAMPLE_SIZE=100` attempts per level, or the T-203
  simulation harness is run to seed it; until then all 26 WR-gated guards fail closed. Not a bug.
- **ST-02/ST-03 (Godot client) still open** — client doesn't yet send `match_stats` on
  level-complete (ST-02) or `level_id` on `/lives/spend` (ST-03). Both optional/backward-compatible
  on the backend side; nothing breaks, but achievements/win-rate stay unevaluated until Juan ships
  them.
- **Achievements client screen** — separate ticket, blocked on this one's backend scope (now done).
