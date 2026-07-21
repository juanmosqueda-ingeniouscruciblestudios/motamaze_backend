"""Tests for POST /share/create, GET /s/{token}, GET /ogimg/{token} — T-440.
Previously zero coverage (the changelog's "ST-01" run was a manual script,
never committed as a test)."""

from datetime import datetime, timedelta, timezone

from app.services import jwt_service

CREATE_URL = "/share/create"


def _auth_headers(test_settings, uid: str = "user-share-1") -> dict:
    token, _ = jwt_service.create_access_token(
        user_id=uid,
        provider="google",
        session_id="session-share-1",
        project_id=test_settings.gcp_project_id,
        secret_name=test_settings.jwt_secret_name,
        key_id=test_settings.jwt_key_id,
        issuer=test_settings.jwt_issuer,
    )
    return {"Authorization": f"Bearer {token}"}


def _valid_body(**overrides) -> dict:
    body = {"score": 4200, "level_reached": 12, "season_id": "season_001"}
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# POST /share/create
# ---------------------------------------------------------------------------


async def test_share_create_requires_auth(client, test_settings):
    resp = await client.post(CREATE_URL, json=_valid_body())
    assert resp.status_code == 401  # HTTPBearer: no Authorization header


async def test_share_create_success_writes_uid_not_user_id(client, fake_db, test_settings):
    resp = await client.post(
        CREATE_URL, json=_valid_body(), headers=_auth_headers(test_settings, "user-share-1")
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"share_url", "token", "og_image_url", "expires_at"}
    assert body["token"] and len(body["token"]) == 12
    assert body["share_url"].endswith(f"/s/{body['token']}")
    assert body["og_image_url"].endswith(f"/ogimg/{body['token']}")

    doc = (await fake_db.collection("shares").document(body["token"]).get()).to_dict()
    assert doc["uid"] == "user-share-1"
    assert "user_id" not in doc  # regression guard for the uid/user_id rename
    assert doc["score"] == 4200
    assert doc["level_reached"] == 12
    assert doc["season_id"] == "season_001"
    assert "cloudinary.com" in doc["og_image_url"]
    assert "4200%20pts" in doc["og_image_url"]
    assert "Nivel%2012" in doc["og_image_url"]
    # f_auto,q_auto delivery flags (2026-07-21 fix) — without these the real
    # Cloudinary URL served an untransformed ~1.2MB PNG instead of <600KB WebP.
    assert "f_auto,q_auto" in doc["og_image_url"]


async def test_share_create_invalid_level_reached(client, test_settings):
    for bad_level in (0, 31, -1):
        resp = await client.post(
            CREATE_URL, json=_valid_body(level_reached=bad_level), headers=_auth_headers(test_settings)
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error_code"] == "SHARE_INVALID_LEVEL"


async def test_share_create_negative_score(client, test_settings):
    resp = await client.post(
        CREATE_URL, json=_valid_body(score=-1), headers=_auth_headers(test_settings)
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "SHARE_INVALID_SCORE"


async def test_share_create_missing_season_id(client, test_settings):
    resp = await client.post(
        CREATE_URL, json=_valid_body(season_id=""), headers=_auth_headers(test_settings)
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error_code"] == "SEASON_NOT_ACTIVE"


# ---------------------------------------------------------------------------
# GET /s/{token}
# ---------------------------------------------------------------------------


async def test_share_view_not_found(client):
    resp = await client.get("/s/doesnotexist12")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error_code"] == "SHARE_TOKEN_NOT_FOUND"


async def test_share_view_renders_og_tags(client, fake_db, test_settings):
    create_resp = await client.post(
        CREATE_URL, json=_valid_body(score=999, level_reached=7), headers=_auth_headers(test_settings)
    )
    token = create_resp.json()["token"]

    resp = await client.get(f"/s/{token}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    html = resp.text
    assert "999 pts" in html
    assert "nivel 7" in html.lower()
    assert 'og:image' in html
    assert f'motamaze://share/{token}' in html


async def test_share_view_expired(client, fake_db):
    fake_db.seed("shares", "expiredtoken", {
        "uid": "u1", "score": 1, "level_reached": 1, "season_id": "season_001",
        "created_at": datetime.now(timezone.utc) - timedelta(days=100),
        "expires_at": datetime.now(timezone.utc) - timedelta(days=1),
        "og_image_url": "https://res.cloudinary.com/x/image/upload/x",
        "share_url": "https://motamaze.com/s/expiredtoken",
    })
    resp = await client.get("/s/expiredtoken")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error_code"] == "SHARE_TOKEN_NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /ogimg/{token}
# ---------------------------------------------------------------------------


async def test_ogimg_redirects_to_stored_url(client, fake_db, test_settings):
    create_resp = await client.post(
        CREATE_URL, json=_valid_body(), headers=_auth_headers(test_settings)
    )
    token = create_resp.json()["token"]

    resp = await client.get(f"/ogimg/{token}", follow_redirects=False)
    assert resp.status_code == 302
    assert "cloudinary.com" in resp.headers["location"]


async def test_ogimg_unknown_token_redirects_to_fallback(client, test_settings):
    resp = await client.get("/ogimg/doesnotexist12", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == (
        f"https://res.cloudinary.com/{test_settings.cloudinary_cloud_name}"
        f"/image/upload/{test_settings.cloudinary_share_image_id}"
    )
