"""Integration tests for GET /store/catalog — T-240."""

from datetime import datetime, timedelta, timezone

from app.services import jwt_service

URL = "/store/catalog"

NOW = datetime.now(timezone.utc)


def _auth_headers(test_settings, uid: str = "user-store-1") -> dict:
    token, _ = jwt_service.create_access_token(
        user_id=uid,
        provider="google",
        session_id="session-store-1",
        project_id=test_settings.gcp_project_id,
        secret_name=test_settings.jwt_secret_name,
        key_id=test_settings.jwt_key_id,
        issuer=test_settings.jwt_issuer,
    )
    return {"Authorization": f"Bearer {token}"}


def _seed_catalog(fake_db):
    fake_db.seed("config", "catalog", {
        "catalog_version": "2026-07-24",
        "products": [
            {
                "product_id": "lives_pack_5", "type": "consumable", "display_name": "5 Extra Lives",
                "description": "Keep playing with 5 extra lives", "price_usd": 0.99, "currency": "USD",
                "lives_granted": 5,
            },
            {
                "product_id": "no_ads", "type": "non_consumable", "display_name": "Remove Ads",
                "description": "Remove all ads permanently", "price_usd": 2.99, "currency": "USD",
                "lives_granted": None,
            },
        ],
    })


def _seed_user(fake_db, uid: str, created_at, paid: bool = True):
    fake_db.seed("users", uid, {"uid": uid, "created_at": created_at})
    if paid:
        fake_db.seed("entitlements", uid, {"no_ads": True})


async def test_catalog_returns_base_prices_no_promotions(client, fake_db, test_settings):
    _seed_catalog(fake_db)
    _seed_user(fake_db, "user-store-1", NOW - timedelta(days=200))

    resp = await client.get(URL, headers=_auth_headers(test_settings))
    assert resp.status_code == 200
    body = resp.json()
    assert body["catalog_version"] == "2026-07-24"
    by_id = {p["product_id"]: p for p in body["products"]}
    assert by_id["no_ads"]["price_usd"] == 2.99
    assert by_id["no_ads"]["owned"] is True  # entitlements.no_ads seeded True
    assert by_id["no_ads"]["promotion"] is None
    assert by_id["lives_pack_5"]["lives_granted"] == 5
    assert "lives_granted" not in by_id["no_ads"]


async def test_catalog_owned_false_without_entitlement(client, fake_db, test_settings):
    _seed_catalog(fake_db)
    _seed_user(fake_db, "user-store-2", NOW - timedelta(days=200), paid=False)

    resp = await client.get(URL, headers=_auth_headers(test_settings, "user-store-2"))
    body = resp.json()
    by_id = {p["product_id"]: p for p in body["products"]}
    assert by_id["no_ads"]["owned"] is False


async def test_catalog_applies_matching_active_promotion(client, fake_db, test_settings):
    _seed_catalog(fake_db)
    _seed_user(fake_db, "user-store-3", NOW - timedelta(days=200), paid=False)  # non_payer segment
    fake_db.seed("promotions", "promo-1", {
        "product_id": "no_ads",
        "audience": "non_payer",
        "discount_percent": 20,
        "original_price_usd": 2.99,
        "active": True,
        "starts_at": NOW - timedelta(days=1),
        "ends_at": NOW + timedelta(days=1),
    })

    resp = await client.get(URL, headers=_auth_headers(test_settings, "user-store-3"))
    body = resp.json()
    by_id = {p["product_id"]: p for p in body["products"]}
    assert by_id["no_ads"]["price_usd"] == 2.39
    assert by_id["no_ads"]["promotion"]["discount_percent"] == 20


async def test_catalog_ignores_promotion_for_different_segment(client, fake_db, test_settings):
    _seed_catalog(fake_db)
    # Established, paid, inactive-recently user -> segment "all", not "lapsed".
    _seed_user(fake_db, "user-store-4", NOW - timedelta(days=200), paid=True)
    fake_db.seed("sessions", "sess-store-4", {
        "uid": "user-store-4", "started_at": NOW - timedelta(hours=1),
    })
    fake_db.seed("promotions", "promo-2", {
        "product_id": "no_ads",
        "audience": "lapsed",
        "discount_percent": 50,
        "original_price_usd": 2.99,
        "active": True,
        "starts_at": NOW - timedelta(days=1),
        "ends_at": NOW + timedelta(days=1),
    })

    resp = await client.get(URL, headers=_auth_headers(test_settings, "user-store-4"))
    body = resp.json()
    by_id = {p["product_id"]: p for p in body["products"]}
    assert by_id["no_ads"]["promotion"] is None
    assert by_id["no_ads"]["price_usd"] == 2.99


async def test_catalog_missing_config_returns_empty_products(client, fake_db, test_settings):
    # config/catalog was never seeded -- must not 500.
    _seed_user(fake_db, "user-store-5", NOW - timedelta(days=200))
    resp = await client.get(URL, headers=_auth_headers(test_settings, "user-store-5"))
    assert resp.status_code == 200
    assert resp.json()["products"] == []
