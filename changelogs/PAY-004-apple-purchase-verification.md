# PAY-004 — Real Apple purchase verification (App Store Server Library)

| Field | Value |
|---|---|
| **Type** | Feature / Security fix |
| **Priority** | High — the stub it replaces was a live fraud hole |
| **Status** | ✅ Done — 2026-07-18 |
| **Date** | 2026-07-18 |
| **Workstream** | Payments |
| **Depends-on** | AUTH-004 (unrelated dependency-wise, but same iOS initiative) |
| **Commit** | `15b6e0b` |

---

## Description

`POST /payments/ios/verify` and `POST /payments/ios/refund-notification` were stubs: `ios_verify` never called Apple, never touched Firestore, and unconditionally returned `verified`/`granted` for any client-submitted `product_id` — a live fraud hole if reachable. `ios_refund_notification` read the request and did nothing.

## Implementation

- New `app/services/app_store_api.py`, using Apple's official `app-store-server-library`: `SignedDataVerifier` verifies a StoreKit 2 signed transaction JWS **purely locally** against Apple's pinned root certs (bundled in `app/certs/apple/`, publicly downloadable, no App Store Connect credentials needed for this — those are only for outbound API calls like refund-history polling, explicitly out of scope).
- **Security fix to the contract:** `IosVerifyRequest` now only accepts `{signed_transaction, session_id}` — `transaction_id`/`product_id` are no longer trusted from the client, since `SignedDataVerifier` doesn't cross-check a client-supplied `product_id` against the JWS the way Play's keyed purchase lookup does. Entitlement type is derived from the verified payload only. This is a breaking change from what `REST-001` originally documented — communicated to Juan for his T-IOS-2 Godot/StoreKit2 client work.
- `ios_refund_notification` now verifies real ASSN v2 notifications (direct HTTPS push from Apple, not Pub/Sub like Android) and revokes entitlements via the already-platform-agnostic `reconcile_service.revoke_entitlement`.
- Added a `platform` field to `purchases/{doc_id}` for **both** platforms (`android_verify` was missing it too) and documented that collection in `docs/DATA_MODEL.md` for the first time — it existed since PAY-001 but was never written up.
- Extracted `_grant_entitlement()` out of `android_verify` so both platforms share one entitlement-granting code path.
- `app/config.py`: added `apple_environment` (Sandbox/Production) and `apple_app_apple_id` (Production-only, deferred until T-IOS-3/App Store Connect app creation).

## Testing

New `tests/test_payments_router.py` — 16/16 passing. Since `SignedDataVerifier`'s trust chain is pinned to Apple's real root certs (unlike Sign-in-with-Apple's JWKS, which could be mocked), tests mock at the `app_store_api` module boundary rather than attempting real cryptographic verification.

## Follow-ups / notes

- `AppStoreServerAPIClient` / refund-history polling reconciliation — deferred, needs Team ID/Key ID/`.p8` key like AUTH-004 deferred those for login.
- `app/routers/jobs.py`'s `/jobs/reconcile-purchases` stays Android-only — nothing Apple to reconcile via polling yet.
- Registering the live ASSN v2 webhook URL in App Store Connect and setting `apple_app_apple_id` for real are both blocked on T-IOS-3.
