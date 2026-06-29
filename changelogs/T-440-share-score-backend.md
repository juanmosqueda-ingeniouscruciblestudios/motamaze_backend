# T-440 — Share Score Backend

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | High |
| **Status** | Done — ST-01 ✅ POST /share/create + GET /s/{token} + GET /ogimg/{token} |
| **Date** | 2026-06-30 |
| **Workstream** | INFRA-003 (FastAPI services) |
| **Commit** | `e355b67` |
| **Depends-on** | INFRA-003 (Cloud Run), DATA-002 (Firestore), Decision L (Tenjin — T-311 stub) |

---

## Description

Implements the share-score backend for MotaMaze. A player finishes a level, taps Share, the client calls `POST /share/create`, receives a `share_url`, and shares it. Anyone who opens the URL sees an HTML page with proper OG meta tags (og:title, og:image, og:url, Twitter Card) so that WhatsApp, Telegram, iMessage, and other crawlers render a rich preview card showing the player's score and level.

**Acceptance criteria:**

- `POST /share/create` (authenticated) → returns `share_url`, `token`, `og_image_url`, `expires_at`
- `GET /s/{token}` (public) → returns HTML with OG meta tags + deep link redirect to `motamaze://share/{token}`
- `GET /ogimg/{token}` (public) → 302 redirect to Cloudinary URL; graceful fallback to base image if token not found
- Share cards use Fredoka font (Google Fonts via Cloudinary)
- `og:image` points to `/ogimg/{token}`, not directly to Cloudinary (provider independence)
- All values in OG image URL come from server-validated integers, not raw client strings
- Token: 12-char base62, collision-retry loop

---

## Previous state (before this change)

`app/routers/social.py` did not exist. `app/config.py` had no Cloudinary or share settings. `.gitignore` had no binary asset exclusions.

---

## Implementation details

### `app/routers/social.py` (new file, 196 lines)

**Token generation:**
```python
_BASE62 = string.ascii_letters + string.digits  # 62^12 ≈ 3.2×10²¹ tokens
def _generate_token(length: int = 12) -> str:
    return "".join(secrets.choice(_BASE62) for _ in range(length))
```
Collision-retry loop (3 attempts): reads Firestore `shares/{token}` before writing; break on first non-existent doc. At 62^12 scale, collisions are virtually impossible.

**Cloudinary OG image URL (`_og_image_url`):**
```python
score_layer = f"l_text:Fredoka@google_90_700:{score}%20pts,co_white,g_center,y_-60"
level_layer = f"l_text:Fredoka@google_55_500:Nivel%20{level_reached},co_white,g_center,y_40"
return f"https://res.cloudinary.com/{cloud}/image/upload/{score_layer}/{level_layer}/{base}"
```
- No Cloudinary API call at runtime — URL is constructed from config constants and server-validated integers
- `score` and `level_reached` are Pydantic `int` types: injection impossible
- Font: Fredoka@google (Google Fonts), weight 700 (score) / 500 (level) — as specified by Juan 2026-06-30
- Base image: `settings.cloudinary_share_image_id` (`motamaze_1200x630_v2_yivwuj`) — stored in config, not hardcoded inline

**OG proxy URL (`_og_proxy_url`):**
```python
def _og_proxy_url(settings: Settings, token: str) -> str:
    return f"{settings.share_base_url}/ogimg/{token}"
```

**`POST /share/create`** (authenticated via `verify_jwt`):
- Validates: `1 ≤ level_reached ≤ 30`, `score ≥ 0`, `season_id` non-empty
- Writes to `shares/{token}`: `user_id`, `score`, `level_reached`, `season_id`, `created_at`, `expires_at`, `og_image_url` (Cloudinary URL), `share_url`
- Returns `og_image_url` as the proxy URL (`/ogimg/{token}`), not the direct Cloudinary URL
- `expires_at` stub: 2026-09-14T23:59:59Z (soft-launch date); Social-001 will derive from active season doc
- `share_url` stub: `motamaze.com/s/{token}`; T-311 will replace with Tenjin tracking link

**`GET /s/{token}`** (public, returns HTML):
- Reads `shares/{token}` from Firestore; 404 if not exists or expired
- OG meta tags use `/ogimg/{token}` (proxy), not direct Cloudinary URL → provider independence
- Deep link redirect: `<script>window.location = "motamaze://share/{token}";</script>`
- Fallback link: Play Store URL

**`GET /ogimg/{token}`** (public, returns 302 redirect):
- Reads `shares/{token}.og_image_url` from Firestore → 302 to Cloudinary URL
- Fallback (token not found): 302 to base image (`cloudinary.com/.../{cloudinary_share_image_id}`)
- Benefit: future provider migration requires only changing `_og_image_url()` + re-saving Firestore docs; no client changes

### `app/config.py`

Three new settings added:
```python
cloudinary_cloud_name: str = "lyku9hz2"
cloudinary_share_image_id: str = "motamaze_1200x630_v2_yivwuj"
share_base_url: str = "https://motamaze.com"
```

### `.gitignore`

Added binary asset exclusions (design assets are stored in Cloudinary, not git):
```
# Design assets — stored in Cloudinary, not in git
*.png
*.jpg
*.webp
Music_SFXs/
Music_SFXs.zip
docs/*.pdf
```

---

## Pre-production gates (separate tickets, must close before 2026-10-15)

See Monday tickets created 2026-06-30:

| # | Action | Owner | Deadline |
|---|---|---|---|
| 5 | Execute Cloudinary DPA before any production traffic | Juan | Before prod deploy |
| 6 | Upgrade to Plus tier ($89/month) before launch | Juan/Saul | Before 2026-10-15 |
| 7 | Add Cloudinary to privacy policy as data processor (CDN delivery IPs) | Juan | Before launch |
| 8 | Health-check monitor: Cloud Scheduler → fetch known OG URL → alert on non-200 | Saul | Before 2026-10-15 |

**Deferred (post-MVP, before Brazil market opening):**
- LGPD coverage verification in Cloudinary DPA
- AI training opt-out for studio assets (Enterprise negotiation)

**Pending design discussion with Juan:**
- Server-side score cross-validation against progression records (requires T-210; currently validated by type+range only)
- PII review: Cloudinary receives CDN delivery IPs — confirm scope under MX/BR/US law

---

## Testing

### ST-01: Implementation smoke test (unit level)

```python
# Manual URL construction verification
from app.routers.social import _og_image_url
from app.config import Settings

s = Settings(gcp_project_id="motamaze-dev")

# 4-digit score
url = _og_image_url(s, 1234, 5)
assert "Fredoka@google_90_700:1234%20pts" in url
assert "Fredoka@google_55_500:Nivel%205" in url
assert "lyku9hz2" in url
assert "motamaze_1200x630_v2_yivwuj" in url

# 5-digit score
url = _og_image_url(s, 12345, 15)
assert "Fredoka@google_90_700:12345%20pts" in url

# 6-digit score
url = _og_image_url(s, 123456, 30)
assert "Fredoka@google_90_700:123456%20pts" in url

print("URL sample (4-digit):", _og_image_url(s, 1234, 5))
```

**Integration tests required (ST-02 — pending deploy to dev):**
- Call `POST /share/create` via Cloud Run dev proxy (port 8081)
- Verify Cloudinary URL renders in browser (Fredoka font, correct score/level)
- Test with Portuguese display formatting (scores as integers, no decimal concern)
- Verify OG crawlers: WhatsApp (web.whatsapp.com debugger), Telegram (@WebPageBot), iMessage (iOS device)
- Confirm `/ogimg/{token}` returns 302 with correct Location header
- Confirm `/ogimg/invalidtoken` returns 302 to fallback base image

---

## Results

### ST-01: Code review and commit

All 3 files committed and pushed as `e355b67`:
- `.gitignore` — 8 lines added
- `app/config.py` — 3 settings added
- `app/routers/social.py` — 196 lines (3 endpoints + 4 helpers)

**Cloudinary font change (Juan condition 1):** Arial → Fredoka@google ✅
**Redirect proxy (Juan recommendation 9):** GET /ogimg/{token} implemented ✅
**og:image isolation:** HTML uses `/ogimg/{token}`, not direct Cloudinary URL ✅
**Config constant for image ID:** `cloudinary_share_image_id` in Settings ✅

### Follow-ups / notes

- **ST-02 (integration tests):** Must be done after next `gcloud run deploy` — requires live Cloud Run endpoint + valid JWT
- **T-311:** Replace `share_url` stub with Tenjin tracking link
- **T-210:** Add server-side score cross-validation (cross-reference with progression record)
- **Social-001:** Replace `expires_at` hardcoded stub with active season lookup
- **Pre-production gates 5-8:** See Monday tickets created 2026-06-30
