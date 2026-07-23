from datetime import datetime, timezone

from google.cloud.firestore import AsyncClient

from app.services import geo_service


async def find_and_recalc_aged_out_users(
    db: AsyncClient, now: datetime | None = None
) -> list[str]:
    """T-404: finds users whose DOB-derived is_child should have flipped to
    False by now, and applies that flip.

    Full `users` collection scan filtered in Python — same MVP-scale
    reasoning as T-123's find_users_due_for_purge (avoids a composite
    index, sidesteps a query needing multiple range/equality filters
    together).

    Filters to consent.is_child == True with birth_month/birth_year
    present. That presence check alone is sufficient to exclude Brazil
    store-signal users, with no need to also check country_code: ST-01
    only ever writes birth_month/birth_year in the DOB-decides branch of
    POST /auth/age-verify, never in the BR-signal branch — so a BR user
    whose is_child came from the store signal simply has no birth fields
    to match here, by construction, and is never re-derived from a DOB
    they may not have even submitted.

    Naturally idempotent: once a user's is_child flips to False, the
    consent.is_child == True filter excludes them from every future run —
    no separate dedup/marker needed.
    """
    now = now or datetime.now(timezone.utc)
    today = now.date()

    docs = await db.collection("users").get()
    aged_out: list[str] = []

    for doc in docs:
        data = doc.to_dict() or {}
        consent = data.get("consent") or {}
        if consent.get("is_child") is not True:
            continue
        birth_month = consent.get("birth_month")
        birth_year = consent.get("birth_year")
        if birth_month is None or birth_year is None:
            continue

        threshold = consent.get("consent_age_threshold", 13)
        if geo_service.has_aged_out(birth_month, birth_year, threshold, today):
            update = geo_service.age_gate_update(False, now)
            await db.collection("users").document(doc.id).update(update)
            aged_out.append(doc.id)

    return aged_out
