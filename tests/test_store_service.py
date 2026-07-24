"""Unit tests for app/services/store_service.py — T-240 audience segmentation
(resolve_user_segment) and catalog resolution (owned_product_ids,
resolve_catalog_products). All pure — no Firestore I/O, callers supply
already-read data."""

from datetime import datetime, timedelta, timezone

from app.services.store_service import (
    owned_product_ids,
    resolve_catalog_products,
    resolve_user_segment,
)

NOW = datetime(2026, 7, 24, tzinfo=timezone.utc)

LIVES_PACK = {
    "product_id": "lives_pack_5", "type": "consumable", "display_name": "5 Extra Lives",
    "description": "Keep playing with 5 extra lives", "price_usd": 0.99, "currency": "USD",
    "lives_granted": 5,
}
NO_ADS = {
    "product_id": "no_ads", "type": "non_consumable", "display_name": "Remove Ads",
    "description": "Remove all ads permanently", "price_usd": 2.99, "currency": "USD",
    "lives_granted": None,
}
SKIN_GOLD = {
    "product_id": "skin_gold", "type": "non_consumable", "display_name": "Gold Mota",
    "description": "A shiny golden skin", "price_usd": 0.99, "currency": "USD",
    "lives_granted": None,
}


def _promo(product_id, audience, discount=20, active=True, starts=-1, ends=1, original=2.99):
    return {
        "product_id": product_id,
        "audience": audience,
        "discount_percent": discount,
        "original_price_usd": original,
        "active": active,
        "starts_at": NOW + timedelta(days=starts),
        "ends_at": NOW + timedelta(days=ends),
    }


def test_non_payer_takes_priority_over_everything():
    # New AND never paid AND no recent session -> non_payer wins, not new.
    created_at = NOW - timedelta(days=1)
    last_session = NOW - timedelta(days=20)
    assert resolve_user_segment(created_at, last_session, False, NOW) == "non_payer"


def test_lapsed_when_last_session_past_window():
    created_at = NOW - timedelta(days=100)
    last_session = NOW - timedelta(days=14)  # exactly at the boundary
    assert resolve_user_segment(created_at, last_session, True, NOW) == "lapsed"


def test_not_lapsed_one_day_before_window():
    created_at = NOW - timedelta(days=100)
    last_session = NOW - timedelta(days=13)
    assert resolve_user_segment(created_at, last_session, True, NOW) == "all"


def test_missing_last_session_is_not_treated_as_lapsed():
    # No session on record at all -- absence of data isn't evidence of
    # lapsing, must not be mislabeled as lapsed.
    created_at = NOW - timedelta(days=100)
    assert resolve_user_segment(created_at, None, True, NOW) == "all"


def test_new_user_within_window():
    created_at = NOW - timedelta(days=3)  # exactly at the boundary
    last_session = NOW  # active just now, not lapsed
    assert resolve_user_segment(created_at, last_session, True, NOW) == "new"


def test_not_new_one_day_after_window():
    created_at = NOW - timedelta(days=4)
    last_session = NOW
    assert resolve_user_segment(created_at, last_session, True, NOW) == "all"


def test_lapsed_takes_priority_over_new():
    # Both conditions technically true is contradictory in practice (a
    # 1-day-old account can't have a 14-day-old last session), but the
    # priority order must still hold if it ever happens.
    created_at = NOW - timedelta(days=1)
    last_session = NOW - timedelta(days=15)
    assert resolve_user_segment(created_at, last_session, True, NOW) == "lapsed"


def test_all_fallback_for_established_active_payer():
    created_at = NOW - timedelta(days=200)
    last_session = NOW - timedelta(hours=1)
    assert resolve_user_segment(created_at, last_session, True, NOW) == "all"


# ---------------------------------------------------------------------------
# owned_product_ids
# ---------------------------------------------------------------------------


def test_owned_consumable_is_never_owned():
    # REST-001's own example always shows owned=false for lives_pack_5 —
    # a consumable is bought again each time, not "owned" persistently.
    entitlements = {"no_ads": True, "skins": ["skin_gold"], "life_packs_total": 5}
    owned = owned_product_ids(entitlements, [LIVES_PACK])
    assert owned == set()


def test_owned_no_ads_from_entitlement_flag():
    assert owned_product_ids({"no_ads": True}, [NO_ADS]) == {"no_ads"}
    assert owned_product_ids({"no_ads": False}, [NO_ADS]) == set()


def test_owned_skin_from_skins_list():
    assert owned_product_ids({"skins": ["skin_gold"]}, [SKIN_GOLD]) == {"skin_gold"}
    assert owned_product_ids({"skins": []}, [SKIN_GOLD]) == set()


def test_owned_empty_entitlements_doc():
    # New user, entitlements/{uid} doesn't exist yet -> caller passes {}.
    assert owned_product_ids({}, [NO_ADS, SKIN_GOLD]) == set()


# ---------------------------------------------------------------------------
# resolve_catalog_products
# ---------------------------------------------------------------------------


def test_resolve_no_active_promotions_returns_base_price():
    result = resolve_catalog_products([NO_ADS], [], set(), "all", NOW)
    assert result[0]["price_usd"] == 2.99
    assert result[0]["promotion"] is None
    assert result[0]["owned"] is False


def test_resolve_applies_matching_promotion():
    promo = _promo("no_ads", "non_payer", discount=20, original=2.99)
    result = resolve_catalog_products([NO_ADS], [promo], set(), "non_payer", NOW)
    assert result[0]["price_usd"] == 2.39  # 2.99 * 0.8, rounded
    assert result[0]["promotion"] == {
        "discount_percent": 20, "original_price_usd": 2.99, "expires_at": promo["ends_at"],
    }


def test_resolve_ignores_promotion_for_wrong_audience():
    promo = _promo("no_ads", "lapsed")
    result = resolve_catalog_products([NO_ADS], [promo], set(), "new", NOW)
    assert result[0]["promotion"] is None
    assert result[0]["price_usd"] == 2.99


def test_resolve_ignores_expired_promotion():
    promo = _promo("no_ads", "all", starts=-10, ends=-1)  # ended yesterday
    result = resolve_catalog_products([NO_ADS], [promo], set(), "all", NOW)
    assert result[0]["promotion"] is None


def test_resolve_ignores_future_promotion():
    promo = _promo("no_ads", "all", starts=1, ends=10)  # starts tomorrow
    result = resolve_catalog_products([NO_ADS], [promo], set(), "all", NOW)
    assert result[0]["promotion"] is None


def test_resolve_ignores_inactive_promotion():
    promo = _promo("no_ads", "all", active=False)
    result = resolve_catalog_products([NO_ADS], [promo], set(), "all", NOW)
    assert result[0]["promotion"] is None


def test_resolve_tiebreak_specific_audience_beats_all():
    all_promo = _promo("no_ads", "all", discount=50, original=2.99)
    specific_promo = _promo("no_ads", "non_payer", discount=10, original=2.99)
    result = resolve_catalog_products(
        [NO_ADS], [all_promo, specific_promo], set(), "non_payer", NOW
    )
    # non_payer-specific wins even though its discount is smaller.
    assert result[0]["promotion"]["discount_percent"] == 10


def test_resolve_tiebreak_highest_discount_when_same_specificity():
    promo_a = _promo("no_ads", "non_payer", discount=10, original=2.99)
    promo_b = _promo("no_ads", "non_payer", discount=30, original=2.99)
    result = resolve_catalog_products([NO_ADS], [promo_a, promo_b], set(), "non_payer", NOW)
    assert result[0]["promotion"]["discount_percent"] == 30


def test_resolve_owned_flag_passed_through():
    result = resolve_catalog_products([NO_ADS], [], {"no_ads"}, "all", NOW)
    assert result[0]["owned"] is True


def test_resolve_lives_granted_only_on_consumables():
    result = resolve_catalog_products([LIVES_PACK, NO_ADS], [], set(), "all", NOW)
    by_id = {p["product_id"]: p for p in result}
    assert by_id["lives_pack_5"]["lives_granted"] == 5
    assert "lives_granted" not in by_id["no_ads"]


def test_resolve_promotion_active_at_exact_start_boundary():
    promo = _promo("no_ads", "all", starts=0, ends=1)  # starts_at == now
    result = resolve_catalog_products([NO_ADS], [promo], set(), "all", NOW)
    assert result[0]["promotion"] is not None


def test_resolve_promotion_active_at_exact_end_boundary():
    promo = _promo("no_ads", "all", starts=-1, ends=0)  # ends_at == now
    result = resolve_catalog_products([NO_ADS], [promo], set(), "all", NOW)
    assert result[0]["promotion"] is not None


def test_resolve_orphaned_promotion_ignored():
    # Promotion references a product_id that isn't in the catalog products
    # list at all -- must not crash, must not appear anywhere.
    promo = _promo("does_not_exist", "all")
    result = resolve_catalog_products([NO_ADS], [promo], set(), "all", NOW)
    assert result[0]["promotion"] is None
