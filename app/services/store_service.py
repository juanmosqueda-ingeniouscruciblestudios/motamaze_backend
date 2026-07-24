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


def owned_product_ids(entitlements: dict, products: list[dict]) -> set[str]:
    """Non-consumables only — a consumable is never "owned", it's bought
    again each time (REST-001's own example always shows owned=false for
    lives_pack_5). Mirrors reconcile_service._infer_entitlement's product_id
    conventions (no_ads flag, skins list) rather than re-deriving them."""
    skins = set(entitlements.get("skins") or [])
    owned: set[str] = set()
    for product in products:
        if product["type"] == "consumable":
            continue
        product_id = product["product_id"]
        if product_id == "no_ads" and entitlements.get("no_ads"):
            owned.add(product_id)
        elif product_id in skins:
            owned.add(product_id)
    return owned


def _select_promotion(candidates: list[dict]) -> dict | None:
    """Tie-break when more than one active promotion matches the same
    product for the same user segment (e.g. an "all" promo and a
    segment-specific one both active at once): most-specific audience wins
    first (mirrors resolve_user_segment's own specificity bias), then
    highest discount_percent as a deterministic final tiebreak."""
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda p: (0 if p["audience"] == "all" else 1, p["discount_percent"]),
    )


def resolve_catalog_products(
    products: list[dict],
    promotions: list[dict],
    owned: set[str],
    user_segment: str,
    now: datetime,
) -> list[dict]:
    """T-240: applies ownership + the best-matching active promotion to
    each catalog product, producing REST-001's exact `products[]` shape.
    Pure — promotions/products/owned are already-read data, no Firestore
    access here.

    A promotion is a candidate for a product if: active, [starts_at,
    ends_at] contains `now` (server time — never trust a client clock),
    and its audience is either the user's exact segment or "all".
    """
    active_by_product: dict[str, list[dict]] = {}
    for promo in promotions:
        if not promo.get("active"):
            continue
        if not (promo["starts_at"] <= now <= promo["ends_at"]):
            continue
        if promo["audience"] not in (user_segment, "all"):
            continue
        active_by_product.setdefault(promo["product_id"], []).append(promo)

    resolved = []
    for product in products:
        product_id = product["product_id"]
        chosen = _select_promotion(active_by_product.get(product_id, []))

        price_usd = product["price_usd"]
        promotion = None
        if chosen is not None:
            original = chosen["original_price_usd"]
            discount = chosen["discount_percent"]
            price_usd = round(original * (1 - discount / 100), 2)
            promotion = {
                "discount_percent": discount,
                "original_price_usd": original,
                "expires_at": chosen["ends_at"],
            }

        entry = {
            "product_id": product_id,
            "type": product["type"],
            "display_name": product["display_name"],
            "description": product["description"],
            "price_usd": price_usd,
            "currency": product["currency"],
            "owned": product_id in owned,
            "promotion": promotion,
        }
        if product["type"] == "consumable":
            entry["lives_granted"] = product.get("lives_granted")
        resolved.append(entry)
    return resolved
