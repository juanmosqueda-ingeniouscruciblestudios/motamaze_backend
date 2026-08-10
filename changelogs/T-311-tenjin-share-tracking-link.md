# T-311 — Tenjin share tracking link (backend scope)

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | Medium — enables referral attribution for T-440 share links |
| **Status** | Done (backend scope only — see "Scope note" below). ST-01/02/06/07 ✅ 2026-08-10; ST-04 Stuck (needs Juan's SDK, ST-03/05); ST-03/05 open (Juan, client) |
| **Date** | 2026-07-21 (backend URL wrapping); 2026-08-10 (fraud filtering + Data Safety review) |
| **Workstream** | External Services |
| **Depends-on** | T-440 (`POST /share/create`), Decision L resolution |
| **Blocks** | Nothing — falls back to pre-Decision-L behavior until the Tenjin dashboard link exists |

---

## Scope note — this is not the full T-311 ticket

The Monday ticket title is *"Tenjin SDK integration (client) + backend fraud filtering (before first paid UA)"*. Research before implementation (`rnd_research/2026-06-04_motamaze-architecture-validation.md:670-676`) found the original architecture explicitly states client SDK install/revenue event firing needs **"No backend changes required"** — that part is Godot/client scope (Juan), not touched here. UA fraud filtering itself happens on Tenjin's SaaS side once the SDK is live — no MotaMaze backend code for that either.

**What this pass actually implements is the one genuine backend deliverable**, driven by Decision L (`changelogs/REST-001-rest-api-contract.md:1962-1979`): wrapping `POST /share/create`'s `share_url` in a Tenjin tracking link so a new install from a shared score can be attributed back to the sharing player (needed for the referral-reward model Juan described in that decision thread).

**Still open, not this ticket's backend scope:**
- Godot client: Tenjin SDK integration, install/revenue event firing (Juan).
- Tenjin dashboard: create the actual account/app/tracking link — `tenjin_share_tracking_link` stays empty (falls back to direct URL) until this happens.
- Client-side: read the `deeplink_url` context Tenjin's SDK hands back on first launch and route to the shared content.

---

## Description

Decision L (Option A vs B, negotiated in `REST-001` since 2026-06-24) was confirmed today by Juan: **Option A**. `share_url` returned by `POST /share/create` and stored on `shares/{token}` should be a Tenjin tracking link, not a bare direct URL.

**How Tenjin tracking links actually work (researched before implementing — see `tenjin.com/docs/deferred-deep-linking`, `tenjin.com/docs/deep-linking`, `tenjin.com/docs/automation-apis`):** a tracking link is a **single static URL created once per channel in Tenjin's dashboard** — there is no API to dynamically mint a new tracking link per request (the Automation API only covers campaign management and reporting metrics). Per-share context rides on a `deeplink_url` query parameter appended to that static link; Tenjin's SDK hands the deeplink value back to the client app on first launch after install. So the backend implementation is pure URL construction — no API key, no outbound HTTP call to Tenjin, no new service module.

---

## Implementation

### `app/config.py` / `.env.example`
```python
tenjin_share_tracking_link: str = ""
```
Empty by default — no Tenjin account/dashboard link exists yet (confirmed via repo-wide grep before this ticket: zero prior Tenjin config anywhere).

### `app/routers/social.py`
```python
def _tenjin_share_url(settings: Settings, token: str) -> str:
    direct_url = f"{settings.share_base_url}/s/{token}"
    if not settings.tenjin_share_tracking_link:
        return direct_url  # Tenjin dashboard link not configured yet
    deeplink = urllib.parse.quote(direct_url, safe="")
    return f"{settings.tenjin_share_tracking_link}?deeplink_url={deeplink}"
```
`share_create` now calls this instead of building `share_url` inline. Graceful fallback: ships working today (Option B behavior) and upgrades silently to Option A the moment `tenjin_share_tracking_link` is set — no code change needed at that point, no coordination required with a deploy.

---

## Testing

`tests/test_social_router.py` — 2 new tests:
```
[PASS] test_share_create_falls_back_to_direct_url_when_tenjin_unset — regression guard, confirms unchanged behavior when unconfigured
[PASS] test_share_create_uses_tenjin_tracking_link_when_configured — share_url = "{base}?deeplink_url={quoted direct url}", verified in both the API response and the stored Firestore doc
```
Full suite: 65/65 passing.

---

## Docs corrected (found stale during research, actively contradicted today's decision)

- `docs/GOOGLE_PLAY_DATA_SAFETY.md` — previously stated *"Decision L / Option B chose a direct URL... Tenjin is v1.1 scope with no ticket yet"* — factually wrong (T-311 existed as an active dated ticket the whole time); this looks like a stale speculative note that was never corrected after being written, not a real prior decision being reversed now. Corrected, and flagged that the actual Data Safety form entry for Tenjin still needs a real compliance review once the dashboard link goes live (not done in this pass — that's a judgment call, not a mechanical fix).
- `docs/DATA_MODEL.md` (`shares/{token}.share_url` note) — updated from "sin resultado registrado" to resolved.
- `changelogs/T-440-share-score-backend.md` — updated the T-311 follow-up line (was: "meeting scheduled 2026-07-27"; decision actually landed before that meeting).
- `changelogs/REST-001-rest-api-contract.md` — Decision L section now has its resolution appended.

## Follow-ups / notes

- **Not done here:** create the actual Tenjin account, app, and organic/referral tracking link in Tenjin's dashboard (Juan/Saul) — required before `tenjin_share_tracking_link` can be set to a real value in `.env`/Secret Manager.
- **Not done here:** Godot client Tenjin SDK integration (Juan) — install event on first launch, revenue events piggybacking on the existing `ad_impression_recorded` signal (`Scripts/autoloads/events.gd`), following the `Scripts/services/<domain>/` real+null service pattern already used for ads/auth/payments.
- **Not done here:** Data Safety form review for the Tenjin data flow (see doc correction above).
- Recommend splitting the Monday ticket T-311 into its client (Juan) and backend (this, done) pieces if it isn't already tracked that way, so "Done" doesn't get misread as covering the client SDK work too.

## 2026-08-10 — ST-06 (fraud filtering) and ST-07 (Data Safety) closed

**ST-07:** written into `docs/GOOGLE_PLAY_DATA_SAFETY.md` — see that file's new "When T-311's
Tenjin tracking link goes live" section. Split into Phase 1 (bare tracking-link click — IP +
User-Agent only, this review) and Phase 2 (future Tenjin SDK, adds Advertising ID/IDFA — deferred to
its own review when ST-03 ships).

**ST-06:** logged into the real Tenjin dashboard (`dashboard.tenjin.com`) with Saul to check what's
actually configurable — public docs describe a "Fraud" tab that doesn't exist on this account's
plan/tier. The real tool is **Configure → Site ID Optimizations**, a reactive blocklist (block known-
bad site IDs), not a proactive rules engine. Empty today because there's no campaign traffic yet —
correct, expected state, nothing to configure without real data. Tenjin's baseline fraud protection
(MTTI, click-injection/spamming detection) is part of the attribution engine and applies
automatically, no dashboard config needed.

**Resolution:** nothing left to do here today. The actual blocklist work moved to where it
chronologically belongs — T-502 (Google App Campaigns LATAM, the paid UA campaign itself) got a new
ST-01 subtask (Saul) to build the Site ID blocklist from real data right before that campaign
launches. T-502's own title already promised "Tenjin fraud filter live" but had zero subtasks
breaking that down.
