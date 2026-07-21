# AUTH-004 — Sign in with Apple + multi-provider user schema

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | High — No-Go item for iOS launch |
| **Status** | ✅ Done — 2026-07-18 |
| **Date** | 2026-07-18 |
| **Workstream** | Auth Backend |
| **Depends-on** | T-112 (Firestore users schema), T-120 (POST /auth/login) |
| **Commit** | `73fbf45` |

---

## Description

iOS support was added to the MVP (architecture update from Juan, 2026-07-17), requiring Sign in with Apple alongside the existing Google OAuth login. `POST /auth/login` already had a `provider` field in its contract (`REST-001`) and an `apple` branch stubbed to `501 NOT_IMPLEMENTED` — this fills it in, plus fixes two real bugs found while doing so.

## Implementation

- `app/services/auth_service.py`: new `verify_apple_token()` — fetches/caches Apple's JWKS (`https://appleid.apple.com/auth/keys`), mirrors the JWKS-fetch-and-cache pattern already used for Firebase App Check in `leaderboard.py`.
- `upsert_user()`: now persists `provider` on `users/{uid}` (previously accepted the argument and silently dropped it); added `AUTH_PROVIDER_MISMATCH` guard (409) if a doc's stored provider differs from the incoming login's provider; only overwrites `email`/`display_name`/`photo_url` when the incoming value is truthy (Apple omits name after the first login).
- `create_session()`: now persists `provider` on `sessions/{session_id}` (same silent-drop bug as above).
- **Bug fix:** `POST /auth/refresh` hardcoded `provider="google"` on every reissued access token regardless of how the user actually logged in — dead code computed the real value then ignored it. Fixed to read `provider` from the session doc, with a `"google"` fallback for pre-migration sessions (no backfill needed, they age out via the 14-day session TTL).
- **Design decision:** user doc IDs stay a bare `sub` (no provider prefix) — Google and Apple `sub` formats are structurally disjoint (numeric vs. alphanumeric-with-dots), so collision risk is negligible, and this avoids migrating `sessions`/`revoked_jtis`/`progress`/`lives`/`entitlements`/`season_progress`/`achievement_progress`. Documented in `docs/DATA_MODEL.md` along with the accepted no-account-linking limitation (Google and Apple logins for the same person produce two independent accounts in this pass).
- `app/config.py`: added `apple_bundle_id` (the `aud` claim on a native iOS identity token is the app's bundle ID).

## Testing

No test coverage existed for the auth module before this ticket. New: `tests/conftest.py` (in-memory Firestore double + RSA keypair fixtures for signing test JWTs, reusable infra), `tests/test_auth_service.py`, `tests/test_auth_router.py` — 17/17 passing, including a regression test proving the `/auth/refresh` provider bug is fixed (login as Apple, refresh, decode the new access token, assert `provider == "apple"`).

## Follow-ups / notes

- No cross-provider account linking — flagged as a known limitation, worth its own future ticket if needed.
- Apple App Store Server API credentials (Team ID / Key ID / `.p8` key) were explicitly **not** added here — not needed for login verification, only for payments (see PAY-004).
