# T-244 — Backend: Firebase Remote Config para tunables de vidas

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | Medium — permite ajustar balance de gameplay (regen de vidas) sin deploy |
| **Status** | ✅ Done — ST-01–05 ✅ |
| **Date** | 2026-07-27 |
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
- [x] Parámetros reales creados en Firebase Remote Config (dev) + validación end-to-end (ST-05)
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

### ST-05 — Parámetros reales en dev + validación end-to-end
`scripts/seed_remote_config.py` (nuevo) — idempotente, mismo patrón que `seed_store_catalog.py`:
`GET` el template actual (preserva lo que ya esté publicado), mergea `PARAMETERS`, `PUT` de vuelta
con el `etag`. Primer publish nunca trae `ETag` (no hay versión previa) → usa `If-Match: *`. Valores
publicados en `motamaze-dev`: `regen_interval_secs=1800`, `default_max_lives=5` — **idénticos al
fallback actual**, deliberado: esta corrida hace los valores tuneables sin cambiar el balance.

**Bloqueos reales encontrados y resueltos, en orden:**
1. `GET`/`PUT` con ADC de usuario → 403 `SERVICE_DISABLED` con `consumer=projects/764086051850` (el
   proyecto del propio OAuth client de `gcloud`, no `motamaze-dev`) — el request nunca llevaba el
   header `X-Goog-User-Project`; `google.auth.transport.requests.AuthorizedSession` lo agrega solo,
   pero el script usa `urllib.request` crudo (mismo patrón que `remote_config_service.py`) y hay que
   agregarlo a mano. Fijado en `seed_remote_config.py`.
2. Con el header correcto, 403 real: **Firebase Remote Config API nunca había sido habilitada en
   `motamaze-dev`** — `gcloud services enable firebaseremoteconfig.googleapis.com --project=motamaze-dev`.
3. Primer `GET` devolvía `{}` (sin template previo) y sin header `ETag` — `PUT` con `If-Match: None`
   fallaba (`TypeError`, `putheader` no acepta `None`). Fijado: `etag = ... or "*"`.
4. Publish exitoso (versión 1, confirmado por `GET` posterior con `updateUser=saulmorin@...`,
   `updateOrigin=REST_API`) — **pero el backend real (Cloud Run) seguía devolviendo el fallback**, no
   el valor publicado. Log de Cloud Run reveló la causa real: `403 [AUTHORIZATION_ERROR]: User does
   not have the following permission: GET_TEMPLATE` para la cuenta de servicio
   `game-api-backend@motamaze-dev.iam.gserviceaccount.com` — nunca tuvo ningún rol que cubriera
   Remote Config. No existe un rol de IAM dedicado (`roles/firebaseremoteconfig.*` no existe como
   predefinido, confirmado por `gcloud iam roles list`; `roles/firebase.developViewer` tampoco cubre
   `GET_TEMPLATE`) — la API v1 de Remote Config solo reconoce los roles clásicos de Firebase. Fix real:
   `roles/firebase.admin` otorgado a la cuenta de servicio en `motamaze-dev`. Detalle completo,
   incluyendo los comandos exactos: `logic/remote-config.md`.
5. **Validación end-to-end real** (no solo "sin error" — prueba de que el valor viene de Remote
   Config y no de una coincidencia con el fallback): publicado temporalmente un valor centinela
   (`regen_interval_secs=777`, imposible por coincidencia), llamado `GET /lives` contra el Cloud Run
   real de dev vía `gcloud run services proxy` + un JWT real firmado con la clave real de Secret
   Manager (`jwt-private-key`, usuario de prueba `e2e-test-remote-config-DELETE-ME`) → respuesta
   confirmó `regen_interval_secs: 777`. Restaurado el valor real (`1800`) con el mismo script;
   borrado el documento Firestore de prueba (`lives/e2e-test-remote-config-DELETE-ME`).

**Bug de aislamiento de tests encontrado en el camino (no relacionado a Remote Config en sí):** al
re-correr la suite completa durante esta validación, los 2 tests de `POST /lives/grant` agregados en
ST-03 fallaron con un `RefreshError` de credenciales reales — resultó que `tests/conftest.py`'s
`_patch_bq_streaming` mockea `stream_event` en `app.routers.auth`/`payments`/`leaderboard`/`jobs`
pero **nunca incluyó `app.routers.game`**. Sin ese mock, cada test de `/lives/grant` estaba haciendo
un **insert real a BigQuery** en el proyecto de `test_settings.gcp_project_id` — silenciosamente
"pasando" antes porque `bq_streaming.stream_event` solo atrapa `GoogleAPIError` (no errores de auth),
así que con ADC sano el insert simplemente se completaba sin que nadie lo notara. Un ADC roto durante
esta sesión fue lo que lo hizo visible. Fix: agregado `app.routers.game.stream_event` +
`.stream_events` al fixture — suite completa vuelve a `200 passed`, ahora genuinamente sin tocar GCP
real, y ~2x más rápida (37s → 17s) al eliminar esas llamadas de red reales.

---

## Testing

```bash
python -m pytest --ignore=tests/test_firestore_rules.py -q
```

---

## Results

```
200 passed in 16.93s
```

Sin regresiones — suite completa, incluyendo los 7 tests nuevos de `test_remote_config_service.py` y
los 4 de `test_game_lives_router.py` sobre el total previo (189 tras T-240). Tiempo bajó de 37.69s a
16.93s tras el fix del gap de aislamiento de `_patch_bq_streaming` (ST-05, ver arriba) — ya no hace
inserts reales a BigQuery.

Validación end-to-end real (ST-05, 2026-07-27): `motamaze-dev` Remote Config template versión 1,
`regen_interval_secs=1800`/`default_max_lives=5`, confirmado servido por el Cloud Run real de dev
tras el fix de IAM (`roles/firebase.admin`) — ver detalle completo en `logic/remote-config.md`.

---

## Follow-ups / notes

- **`POST /lives/spend` sin cobertura de test para Remote Config** — ver limitación documentada
  arriba (ST-03). Requiere soporte de `.transaction()` en `FakeFirestoreClient`, fuera de alcance de
  este ticket.
- **Prod no configurado** — deliberado, queda para después del soft launch, mismo criterio aplicado
  en T-123/T-302/T-404/T-240. **Requiere repetir el fix de IAM** (`roles/firebase.admin` en
  `game-api-backend@motamaze.iam.gserviceaccount.com`) **antes** de publicar parámetros en prod — sin
  eso, seguiría funcionando (fallback = valor correcto) pero de forma silenciosamente no-tunable, sin
  ninguna señal visible del problema. Ver `logic/remote-config.md`.
- **Catálogo/promociones (T-240) y tunables de nivel quedaron fuera de T-244** por decisión explícita
  de scope — ver `docs/CONFIG_REFERENCE.md`.
- **Hallazgo reusable para futuros tickets:** cualquier script admin/debug que use ADC de usuario
  (`gcloud auth application-default login`) contra una API que requiera quota project (como
  `firebaseremoteconfig.googleapis.com`) necesita agregar manualmente el header
  `X-Goog-User-Project` si construye requests con `urllib`/`requests` crudo en vez de
  `google.auth.transport.requests.AuthorizedSession` — de lo contrario falla con un 403
  `SERVICE_DISABLED` engañoso (apunta al proyecto del OAuth client de `gcloud`, no al proyecto real).
