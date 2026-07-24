# T-240 — Backend /store/catalog + promotions (server-resolved, audience-segmented)

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | Medium — unblocks T-241 (store UI, client), T-243 (equip-skin), T-244 (Remote Config tunables) |
| **Status** | ✅ Done — ST-01–05 |
| **Date** | 2026-07-24 |
| **Engine** | FastAPI backend (no client work — T-241 is the separate client ticket) |
| **Depends-on** | T-112 (Firestore schema ✅), T-210 (progress backend ✅) — both already Done, no blockers |

---

## Description

Server-resolved product catalog with audience-segmented promotions (architecture doc §9A.4).
Pricing/offers must be controlled server-side and gacha-free per Brazil's Digital ECA — this is the
source of truth the store UI (T-241, client) will render from.

**Acceptance criteria:**
- [x] `/store/catalog` returns a server-resolved catalog (direct-price, no gacha)
- [x] Audience-segmented promotions, config-driven (Firestore, not Remote Config — see below)
- [x] Matches REST-001's API contract exactly

---

## Previous state (before this change)

Nothing existed. `GET /store/catalog` was a bare TODO comment in `app/routers/game.py`
(`# GET /store/catalog — GAME-003 (T-240)`, no implementation). The architecture doc had already
specified the exact Firestore schema (`config/catalog`, `config/promotions/{promo_id}`) and the
resolution algorithm (§9A.4) — never built. 3 generic subitems existed on the Monday ticket since
2026-06-17 (a literal restatement of the acceptance criteria, same pattern found on T-123/T-302's
original subitems) — replaced with the 5 detailed ones this changelog covers.

---

## Implementation details

### ST-01 — `scripts/seed_store_catalog.py` (new)
Idempotent Firestore seed for `config/catalog` — real production config, not test data (different
category from `scripts/seed_bq_test_data.py`). **Scope decision made with the user:** only products
with a price confirmed in *both* the architecture doc's own pricing table (2026-06-04, lines
737-740) and REST-001's contract are seeded — `lives_pack_5` ($0.99) and `no_ads` ($2.99).
`skin_gold`, `skin_silver`, and the large life pack are still marked `TBD` in the architecture
doc — REST-001's example payload uses placeholder numbers for those to illustrate the response
shape, not approved pricing. Excluded rather than guessed, since a wrong price would show a real
charge to players. `catalog_version` (date of last seed run) was added in ST-03 after discovering
the original seed omitted it — see ST-03 below.

### ST-02 — `app/services/store_service.py`, `resolve_user_segment()`
Pure function deriving a user's audience segment (`"non_payer" | "lapsed" | "new" | "all")
server-side — the architecture doc explicitly requires this (never trust a client-claimed segment).
Thresholds are initial defaults confirmed with the user 2026-07-23 (`NEW_USER_WINDOW_DAYS=3`,
`LAPSED_WINDOW_DAYS=14`), not final — adjustable later via T-244 without code changes. Priority when
a user qualifies for more than one segment at once: `non_payer > lapsed > new > "all"`. A missing
`last_session_at` is deliberately **not** treated as `lapsed` — absence of session data isn't
evidence a user actually stopped engaging.

### ST-03 — `GET /store/catalog` (`app/routers/game.py`) + `store_service.owned_product_ids()` / `resolve_catalog_products()`
- `owned_product_ids()`: non-consumables only (a consumable is never "owned" — REST-001's own
  example always shows `owned: false` for `lives_pack_5`). Maps `no_ads` → the entitlement flag,
  `skin_*` → membership in `entitlements.skins`.
- `resolve_catalog_products()`: pure — matches active promotions to products by `product_id` +
  `active` + `[starts_at, ends_at]` containing server-`now` (inclusive, never a client clock) +
  `audience` in `(user_segment, "all")`. Tie-break when multiple promotions match the same product:
  most-specific audience wins first, then highest `discount_percent` as a deterministic final
  tiebreak.
- Router wires it together: reads `config/catalog`, the full `promotions` collection (flat top-level
  collection, not literally nested under `config` — the architecture doc's `config/promotions/{id}`
  shorthand doesn't require real Firestore subcollection nesting), `users/{uid}` for `created_at`,
  `entitlements/{uid}`, and the most recent `sessions` doc
  (`where(uid=).order_by(started_at DESC).limit(1)`) for `last_session_at`.
- **Bug found and fixed during this pass:** ST-01's seed never wrote `catalog_version`, which the
  endpoint needs to return per REST-001. Fixed in the seed script (bumps to today's date on every
  run) and re-seeded in dev.

### ST-04 — Test gap review
Reviewed consolidated coverage across ST-01–03 (same exercise as T-123/T-404) and found: `has_paid`
was only tested via the `no_ads` flag (not `life_packs_total` alone); the router's actual sessions
query was never exercised end-to-end; nothing confirmed the query picks the *most recent* session
when several exist; the promotion date range was never tested at its exact inclusive boundaries; an
orphaned promotion (referencing a `product_id` not in the catalog) was never confirmed to be ignored
rather than crashing. 7 tests added to close these.

### Docs
`docs/DATA_MODEL.md` — new `config/catalog` and `promotions/{promo_id}` sections, including the
`price_tier` vs `price_usd` reconciliation. New `logic/store-catalog.md` — current-state reference
for segmentation + resolution + tie-break logic.

---

## Testing

```bash
python -m pytest --ignore=tests/test_firestore_rules.py -q
```

New test files: `tests/test_store_service.py` (pure-function coverage — segmentation, ownership,
promotion matching, tie-break, date boundaries), `tests/test_store_router.py` (integration —
end-to-end catalog resolution, session-query correctness, orphaned-promotion handling).

---

## Results

```
======================== 189 passed ========================  (full suite, no regressions across ST-01–04)
```

Dev seed verified: `config/catalog seeded in project=motamaze-dev (catalog_version=2026-07-24)` — 2
products.

---

## Follow-ups / notes

- **`skin_gold`, `skin_silver`, large life pack not seeded** — pending real pricing from Juan.
- **No promotions created yet** — `promotions` collection exists empty; the first real promo will be
  the first end-to-end proof of the tie-break logic against real data.
- **`price_tier` (architecture doc) superseded by `price_usd` (REST-001, signed-off contract)** — see
  `logic/store-catalog.md` for the full reasoning.
- **Segmentation thresholds unvalidated against real traffic** — revisit once there's production
  usage data, likely as part of T-244's Remote Config migration.
- **PROD not seeded yet** — deferred until this endpoint itself is live in prod, per the user's call,
  so there's no orphaned config with nothing serving it.
- **No client (Godot) work in this ticket** — T-241 (store UI) is the separate client-side ticket
  that will render from this endpoint.
