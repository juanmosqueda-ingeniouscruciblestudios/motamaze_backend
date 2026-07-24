# T-244 — Backend: Firebase Remote Config para tunables de vidas

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | Medium — permite ajustar balance de gameplay (regen de vidas) sin deploy |
| **Status** | In Progress — ST-01–04 ✅, ST-05 ⬜ |
| **Date** | 2026-07-24 |
| **Engine** | FastAPI backend (sin trabajo de cliente Godot — los tunables son server-side) |
| **Depends-on** | T-220 (lives backend ✅) — ya Done, sin bloqueos |

---

## Description

Migrar `REGEN_INTERVAL_SECS` y `DEFAULT_MAX_LIVES` (hasta ahora constantes hardcodeadas en
`app/routers/game.py`) a Firebase Remote Config, para poder ajustar el balance de regeneración de
vidas sin necesidad de un deploy. Alcance confirmado con el usuario 2026-07-23: **no** incluye
catálogo/promociones (ya son live-tunable vía Firestore desde T-240) ni tunables de nivel (100%
recursos `.tres` de Godot, el backend no tiene ningún parámetro de nivel).

**Acceptance criteria:**
- [x] Cliente de Remote Config (REST, sin SDK nuevo — ver decisión de scope abajo)
- [x] `REGEN_INTERVAL_SECS`/`DEFAULT_MAX_LIVES` leídos de Remote Config con fallback si no está
  publicado
- [x] Tests completos (con la limitación documentada de `/lives/spend`, ver Follow-ups)
- [x] Documentación: este changelog, `logic/remote-config.md`, `docs/CONFIG_REFERENCE.md` (nuevo)
- [ ] Parámetros reales creados en la consola de Firebase Remote Config (dev) + validación
  end-to-end (ST-05, pendiente)
- [x] "Change auditing" — interpretado explícitamente como el historial de versiones nativo de la
  consola de Firebase (sin código de auditoría adicional), ver `docs/CONFIG_REFERENCE.md`

---

## Previous state (before this change)

`app/routers/game.py` tenía dos constantes de módulo, hardcodeadas desde T-220:
```python
REGEN_INTERVAL_SECS = 1800  # 30 minutes
DEFAULT_MAX_LIVES = 5
```
Leídas directamente por `_apply_regen`, `_next_regen_dt`, `get_lives`, `_spend_txn` y `lives_grant` —
cualquier ajuste de balance requería un cambio de código + deploy. El proyecto no tenía ninguna
integración con Firebase Remote Config todavía (`remote_config_service.py` no existía).

---

## Implementation details

### ST-01 — `app/services/remote_config_service.py` (nuevo)
Cliente REST crudo (`urllib.request` + `google.auth` ADC), sin el SDK `firebase-admin` — decisión de
scope forzada por `motamaze_backend/CLAUDE.md` (no agregar dependencias/servicios de terceros nuevos
sin aprobación de Juan+Saul), mismo patrón ya usado por `admob_api.py`. `get_value(project_id, key,
default, cast=str)`: fetch del template completo (`GET .../remoteConfig`), cacheado
`TTLCache(maxsize=2, ttl=300)` keyed por `project_id`, con **fallback silencioso a `default`** ante
cualquier fallo (red, auth, key ausente, cast fallido) — nunca lanza. Detalle completo:
`logic/remote-config.md`.

### ST-02 — Migración de `app/routers/game.py`
Nuevo helper `_resolve_lives_config(settings) -> (regen_interval_secs, default_max_lives)`, llamado
al inicio de `GET /lives`, `POST /lives/spend` y `POST /lives/grant`. `_apply_regen`,
`_next_regen_dt` y `_spend_txn` ganaron un parámetro explícito `regen_interval_secs` (dejaron de leer
el global del módulo). Las constantes `REGEN_INTERVAL_SECS`/`DEFAULT_MAX_LIVES` **siguen existiendo**
— ahora solo se usan como el `default=` pasado a `get_value()`. `get_lives` ganó una nueva dependencia
`settings: Settings = Depends(get_settings)` que no tenía antes.

### ST-03 — Tests completos
- `tests/test_remote_config_service.py` (nuevo, 7 tests): cast exitoso, fallback por fallo de fetch,
  fallback por key ausente, fallback por fallo de cast, cast default `str`, template vacío, y
  cache-hit evita un segundo fetch (assertion de call-count).
- `tests/test_game_lives_router.py` (nuevo — primera cobertura de test que existe para `/lives*`,
  cualquiera de sus 3 endpoints): `GET /lives` con fallback y con valor publicado; `POST /lives/grant`
  respeta el `max_lives` resuelto de Remote Config (no el hardcodeado) tanto para capping como para
  el caso de solo un key publicado.
- `tests/conftest.py`: nuevo fixture autouse `_patch_remote_config` — sin él, cada test que golpeara
  `/lives*` intentaría un fetch real de Remote Config (google.auth + red, hasta 10s de timeout).
  Simula "sin template publicado" por default; tests individuales pueden sobreescribir
  `_fetch_template_sync` para ejercitar el path real. También limpia `_template_cache` antes de cada
  test — sin esto, un test que publica un template contaminaría tests posteriores no relacionados
  durante toda la ventana de TTL (5 min, más larga que una corrida completa de la suite), ya que todos
  los tests de router comparten el mismo `test_settings.gcp_project_id`.
- **Limitación encontrada y documentada, no resuelta silenciosamente:** `POST /lives/spend` no tiene
  cobertura de test para su integración con Remote Config. Está decorado con `@async_transactional`
  (Firestore real) y `FakeFirestoreClient` (`tests/conftest.py`) no implementa `.transaction()` en
  absoluto — fakear fielmente el ciclo de vida real de una transacción de Firestore (begin/commit/
  rollback + retry, atado a los stubs gRPC del cliente real) es una tarea separada y más grande que el
  alcance de T-244. Gap pre-existente (el endpoint no tenía ningún test antes de este ticket tampoco).
  `_spend_txn` comparte exactamente los mismos helpers `_apply_regen`/`_next_regen_dt` que `GET
  /lives` ya prueba correctamente contra valores resueltos de Remote Config — lo no probado es
  específicamente el wrapping transaccional de Firestore, no el cambio de T-244 en sí.

### ST-04 — Documentación (este pase)
`docs/CONFIG_REFERENCE.md` (nuevo, referenciado por el ticket original pero nunca creado antes):
tabla de cada parámetro (key, default, qué controla), la decisión explícita de scope sobre "change
auditing", y qué tunables quedaron deliberadamente fuera (catálogo/promociones, niveles).
`logic/remote-config.md` (nuevo): referencia de estado actual del cliente, cache, filosofía de
fallback, y los 2 parámetros migrados.

---

## Testing

```bash
python -m pytest --ignore=tests/test_firestore_rules.py -q
```

---

## Results

```
200 passed in 37.69s
```

Sin regresiones — suite completa, incluyendo los 7 tests nuevos de `test_remote_config_service.py` y
los 4 de `test_game_lives_router.py` sobre el total previo (189 tras T-240).

---

## Follow-ups / notes

- **ST-05 pendiente**: crear `regen_interval_secs`/`default_max_lives` reales en la consola de
  Firebase Remote Config (proyecto `motamaze-dev`) y validar end-to-end contra Cloud Run dev. Hasta
  entonces el backend corre 100% con los defaults de fallback (`1800`, `5`).
- **`POST /lives/spend` sin cobertura de test para Remote Config** — ver limitación documentada
  arriba (ST-03). Requiere soporte de `.transaction()` en `FakeFirestoreClient`, fuera de alcance de
  este ticket.
- **Prod no configurado** — ST-05 solo contempla dev; prod queda para después del soft launch, mismo
  criterio aplicado en T-123/T-302/T-404/T-240.
- **Catálogo/promociones (T-240) y tunables de nivel quedaron fuera de T-244** por decisión explícita
  de scope — ver `docs/CONFIG_REFERENCE.md`.
