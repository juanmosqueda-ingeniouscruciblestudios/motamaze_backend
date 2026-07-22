import hashlib
from datetime import datetime, timedelta, timezone

from google.cloud import bigquery
from google.cloud.firestore import AsyncClient

from app.services import bq_streaming

GRACE_PERIOD_DAYS = 30

# Collections with no retention requirement — hard-deleted for the purged uid.
# entitlements is here (not anonymized): its doc ID IS the uid, so there's no
# way to "strip the identifier" without deleting it, and unlike purchases it's
# derived operational state (what the user currently owns), not a financial
# transaction record — nothing requires keeping it once the user is gone.
_HARD_DELETE_COLLECTIONS = ["progress", "lives", "entitlements", "season_progress", "achievement_progress"]

# BigQuery historical tables (DATA-001) with no retention need for a deleted
# user — rows fully removed. Same reasoning as the Firestore hard-delete set
# above: analytics/behavioral data, not a financial record.
# admob_daily_report and account_deletions are NOT here on purpose: the
# former is aggregate (ad_unit_id + country), no user_id column at all; the
# latter is this very deletion's own audit trail — deleting from it would
# erase the evidence that erasure occurred.
_BQ_HARD_DELETE_TABLES = [
    "login_events", "session_durations", "player_behavior",
    "ad_impressions", "entitlement_grants",
]

# Financial transaction ledger — anonymized (user_id replaced with a
# one-way hash), never deleted. Same GDPR Art.17(3)(b) reasoning as the
# Firestore `purchases` anonymization above (accounting/fraud audit).
_BQ_ANONYMIZE_TABLES = ["purchase_events"]


def _anon_bq_user_id(user_id: str) -> str:
    """One-way, deterministic — a deleted user's rows across tables still
    group together (useful for aggregate revenue reporting or a refund
    dispute audit) without being reversible to the real uid. Same SHA-256
    technique already used for Android purchase_token hashing
    (purchases/{doc_id})."""
    return "deleted_" + hashlib.sha256(user_id.encode()).hexdigest()[:16]


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


async def purge_user_bigquery_data(project_id: str, dataset_id: str, uid: str) -> list[str]:
    """Mirrors purge_user_firestore_data's split for the BigQuery historical
    tables (DATA-001): hard-deletes analytics/behavioral tables, anonymizes
    purchase_events (financial ledger — user_id is NOT NULL on every one of
    these tables, so "anonymize" means replacing it with a deterministic
    hash, not nulling it out).

    Runs after the 30-day grace period, so these rows are always well past
    BigQuery's streaming buffer window (rows inserted in roughly the last
    90 minutes can't be mutated by DML) — not expected to ever hit that
    restriction here, but a failure on one table doesn't stop the others:
    each DML call is independent, and the caller (jobs.py) catches any
    exception from this function as a whole and marks the deletion "failed"
    rather than reporting a silent partial success.
    """
    touched: list[str] = []

    for table in _BQ_HARD_DELETE_TABLES:
        affected = await bq_streaming.run_dml(
            f"DELETE FROM `{project_id}.{dataset_id}.{table}` WHERE user_id = @user_id",
            [bigquery.ScalarQueryParameter("user_id", "STRING", uid)],
        )
        if affected:
            touched.append(table)

    anon_id = _anon_bq_user_id(uid)
    for table in _BQ_ANONYMIZE_TABLES:
        affected = await bq_streaming.run_dml(
            f"UPDATE `{project_id}.{dataset_id}.{table}` SET user_id = @anon_id WHERE user_id = @user_id",
            [
                bigquery.ScalarQueryParameter("anon_id", "STRING", anon_id),
                bigquery.ScalarQueryParameter("user_id", "STRING", uid),
            ],
        )
        if affected:
            touched.append(table)

    return touched
