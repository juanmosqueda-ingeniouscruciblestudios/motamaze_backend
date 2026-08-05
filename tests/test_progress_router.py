"""Integration tests for GET /progress. Zero prior coverage (same pre-existing
gap as /lives/spend and /progress/level-complete had) -- written alongside the
2026-08-05 fix where `levels` was returning Firestore's raw map instead of the
array REST-001 documents and the Godot client (progression_service.gd)
parses. See docs/DATA_MODEL.md#progress and REST-001's GET /progress."""

from datetime import datetime, timezone

from app.services import jwt_service

URL = "/progress"

NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)


def _auth_headers(test_settings, uid: str = "user-progress-1") -> dict:
    token, _ = jwt_service.create_access_token(
        user_id=uid,
        provider="google",
        session_id="session-progress-1",
        project_id=test_settings.gcp_project_id,
        secret_name=test_settings.jwt_secret_name,
        key_id=test_settings.jwt_key_id,
        issuer=test_settings.jwt_issuer,
    )
    return {"Authorization": f"Bearer {token}"}


async def test_new_user_returns_empty_levels_array(client, fake_db, test_settings):
    resp = await client.get(URL, headers=_auth_headers(test_settings, "user-progress-new"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "user-progress-new"
    assert body["levels"] == []
    assert body["best_level"] == 0
    assert body["highest_unlocked_level"] == 1
    assert body["total_stars"] == 0


async def test_levels_returned_as_array_of_objects_sorted_by_level_id(client, fake_db, test_settings):
    fake_db.seed("progress", "user-progress-2", {
        "uid": "user-progress-2",
        "best_level": 3,
        "levels": {
            # seeded out of order to prove the response sorts, not just echoes
            "3": {"stars": 2, "best_score": 500, "completed_at": NOW},
            "1": {"stars": 3, "best_score": 900, "completed_at": NOW},
        },
    })

    resp = await client.get(URL, headers=_auth_headers(test_settings, "user-progress-2"))
    body = resp.json()

    assert isinstance(body["levels"], list)
    assert [lvl["level_id"] for lvl in body["levels"]] == [1, 3]

    level_1 = body["levels"][0]
    assert level_1 == {
        "level_id": 1,
        "stars_earned": 3,
        "best_score": 900,
        "completed_at": NOW.isoformat(),
    }
    assert body["total_stars"] == 5  # 3 + 2
    assert body["best_level"] == 3
    assert body["highest_unlocked_level"] == 4


async def test_season_stars_only_counted_for_active_season(client, fake_db, test_settings):
    fake_db.seed("season_progress", "user-progress-3", {
        "season_id": "season_stale", "season_stars": 999,
    })
    resp = await client.get(URL, headers=_auth_headers(test_settings, "user-progress-3"))
    assert resp.json()["season_stars"] == 0  # stale season_id, ignored


async def test_season_stars_included_for_active_season(client, fake_db, test_settings):
    fake_db.seed("season_progress", "user-progress-4", {
        "season_id": test_settings.active_season_id, "season_stars": 42,
    })
    resp = await client.get(URL, headers=_auth_headers(test_settings, "user-progress-4"))
    assert resp.json()["season_stars"] == 42
