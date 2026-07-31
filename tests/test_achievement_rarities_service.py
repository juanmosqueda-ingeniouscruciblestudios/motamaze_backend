"""Unit tests for app/services/achievement_rarities_service.py — T-447 ST-10."""

from app.services import achievement_rarities_service, bq_streaming
from app.services.achievement_rarities_service import compute_rarity_tier

CATALOG = {
    "achievements": [
        {"achievement_id": "first_blood", "name": "First Blood", "rarity_tier": "COMMON"},
        {"achievement_id": "maze_master", "name": "Maze Master", "rarity_tier": "UNCOMMON"},
    ],
}


def test_rarity_tier_boundaries():
    assert compute_rarity_tier(100) == "COMMON"
    assert compute_rarity_tier(50) == "COMMON"
    assert compute_rarity_tier(49.9) == "UNCOMMON"
    assert compute_rarity_tier(20) == "UNCOMMON"
    assert compute_rarity_tier(19.9) == "RARE"
    assert compute_rarity_tier(8) == "RARE"
    assert compute_rarity_tier(7.9) == "EPIC"
    assert compute_rarity_tier(4) == "EPIC"
    assert compute_rarity_tier(3.9) == "LEGENDARY"
    assert compute_rarity_tier(0) == "LEGENDARY"


async def test_count_unlocks_among_only_counts_given_uids(fake_db):
    fake_db.seed("achievement_progress", "active-1", {"unlocked": ["first_blood", "maze_master"]})
    fake_db.seed("achievement_progress", "active-2", {"unlocked": ["first_blood"]})
    # Churned player -- unlocked plenty, but NOT in the active-uid set passed in.
    fake_db.seed("achievement_progress", "churned-1", {"unlocked": ["first_blood", "maze_master"]})

    counts = await achievement_rarities_service.count_unlocks_among(fake_db, ["active-1", "active-2"])

    assert counts == {"first_blood": 2, "maze_master": 1}


async def test_count_unlocks_among_missing_progress_doc_is_zero(fake_db):
    fake_db.seed("achievement_progress", "active-1", {"unlocked": ["first_blood"]})
    # active-2 has no achievement_progress doc at all -- never unlocked anything.
    counts = await achievement_rarities_service.count_unlocks_among(fake_db, ["active-1", "active-2"])
    assert counts == {"first_blood": 1}


async def test_recalc_writes_rarity_docs_scoped_to_active_players(fake_db, monkeypatch):
    fake_db.seed("config", "achievements", CATALOG)
    fake_db.seed("achievement_progress", "active-1", {"unlocked": ["first_blood"]})
    fake_db.seed("achievement_progress", "active-2", {"unlocked": ["first_blood", "maze_master"]})
    # Long-churned player who unlocked everything -- must not inflate the denominator or count.
    fake_db.seed("achievement_progress", "churned-1", {"unlocked": ["first_blood", "maze_master"]})

    async def _fake_run_select(query, params):
        return [{"user_id": "active-1"}, {"user_id": "active-2"}]

    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select)

    result = await achievement_rarities_service.recalc_achievement_rarities(fake_db, "proj", "ds")

    assert result["total_players"] == 2
    assert set(result["computed"]) == {"first_blood", "maze_master"}

    first_blood = fake_db._collections["achievement_rarities"]["first_blood"]
    assert first_blood["unlocked_by"] == 2
    assert first_blood["rarity_percent"] == 100.0
    assert first_blood["rarity_tier"] == "COMMON"

    maze_master = fake_db._collections["achievement_rarities"]["maze_master"]
    assert maze_master["unlocked_by"] == 1
    assert maze_master["rarity_percent"] == 50.0


async def test_recalc_skips_when_no_active_players(fake_db, monkeypatch):
    fake_db.seed("config", "achievements", CATALOG)

    async def _fake_run_select(query, params):
        return []

    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select)

    result = await achievement_rarities_service.recalc_achievement_rarities(fake_db, "proj", "ds")

    assert result == {"computed": [], "total_players": 0, "skipped": "no_active_players"}
    assert "achievement_rarities" not in fake_db._collections or not fake_db._collections["achievement_rarities"]


async def test_recalc_missing_catalog_computes_nothing(fake_db, monkeypatch):
    # config/achievements never seeded -- must not crash.
    async def _fake_run_select(query, params):
        return [{"user_id": "active-1"}]

    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select)

    result = await achievement_rarities_service.recalc_achievement_rarities(fake_db, "proj", "ds")

    assert result == {"computed": [], "total_players": 1}
