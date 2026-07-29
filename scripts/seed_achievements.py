#!/usr/bin/env python3
"""
scripts/seed_achievements.py

Seeds/updates the config/achievements document that GET /achievements (T-447
ST-09) reads from — the static catalog (name, description, rarity, points)
for the 40 achievements defined in motamaze-project/docs/project_spec.md
(§Achievements). Idempotent — uses Firestore .set() on a fixed document ID,
safe to re-run whenever the catalog needs updating.

Guard conditions ("WR <= 80%", "n_zas >= 1", "0 hits on 10 different levels
this season", ...) are NOT stored here. They're too heterogeneous to be
worth a rules DSL for a fixed set of 40 achievements that only change via a
code deploy anyway — they're implemented as Python predicates in the
evaluation engine (T-447 ST-07), keyed by the same achievement_id used here.
This document is the display-facing catalog only: what GET /achievements
merges with achievement_progress/{uid} (unlocked + progress) and
achievement_rarities/{achievement_id} (measured rarity %) to build its
response.

achievement_id is a human-readable slug derived from the project_spec name,
not the project_spec numeric ID (which isn't contiguous 1-40 and isn't
meant to be player- or log-facing). spec_id is kept for traceability back
to project_spec.md.

Usage:
    gcloud auth application-default login --project motamaze-dev   # or motamaze for prod
    python scripts/seed_achievements.py --project motamaze-dev
"""

import argparse
from datetime import date

from google.cloud import firestore

# Source: motamaze-project/docs/project_spec.md, "Achievement definitions
# (40 total)" table, and the rarity/points table above it. guard_notes is the
# project_spec "Guards / Conditions" column verbatim, for reference only —
# see module docstring for why it isn't executable data here.
ACHIEVEMENTS = [
    {"achievement_id": "first_blood", "spec_id": 1, "name": "First Blood", "description": "Win your first match", "rarity_tier": "COMMON", "points": 25, "guard_notes": "No guard"},
    {"achievement_id": "on_a_roll", "spec_id": 3, "name": "On a Roll", "description": "Win 2 different levels in a row", "rarity_tier": "COMMON", "points": 25, "guard_notes": "WR <= 80%"},
    {"achievement_id": "star_born", "spec_id": 4, "name": "Star Born", "description": "Earn your first 3-star", "rarity_tier": "COMMON", "points": 25, "guard_notes": "No guard"},
    {"achievement_id": "never_give_up", "spec_id": 7, "name": "Never Give Up", "description": "Win after being 5+ food behind", "rarity_tier": "COMMON", "points": 25, "guard_notes": "WR <= 60%; Huracan or Zas present"},
    {"achievement_id": "always_moving", "spec_id": 10, "name": "Always Moving", "description": "Win with <= 5s idle", "rarity_tier": "COMMON", "points": 25, "guard_notes": "Food mode; level >= L11; WR <= 70%"},
    {"achievement_id": "hot_streak", "spec_id": 12, "name": "Hot Streak", "description": "Win 3 different levels in a row", "rarity_tier": "COMMON", "points": 25, "guard_notes": "WR <= 70%"},
    {"achievement_id": "big_eater", "spec_id": 13, "name": "Big Eater", "description": "Collect 25+ food in one match", "rarity_tier": "COMMON", "points": 25, "guard_notes": "Food modes (not deep_run); n_huracan + n_zas >= 2"},
    {"achievement_id": "stars_75", "spec_id": 18, "name": "75 Stars", "description": "Earn 75 stars this season", "rarity_tier": "COMMON", "points": 25, "guard_notes": "Stars count once per unique level (best rating)"},
    {"achievement_id": "full_house", "spec_id": 20, "name": "Full House!", "description": "Win 5 different Whole Gang's Here! levels", "rarity_tier": "COMMON", "points": 25, "guard_notes": "WR <= 70%"},
    {"achievement_id": "zas_chaser", "spec_id": 30, "name": "Zas Chaser", "description": "Win 3 different levels with Zas present", "rarity_tier": "COMMON", "points": 25, "guard_notes": "n_zas >= 1; WR <= 50%"},
    {"achievement_id": "speedy", "spec_id": 6, "name": "Speedy", "description": "First Bite - 60+ sec remaining", "rarity_tier": "UNCOMMON", "points": 75, "guard_notes": "TARGET_SCORE >= 10; WR <= 60%"},
    {"achievement_id": "stink_proof", "spec_id": 9, "name": "Stink Proof", "description": "Win with 0 badsmell hits", "rarity_tier": "UNCOMMON", "points": 75, "guard_notes": "n_mancha >= 1; level >= L11; WR <= 70%"},
    {"achievement_id": "comeback_king", "spec_id": 14, "name": "Comeback King", "description": "3 comeback wins (5+ behind) this season", "rarity_tier": "UNCOMMON", "points": 75, "guard_notes": "Different levels; WR <= 60%; Huracan/Zas present"},
    {"achievement_id": "maze_master", "spec_id": 15, "name": "Maze Master", "description": "Cover 90%+ of maze in one match", "rarity_tier": "UNCOMMON", "points": 75, "guard_notes": "Level >= L11; WR <= 70%; food mode"},
    {"achievement_id": "bola_dancer", "spec_id": 17, "name": "Bola Dancer", "description": "Win with Bola present and 0 stuns", "rarity_tier": "UNCOMMON", "points": 75, "guard_notes": "n_bola >= 1; WR <= 60%"},
    {"achievement_id": "daredevil", "spec_id": 19, "name": "Daredevil", "description": "Win after being frozen by Mancha", "rarity_tier": "UNCOMMON", "points": 75, "guard_notes": "n_mancha >= 1; frozen > 0s; WR <= 60%"},
    {"achievement_id": "hungry_hungry", "spec_id": 22, "name": "Hungry Hungry", "description": "Win with no food drought > 20s", "rarity_tier": "UNCOMMON", "points": 75, "guard_notes": "Food mode (not deep_run); n_npcs >= 2; WR <= 60%"},
    {"achievement_id": "all_modes", "spec_id": 25, "name": "All Modes", "description": "Win once in all 8 game modes", "rarity_tier": "UNCOMMON", "points": 75, "guard_notes": "WR <= 80% qualifying level per mode"},
    {"achievement_id": "thriller", "spec_id": 26, "name": "Thriller", "description": "3 close wins (gap <= 3 food, lead changes >= 2)", "rarity_tier": "UNCOMMON", "points": 75, "guard_notes": "WR <= 60%; Huracan/Zas present"},
    {"achievement_id": "three_star_warrior", "spec_id": 29, "name": "3-Star Warrior", "description": "3-star on 20 different levels", "rarity_tier": "UNCOMMON", "points": 75, "guard_notes": "10 of 20 must be WR <= 50%"},
    {"achievement_id": "wall_dodger", "spec_id": 16, "name": "Wall Dodger", "description": "5+ shift reroutes in one match", "rarity_tier": "RARE", "points": 200, "guard_notes": "Watch the Walls! mode; win required"},
    {"achievement_id": "ghost", "spec_id": 24, "name": "Ghost", "description": "0 hits on 5 different levels this season", "rarity_tier": "RARE", "points": 200, "guard_notes": "Bola or Mancha present; WR <= 50%"},
    {"achievement_id": "deep_survivor", "spec_id": 27, "name": "Deep Survivor", "description": "Win a Deep Run with 0 hits", "rarity_tier": "RARE", "points": 200, "guard_notes": "deep_run mode; Bola or Mancha present"},
    {"achievement_id": "speedster", "spec_id": 28, "name": "Speedster", "description": "First Bite - 90+ sec remaining", "rarity_tier": "RARE", "points": 200, "guard_notes": "first_bite mode; WR <= 50%"},
    {"achievement_id": "outrun_the_swarm", "spec_id": 31, "name": "Outrun the Swarm", "description": "Win 5 different Huracan's Friends! levels with 0 lead changes", "rarity_tier": "RARE", "points": 200, "guard_notes": "huracans_friends mode; 5 unique levels"},
    {"achievement_id": "clean_sweep_season", "spec_id": 32, "name": "Clean Sweep Season", "description": "0 hits on 10 different levels this season", "rarity_tier": "RARE", "points": 200, "guard_notes": "Bola or Mancha; WR <= 50%"},
    {"achievement_id": "perfectionist", "spec_id": 35, "name": "Perfectionist", "description": "3-star on 20 different levels (8 must be WR <= 40%)", "rarity_tier": "RARE", "points": 200, "guard_notes": "Stars counted once per level per season"},
    {"achievement_id": "double_threat", "spec_id": 41, "name": "Double Threat", "description": "Win with Bola + Mancha; 0 hits AND 0 badsmell", "rarity_tier": "RARE", "points": 200, "guard_notes": "n_bola >= 1; n_mancha >= 1"},
    {"achievement_id": "manchas_nightmare", "spec_id": 39, "name": "Mancha's Nightmare", "description": "0 badsmell hits on 10 Mancha levels", "rarity_tier": "EPIC", "points": 400, "guard_notes": "n_mancha >= 1; WR <= 40%; 10 unique levels"},
    {"achievement_id": "full_roster_zero_scars", "spec_id": 42, "name": "Full Roster Zero Scars", "description": "Win with all 4 NPCs present and 0 hits", "rarity_tier": "EPIC", "points": 400, "guard_notes": "All NPC counts >= 1; win required"},
    {"achievement_id": "speed_legend", "spec_id": 43, "name": "Speed Legend", "description": "First Bite - 100+ sec remaining", "rarity_tier": "EPIC", "points": 400, "guard_notes": "first_bite mode; round_dur - time_to_target >= 100"},
    {"achievement_id": "survivors_gauntlet", "spec_id": 44, "name": "Survivor's Gauntlet", "description": "0 hits on 15 different levels this season", "rarity_tier": "EPIC", "points": 400, "guard_notes": "Bola or Mancha; WR <= 50%"},
    {"achievement_id": "the_hard_way", "spec_id": 45, "name": "The Hard Way", "description": "Earn 3-star on any WR <= 20% level", "rarity_tier": "EPIC", "points": 400, "guard_notes": "WR <= 20%; Bola or Mancha present"},
    {"achievement_id": "relentless", "spec_id": 46, "name": "Relentless", "description": "Win 7 different levels in a row", "rarity_tier": "EPIC", "points": 400, "guard_notes": "WR <= 40%; no repeats in streak"},
    {"achievement_id": "unbreakable", "spec_id": 36, "name": "Unbreakable", "description": "Win 10 different levels in a row", "rarity_tier": "LEGENDARY", "points": 800, "guard_notes": "WR <= 60%; no repeats in streak"},
    {"achievement_id": "invincible", "spec_id": 37, "name": "Invincible", "description": "0 hits on 10 WR <= 25% levels this season", "rarity_tier": "LEGENDARY", "points": 800, "guard_notes": "Bola or Mancha; 10 unique levels"},
    {"achievement_id": "flawless", "spec_id": 38, "name": "Flawless", "description": "0 hits on 20 different levels this season", "rarity_tier": "LEGENDARY", "points": 800, "guard_notes": "Bola or Mancha; WR <= 40%"},
    {"achievement_id": "apex_predator", "spec_id": 47, "name": "Apex Predator", "description": "0 hits on 5 Full Roster levels (all 4 NPCs)", "rarity_tier": "LEGENDARY", "points": 800, "guard_notes": "hits_taken = 0; 5 unique levels"},
    {"achievement_id": "seasonal_legend", "spec_id": 48, "name": "Seasonal Legend", "description": "Earn season_points >= threshold", "rarity_tier": "LEGENDARY", "points": 800, "guard_notes": "Threshold = 4,000 pts (top ~2-3% of Core)"},
    {"achievement_id": "perfect_champion", "spec_id": 49, "name": "Perfect Champion", "description": "3-star on 10 WR <= 20% levels", "rarity_tier": "LEGENDARY", "points": 800, "guard_notes": "WR <= 20%; Bola or Mancha; 10 unique levels"},
]


def main(project: str) -> None:
    client = firestore.Client(project=project)
    ref = client.collection("config").document("achievements")
    ref.set({
        "achievements": ACHIEVEMENTS,
        "catalog_version": date.today().isoformat(),
    })

    doc = ref.get().to_dict()
    print(f"config/achievements seeded in project={project} (catalog_version={doc['catalog_version']})")
    by_rarity: dict[str, int] = {}
    for a in doc["achievements"]:
        by_rarity[a["rarity_tier"]] = by_rarity.get(a["rarity_tier"], 0) + 1
    print(f"  {len(doc['achievements'])} achievements: {by_rarity}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, choices=["motamaze-dev", "motamaze"])
    args = parser.parse_args()
    main(args.project)
