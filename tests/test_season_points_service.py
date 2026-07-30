from app.services import season_points_service


def test_compute_season_points_formula():
    # 10 stars*3 + 4 levels*5 + 100 bonus = 30 + 20 + 100 = 150
    assert season_points_service.compute_season_points(10, 4, 100) == 150


def test_compute_season_points_zero_bonus():
    assert season_points_service.compute_season_points(0, 0, 0) == 0
