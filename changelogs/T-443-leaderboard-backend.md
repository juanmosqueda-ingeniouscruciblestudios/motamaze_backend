# T-443 — Leaderboard Backend

| Field | Value |
|---|---|
| **Type** | Feature — Game Services Backend |
| **Priority** | High — No-Go item 15 (App Check + CDN mandatory pre-launch) |
| **Status** | ✅ Done — ST-01 ✅ implementación completa (2026-07-14) |
| **Date** | 2026-07-14 |
| **Workstream** | Game Services Backend |
| **Owner** | Saul Zavala Morin |
| **Monday Item ID** | 12364125889 |
| **Depends-on** | T-112 ✅ (Firestore users schema), T-120 ✅ (JWT auth), T-300 ✅ (BQ tables) |
| **Desbloquea** | T-444 (Leaderboard client + screen) |

---

## Descripción

Implementa el backend del leaderboard de temporada: Firestore `leaderboards/{season_id}` schema, `POST /leaderboard/score` (App Check obligatorio + anomaly log en BigQuery) y `GET /leaderboard` (CDN-cached, top 100 + player rank).

Requisitos no negociables del ticket:
- **App Check MANDATORY** en cada write (No-Go item 15)
- **CDN 5-min TTL MANDATORY** en GET antes de soft launch
- **BigQuery anomaly log** por cada score event
- **Children excluidos** (`restricted_features=true` → 403)

---

## Estado previo

No existía ningún endpoint de leaderboard. El contrato REST-001 tenía `POST /leaderboard/score` y `GET /leaderboard` como endpoints pendientes (T-443).

---

## Implementación

### `app/config.py`

```python
firebase_project_number: str = "542009654415"
```

Número de proyecto GCP — requerido para verificar el `iss` y `aud` del App Check JWT.

---

### `app/routers/leaderboard.py` (nuevo)

#### App Check verification

```python
_APPCHECK_JWKS_URL = "https://firebaseappcheck.googleapis.com/v1/jwks"
_appcheck_jwks_cache: TTLCache = TTLCache(maxsize=1, ttl=3600)
```

`_get_appcheck_jwks()` — fetches Firebase's public JWKS async (via `asyncio.to_thread` + `urllib.request`). Cacheado 1 hora con `cachetools.TTLCache` (ya en `pyproject.toml`). Sin nueva dependencia.

`verify_app_check()` — dependencia FastAPI:
1. Header `X-Firebase-AppCheck` ausente → 401 `LEADERBOARD_APPCHECK_MISSING`
2. Decode header para obtener `kid`
3. Buscar la clave en JWKS por `kid`; si no se encuentra, limpia el cache y lanza error (maneja rotación de claves)
4. Verifica firma RS256 con `python-jose[cryptography]` (ya instalado)
5. Verifica `iss = https://firebaseappcheck.googleapis.com/542009654415`
6. Verifica `aud` contiene `projects/542009654415` (el token puede tener `aud` como array o string)

#### Firestore schema

```
leaderboards/{season_id}                    ← root doc: metadata de temporada
  ├── name: string                          e.g. "Garden Rush"
  ├── season_id: string
  └── top3_prizes: [{rank, prize}]

leaderboards/{season_id}/scores/{uid}       ← subcollección: una entrada por jugador
  ├── uid: string
  ├── display_name: string
  ├── season_stars: int                     score autoritativo
  └── updated_at: timestamp
```

#### `POST /leaderboard/score`

```
Auth: JWT + App Check (verify_app_check dependency)
```

Flujo:
1. Verifica `season_id == active_season_id` → 404 `SEASON_NOT_ACTIVE` si no coincide
2. Lee `users/{uid}.restricted_features` → 403 `LEADERBOARD_RESTRICTED` si `True`
3. Lee `season_progress/{uid}.season_stars` como score **autoritativo** — ignora `body.score`
4. Detecta anomalía: `body.score != season_stars` → `anomaly=True` en BQ
5. Lee `leaderboards/{season_id}/scores/{uid}` — actualiza solo si `season_stars > existing_stars`
6. Rank aproximado: `count(scores where season_stars > current) + 1` vía Firestore count aggregation
7. BQ background: `player_behavior` event `leaderboard_score_submit` con `extra_json: {client_score, anomaly, updated}`

**Por qué se ignora `body.score`:** El cliente puede enviar cualquier valor. El score autoritativo siempre viene de `season_progress/{uid}.season_stars` en Firestore, que solo se actualiza desde el backend en `POST /progress/level-complete`. La discrepancia se loguea como anomalía para detectar intentos de manipulación.

#### `GET /leaderboard`

```
Auth: JWT
Query params: type=global|weekly, season_id?
Response headers: Cache-Control: public, max-age=300
```

Flujo:
1. Valida `type` → 400 `LEADERBOARD_INVALID_TYPE` si no es `global|weekly`
2. Lee `leaderboards/{target_season}` doc → 404 `SEASON_NOT_FOUND` si no existe
3. Query `scores` subcollection `ORDER BY season_stars DESC LIMIT 100`
4. Si el jugador está en top 100: su rank es su posición (i+1)
5. Si no está en top 100: lee su doc individual + count aggregation para rank exacto
6. Responde con `Cache-Control: public, max-age=300` (No-Go item 15 — CDN)

**Nota weekly:** Para MVP, `type=weekly` usa los mismos datos que `global` (score de temporada). La diferenciación por semana requiere una subcollección `weekly_scores/{week_id}` — diferida a T-444 si se requiere.

#### `app/main.py`

```python
from app.routers import auth, game, health, jobs, leaderboard, payments, social, well_known
...
app.include_router(leaderboard.router)
```

---

## Testing

### ST-01 — Syntax check (2026-07-14)

```bash
python -c "
import ast
for f in ['app/config.py', 'app/routers/leaderboard.py', 'app/main.py']:
    ast.parse(open(f).read())
    print(f'SYNTAX OK: {f}')
"
# SYNTAX OK: app/config.py
# SYNTAX OK: app/routers/leaderboard.py
# SYNTAX OK: app/main.py
```

### ST-02 — Integration tests vs Cloud Run (pendiente T-444 / T-607)

Requiere:
1. Seed de `leaderboards/season_001` en Firestore (ver comando abajo)
2. Firebase App Check token real (requiere app publicada en Play Console o debug token)
3. Usuario con `season_stars > 0` en Firestore

**Seed del doc de temporada:**
```bash
# Crear leaderboards/season_001 en Firestore prod
python - <<'EOF'
import asyncio
from google.cloud import firestore

async def seed():
    db = firestore.AsyncClient(project="motamaze")
    await db.collection("leaderboards").document("season_001").set({
        "season_id": "season_001",
        "name": "Garden Rush",
        "top3_prizes": [
            {"rank": 1, "prize": "Mota Gold Badge"},
            {"rank": 2, "prize": "Mota Silver Badge"},
            {"rank": 3, "prize": "Mota Bronze Badge"},
        ],
    })
    print("Seeded leaderboards/season_001")

asyncio.run(seed())
EOF
```

**App Check debug token (dev testing):**
Firebase Console → Project Settings → App Check → MotaMaze Android → Manage debug tokens → Add debug token. Usar ese token en `X-Firebase-AppCheck` header durante pruebas.

**Test POST (con debug token):**
```bash
curl -X POST https://motamaze-backend-xxx.a.run.app/leaderboard/score \
  -H "Authorization: Bearer $JWT" \
  -H "X-Firebase-AppCheck: $DEBUG_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"season_id": "season_001", "score": 999}'
# Esperado: {"updated": true/false, "rank": N, "season_stars": <authoritative>}
```

**Test GET:**
```bash
curl https://motamaze-backend-xxx.a.run.app/leaderboard \
  -H "Authorization: Bearer $JWT"
# Esperado: 200, top_players[], player_rank, Cache-Control: public, max-age=300
```

---

## Follow-ups / Notes

- **Firestore index:** `scores` subcollection requiere índice en `season_stars` (descendente) para el query `ORDER BY`. Firestore crea índices single-field automáticamente. El count aggregation `where season_stars > X` usa el mismo índice. Si Firestore lanza error de índice en el primer request, crear manualmente en Firestore Console → Indexes.
- **weekly leaderboard:** MVP usa los mismos datos que `global`. Si T-444 requiere weekly diferenciado, agregar subcollección `weekly_scores/{week_id}/scores/{uid}` y Cloud Scheduler para resetear semanalmente.
- **restricted_features:** Campo leído de `users/{uid}.restricted_features`. T-401 (parental consent) settea este campo cuando un usuario es identificado como menor. Hasta que T-401 esté implementado, el campo no existe → tratado como `False` (no restringido) — comportamiento correcto.
- **CDN:** `Cache-Control: public, max-age=300` habilitado en el response. Para que el CDN (Cloud CDN) lo cachee, el load balancer del Cloud Run debe estar configurado con un backend que honre este header. Verificar en T-607 E2E.
- **App Check debug mode:** Para testing en dev sin app publicada, Firebase App Check soporta debug tokens. Registrar en Firebase Console → App Check → Debug tokens. El backend acepta estos tokens en dev igual que en prod (App Check verifica contra los mismos JWKS).
- **Rotación de claves JWKS:** Si Firebase rota sus claves App Check, el cache (1h TTL) tiene claves stale. El `_appcheck_jwks_cache.clear()` en el `unknown kid` path fuerza un refresh inmediato en el próximo request.
- **`display_name` en scores:** Se lee de `users/{uid}.display_name` al momento del score submit. Si el usuario cambia su nombre después, el score en leaderboard muestra el nombre viejo. Para MVP esto es aceptable — actualizar en T-444 si se requiere consistencia.
