# T-220 — Backend /lives (GAME-002)

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | High — critical path para el loop core (gastar vida antes de cada partida) |
| **Status** | Done — GET /lives ✅ + POST /lives/spend ✅ + POST /lives/grant ✅ (Firestore completo) |
| **Date** | 2026-06-30 |
| **Workstream** | INFRA-003 (FastAPI services) |
| **Commit** | `abee8a9` |
| **Depends-on** | T-210 (progress schema pattern), INFRA-005 (lives/{uid} schema), INFRA-003 (Cloud Run) |

---

## Descripción

Implementa el sistema de vidas server-authoritative de MotaMaze. El servidor controla el estado de las vidas, aplica regeneración automática en cada lectura, y garantiza que el gasto sea atómico (sin vidas negativas).

**Acceptance criteria:**

- `GET /lives` inicializa nuevo jugador con 5 vidas (no 404); aplica regeneración server-side
- `POST /lives/spend` es atómico: Firestore transaction previene race conditions
- `POST /lives/grant` completa el stub DATA-002 ST-09: rellena `current_lives`, `max_lives`, `next_regen_at`, `capped` (elimina los `None` previos)
- Regen: `floor(elapsed / 1800s)` vidas añadidas, avanzando `last_regen_at` en múltiplos del intervalo
- `next_regen_at = null` cuando `current_lives == max_lives`

---

## Estado previo (stub DATA-002 ST-09)

```python
# POST /lives/grant devolvía:
return {
    "granted": quantity or 1,
    "current_lives": None,   # stub
    "max_lives": None,       # stub
    "next_regen_at": None,   # stub
    "capped": False,
}
# Sin GET /lives. Sin POST /lives/spend. Sin writes a Firestore.
```

---

## Implementación

### `app/routers/game.py`

**Nuevas dependencias:**
```python
from datetime import timedelta  # añadido (ya existía datetime, timezone)
from google.cloud.firestore import AsyncClient, async_transactional
```

**Constantes:**
```python
REGEN_INTERVAL_SECS = 1800  # 30 min — Remote Config tuneable en v1.1
DEFAULT_MAX_LIVES = 5
```

**Helpers:**

```python
def _apply_regen(count, max_lives, last_regen_at, now) -> (int, datetime):
    """Aplica regeneración. Avanza last_regen_at por intervalos completos."""
    elapsed = (now - last_regen_at).total_seconds()
    lives_to_add = int(elapsed // REGEN_INTERVAL_SECS)
    new_count = min(count + lives_to_add, max_lives)
    new_last = last_regen_at + timedelta(seconds=lives_to_add * REGEN_INTERVAL_SECS)
    return new_count, new_last

def _next_regen_dt(count, max_lives, last_regen_at) -> datetime | None:
    if count >= max_lives:
        return None
    return last_regen_at + timedelta(seconds=REGEN_INTERVAL_SECS)
```

**Por qué avanzar `last_regen_at` por intervalos completos:**
Si la última regen fue a las 10:00 y han pasado 2h30min (= 5 intervalos completos de 30 min):
- `last_regen_at` avanza a 10:00 + 5×30min = 12:30
- `next_regen_at` = 12:30 + 30min = 13:00
- Si se hiciera `last_regen_at = now`, el siguiente ciclo empezaría desde 12:30 — correcto
- Si se hiciera `last_regen_at = now (12:30)`, perdería el tiempo parcial ya transcurrido — incorrecto

**`GET /lives`** — Lee, aplica regen, escribe si cambió:
- Nuevo jugador sin documento: `set()` con 5 vidas, sin regen timer
- `max_lives` leído de Firestore (permite customización futura por Remote Config)
- Solo escribe a Firestore si `new_count != count` (evita writes innecesarios)

**`POST /lives/spend`** — Firestore transaction:

```python
@async_transactional
async def _spend_txn(txn, lives_ref, user_id, now):
    snap = await lives_ref.get(transaction=txn)
    # ... aplica regen ...
    if new_count == 0:
        raise HTTPException(400, detail={"error_code": "LIVES_INSUFFICIENT"})
    new_count -= 1
    txn.update(lives_ref, {...})
    return new_count, next_r

# Llamado como:
remaining, next_regen = await _spend_txn(db.transaction(), lives_ref, user_id, now)
```

`@async_transactional` reintenta automáticamente en contención Firestore (`Aborted`). `HTTPException` no es `Aborted` — propaga sin retry.

Nota: el decorator se define a nivel de módulo (no dentro de la función del endpoint) para evitar recrearlo en cada request.

**`POST /lives/grant`** — Completa stub con Firestore:
1. Mantiene toda la lógica BQ del stub (sin cambios)
2. Si `quantity > 0`: lee `lives/{uid}`, aplica regen, suma vidas (capped a `max_lives`)
3. `actual_granted = min(quantity, max_lives - count)` — puede ser menor al solicitado
4. `capped = actual_granted < quantity`
5. Para `source == "iap"` y `entitlement_type == "life_pack"`: actualiza `entitlements/{uid}.life_packs_total += 1`
6. `quantity = None` para `no_ads` y `skin` products → salta el write de vidas

---

## Firestore schema — `lives/{uid}`

| Campo | Tipo | Descripción |
|---|---|---|
| `uid` | string | = document ID |
| `count` | number | Vidas actuales (0–max_lives) |
| `max_lives` | number | Máximo (default 5) |
| `last_regen_at` | timestamp | Referencia para el ciclo de regen |
| `next_regen_at` | timestamp \| null | Pre-computado para el timer del cliente |
| `updated_at` | timestamp | Última escritura |

---

## Testing

### ST-01 — Validación de lógica (manual, ejecutar contra Cloud Run dev)

```bash
# Setup: Cloud Run dev proxy en puerto 8081
gcloud run services proxy motamaze-api --port=8081 --project=motamaze-dev --region=us-central1

BASE="http://localhost:8081"
JWT="<token>"   # usar script de DATA-002 ST-12

# 1. GET /lives — nuevo jugador (sin documento en Firestore)
curl -s -H "Authorization: Bearer $JWT" $BASE/lives | python3 -m json.tool
# Esperado: {"current_lives":5,"max_lives":5,"next_regen_at":null,"regen_interval_secs":1800}

# 2. POST /lives/spend — primera vida
curl -s -X POST $BASE/lives/spend \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"session_id":"test-session-1"}' | python3 -m json.tool
# Esperado: {"remaining_lives":4,"next_regen_at":"<ISO timestamp ~30min from now>"}

# 3. GET /lives — verificar estado post-spend
curl -s -H "Authorization: Bearer $JWT" $BASE/lives | python3 -m json.tool
# Esperado: current_lives=4, next_regen_at=<timestamp>

# 4. POST /lives/spend — vaciar hasta 0 (4 veces más)
for i in 1 2 3 4; do
  curl -s -X POST $BASE/lives/spend \
    -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
    -d "{\"session_id\":\"test-session-drain-$i\"}" | python3 -m json.tool
done
# Esperado: remaining_lives va de 3 → 2 → 1 → 0

# 5. POST /lives/spend — cuando count=0 → debe rechazar
curl -s -X POST $BASE/lives/spend \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"session_id":"test-session-fail"}' | python3 -m json.tool
# Esperado: HTTP 400, error_code=LIVES_INSUFFICIENT

# 6. POST /lives/grant — rewarded ad (1 vida)
curl -s -X POST $BASE/lives/grant \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"source":"rewarded_ad_ssv","reward_token":"test-token-1","ad_unit_id":"ca-app-pub-test/001","session_id":"test-session-grant"}' \
  | python3 -m json.tool
# Esperado: granted=1, current_lives=1, capped=false

# 7. POST /lives/grant — promo (1 vida)
curl -s -X POST $BASE/lives/grant \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"source":"promo","promo_code":"BETA_LAUNCH","session_id":"test-session-promo"}' \
  | python3 -m json.tool
# Esperado: granted=1, current_lives=2, capped=false

# 8. POST /lives/grant — IAP lives_pack_5 con current_lives=4 (capped)
curl -s -X POST $BASE/lives/grant \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"source":"iap","product_id":"lives_pack_5","session_id":"test-session-iap"}' \
  | python3 -m json.tool
# Esperado: granted=1 (solo cabe 1 más para llegar a max 5), capped=true, current_lives=5
```

---

## Resultados

### ST-01: Code review y commit

Commit `abee8a9` pusheado — 1 archivo:
- `app/routers/game.py` — GET /lives + POST /lives/spend + POST /lives/grant completo (233 líneas añadidas, 24 eliminadas)

**Validaciones implementadas:**
- Init nuevo jugador (5 vidas, sin timer) ✅
- Regen server-side con `last_regen_at` avanzado por intervalos ✅
- Transaction atómica en spend (LIVES_INSUFFICIENT en 0 vidas) ✅
- Capped y actual_granted en grant ✅
- entitlements.life_packs_total actualizado en IAP life_pack ✅
- Todos los `None` del stub eliminados ✅

### Follow-ups / notes

- **ST-02 (integration tests):** Pendiente deploy a Cloud Run dev — ejecutar el script de testing de esta sección
- **Remote Config para `REGEN_INTERVAL_SECS` y `DEFAULT_MAX_LIVES`:** Actualmente hardcodeados en Settings. Mover a Remote Config en v1.1 para ajuste sin deploy.
- **GAME-002 SSV validation:** `reward_token` de AdMob aún no se verifica criptográficamente — stub comment en código. GAME-002 completo (T-230) lo agrega.
- **Concurrent spend (multi-device):** La transaction de Firestore ya protege contra esto. La retry logic de `@async_transactional` maneja contención automáticamente.
