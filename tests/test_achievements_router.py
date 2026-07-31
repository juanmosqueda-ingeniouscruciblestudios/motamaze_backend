"""Integration tests for GET /achievements — T-447 ST-09."""

from datetime import datetime, timezone

from app.services import jwt_service

URL = "/achievements"

NOW = datetime.now(timezone.utc)


def _auth_headers(test_settings, uid: str = "user-achv-1") -> dict:
    token, _ = jwt_service.create_access_token(
        user_id=uid,
        provider="google",
        session_id="session-achv-1",
        project_id=test_settings.gcp_project_id,
        secret_name=test_settings.jwt_secret_name,
        key_id=test_settings.jwt_key_id,
        issuer=test_settings.jwt_issuer,
    )
    return {"Authorization": f"Bearer {token}"}


def _seed_catalog(fake_db):
    fake_db.seed("config", "achievements", {
        "catalog_version": "2026-07-29",
        "achievements": [
            {
                "achievement_id": "first_blood", "spec_id": 1, "name": "First Blood",
                "description": "Win your first match", "rarity_tier": "COMMON", "points": 25,
                "guard_notes": "won == true",
            },
            {
                "achievement_id": "maze_master", "spec_id": 14, "name": "Maze Master",
                "description": "Cover 90% of the maze", "rarity_tier": "UNCOMMON", "points": 75,
                "guard_notes": "maze_coverage_pct >= 90",
            },
        ],
    })


async def test_achievements_missing_catalog_returns_empty_list(client, fake_db, test_settings):
    # config/achievements never seeded -- must not 500.
    resp = await client.get(URL, headers=_auth_headers(test_settings))
    assert resp.status_code == 200
    assert resp.json()["achievements"] == []


async def test_achievements_no_progress_all_locked(client, fake_db, test_settings):
    _seed_catalog(fake_db)
    resp = await client.get(URL, headers=_auth_headers(test_settings, "user-achv-2"))
    body = resp.json()
    assert len(body["achievements"]) == 2
    assert all(a["unlocked"] is False for a in body["achievements"])


async def test_achievements_reflects_unlocked_state_for_this_user(client, fake_db, test_settings):
    _seed_catalog(fake_db)
    fake_db.seed("achievement_progress", "user-achv-3", {
        "uid": "user-achv-3",
        "unlocked": ["first_blood"],
        "unlock_timestamps": {"first_blood": NOW},
    })

    resp = await client.get(URL, headers=_auth_headers(test_settings, "user-achv-3"))
    by_id = {a["achievement_id"]: a for a in resp.json()["achievements"]}
    assert by_id["first_blood"]["unlocked"] is True
    assert by_id["first_blood"]["unlocked_at"] is not None
    assert by_id["maze_master"]["unlocked"] is False


async def test_achievements_isolated_per_user(client, fake_db, test_settings):
    _seed_catalog(fake_db)
    fake_db.seed("achievement_progress", "user-achv-4", {
        "uid": "user-achv-4", "unlocked": ["first_blood"], "unlock_timestamps": {"first_blood": NOW},
    })

    # A different user must not see user-achv-4's unlock.
    resp = await client.get(URL, headers=_auth_headers(test_settings, "user-achv-5"))
    by_id = {a["achievement_id"]: a for a in resp.json()["achievements"]}
    assert by_id["first_blood"]["unlocked"] is False


async def test_achievements_rarity_falls_back_without_rarity_job_data(client, fake_db, test_settings):
    _seed_catalog(fake_db)
    resp = await client.get(URL, headers=_auth_headers(test_settings, "user-achv-6"))
    by_id = {a["achievement_id"]: a for a in resp.json()["achievements"]}
    assert by_id["first_blood"]["rarity"] == "COMMON"
    assert by_id["first_blood"]["rarity_percent"] is None


async def test_achievements_uses_measured_rarity_when_available(client, fake_db, test_settings):
    _seed_catalog(fake_db)
    fake_db.seed("achievement_rarities", "first_blood", {
        "achievement_id": "first_blood", "total_players": 1000, "unlocked_by": 784,
        "rarity_percent": 78.4, "rarity_tier": "COMMON", "computed_at": NOW,
    })

    resp = await client.get(URL, headers=_auth_headers(test_settings, "user-achv-7"))
    by_id = {a["achievement_id"]: a for a in resp.json()["achievements"]}
    assert by_id["first_blood"]["rarity_percent"] == 78.4
