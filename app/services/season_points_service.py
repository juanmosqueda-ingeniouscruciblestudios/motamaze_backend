"""T-447 ST-08. Formula from motamaze-project/docs/project_spec.md
("Season Points Formula"):

    season_points = (total_stars * 3) + (levels_cleared * 5) + achievement_bonus

Deliberately NOT wired into leaderboard.py's ranking (leaderboards/{season}/
scores still orders by raw season_stars) -- that's a separate, larger scope
decided against for this ST (2026-07-30): the leaderboard's stored field,
its query filters, and POST /leaderboard/score's "authoritative score" logic
would all need to change together, and that's touching a system that
already works, not just adding a formula. Flagged as a known gap, not
silently left inconsistent -- see DATA_MODEL.md#season_progress.
"""

STARS_MULTIPLIER = 3
LEVELS_CLEARED_MULTIPLIER = 5


def compute_season_points(season_stars: int, levels_cleared: int, achievement_bonus_points: int) -> int:
    return season_stars * STARS_MULTIPLIER + levels_cleared * LEVELS_CLEARED_MULTIPLIER + achievement_bonus_points
