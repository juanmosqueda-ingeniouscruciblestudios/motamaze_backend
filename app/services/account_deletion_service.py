from datetime import datetime, timedelta, timezone

from google.cloud.firestore import AsyncClient

GRACE_PERIOD_DAYS = 30

# Collections with no retention requirement — hard-deleted for the purged uid.
# entitlements is here (not anonymized): its doc ID IS the uid, so there's no
# way to "strip the identifier" without deleting it, and unlike purchases it's
# derived operational state (what the user currently owns), not a financial
# transaction record — nothing requires keeping it once the user is gone.
_HARD_DELETE_COLLECTIONS = ["progress", "lives", "entitlements", "season_progress", "achievement_progress"]


async def find_users_due_for_purge(db: AsyncClient, now: datetime | None = None) -> list[str]:
    """Users whose 30-day grace period has elapsed without being cancelled.

    Full collection scan, filtered in Python — MVP scale (<1,000 users per
    soft launch, same assumption used elsewhere in this codebase). Avoids a
    composite index and sidesteps a Firestore inequality query against a
    field (`delete_requested_at`) that's `None` for most documents. Revisit
    if the user base grows significantly.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=GRACE_PERIOD_DAYS)
    docs = await db.collection("users").get()
    due: list[str] = []
    for doc in docs:
        requested_at = (doc.to_dict() or {}).get("delete_requested_at")
        if requested_at is not None and requested_at <= cutoff:
            due.append(doc.id)
    return due


async def purge_user_firestore_data(
    db: AsyncClient, uid: str, now: datetime | None = None
) -> list[str]:
    """Hard-deletes uid-keyed data with no retention need, anonymizes
    `purchases` (financial transaction ledger — kept for accounting/fraud
    audit under GDPR Art.17(3)(b), decision 2026-07-22), deletes any
    remaining session docs, and finally the `users/{uid}` doc itself (last —
    it's the source-of-truth flag for "does this account still exist", so
    deleting it makes the purge irreversible and must be the final step).

    Returns the collections touched, for the account_deletions
    `tables_purged` audit trail. BigQuery historical-table purge and the
    final `status="completed"` update are a separate step — see
    `app/routers/jobs.py`.

    Deliberately excluded (not an oversight):
    - `revoked_jtis`: already has its own 14-day TTL cleanup — any JTIs tied
      to this user are long past that TTL by the time the 30-day grace
      period ends.
    - `shares/{token}`: `uid` is internal-only, never in the public response
      (`GET /s/{token}`), and the collection already expires with the season.
    - `leaderboard_cache`: a stale entry can persist for up to 5 minutes (its
      own Cloud Scheduler refresh interval) — self-heals, not worth
      special-casing in this job.
    """
    now = now or datetime.now(timezone.utc)
    touched: list[str] = []

    for collection in _HARD_DELETE_COLLECTIONS:
        ref = db.collection(collection).document(uid)
        if (await ref.get()).exists:
            await ref.delete()
            touched.append(collection)

    session_docs = await db.collection("sessions").where("uid", "==", uid).get()
    for s in session_docs:
        await db.collection("sessions").document(s.id).delete()
    if session_docs:
        touched.append("sessions")

    purchase_docs = await db.collection("purchases").where("uid", "==", uid).get()
    for p in purchase_docs:
        await db.collection("purchases").document(p.id).set(
            {"uid": None, "anonymized_at": now}, merge=True
        )
    if purchase_docs:
        touched.append("purchases")

    await db.collection("users").document(uid).delete()
    touched.append("users")

    return touched
