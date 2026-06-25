# DATA-002 — Firestore → BigQuery Async Streaming

| Campo | Valor |
|---|---|
| **Tipo** | Dataflow & Outputs / Backend Implementation |
| **Prioridad** | Alta |
| **Status** | In Progress — ST-01–07 ✅, ST-08–12 ⬜ |
| **Fecha planeada** | 2026-06-22 – 2026-06-23 |
| **Workstream** | Dataflow & Outputs |
| **Owner** | Saul Zavala Morin |
| **Monday.com Item ID** | 12272094755 |
| **Depends on** | DATA-001 ✅ (7 tablas BQ creadas), INFRA-001 ✅ (IAM, billing), INFRA-003 ⬜ (FastAPI scaffold — integración final) |
| **Desbloquea** | DATA-003 (ad revenue reconciliation, 7/10), DATA-004 (Looker Studio dashboards, 7/2), Retention KPIs del soft launch |

---

## Descripción

MotaMaze necesita que cada evento de usuario (login, sesión, comportamiento, compra, anuncio, entitlement) quede registrado en BigQuery para poder calcular los KPIs de kill-criteria del soft launch: `D1 ≥ 25–30%`, `D7 ≥ 10%`, `LTV > costo de UA`.

Las 7 tablas de BigQuery ya existen (DATA-001). Lo que falta es el **pipeline que las alimenta**: cada vez que el backend FastAPI procesa un evento, debe escribir la fila correspondiente en BigQuery sin bloquear la respuesta al cliente.

**Por qué "async":**
BigQuery Streaming Inserts tienen latencia de red (50–200ms). Si el endpoint `/auth/login` esperara la confirmación de BQ antes de responder, cada login tardaría 200ms extra — inaceptable en móvil. La solución es disparar el write a BQ como tarea de fondo (`BackgroundTask` de FastAPI) y responder al cliente de inmediato.

**Firestore vs. BigQuery — separación de responsabilidades:**

| Sistema | Rol | Quién escribe |
|---|---|---|
| **Firestore** | Fuente de verdad operacional — estado actual del juego (vidas, progreso, sesión) | FastAPI (en el request path) |
| **BigQuery** | Analytics inmutable — historial de eventos para KPIs y compliance | FastAPI (background task, fuera del request path) |

No se usa CDC (Change Data Capture) de Firestore → BQ porque los esquemas de analytics son diferentes a los documentos de Firestore: BQ recibe eventos normalizados con campos calculados (ej: `session_duration_secs`) que Firestore no tiene.

---

## Criterios de aceptación

- [ ] Helper `bq_streaming.py` implementado con cliente BigQuery reutilizable
- [ ] `BackgroundTask` integrado en los 6 endpoints de escritura de FastAPI
- [ ] Retry logic para errores transitorios de BQ (max 3 intentos con backoff)
- [ ] Errores de BQ logeados (no silenciados, no propagados al cliente)
- [ ] Test de integración: evento enviado → fila visible en BQ en < 30 segundos
- [ ] Sin impacto en latencia del endpoint (< 5ms overhead)

---

## Estado previo (antes de DATA-002)

- 7 tablas BQ en `motamaze_analytics`: ✅ creadas y verificadas (DATA-001)
- Escrituras a BQ: **ninguna** — las tablas están vacías
- FastAPI: ⬜ no existe aún (INFRA-003) — el código se prepara aquí y se integra en INFRA-003

---

## Decisión de arquitectura — Opciones evaluadas

### Opción A — FastAPI BackgroundTasks + BQ Streaming Insert API ✅ Elegida

```
[Cliente Godot]
    │  POST /auth/login
    ▼
[FastAPI endpoint]
    │  1. Escribe en Firestore (request path — bloqueante)
    │  2. Responde 200 al cliente  ← rápido
    │  3. background_task: insert_rows_json → BQ  ← no bloquea
    ▼
[BigQuery: login_events]
```

**Pros:** Sin infraestructura adicional, código simple, latencia de endpoint no afectada.
**Contras:** Si el proceso de Cloud Run muere antes de que la background task termine, se pierde el evento BQ (el dato en Firestore está seguro, BQ es best-effort en MVP).

**Por qué es suficiente para MVP:** Con < 1,000 usuarios en soft launch, la probabilidad de perder eventos por restart de Cloud Run es despreciable. Post-soft-launch se puede agregar Pub/Sub para durabilidad garantizada.

---

### Opción B — Pub/Sub → Cloud Function → BQ (descartada para MVP)

```
[FastAPI] → publish(Pub/Sub topic) → [Cloud Function] → BQ
```

**Pros:** Durabilidad garantizada (mensajes persistidos en Pub/Sub aunque Cloud Run reinicie).
**Contras:** 2 recursos adicionales (topic + subscription + Cloud Function), costo mayor, latencia de propagación de 1–5 segundos, más superficie de debugging. Overkill para MVP.

**Cuándo migrar a esta opción:** Cuando el volumen de usuarios justifique no perder ningún evento (post soft launch con > 10K DAU).

---

### Opción C — Firebase Extension "Stream Firestore to BigQuery" (descartada)

Sincroniza documentos Firestore automáticamente a BQ. No aplica porque:
- Los documentos de Firestore son de estado (ej: `lives/{uid}.count = 5`), no de eventos
- Los schemas de las tablas BQ (events con timestamps) no corresponden a la estructura de documentos Firestore
- No da control sobre qué campos van a BQ ni cuándo

---

## Implementación — Diseño de código

### Módulo `bq_streaming.py`

El helper central que todos los endpoints usarán:

```python
# app/services/bq_streaming.py
import logging
import asyncio
from google.cloud import bigquery
from google.api_core.exceptions import GoogleAPIError

_client: bigquery.Client | None = None

def get_bq_client() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client()
    return _client

async def stream_event(table_id: str, row: dict, max_retries: int = 3) -> None:
    """
    Inserta una fila en la tabla BQ especificada.
    Llamar siempre desde BackgroundTasks — nunca en el request path.
    Los errores se logean pero NO se propagan al cliente.
    """
    table_ref = f"motamaze.motamaze_analytics.{table_id}"
    client = get_bq_client()

    for attempt in range(1, max_retries + 1):
        try:
            errors = client.insert_rows_json(table_ref, [row])
            if not errors:
                return
            logging.error(
                "BQ insert errors [table=%s attempt=%d]: %s",
                table_id, attempt, errors
            )
        except GoogleAPIError as e:
            logging.error(
                "BQ API error [table=%s attempt=%d]: %s",
                table_id, attempt, str(e)
            )

        if attempt < max_retries:
            await asyncio.sleep(2 ** attempt)  # backoff: 2s, 4s

    logging.error("BQ streaming failed after %d attempts [table=%s]", max_retries, table_id)
```

### Integración en endpoints FastAPI

Patrón a seguir en cada endpoint que genera un evento analytics:

```python
# app/routers/auth.py
from fastapi import APIRouter, BackgroundTasks
from app.services.bq_streaming import stream_event
from datetime import datetime, timezone

router = APIRouter()

@router.post("/auth/login")
async def login(background_tasks: BackgroundTasks, ...):
    # --- request path (bloqueante) ---
    user = await firestore.get_or_create_user(...)
    token = create_jwt(user.uid)

    # --- analytics (non-bloqueante) ---
    now = datetime.now(timezone.utc)
    background_tasks.add_task(stream_event, "login_events", {
        "event_timestamp": now.isoformat(),
        "event_date": now.date().isoformat(),
        "user_id": user.uid,
        "session_id": token.jti,
        "platform": request_body.platform,
        "app_version": request_body.app_version,
        "country": request_body.country,
        "login_method": "google_oauth",
        "is_new_user": user.is_new,
        "age_verified": user.age_verified,
        "device_model": request_body.device_model,
        "os_version": request_body.os_version,
    })

    return {"access_token": token.value, "user_id": user.uid}
```

### Tabla de endpoints → tablas BQ

> **Actualizado 2026-06-18 (ST-02):** Mapping reconciliado con REST-001 contract. 3 endpoints originales no existían en REST-001 — ver análisis ST-02 abajo.
> **Actualizado 2026-06-22:** +2 endpoints de Dominio 5 con escritura BQ: `POST /leaderboard/score` y `POST /season/claim-reward`. Los otros 5 endpoints de Dominio 5 son read-only (no escriben a BQ).

| Endpoint FastAPI | Tabla(s) BQ | Cuándo se dispara |
|---|---|---|
| `POST /auth/login` | `login_events`, `session_durations` (event_type: session_start) | Cada login exitoso — también inicia registro de sesión |
| `POST /auth/logout` | `session_durations` (event_type: session_end, duration_secs calculado) | Fin de sesión — calcula duración desde Firestore session.started_at |
| `POST /events/behavior` *(REST-001 #14)* | `player_behavior` | Batch de eventos de gameplay enviado por Godot |
| `POST /progress/level-complete` | `player_behavior` (event_name: level_complete) | También registra el nivel completado como evento de comportamiento |
| `POST /payments/android/verify` | `purchase_events`, `entitlement_grants` | Verificación IAP Android — escribe compra + entitlement otorgado |
| `POST /payments/ios/verify` | `purchase_events`, `entitlement_grants` | Verificación IAP iOS — mismo patrón |
| `POST /lives/grant` (source: rewarded_ad_ssv) | `ad_impressions`, `entitlement_grants` | SSV de AdMob — registra impresión + vidas otorgadas |
| `POST /lives/grant` (source: iap \| promo) | `entitlement_grants` | Grant directo de vidas — solo entitlement, no ad_impressions |
| `DELETE /auth/account` | `account_deletions` | Solicitud de borrado GDPR |
| `POST /leaderboard/score` *(REST-001 #25)* | `player_behavior` (event_name: leaderboard_score_submitted) | Siempre. `extra_json` incluye `{"season_id": "...", "submitted_score": N, "actual_stars": N, "anomaly": true/false}`. `anomaly: true` cuando submitted_score ≠ actual_stars — permite detección de manipulación. T-443. |
| `POST /season/claim-reward` *(REST-001 #23)* | `entitlement_grants` (entitlement_type: season_reward) | Cada reward de Season Pass reclamado — `entitlement_id` = `"season_{season_id}_tier_{tier}_{track}"`, `source` = `"season_pass"`. |

---

## Subtareas

| # | Subtarea | Status | Dependencias | Notas |
|---|---|---|---|---|
| ST-01 | Diseño de arquitectura: BackgroundTasks + BQ Streaming Insert | ✅ Done 2026-06-17 | DATA-001 ✅ | Descartadas Pub/Sub y Firebase Extension para MVP |
| ST-02 | Alinear endpoint → tabla mapping con REST-001 | ✅ Done 2026-06-18 (actualizado 2026-06-22) | REST-001 ✅ | 3 gaps resueltos (2026-06-18). +2 endpoints Dominio 5 (2026-06-22): `POST /leaderboard/score` → `player_behavior` (anomaly detection), `POST /season/claim-reward` → `entitlement_grants` |
| ST-03 | Implementar `app/services/bq_streaming.py` con retry logic | ✅ Done 2026-06-24 | INFRA-003 ✅ | commit `2143994` |
| ST-04 | Definir dedup keys y backfill-safety strategy | ✅ Done 2026-06-24 | ST-03 | `row_id` param en `stream_event`, estrategia por tabla documentada |
| ST-05 | Integrar `POST /auth/login` → `login_events` + `session_durations` (session_start) | ✅ Done 2026-06-24 | ST-03, INFRA-003 ✅ | commit `2143994` |
| ST-06 | Integrar `POST /auth/logout` → `session_durations` (session_end, duration_secs calculado) | ✅ Done 2026-06-24 | ST-03, INFRA-003 ✅ | `revoke_session` ahora retorna `(ended_at, duration_secs)` |
| ST-07 | Integrar `POST /events/behavior` → `player_behavior` (batch) | ✅ Done 2026-06-25 | ST-03, INFRA-003 | commit `8898a33` — `stream_events()` batch + `BehaviorBatchRequest` model |
| ST-08 | Integrar `POST /payments/*/verify` → `purchase_events` + `entitlement_grants` | ⬜ Pending | ST-03, INFRA-003 | Android + iOS |
| ST-09 | Integrar `POST /lives/grant` → `ad_impressions` (SSV) + `entitlement_grants` | ⬜ Pending | ST-03, INFRA-003 | |
| ST-10 | Integrar `DELETE /auth/account` → `account_deletions` | ⬜ Pending | ST-03, INFRA-003 | |
| ST-11 | Integrar `POST /progress/level-complete` → `player_behavior` (event: level_complete) | ⬜ Pending | ST-03, INFRA-003 | |
| ST-12 | Monitor y confirmar que datos llegan a BigQuery — query de verificación por tabla | ⬜ Pending | ST-05–11, INFRA-003 deployed | `SELECT * FROM login_events LIMIT 1` + verificar las 8 tablas |

---

## Análisis ST-02 — Reconciliación endpoint mapping vs. REST-001 (2026-06-18)

Al cruzar el mapping original de DATA-002 con el contrato REST-001 finalizado, se detectaron 3 endpoints que no existían en REST-001. Resolución:

### Gap 1: `POST /sessions/start` y `POST /sessions/end` → `session_durations`

**Resolución: eliminados — cubiertos por endpoints de Auth existentes.**

- `POST /auth/login` escribe fila `event_type: "session_start"` en `session_durations` como background_task. El campo `session_duration_secs = null` en este momento.
- `POST /auth/logout` calcula `session_duration_secs = logout_time - session.started_at` (desde Firestore) y escribe fila `event_type: "session_end"`.
- Edge case — app cerrada sin logout: la fila `session_end` nunca se escribe, `session_duration_secs` queda null. Aceptable para MVP (afecta solo a la duración, no al conteo de sesiones).

### Gap 2: `POST /events/behavior` → `player_behavior`

**Resolución: endpoint agregado a REST-001 como #14 (Game Services).**

Ningún endpoint existente capturaba eventos granulares de gameplay (`level_start`, `level_fail`, `maze_shift`, `npc_caught`, `item_collected`, `tutorial_step`). `POST /progress/level-complete` solo captura el evento `level_complete`. Se agregó `POST /events/behavior` como endpoint batch write-only — Godot acumula eventos durante la partida y los envía en un solo request al terminar el nivel o ir al background.

`POST /progress/level-complete` también escribe un evento `level_complete` a `player_behavior` como background_task para tener el evento en ambos contextos (progreso + comportamiento).

### Gap 3: `POST /entitlements/grant` → `entitlement_grants`

**Resolución: eliminado — no es un endpoint público, es una operación interna.**

Los grants de entitlements ocurren dentro de los handlers de endpoints existentes:
- `POST /payments/android/verify` y `POST /payments/ios/verify` → otorgan entitlement IAP → escriben a `entitlement_grants`
- `POST /lives/grant` (cualquier source) → otorga vidas → escribe a `entitlement_grants`

No se necesita un endpoint independiente `POST /entitlements/grant`.

---

## Follow-ups / Notes

- **INFRA-003 bloqueante:** ST-02 en adelante requiere el repo FastAPI. El código de `bq_streaming.py` está diseñado aquí — cuando exista el repo se copia directamente.
- **Dominio 5 endpoints read-only (sin escritura BQ):** `GET /leaderboard`, `GET /season`, `GET /achievements`, `POST /share/create`, `GET /s/{token}` — no escriben a BigQuery. `POST /share/create` escribe solo a Firestore `shares/{token}`.
- **Migración a Pub/Sub post-MVP:** Si en producción se observan eventos perdidos por reinicios de Cloud Run, agregar un Pub/Sub topic como buffer durable. El helper `bq_streaming.py` se reemplaza por un publisher, sin cambiar los endpoints.
- **`account_deletions` y GDPR:** Cuando `DELETE /auth/account` inserta en `account_deletions`, también debe iniciar el proceso de purge en Firestore. Ese flujo detallado es de COMP-001 (Compliance, 7/27) — aquí solo se inserta la fila en BQ.
- **Costo BQ Streaming:** A $0.01/200MB y con < 1,000 usuarios en soft launch, el costo mensual de streaming será < $1 USD.
- **Campos `event_date`:** BigQuery requiere el campo de partición en formato `YYYY-MM-DD` (string o DATE). El helper debe asegurarse de enviar `datetime.now().date().isoformat()`, no un timestamp completo.
