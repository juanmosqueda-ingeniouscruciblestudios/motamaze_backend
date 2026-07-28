"""Integration tests for POST /profile/equip-skin — T-243.

Covers the endpoint's own paths (ST-01). ST-03 adds the refund-cleanup cases,
which depend on ST-02 clearing equipped_skin inside revoke_entitlement."""

from app.services import jwt_service

URL = "/profile/equip-skin"


def _auth_headers(test_settings, uid: str) -> dict:
    token, _ = jwt_service.create_access_token(
        user_id=uid,
        provider="google",
        session_id="session-skin-1",
        project_id=test_settings.gcp_project_id,
        secret_name=test_settings.jwt_secret_name,
        key_id=test_settings.jwt_key_id,
        issuer=test_settings.jwt_issuer,
    )
    return {"Authorization": f"Bearer {token}"}


def _stored(fake_db, collection: str, doc_id: str) -> dict:
    return fake_db._collections[collection][doc_id]


def _seed(fake_db, uid: str, owned_skins: list[str] | None = None):
    fake_db.seed("config", "catalog", {
        "catalog_version": "2026-07-28",
        "products": [
            {"product_id": "lives_pack_5", "type": "consumable"},
            {"product_id": "no_ads", "type": "non_consumable"},
            {"product_id": "skin_gold", "type": "non_consumable"},
            {"product_id": "skin_silver", "type": "non_consumable"},
        ],
    })
    fake_db.seed("users", uid, {"uid": uid, "equipped_skin": None})
    fake_db.seed("entitlements", uid, {"skins": owned_skins or []})


async def test_equip_owned_skin(client, fake_db, test_settings):
    _seed(fake_db, "u-skin-1", owned_skins=["skin_gold"])
    resp = await client.post(URL, json={"skin_id": "skin_gold"},
                             headers=_auth_headers(test_settings, "u-skin-1"))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"skin_id": "skin_gold", "equipped": True}
    assert _stored(fake_db, "users", "u-skin-1")["equipped_skin"] == "skin_gold"


async def test_equip_unowned_skin_403(client, fake_db, test_settings):
    _seed(fake_db, "u-skin-2", owned_skins=[])
    resp = await client.post(URL, json={"skin_id": "skin_gold"},
                             headers=_auth_headers(test_settings, "u-skin-2"))
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["error_code"] == "SKIN_NOT_OWNED"


async def test_unknown_skin_400(client, fake_db, test_settings):
    _seed(fake_db, "u-skin-3", owned_skins=["skin_gold"])
    resp = await client.post(URL, json={"skin_id": "skin_unicorn"},
                             headers=_auth_headers(test_settings, "u-skin-3"))
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["error_code"] == "SKIN_NOT_FOUND"


async def test_skin_default_persists_null_without_ownership(client, fake_db, test_settings):
    # No purchases at all -- must still be able to go back to the plain look.
    _seed(fake_db, "u-skin-4", owned_skins=[])
    fake_db.seed("users", "u-skin-4", {"uid": "u-skin-4", "equipped_skin": "skin_gold"})
    resp = await client.post(URL, json={"skin_id": "skin_default"},
                             headers=_auth_headers(test_settings, "u-skin-4"))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"skin_id": "skin_default", "equipped": True}
    assert _stored(fake_db, "users", "u-skin-4")["equipped_skin"] is None


async def test_non_skin_product_rejected(client, fake_db, test_settings):
    # no_ads is a real, owned non-consumable -- but not a skin.
    _seed(fake_db, "u-skin-5", owned_skins=[])
    fake_db.seed("entitlements", "u-skin-5", {"no_ads": True})
    resp = await client.post(URL, json={"skin_id": "no_ads"},
                             headers=_auth_headers(test_settings, "u-skin-5"))
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["error_code"] == "SKIN_NOT_FOUND"


async def test_requires_jwt(client, fake_db):
    _seed(fake_db, "u-skin-6", owned_skins=["skin_gold"])
    resp = await client.post(URL, json={"skin_id": "skin_gold"})
    assert resp.status_code == 401, resp.text
