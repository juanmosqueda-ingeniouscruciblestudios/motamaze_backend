# Google Play Console — Data Safety Section (DRAFT)

**This document is an internal working aid for completing the Play Console Data Safety form. The
Play Console itself is the authoritative source when category definitions differ from this document.**

Status: ready to submit now, for the app's CURRENT shipped state — built from T-405's SDK/data
research (privacy notice + architecture doc). Apple's Privacy Nutrition Label is intentionally out
of scope here (Google Play only, for now — separate legal review in progress).

**Two-stage submission — read before entering data in Play Console.** Google's own guidance:
*"You should update your Data safety section when there are relevant changes to the data practices
of the app"* and *"Your Data safety form responses must remain accurate and complete at all
times"* (support.google.com/googleplay/android-developer/answer/10787469). There is no requirement
to wait until every SDK is integrated before the first submission — the correct process is the
opposite: submit now describing what the app actually does today, then edit the two rows below in
Play Console the day each dependent SDK ships. No fixed grace-period deadline is stated in Google's
docs, but the form must never describe a practice that isn't live yet — so two rows in Part 1 below
are written for **today's state**, not the end-state architecture. Part 1B gives the exact values
to flip once T-261 (AdMob) and T-310 (Crashlytics) ship.

**Some categories apply only when a user chooses the associated feature** (e.g. purchase history
only exists after a purchase; share-card data only exists after tapping Share; guardian email only
exists for protected/underage accounts) — "Collected: Yes" means "collected when that feature is
used," not "collected from every user on day one."

---

# Part 1 — Answers (for direct entry into Play Console)

Every cell below is the recommended value to enter. No explanations here — see Part 2 for reasoning
and sourcing behind any answer.

## Top-level declarations

| Question | Answer |
|---|---|
| Does your app collect or share any of the required user data types? | Yes |
| Is all user data collected by your app encrypted in transit? | Yes |
| Do you provide a way for users to request data deletion? | Yes |
| Does your app follow the Play Families Policy? | No |
| Has your app undergone an independent security review? | No |

## Personal info

| Data type | Collected | Shared with 3rd party | Optional/Required | Purpose(s) |
|---|---|---|---|---|
| Name (display name) | Yes | No | Required | App functionality |
| Email address | Yes | No | Required | Account management, App functionality |
| User IDs | Yes | No | Required | App functionality, Account management |
| Other info (age/consent status) | Yes | No | Required | App functionality, Fraud prevention/compliance |
| Address | No | — | — | — |
| Phone number | No | — | — | — |

## Photos

| Data type | Collected | Shared | Optional/Required | Purpose(s) |
|---|---|---|---|---|
| Photos (profile photo) | No | No | Optional | App functionality |

## Financial info

| Data type | Collected | Shared | Optional/Required | Purpose(s) |
|---|---|---|---|---|
| Purchase history | Yes | No | Required | App functionality, Fraud prevention/security, Account management |
| Payment info (card details) | No | — | — | — |

## App activity

| Data type | Collected | Shared | Optional/Required | Purpose(s) |
|---|---|---|---|---|
| App interactions (gameplay) | Yes | No | Required | App functionality, Analytics |
| Other user-generated content (share-score card) | Yes | No | Optional | App functionality |
| In-app search history | N/A | — | — | — |

## App info and performance

**Submit now with:**

| Data type | Collected | Shared | Optional/Required | Purpose(s) |
|---|---|---|---|---|
| Crash logs | No | — | — | — |
| Diagnostics | No | — | — | — |

*(Crashlytics — T-310 — hasn't shipped. See Part 1B for the values to enter once it does.)*

## Device or other IDs

**Submit now with:**

| Data type | Collected | Shared | Optional/Required | Purpose(s) |
|---|---|---|---|---|
| Device or other IDs (Advertising ID / App Set ID) | No | — | — | — |

*(AdMob — T-261 — hasn't shipped, so no Advertising ID is collected yet. See Part 1B for the
values to enter once it does. Tenjin is NOT part of this update — see Part 1B note.)*

## Location

| Data type | Collected | Shared | Optional/Required | Purpose(s) |
|---|---|---|---|---|
| Approximate location (IP-derived) | Yes | No | Required | Fraud prevention/security/compliance, App functionality |
| Precise location | No | — | — | — |

## Not applicable

Health and fitness, Messages, Audio files, Files and docs, Calendar, Contacts, Web browsing — not collected by MotaMaze.

---

# Part 1B — Values to add later (not for today's submission)

Two separate updates, each triggered by its own ticket shipping. Don't wait for both — update Play
Console as soon as each one individually goes live. Whoever picks up T-261 or T-310 should return
to this file, take the exact table below for their ticket, and enter it in Play Console → App
content → Data safety → edit. Re-verify each row against the actually-shipped SDK behavior first —
see Part 2's verification checklist below for what to check before entering these.

## When T-310 (Crashlytics) ships

Replace the "App info and performance" table in Part 1 with:

| Data type | Collected | Shared | Optional/Required | Purpose(s) |
|---|---|---|---|---|
| Crash logs | Yes | No | Required | Analytics |
| Diagnostics | Yes | No | Required | App functionality, Analytics |

Reasoning for Required (not Optional): the architecture has no crash-reporting opt-out anywhere in
the design — nothing for a user to decline — see Part 2 for the full sourcing on this.

## When T-261 (AdMob) ships

Replace the "Device or other IDs" table in Part 1 with:

| Data type | Collected | Shared | Optional/Required | Purpose(s) |
|---|---|---|---|---|
| Device or other IDs (Advertising ID / App Set ID) | Yes | Yes — AdMob | Required | Advertising or marketing, Analytics |

**Do not add Tenjin to the "Shared" column at this point.** Tenjin-wrapped share links are
post-MVP (Decision L / Option B chose a direct URL with no attribution for MVP; Tenjin is v1.1
scope with no ticket yet). Add Tenjin to this row only when that work actually ships, under its own
ticket — not automatically alongside T-261.

## T-414 (Firebase Blaze) — no update needed here

Firebase Blaze is a billing-plan upgrade (pay-as-you-go), not a new data flow or SDK integration.
It doesn't change what data the app collects or shares, so it has no Data Safety form impact and
nothing in this document depends on it.

---

# Part 2 — Engineering / verification notes (not for direct entry)

**Currently identified third-party data transfers: Advertising ID → AdMob, Tenjin (Tenjin deferred, see Part 1B).**

Note on the rest of this section: Google never states "Cloudinary image generation is not shared" or
"displaying an OAuth photo by URL is not collection" — those are reasoned interpretations of Google's
general framework applied to MotaMaze's specific implementation, not verbatim confirmations of this
exact scenario. Labeled "Recommended," not "Resolved," below for that reason — strong enough to act
on, not strong enough to treat as beyond question if Google's guidance shifts.

## Pre-submission sanity-check list

- [x] **Crashlytics (Crash logs, Diagnostics) — Recommended: No** (Shared column). Firebase's own
      official Play Data Safety disclosure page states: *"Firebase does not transfer this data to
      third parties except: to third-party subprocessors that assist us in providing Firebase
      services."* Same service-provider pattern as Play Billing/Cloudinary — a direct, strong source,
      though it doesn't literally say "answer No on the Data Safety form." Source:
      firebase.google.com/docs/android/play-data-disclosure

- [x] **Crash logs — Required, resolved (Optional/Required column), changed from the earlier draft.**
      Google's test is whether a user can decline the data and still use core features. The
      architecture doc's own infrastructure table (§5) states Crashlytics is "**Required**; integrate
      ... before any mobile testing," and the SDK init sequence initializes it unconditionally at
      step 5 with no consent gate — unlike the CCPA ad opt-out, which the architecture explicitly
      designs *with* a mechanism (in-app toggle, Firestore persistence, audit trail). No opt-out for
      crash reporting exists anywhere in the design, so there's nothing for a user to "decline." That
      settles this from the actual implementation, not a Play Console guess — if a crash-reporting
      opt-out is ever added, revisit this.

- [x] **Profile photo — Recommended: No. Confirmed against actual code**, not just the data model
      schema. `app/services/auth_service.py`, `upsert_user()`: `photo_url` arrives as a plain
      `str | None` parameter and is written directly to Firestore (`"photo_url": photo_url`) — no
      HTTP fetch, no image download, no re-hosting anywhere in the auth flow. The backend genuinely
      only ever stores the URL string Google/Apple supplies. Google's general collection principle
      — *"'Collect' means transmitting data from your app off a user's device"* — supports "No" given
      this confirmed behavior. Google's page doesn't address URL-reference display explicitly, so
      this is still a reasoned application of the principle rather than a verbatim Google statement
      about this exact scenario — same caveat as Cloudinary above, but the underlying fact is now
      code-verified, not inferred from schema alone.

- [x] **Cloudinary — Recommended: No.** Confirmed against `_og_image_url()` in `app/routers/social.py`
      — only `score` and `level_reached` (plain integers) are sent as URL text-overlay parameters,
      nothing player-identifying. The code fact is fully confirmed; whether that fact means "No" on
      the form is Google's general service-provider framework applied here, not a Google statement
      about Cloudinary by name.

- [x] **Approximate location / IP-derived jurisdiction — Recommended: declare under Approximate
      Location.** Google's official FAQ: *"where developers use IP addresses as a means to determine
      location, then that data type should be declared."* The category's core definition centers on
      device/permission signals rather than IP specifically, so "recommended" rather than "resolved"
      — strong support, not verbatim-identical wording.

- [ ] **AdMob (T-261) and Crashlytics (T-310) — verify shipped code against architecture spec, not
      just re-run this document.** Every "Recommended" answer above for these two is based on what
      the architecture *says* will happen — there's no code yet to check, unlike Cloudinary and
      Profile photo, which are verified against actual shipped code. This project already has one
      confirmed case of shipped code diverging from spec (purchase-token hashing, flagged separately
      to Saúl) — so this isn't a formality. Once built, confirm: (1) AdMob only shares Advertising ID
      with AdMob + Tenjin as declared, and the SDK init order actually gates on consent before AdMob
      loads, matching the architecture's stated sequence; (2) the Godot-Firebase Crashlytics plugin
      only collects the standard crash/diagnostic set and doesn't bundle anything extra by default;
      (3) no crash-reporting opt-out got added during implementation that wasn't in the spec (would
      flip Crash logs back to Optional).
      **Firebase Blaze (T-414) does not need a re-check here** — it's a billing-plan upgrade, not a
      new data flow; it doesn't belong in this checklist.

      **Once verified, enter the values from Part 1B** for whichever ticket shipped — don't
      re-derive them from scratch.

## Keep in sync

This document and the published privacy notice describe the same underlying data practices. If one
changes, review the other. Part 1 reflects the CURRENT submission; Part 1B tracks what's still
owed and by which ticket — keep Part 1B's checkboxes below updated as each lands.

- [ ] T-310 (Crashlytics) shipped → Part 1B "Crashlytics" values entered in Play Console
- [ ] T-261 (AdMob) shipped → Part 1B "AdMob" values entered in Play Console (Tenjin excluded per note)
