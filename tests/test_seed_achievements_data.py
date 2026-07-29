"""Data-integrity checks for scripts/seed_achievements.py — T-447 ST-05.

No Firestore I/O here (that script uses the real firestore.Client, same as
seed_store_catalog.py, and isn't exercised by the suite). This only guards
against a transcription slip against project_spec.md's achievement table:
wrong count, a duplicate ID, or a rarity/points mismatch would otherwise
only surface by someone eyeballing 40 rows.
"""

import importlib.util
from pathlib import Path

_SPEC_PATH = Path(__file__).parent.parent / "scripts" / "seed_achievements.py"
_spec = importlib.util.spec_from_file_location("seed_achievements", _SPEC_PATH)
seed_achievements = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_achievements)

ACHIEVEMENTS = seed_achievements.ACHIEVEMENTS

# project_spec.md "Rarity tiers" table (§Achievements).
EXPECTED_RARITY_COUNTS = {"COMMON": 10, "UNCOMMON": 10, "RARE": 8, "EPIC": 6, "LEGENDARY": 6}
EXPECTED_RARITY_POINTS = {"COMMON": 25, "UNCOMMON": 75, "RARE": 200, "EPIC": 400, "LEGENDARY": 800}


def test_total_count_is_40():
    assert len(ACHIEVEMENTS) == 40


def test_achievement_ids_are_unique():
    ids = [a["achievement_id"] for a in ACHIEVEMENTS]
    assert len(ids) == len(set(ids))


def test_spec_ids_are_unique():
    spec_ids = [a["spec_id"] for a in ACHIEVEMENTS]
    assert len(spec_ids) == len(set(spec_ids))


def test_rarity_counts_match_project_spec():
    counts: dict[str, int] = {}
    for a in ACHIEVEMENTS:
        counts[a["rarity_tier"]] = counts.get(a["rarity_tier"], 0) + 1
    assert counts == EXPECTED_RARITY_COUNTS


def test_points_match_rarity_tier():
    for a in ACHIEVEMENTS:
        assert a["points"] == EXPECTED_RARITY_POINTS[a["rarity_tier"]], a["achievement_id"]


def test_total_points_available_is_9800():
    assert sum(a["points"] for a in ACHIEVEMENTS) == 9800


def test_every_achievement_has_required_fields():
    required = {"achievement_id", "spec_id", "name", "description", "rarity_tier", "points", "guard_notes"}
    for a in ACHIEVEMENTS:
        assert required <= a.keys(), a
