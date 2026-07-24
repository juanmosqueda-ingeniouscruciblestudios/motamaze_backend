from datetime import datetime, timedelta

# T-240: initial defaults confirmed with the user 2026-07-23 — not final,
# adjustable later via T-244 (Remote Config tunables) without code changes.
NEW_USER_WINDOW_DAYS = 3
LAPSED_WINDOW_DAYS = 14


def resolve_user_segment(
    created_at: datetime,
    last_session_at: datetime | None,
    has_paid: bool,
    now: datetime,
) -> str:
    """T-240: derives a user's promotion audience segment server-side —
    never trust a client-claimed segment (architecture doc §9A.4).

    Priority when a user qualifies for more than one segment at once (e.g.
    a brand-new user who has also never paid): non_payer > lapsed > new >
    "all". The most specific segment wins, checked in that order.

    - non_payer: has never completed a purchase (caller derives has_paid
      from entitlements/{uid} — a single doc read, cheaper than querying
      the purchases collection on every catalog request).
    - lapsed: last session was LAPSED_WINDOW_DAYS+ ago. last_session_at
      being None (no session on record) is NOT treated as lapsed — that
      would mislabel a user based on absent data rather than evidence of
      actually stopping; it just skips this check.
    - new: account created within NEW_USER_WINDOW_DAYS.
    - "all": fallback when none of the above apply.
    """
    if not has_paid:
        return "non_payer"
    if last_session_at is not None and now - last_session_at >= timedelta(days=LAPSED_WINDOW_DAYS):
        return "lapsed"
    if now - created_at <= timedelta(days=NEW_USER_WINDOW_DAYS):
        return "new"
    return "all"
