"""Source-aware skin revocation — T-243.

A refund may only take back what was bought. The same skin can also arrive from
the Season Pass free track or a leaderboard prize (project_spec.md), and those
are not the refund's to reclaim."""

from datetime import datetime, timezone

from app.services import reconcile_service

NOW = datetime.now(timezone.utc)


async def test_refund_removes_purchased_skin_and_unequips_it(fake_db):
    fake_db.seed("entitlements", "u-rev-1", {
        "no_ads": True,
        "life_packs_total": 3,
        "skins": {"skin_gold": {"source": "purchase", "acquired_at": NOW}},
    })
    fake_db.seed("users", "u-rev-1", {"uid": "u-rev-1", "equipped_skin": "skin_gold"})

    await reconcile_service.revoke_entitlement(fake_db, "u-rev-1", "skin", "skin_gold", NOW)

    ent = fake_db._collections["entitlements"]["u-rev-1"]
    assert "skin_gold" not in ent["skins"]
    assert fake_db._collections["users"]["u-rev-1"]["equipped_skin"] is None
    # The rest of the document must survive — a refund of one skin is not a
    # reset of everything the player owns.
    assert ent["no_ads"] is True
    assert ent["life_packs_total"] == 3


async def test_refund_leaves_earned_skin_alone(fake_db):
    fake_db.seed("entitlements", "u-rev-2", {
        "skins": {"skin_garden_rush": {"source": "earned", "acquired_at": NOW}},
    })
    fake_db.seed("users", "u-rev-2", {"uid": "u-rev-2", "equipped_skin": "skin_garden_rush"})

    await reconcile_service.revoke_entitlement(fake_db, "u-rev-2", "skin", "skin_garden_rush", NOW)

    ent = fake_db._collections["entitlements"]["u-rev-2"]
    assert "skin_garden_rush" in ent["skins"]
    assert fake_db._collections["users"]["u-rev-2"]["equipped_skin"] == "skin_garden_rush"


async def test_refund_of_one_skin_does_not_unequip_another(fake_db):
    """The naive fix — always null equipped_skin on any skin revocation — fails
    here."""
    fake_db.seed("entitlements", "u-rev-3", {
        "skins": {
            "skin_gold": {"source": "purchase", "acquired_at": NOW},
            "skin_silver": {"source": "purchase", "acquired_at": NOW},
        },
    })
    fake_db.seed("users", "u-rev-3", {"uid": "u-rev-3", "equipped_skin": "skin_silver"})

    await reconcile_service.revoke_entitlement(fake_db, "u-rev-3", "skin", "skin_gold", NOW)

    ent = fake_db._collections["entitlements"]["u-rev-3"]
    assert "skin_gold" not in ent["skins"]
    assert "skin_silver" in ent["skins"]
    assert fake_db._collections["users"]["u-rev-3"]["equipped_skin"] == "skin_silver"


async def test_refund_of_legacy_list_shape_still_revokes(fake_db):
    """Pre-T-243 documents read as purchases, so a refund still applies."""
    fake_db.seed("entitlements", "u-rev-4", {"skins": ["skin_gold", "skin_silver"]})
    fake_db.seed("users", "u-rev-4", {"uid": "u-rev-4", "equipped_skin": "skin_gold"})

    await reconcile_service.revoke_entitlement(fake_db, "u-rev-4", "skin", "skin_gold", NOW)

    ent = fake_db._collections["entitlements"]["u-rev-4"]
    assert "skin_gold" not in ent["skins"]
    assert "skin_silver" in ent["skins"]
    assert fake_db._collections["users"]["u-rev-4"]["equipped_skin"] is None
