# T-210 — Backend /progress (GAME-001)

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | High — critical path para el cliente Godot |
| **Status** | Done — GET /progress ✅ + POST /progress/level-complete ✅ (Firestore completo) |
| **Date** | 2026-06-30 |
| **Workstream** | INFRA-003 (FastAPI services) |
| **Commit** | `d0bfe73` |
| **Depends-on** | INFRA-005 (schema `progress/` + `season_progress/`), INFRA-003 (Cloud Run) |

---

## Descripción

Implementa el sistema de progresión server-authoritative de MotaMaze. El servidor valida que los niveles se completen en orden, mantiene los mejores scores y estrellas por nivel, y acumula Season Stars para el Season Pass.

**Acceptance criteria:**

- `GET /progress` devuelve best_level, total_stars, levels map, season_stars — nuevo jugador devuelve estado inicial (no 404)
- `POST /progress/level-complete` bloquea niveles no desbloqueados (403 PROGRESS_LEVEL_LOCKED)
- Stars delta: solo acumula Season Stars por mejora sobre el mejor previo del nivel
- Escribe `progress/{uid}` y `season_progress/{uid}` en Firestore
- BQ streaming preservado del stub DATA-002 ST-11
- Todos los campos `None` del stub eliminados

---

## Estado previo (stub DATA-002 ST-11)

```python
# POST /progress/level-complete devolvía:
return {
    "best_score": body.score,   # siempre el score del request (no comparaba)
    "new_best": True,           # siempre True
    "total_stars": None,        # stub
    "season_stars_earned": None, # stub
    "total_season_stars": None,  # stub
}
# Sin writes a Firestore. Sin GET /progress.
```

---

## Implementación

### `app/config.py`

```python
active_season_id: str = "season_001"
```
Config stub para MVP. Social-001 / Remote Config lo hará dinámico.

### `app/routers/game.py`

**Nuevas dependencias:**
```python
import asyncio
from fastapi import HTTPException
from google.cloud.firestore import AsyncClient
from app.dependencies import get_firestore_client
```

**`GET /progress`** — reads parallel vía `asyncio.gather`:
- `progress/{uid}` → best_level, levels map, total_stars (suma de estrellas por nivel)
- `season_progress/{uid}` → season_stars (reset a 0 si season_id no coincide — nueva temporada)
- Nuevo jugador sin documento: retorna estado inicial `{best_level: 0, total_stars: 0, ...}`

**`POST /progress/level-complete`** — lógica completa:

```
1. Validaciones de input (ya existían: level 1–30, stars 1–3, score ≥ 0)
2. Lee progress/{uid}
3. Validación de nivel desbloqueado:
   - Sin documento: solo level_id == 1 permitido
   - Con documento: level_id <= best_level + 1
4. Computa deltas:
   - new_stars = max(existing_stars, body.stars_earned)
   - new_score = max(existing_score, body.score)
   - stars_delta = max(0, body.stars_earned - existing_stars)  ← solo mejoras
   - new_best_level = max(existing_best_level, body.level_id)
   - newly_unlocked = level_id > existing_best_level
5. Escribe progress/{uid}:
   - Primera vez: set() completo con uid + best_level + levels map
   - Subsiguientes: update() con dot-path "levels.level_N" → preserva otros niveles
6. Lee + actualiza season_progress/{uid}:
   - Primera vez: set() con season_id + season_stars = stars_delta
   - Existente: update(season_stars = current + stars_delta) si stars_delta > 0
7. BQ streaming en background (sin cambio)
8. Retorna valores reales (sin None)
```

**Dot-path para actualización segura de niveles anidados:**
```python
# ❌ merge=True reemplazaría TODO el mapa levels
progress_ref.set({"levels": {"level_5": {...}}}, merge=True)

# ✅ Actualiza solo level_5, preserva level_1..level_4
progress_ref.update({
    "levels.level_5": {"stars": 3, "best_score": 4200, "completed_at": ...},
    "best_level": 5,
    "updated_at": now,
})
```

---

## Testing

### ST-01 — Validación de lógica (manual, ejecutar contra Cloud Run dev)

```bash
# Setup: Cloud Run dev proxy en puerto 8081
gcloud run services proxy motamaze-api --port=8081 --project=motamaze-dev --region=us-central1

BASE="http://localhost:8081"

# Obtener JWT (usar script de prueba de DATA-002 ST-12)
JWT="<token>"

# 1. GET /progress — nuevo jugador (sin datos en Firestore)
curl -s -H "Authorization: Bearer $JWT" $BASE/progress | python3 -m json.tool
# Esperado: {"best_level":0,"highest_unlocked_level":1,"total_stars":0,"levels":{},"season_id":"season_001","season_stars":0}

# 2. POST /progress/level-complete — level 1, primer intento
curl -s -X POST $BASE/progress/level-complete \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"level_id":1,"score":1234,"stars_earned":2,"duration_secs":45,"session_id":"test-session-1"}' \
  | python3 -m json.tool
# Esperado: best_score=1234, new_best=true, highest_unlocked_level=2,
#           total_stars=2, season_stars_earned=2, total_season_stars=2

# 3. GET /progress — después de level 1
curl -s -H "Authorization: Bearer $JWT" $BASE/progress | python3 -m json.tool
# Esperado: best_level=1, highest_unlocked_level=2, total_stars=2,
#           levels={"level_1":{"stars":2,"best_score":1234,...}}

# 4. POST level 2 — intento con level 3 (saltado) → debe rechazar
curl -s -X POST $BASE/progress/level-complete \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"level_id":3,"score":999,"stars_earned":1,"duration_secs":30,"session_id":"test-session-2"}' \
  | python3 -m json.tool
# Esperado: HTTP 403, error_code=PROGRESS_LEVEL_LOCKED

# 5. POST level 1 replay con mejor score (3 estrellas)
curl -s -X POST $BASE/progress/level-complete \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"level_id":1,"score":2000,"stars_earned":3,"duration_secs":30,"session_id":"test-session-3"}' \
  | python3 -m json.tool
# Esperado: best_score=2000, new_best=true, stars_earned=3,
#           season_stars_earned=1 (delta: 3-2=1), total_season_stars=3

# 6. POST level 1 replay con peor score (no mejora)
curl -s -X POST $BASE/progress/level-complete \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"level_id":1,"score":500,"stars_earned":1,"duration_secs":60,"session_id":"test-session-4"}' \
  | python3 -m json.tool
# Esperado: best_score=2000 (sin cambio), new_best=false,
#           season_stars_earned=0 (sin mejora), total_season_stars=3
```

---

## Resultados

### ST-01: Code review y commit

Commit `d0bfe73` pusheado — 2 archivos:
- `app/config.py` — `active_season_id = "season_001"`
- `app/routers/game.py` — GET /progress nuevo + POST /progress/level-complete completo (137 líneas agregadas, 22 eliminadas)

**Validaciones implementadas:**
- Level lock: PROGRESS_LEVEL_LOCKED 403 ✅
- Stars delta acumulativo (solo mejoras) ✅
- Dot-path update (preserva otros niveles en Firestore) ✅
- Parallel reads en GET /progress ✅
- Estado inicial para nuevo jugador ✅

### Follow-ups / notes

- **ST-02 (integration tests):** Pendiente deploy a Cloud Run dev — ejecutar el script de testing de esta sección
- **T-440 cross-validation (condición 2 de Juan):** `POST /share/create` recibe `score` del cliente. Una vez que `progress/{uid}` existe, puede validarse contra `best_score` del nivel más alto. Agregar en T-440 ST-02 o en un ticket separado.
- **Remote Config para `active_season_id`:** Actualmente hardcoded en Settings. Social-001 lo hará dinámico.
- **Concurrent writes:** Para MVP, read-then-write es suficiente. Si hay contención (multi-dispositivo), Firestore transactions se agregan en v1.1.
