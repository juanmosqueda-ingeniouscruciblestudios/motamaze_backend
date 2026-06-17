# DATA-001 — BigQuery Analytics Tables

| Campo | Valor |
|---|---|
| **Tipo** | Dataflow & Outputs / Setup |
| **Prioridad** | Alta |
| **Status** | ✅ Done — 7 tablas creadas y verificadas 2026-06-16 |
| **Fecha planeada** | 2026-06-18 – 2026-06-19 |
| **Workstream** | Dataflow & Outputs |
| **Owner** | Saul Zavala Morin |
| **Monday.com Item ID** | 12272094753 |
| **Depends on** | INFRA-001 ✅ — dataset `motamaze_analytics` ya creado en región US |
| **Desbloquea** | DATA-002 (Firestore→BQ streaming, 6/22), DATA-003 (ad revenue reconciliation, 7/10), Looker Studio dashboards (DATA-004, 7/2), DELETE /auth/account — deletion queue (AUTH-003, 7/14) |

---

## Descripción

MotaMaze necesita datos de comportamiento, monetización y compliance para tres propósitos:

1. **KPIs de negocio** — D1/D7 retention, revenue por región/edad, LTV, ad fill rate. Son los kill-criteria del soft launch (9/14): `D1 ≥ 25–30%`, `D7 ≥ 10%`, `No-Ads conversion 2–5%`, `LTV > costo de UA`.

2. **Compliance** — GDPR Art. 17 (derecho al olvido) y Apple 5.1.1 requieren poder borrar todos los datos de un usuario. La `deletion_queue` orquesta ese proceso across todas las tablas.

3. **Fraud prevention** — cruzar `purchase_events` con verificaciones fallidas de Play Developer API para detectar purchase token replay attacks.

**Por qué tablas separadas y no una sola tabla de eventos:**
BigQuery cobra por datos escaneados. Tener `behavior_events` separado de `purchase_events` significa que una query de revenue no escanea millones de filas de gameplay, reduciendo el costo operativo hasta 10x en producción.

**Dataset:** `motamaze_analytics` (región US, ya existe desde INFRA-001 ST-08).

---

## Criterios de aceptación

- [ ] 7 tablas creadas en `motamaze_analytics` con esquemas correctos
- [ ] Todas particionadas por `event_date` (reducción de costo de queries)
- [ ] Tablas de alta cardinalidad clusterizadas por `user_id`
- [ ] `deletion_queue` con campo `status` para orquestar purges GDPR
- [ ] Verificación: todas las tablas visibles vía REST API

---

## Estado previo

- Dataset `motamaze_analytics`: ✅ existe (INFRA-001 ST-08, 2026-06-16)
- Tablas: **0** — dataset vacío

---

## Diseño de esquemas

### Decisiones de diseño globales

| Decisión | Razón |
|---|---|
| Particionado por `event_date` (DATE) | BigQuery cobra por GB escaneado — particionar permite queries que solo lean días específicos |
| Clustering por `user_id` | Queries de retention y LTV filtran casi siempre por usuario |
| `platform` en todas las tablas | MVP es Android, pero iOS vendrá. Schema ready desde el día 1 |
| `app_version` en todas las tablas | Permite correlacionar bugs o cambios de balance con métricas |
| `country` en todas las tablas | Requerido para compliance regional (US13/BR18) y para KPIs por región |
| `extra_json` en behavior_events | Campos de gameplay evolucionan rápido — overflow flexible sin ALTER TABLE |

---

### Tabla 1: `login_events`

Registra cada login de usuario. Fuente: backend `/auth/login` (AUTH-001).

```sql
event_timestamp  TIMESTAMP  NOT NULL
event_date       DATE       NOT NULL   -- partition key
user_id          STRING     NOT NULL   -- clustering
session_id       STRING     NOT NULL
platform         STRING                -- 'android' | 'ios'
app_version      STRING
country          STRING                -- ISO 3166-1 alpha-2, ej: 'MX', 'BR'
login_method     STRING                -- 'google_oauth'
is_new_user      BOOL                  -- true en primer login
age_verified     BOOL                  -- pasó el flujo de verificación de edad
device_model     STRING
os_version       STRING
```

---

### Tabla 2: `session_events`

Registra inicio y fin de cada sesión de juego. Fuente: cliente Godot vía HTTP API.

```sql
event_timestamp       TIMESTAMP  NOT NULL
event_date            DATE       NOT NULL   -- partition key
user_id               STRING     NOT NULL   -- clustering
session_id            STRING     NOT NULL
event_type            STRING     NOT NULL   -- 'session_start' | 'session_end'
platform              STRING
app_version           STRING
country               STRING
session_duration_secs INT64                 -- null en session_start, lleno en session_end
levels_played         INT64                 -- null en session_start
ads_shown             INT64                 -- interstitials + banners en sesión
```

---

### Tabla 3: `behavior_events`

Eventos de gameplay granulares. Fuente: cliente Godot. Es la tabla de mayor volumen.

```sql
event_timestamp    TIMESTAMP  NOT NULL
event_date         DATE       NOT NULL   -- partition key
user_id            STRING     NOT NULL   -- clustering key 1
session_id         STRING
event_name         STRING     NOT NULL   -- ver catálogo abajo
platform           STRING
app_version        STRING
country            STRING
level_id           INT64                 -- 1-30
score              INT64
stars_earned       INT64                 -- 0-3
duration_secs      INT64
npc_type           STRING                -- 'bola'|'mancha'|'huracan'|'conejo'
extra_json         STRING                -- JSON string para campos variables
```

**Catálogo de `event_name`:**
```
level_start       — jugador inicia un nivel
level_complete    — nivel completado con éxito
level_fail        — jugador muere / se queda sin vidas
maze_shift        — el laberinto se reconfiguró
npc_caught        — NPC atrapó al jugador
item_collected    — Mota recolectó un ítem
tutorial_step     — paso del tutorial completado
```

---

### Tabla 4: `purchase_events`

Cada intento de compra IAP. Fuente: backend `/payments/android/verify` (PAY-001).

```sql
event_timestamp      TIMESTAMP  NOT NULL
event_date           DATE       NOT NULL   -- partition key
user_id              STRING     NOT NULL   -- clustering
session_id           STRING
platform             STRING
app_version          STRING
country              STRING
product_id           STRING     NOT NULL   -- SKU, ej: 'lives_pack_5'
product_type         STRING                -- 'consumable' | 'non_consumable'
purchase_token       STRING                -- token de Play Billing / StoreKit
order_id             STRING                -- ID de orden de Google Play
price_usd            FLOAT64               -- precio en USD (para revenue analytics)
currency_code        STRING                -- moneda original del usuario
verification_status  STRING                -- 'verified' | 'pending' | 'invalid' | 'refunded'
grant_status         STRING                -- 'granted' | 'failed' | 'duplicate'
```

---

### Tabla 5: `ad_events`

Impresiones, clicks y rewards de anuncios. Fuente: AdMob SSV callback + cliente.

```sql
event_timestamp  TIMESTAMP  NOT NULL
event_date       DATE       NOT NULL   -- partition key
user_id          STRING     NOT NULL   -- clustering
session_id       STRING
platform         STRING
app_version      STRING
country          STRING
ad_unit_id       STRING                -- ID de AdMob
ad_type          STRING                -- 'rewarded' | 'interstitial' | 'banner'
event_type       STRING                -- 'impression' | 'click' | 'reward_earned' | 'skipped' | 'failed_load'
revenue_usd      FLOAT64               -- revenue estimado por impresión (de AdMob SSV)
ad_network       STRING                -- 'admob' | futuras redes de mediation
```

---

### Tabla 6: `entitlement_events`

Cada vez que se otorga un entitlement. Fuente: backend tras verificar IAP o SSV ad.

```sql
event_timestamp   TIMESTAMP  NOT NULL
event_date        DATE       NOT NULL   -- partition key
user_id           STRING     NOT NULL   -- clustering
session_id        STRING
platform          STRING
app_version       STRING
country           STRING
entitlement_type  STRING     NOT NULL   -- 'skin' | 'no_ads' | 'life_pack' | 'life_rewarded_ad' | 'promo'
entitlement_id    STRING                -- SKU o ID de skin, ej: 'skin_gold'
source            STRING                -- 'iap' | 'rewarded_ad_ssv' | 'promo_code'
granted_by        STRING                -- 'payment_verify' | 'admob_ssv' | 'backend_promo'
quantity          INT64                 -- para life_pack: cuántas vidas
```

---

### Tabla 7: `deletion_queue`

Solicitudes de borrado de datos de usuario. Fuente: backend `DELETE /auth/account` (AUTH-003).

```sql
requested_at    TIMESTAMP      NOT NULL
request_date    DATE           NOT NULL   -- partition key
user_id         STRING         NOT NULL
platform        STRING
request_source  STRING                    -- 'user_request' | 'gdpr_erasure' | 'apple_511'
status          STRING                    -- 'pending' | 'processing' | 'completed' | 'failed'
completed_at    TIMESTAMP
tables_purged   ARRAY<STRING>             -- lista de tablas ya purgadas
notes           STRING                    -- errores o información de auditoría
```

**Flujo de borrado (para GDPR / Apple 5.1.1):**
1. Usuario solicita borrado → backend crea fila `status='pending'`
2. Cloud Function periódica procesa la cola → DELETE en todas las tablas por `user_id`
3. Actualiza `status='completed'` y `tables_purged`

---

## Subtareas

| # | Subtarea | Status | Notas |
|---|---|---|---|
| ST-01 | Crear tabla `login_events` | ✅ Done 2026-06-16 | partition: event_date, cluster: user_id |
| ST-02 | Crear tabla `session_events` | ✅ Done 2026-06-16 | partition: event_date, cluster: user_id |
| ST-03 | Crear tabla `behavior_events` | ✅ Done 2026-06-16 | partition: event_date, cluster: user_id + event_name |
| ST-04 | Crear tabla `purchase_events` | ✅ Done 2026-06-16 | partition: event_date, cluster: user_id |
| ST-05 | Crear tabla `ad_events` | ✅ Done 2026-06-16 | partition: event_date, cluster: user_id + ad_type |
| ST-06 | Crear tabla `entitlement_events` | ✅ Done 2026-06-16 | partition: event_date, cluster: user_id |
| ST-07 | Crear tabla `deletion_queue` | ✅ Done 2026-06-16 | partition: request_date, cluster: user_id + status |
| ST-08 | Verificar 7 tablas en `motamaze_analytics` | ✅ Done 2026-06-16 | totalItems: 7 confirmado via REST API |

---

## Audit — Estado inicial verificado (2026-06-16)

```
Dataset motamaze_analytics: ✅ existe, región US
Tablas: 0 (dataset vacío)
```

---

## Follow-ups / Notes

- **DATA-002 (Firestore → BQ streaming):** Una vez que estas tablas existen, DATA-002 configura el pipeline que escribe en ellas en tiempo real desde el backend. Las tablas son el prerequisito.
- **`ad_unit_id` en `ad_events`:** Los IDs reales de AdMob vienen de EXT-002 (Juan). Para el MVP la tabla puede tener IDs de test en dev sin problema.
- **`deletion_queue` y GDPR:** La Cloud Function que procesa la cola es parte de COMP-001 (Compliance, 7/27). El esquema de la tabla está diseñado para soportar ese flujo desde ahora.
- **Evolución del schema:** BigQuery permite agregar columnas (no modificar existentes). Para campos variables de gameplay usar `extra_json` en `behavior_events` — evita migrations frecuentes.
- **Costo estimado en MVP:** Con ~1,000 usuarios en soft launch y queries diarias de retención, el costo mensual de BigQuery será < $5 USD. El particionado por `event_date` es lo que mantiene ese costo bajo.
