# T-302 — Ad-revenue reconciliation: custom impression event + AdMob Reporting API daily job

| Field | Value |
|---|---|
| **Type** | Feature / Dataflow |
| **Priority** | High — ad revenue must be accurate and verifiable for the financial model and kill-criteria (LTV) decisions |
| **Status** | ✅ Done (backend scope) — 2026-07-23. Full per-format coverage depends on client work not yet scheduled — see Follow-ups |
| **Date** | 2026-07-23 |
| **Engine** | FastAPI backend + Cloud Scheduler (not yet created — see Follow-ups) |
| **Depends-on** | T-261 (AdMob ✅), T-300 (BigQuery tables ✅), DATA-003 (admob-daily-report job ✅, 2026-07-09) |

---

## Description

Compare our own logged ad impression counts against AdMob's own Reporting API numbers, per ad_unit,
and flag discrepancies — a signal for fraud, missed logging, or SDK misconfiguration.

**Acceptance criteria (original, from the ticket description):**
- [x] Custom impression event logged — ⚠️ partial, see Previous state / Follow-ups
- [x] AdMob Reporting API pulled; reconciled vs impressions
- [x] Discrepancies flagged

A scope decision was made with the user before implementation (2026-07-23): build the reconciliation
job now against whatever impression data already exists (rewarded ads only), rather than waiting on
the client-side work required for full per-format coverage. See Previous state for why.

---

## Previous state (before this change)

`admob_daily_report` (AdMob's own numbers) was already fully populated daily via
`POST /jobs/admob-daily-report` (DATA-003, Done 2026-07-09) — that half of this ticket already
existed under a different ticket number.

`ad_impressions` (our own numbers) was only ever written for one narrow case: `POST /lives/grant`
with `source=rewarded_ad_ssv` (`app/routers/game.py`) streams a row on `reward_earned`, with
`revenue_usd` always `None` (never actually captured). No interstitial or banner impression is
logged anywhere server-side — no endpoint receives them, and the architecture doc's original design
(a per-impression AdMob revenue callback — `OnPaidEventListener` — firing for every ad format,
piped through Firebase Analytics or a custom endpoint) was never built, client or backend.

No reconciliation logic existed at all — nothing compared these two tables, nothing flagged
anything. This is the actual gap this ticket closes.

**Why build it now instead of waiting for full client instrumentation:** the reconciliation job
itself is pure backend logic, independent of how complete the input data is. Building it now against
today's rewarded-only data means interstitial/banner ad_units correctly show up as ~100%
discrepancies — which is itself a true, useful signal (visible proof of the coverage gap) rather than
something to hide behind an unbuilt job. Decision made explicitly with the user, not assumed.

---

## Implementation details

### `app/services/bq_streaming.py`
- `run_select()` — new. First `SELECT` surface against BigQuery in this codebase (prior additions
  were streaming inserts and, from T-123, DML UPDATE/DELETE). Same `asyncio.to_thread` wrapper
  pattern as `run_dml`, returns rows as plain dicts.

### `app/services/ad_revenue_reconciliation_service.py` (new file)
- `reconcile_ad_revenue(project_id, dataset_id, report_date)` — two `SELECT`s (AdMob's per-ad_unit
  totals from `admob_daily_report`, our own per-ad_unit counts from `ad_impressions`), joined in
  Python by `ad_unit_id`. `discrepancy_percent = abs(admob - ours) / admob * 100`;
  `DISCREPANCY_THRESHOLD_PERCENT = 10.0` (documented as an untuned starting point, not validated
  against real traffic). `admob_impressions == 0` → `discrepancy_percent = None` (nothing to
  compare, not a misleading 0%/100%).

### `app/routers/jobs.py`
- New `POST /jobs/reconcile-ad-revenue`, same `X-CloudScheduler-JobName` header-check pattern as
  every other `/jobs` endpoint. **Must be scheduled after `admob-daily-report`** — it reads
  `admob_daily_report` for the same `report_date`, populated only by that other job. Flagged
  discrepancies are logged (`logger.warning`, Cloud Logging) and returned in the response — no
  dedicated audit table, matching `reconcile-purchases`' (PAY-002) existing precedent.

### Docs
`logic/ad-revenue-reconciliation.md` — new current-state reference: the two data sources, the
rewarded-only gap and why it's not hidden, the threshold, the special-case handling for zero AdMob
impressions, and the scheduling-order dependency.

---

## Testing

```bash
python -m pytest tests/test_ad_revenue_reconciliation_service.py tests/test_reconcile_ad_revenue_router.py -v
python -m pytest --ignore=tests/test_firestore_rules.py -q
```

New test files: `tests/test_ad_revenue_reconciliation_service.py` (5 cases — within-threshold not
flagged, large discrepancy flagged, zero-AdMob-impressions not compared, multiple ad_units handled
independently, no AdMob data returns empty) and `tests/test_reconcile_ad_revenue_router.py` (3
cases — header requirement, summary + flagged list in the response, no-data no-op).

---

## Results

```
======================== 134 passed ========================  (full suite, no regressions)
```

---

## Follow-ups / notes

- **Full per-format coverage requires client work, not scheduled yet.** Either (a) Godot wires
  AdMob's `OnPaidEventListener` for every ad format and sends each impression to a new backend
  endpoint (matching this codebase's "client always through FastAPI" convention), or (b) Firebase
  Analytics → BigQuery export is configured and a transform step reshapes it into `ad_impressions`.
  Neither exists today — interstitial/banner ad_units will keep showing ~100% discrepancy in this
  job's output until one does. Not a bug; see `logic/ad-revenue-reconciliation.md`.
- **Cloud Scheduler job not created yet** — unlike T-123's purge job, this one wasn't set up against
  dev/prod as part of this pass. Needs a schedule placed *after* `admob-daily-report`'s.
- **10% discrepancy threshold is a starting guess**, not validated against real traffic — revisit
  once there's production data to tune against.
- **Revenue-based reconciliation (not just impression counts) needs the same client work** as the
  per-format coverage gap above — `ad_impressions.revenue_usd` is always `None` today.
