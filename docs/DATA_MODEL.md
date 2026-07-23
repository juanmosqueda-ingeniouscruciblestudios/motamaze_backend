# MotaMaze — Firestore Data Model

> Última actualización: 2026-07-18
> Fuente: INFRA-005 ST-04 + REST-001 actualización 2026-06-22 (Season Pass, Achievements, Leaderboard) + AUTH-004 (Sign in with Apple / multi-provider) + PAY-001/T-251 (Apple purchase verification, discriminador platform, documentación de purchases/{doc_id})
> Scope: MVP (soft launch 2026-09-14)

Todas las escrituras y lecturas de Firestore pasan por FastAPI (Admin SDK).
El cliente Godot **nunca accede directamente** a Firestore — solo hace HTTP a FastAPI.

---

## Proyecto GCP y base de datos

| Entorno | Project ID | Firestore DB | Región |
|---|---|---|---|
| Production | `motamaze` | `(default)` | `nam5` (Iowa + Council Bluffs) |
| Development | `motamaze-dev` | `(default)` | `nam5` (por crear — INFRA-006 ST-04) |
| Staging | `motamaze-staging` | `(default)` | `nam5` — **diferido** a ~1 mes post-lanzamiento (2026-06-22) |

---

## Colecciones

### `users/{uid}`

Perfil del jugador. Se crea/actualiza en `POST /auth/login` (upsert por `sub` del proveedor de identidad — Google o Apple).

| Campo | Tipo | Descripción |
|---|---|---|
| `uid` | `string` | = document ID = `sub` del proveedor de identidad (Google `sub` o Apple `sub`) — sin prefijo de proveedor, ver nota abajo |
| `provider` | `"google" \| "apple"` | Proveedor de autenticación de origen. Ver nota de colisión/no-linking abajo |
| `email` | `string` | Email del proveedor. Apple puede entregar una dirección privada `@privaterelay.appleid.com` — es válida y usable |
| `display_name` | `string` | Nombre del proveedor. Para Apple, solo llega en la primera autorización (el cliente lo captura y lo reenvía en logins futuros) |
| `photo_url` | `string \| null` | URL de foto de perfil. Apple nunca la provee → siempre `null` para cuentas Apple |
| `created_at` | `timestamp` | Primera vez que inició sesión |
| `updated_at` | `timestamp` | Último upsert |
| `equipped_skin` | `string \| null` | Skin activo: `"skin_gold"`, `"skin_silver"`, `null` = default |
| `consent` | `map` | Ver campos anidados abajo |
| `delete_requested_at` | `timestamp \| null` | `null` = activo; non-null = borrado solicitado, en periodo de gracia de 30 días (T-123) |

> **Nota — multi-provider (AUTH-004, 2026-07-17):** el document ID sigue siendo el `sub` crudo, sin prefijo de proveedor. Se decidió así porque los formatos de `sub` de Google (numérico) y Apple (alfanumérico con puntos) son estructuralmente disjuntos — la colisión es, en la práctica, imposible — y evita migrar `sessions`, `revoked_jtis`, `progress`, `lives`, `entitlements`, `season_progress` y `achievement_progress`, todos referenciando el mismo `uid`. Como red de seguridad adicional, `upsert_user` rechaza (`409 AUTH_PROVIDER_MISMATCH`) cualquier intento de login cuyo `provider` no coincida con el ya almacenado en el documento, en vez de fusionar identidades silenciosamente. **Limitación aceptada:** esta versión no soporta account linking — un jugador que use Google y luego Apple obtiene dos cuentas independientes (progreso/vidas/entitlements separados). Documentos creados antes de este cambio no tienen `provider`; se hace backfill automático en su próximo login.

> **Nota — T-123 (2026-07-22): borrado de cuenta con periodo de gracia de 30 días.**
> `DELETE /auth/account` marca `delete_requested_at` (no borra nada todavía) y revoca la sesión que
> hizo el request. **Login se mantiene abierto** a propósito para cuentas con borrado pendiente —
> `LoginResponse.deletion_pending` avisa al cliente — porque es el único camino para llegar a
> `POST /auth/account/cancel-deletion`, que limpia `delete_requested_at` y reactiva la cuenta.
> **Refresh sí se bloquea** (`401 AUTH_ACCOUNT_DELETION_PENDING`) — ahí es donde se cierra el hueco de
> que otro dispositivo logueado pudiera seguir renovando indefinidamente. Un Cloud Scheduler diario
> (`POST /jobs/purge-deleted-accounts`) purga las cuentas cuyo `delete_requested_at` supera los 30
> días: borra `progress`/`lives`/`entitlements`/`season_progress`/`achievement_progress`/`sessions`/
> `users`, y anonimiza (no borra) `purchases` — ver la nota en esa colección más abajo. Detalle
> completo, incluyendo el purgado de las tablas históricas de BigQuery: `logic/account-deletion.md`.

**`consent` (anidado):**

| Campo | Tipo | Descripción |
|---|---|---|
| `coppa_compliant` | `boolean` | `true` si usuario ≥ 13 años (US) / ≥ 18 (BR) |
| `gdpr_consent` | `boolean \| null` | `null` si no está en EU |
| `ccpa_opt_out` | `boolean` | `false` = opt-in (default) |
| `age_verified_at` | `timestamp \| null` | Cuándo se verificó la edad (DOB autodeclarado, T-401) |
| `is_child` | `boolean \| null` | Derivado del DOB vs. `consent_age_threshold` (T-401). `null` hasta el primer `/auth/age-verify` |
| `country_code` | `string \| null` | Resuelto por `geo_service.resolve_country()` en cada login (T-400) |
| `consent_age_threshold` | `number` | Umbral de edad del país resuelto (US=13, BR=18, MX=18, AR=16, PE=14, UY=18 — T-400/T-407) |
| `country_signal_mismatch` | `boolean` | `true` si la señal primaria (store/device) no coincide con la IP — señal de fraude, no cambia la resolución |
| `store_age_signal` | `string \| null` | *(T-402, solo Brasil)* Banda de edad cruda de Apple Declared Age Range / Google Play Age Signals, ej. `"13-15"`. **Sin normalizar** — la lógica de reconciliación contra el DOB es trabajo aparte, todavía no implementado |
| `store_age_signal_source` | `string \| null` | `"apple_declared_age_range"` \| `"play_age_signals"` — qué API entregó `store_age_signal` |
| `store_age_signal_captured_at` | `timestamp \| null` | Cuándo se capturó `store_age_signal` por última vez |
| `birth_month` | `number \| null` | *(T-404)* Mes de nacimiento (1-12), derivado del DOB en `POST /auth/age-verify`. **Nunca el día** — minimización de datos (COPPA/GDPR Art.5(1)(e)). Solo se llena en la rama donde el DOB decidió `is_child` (nunca en la rama de señal BR — ver nota abajo) |
| `birth_year` | `number \| null` | *(T-404)* Año de nacimiento, mismo origen y misma restricción de rama que `birth_month` |

> **Nota — T-402 (2026-07-22, corregida 2026-07-23):** Brasil prohíbe la autodeclaración de edad (Digital ECA) — el DOB de T-401 no es suficiente ahí por sí solo. `store_age_signal` captura la señal cruda de la API de tienda correspondiente, enviada por el cliente en `POST /auth/login` (mismo mecanismo que `store_country_code`). Estos campos **solo se llenan si el cliente los envía** (Godot, Juan — pendiente) y **no se sobreescriben con vacío** en logins posteriores (mismo patrón que `email`/`display_name`). ~~Todavía no hay lógica que reaccione a estos valores~~ — **esto ya no es cierto**: la reconciliación (señal de tienda con prioridad sobre el DOB en Brasil) se implementó el mismo día como subtarea aparte de T-402 — ver `logic/age-assurance.md`. Tratar como **provisional**: el mecanismo (Apple Declared Age Range / Google Play Age Signals) está disponible y es gratis, pero ANPD solo tiene lineamientos preliminares — revisar antes de escalar en Brasil.

> **Nota — T-404 (2026-07-23): recálculo mensual de umbral de edad.** `POST /auth/age-verify` ya recibe el DOB completo del cliente para calcular `age`, pero antes lo descartaba enteramente después — el architecture doc especificaba guardar `birth_month`/`birth_year` ("Never write birth_day") para permitir un recálculo periódico, nunca implementado hasta ahora. Un Cloud Scheduler mensual (`POST /jobs/recalc-age-thresholds`) recorre usuarios con `is_child == true` y `birth_month`/`birth_year` presentes, y voltea a `is_child = false` a quienes ya cruzaron su `consent_age_threshold` — con redondeo conservador (protegido hasta el último día de su mes de nacimiento). **Alcance limitado a usuarios verificados por DOB** (Rama 1) — los usuarios BR verificados por `store_age_signal` (Rama 2, banda sin fecha exacta) no tienen `birth_month`/`birth_year` y quedan fuera de este job. Detalle completo: `logic/age-threshold-recalc.md`.

**Endpoints que usan esta colección:**

| Endpoint | Operación |
|---|---|
| `POST /auth/login` | `set` (upsert) — incluye `deletion_pending` en la respuesta si aplica |
| `POST /auth/age-verify` | `update` (`is_child`, `restricted_features`, `coppa_compliant`, `age_verified_at`, y `birth_month`/`birth_year` si el DOB decidió) |
| `DELETE /auth/account` | `update` (set `delete_requested_at`) + fila `pending` en BQ `account_deletions` |
| `POST /auth/account/cancel-deletion` | `update` (`delete_requested_at = null`) + fila `cancelled` en BQ |
| `POST /jobs/purge-deleted-accounts` (Cloud Scheduler, T+30 días) | `delete` (borrado final) |
| `POST /jobs/recalc-age-thresholds` (Cloud Scheduler, mensual — T-404) | `update` (`is_child = false` para quienes cruzaron su umbral) |
| `POST /profile/equip-skin` | `update` (`equipped_skin`) |

---

### `sessions/{session_id}`

Registro de sesiones de juego. Sirve para calcular `session_duration_secs` en BigQuery.

| Campo | Tipo | Descripción |
|---|---|---|
| `session_id` | `string` | = document ID = UUID v4, generado por FastAPI en login |
| `uid` | `string` | Referencia a `users/{uid}` |
| `provider` | `"google" \| "apple"` | Proveedor usado en el login que originó esta sesión. Ausente en sesiones creadas antes de AUTH-004 (2026-07-17) — `POST /auth/refresh` usa fallback `"google"` para esos casos, y se auto-limpian por el TTL de 14 días |
| `started_at` | `timestamp` | Momento del `POST /auth/login` |
| `ended_at` | `timestamp \| null` | `null` = sesión activa. Se escribe en `POST /auth/logout` |
| `duration_secs` | `number \| null` | `ended_at - started_at` en segundos. `null` si la app murió sin logout |
| `device` | `map \| null` | Metadata del dispositivo (opcional, para analytics) |

**`device` (anidado, opcional):**

| Campo | Tipo | Descripción |
|---|---|---|
| `platform` | `"android" \| "ios"` | OS del dispositivo |
| `os_version` | `string` | e.g. `"14.0"` |
| `app_version` | `string` | e.g. `"1.0.0"` |

**Comportamiento edge cases:**

| Caso | `ended_at` | `duration_secs` |
|---|---|---|
| Logout normal | timestamp | calculado |
| App killed / crash | `null` | `null` |
| Token expirado sin logout | `null` | `null` |

**Nota:** Los `session_id` se incluyen en el JWT access token como claim `sid`. FastAPI lo extrae del JWT en `POST /auth/logout` — no necesita que el cliente lo envíe por separado.

**Endpoints que usan esta colección:**

| Endpoint | Operación |
|---|---|
| `POST /auth/login` | `create` |
| `POST /auth/logout` | `update` (`ended_at`, `duration_secs`) |

---

### `revoked_jtis/{jti}`

JWTs revocados (logout y borrado de cuenta). FastAPI consulta esta colección en `POST /auth/refresh` para denegar refresh tokens inválidos.

| Campo | Tipo | Descripción |
|---|---|---|
| `jti` | `string` | = document ID = UUID v4 del JWT |
| `uid` | `string` | Usuario dueño del token |
| `revoked_at` | `timestamp` | Cuándo se revocó |
| `expires_at` | `timestamp` | TTL para limpieza = `revoked_at + 14 días` (vida del refresh token) |
| `reason` | `"logout" \| "account_delete" \| "forced"` | Razón de revocación |

**Limpieza (TTL):** Un Cloud Scheduler job corre cada 24h y elimina documentos donde `expires_at < now()`. Esto mantiene la colección pequeña y las consultas rápidas.

**Nota de performance:** El lookup en refresh es `db.collection("revoked_jtis").document(jti).get()` — acceso directo por document ID, O(1), sin necesidad de índices compuestos.

**Endpoints que usan esta colección:**

| Endpoint | Operación |
|---|---|
| `POST /auth/refresh` | `get` (lectura por JTI) |
| `POST /auth/logout` | `set` (add JTI del access + refresh token) |
| `DELETE /auth/account` | `set` (add JTI de todos los tokens activos) |

---

### `progress/{uid}`

Progresión del jugador por nivel. Autoridad del servidor — el cliente no puede modificar esto directamente.

| Campo | Tipo | Descripción |
|---|---|---|
| `uid` | `string` | = document ID |
| `best_level` | `number` | Nivel más alto completado (para desbloquear siguiente) |
| `levels` | `map<string, LevelResult>` | Mapa nivel → resultado |
| `updated_at` | `timestamp` | Última actualización |

**`LevelResult` (valor del mapa `levels`):**

| Campo | Tipo | Descripción |
|---|---|---|
| `stars` | `0 \| 1 \| 2 \| 3` | Estrellas obtenidas en la mejor run |
| `best_score` | `number` | Puntuación más alta |
| `completed_at` | `timestamp` | Primera vez que completó el nivel |

**Ejemplo de documento:**
```json
{
  "uid": "google-sub-123",
  "best_level": 5,
  "levels": {
    "level_1": { "stars": 3, "best_score": 4200, "completed_at": "2026-09-15T14:30:00Z" },
    "level_2": { "stars": 2, "best_score": 3100, "completed_at": "2026-09-15T14:45:00Z" }
  },
  "updated_at": "2026-09-15T14:45:00Z"
}
```

**Validación server-side en `POST /progress/level-complete`:**
- El nivel enviado por el cliente debe ser `<= best_level + 1` (no puede saltar niveles)
- El score se acepta tal cual (validación de engagement via BigQuery analytics, no Firestore)

**Endpoints que usan esta colección:**

| Endpoint | Operación |
|---|---|
| `GET /progress` | `get` |
| `POST /progress/level-complete` | `set` (merge: solo actualiza el nivel enviado) + también escribe en `season_progress/{uid}` |

---

### `lives/{uid}`

Vidas del jugador. Regeneración server-authoritative: el servidor calcula cuántas vidas recuperó el usuario desde `last_regen_at`.

| Campo | Tipo | Descripción |
|---|---|---|
| `uid` | `string` | = document ID |
| `count` | `number` | Vidas actuales (0–`max_lives`) |
| `max_lives` | `number` | Máximo (default 5, Remote Config tuneable) |
| `last_regen_at` | `timestamp` | Última vez que el servidor aplicó regeneración |
| `next_regen_at` | `timestamp` | Pre-computado: cuándo se añade la próxima vida (para timer en cliente) |
| `updated_at` | `timestamp` | Última escritura |

**Lógica de regeneración (en `GET /lives` y antes de `POST /lives/spend`):**
```
tiempo_transcurrido = now() - last_regen_at
vidas_a_añadir = floor(tiempo_transcurrido / REGEN_INTERVAL_SECS)  # Remote Config: default 1800s = 30 min
nuevas_vidas = min(count + vidas_a_añadir, max_lives)
```
Si `nuevas_vidas != count`, se escribe el nuevo valor + `last_regen_at = now()`.

**Endpoints que usan esta colección:**

| Endpoint | Operación |
|---|---|
| `GET /lives` | `get` + posible `update` (si hay vidas para regenerar) |
| `POST /lives/spend` | `update` (`count -= 1`, con transacción Firestore) |
| `POST /lives/grant` | `update` (`count = min(count + amount, max_lives)`) |

---

### `entitlements/{uid}`

Compras y entitlements del jugador. Se actualiza tras verificar compras en `POST /payments/*/verify`.

| Campo | Tipo | Descripción |
|---|---|---|
| `uid` | `string` | = document ID |
| `no_ads` | `boolean` | `true` si compró "No Ads" IAP |
| `skins` | `string[]` | Skins compradas: `["skin_gold", "skin_silver"]` |
| `life_packs_total` | `number` | Total de life packs comprados (para analytics) |
| `updated_at` | `timestamp` | Última actualización |

**Endpoint `POST /profile/equip-skin`** lee esta colección para verificar que el usuario posee la skin antes de escribir `users/{uid}.equipped_skin`.

**Endpoints que usan esta colección:**

| Endpoint | Operación |
|---|---|
| `POST /payments/android/verify` | `update` (add skin / set no_ads) |
| `POST /payments/ios/verify` | `update` (add skin / set no_ads) |
| `POST /payments/android/refund` | `update` (remove skin / unset no_ads) |
| `POST /payments/ios/refund` | `update` (remove skin / unset no_ads) |
| `POST /lives/grant` | `update` (increment `life_packs_total` si es IAP) |
| `POST /profile/equip-skin` | `get` (verificar ownership) |
| `POST /auth/login` | `get` (para incluir entitlements en JWT claims) |

---

### `purchases/{doc_id}` *(documentado 2026-07-18 — PAY-001/T-251, existía desde antes sin documentar)*

Registro de cada compra verificada, usado para idempotencia (`POST /payments/*/verify`) y por `reconcile_service.py` (PAY-002 reconciliación de acks pendientes, detección de reembolsos). `doc_id` difiere por plataforma:

- **Android:** `SHA-256(purchase_token)` hex — el `purchase_token` crudo es un *bearer credential* (permite llamar `consume`/`acknowledge` en la Play API en nombre del usuario), por eso se hashea antes de usarlo como ID.
- **iOS:** `transaction_id` crudo de Apple (sin hash) — no es un bearer credential (el JWS firmado ES la credencial, no el ID), y mantenerlo en texto plano facilita cruzar contra App Store Connect y las notificaciones ASSN v2 para debugging/soporte.

| Campo | Tipo | Descripción |
|---|---|---|
| `uid` | `string` | Referencia a `users/{uid}` |
| `platform` | `"android" \| "ios"` | *(agregado 2026-07-18)* Discriminador de plataforma |
| `product_id` | `string` | SKU del producto |
| `product_type` | `"consumable" \| "non_consumable"` | Determina la lógica de idempotencia |
| `order_id` | `string \| null` | Android: `orderId` de Play. iOS: siempre `null` — no existe concepto equivalente |
| `purchase_token` | `string \| null` | Android: token crudo (usado por `reconcile_pending_acks`). iOS: siempre `null` |
| `acknowledged` | `boolean` | Android: `false` hasta completar ack/consume vía Play API. iOS: siempre `true` desde la creación — StoreKit 2 / App Store Server no tiene concepto de ack/consume, por lo que los docs iOS quedan naturalmente excluidos de la query `.where("acknowledged", "==", False)` de `reconcile_pending_acks()` (Android-only) sin necesidad de código adicional |
| `acknowledged_at` | `timestamp \| null` | Cuándo se confirmó el ack/consume (Android) o creación (iOS) |
| `voided` | `boolean` | *(unificado entre plataformas 2026-07-18 — antes solo existía para Android)* `true` tras un reembolso procesado |
| `voided_at` | `timestamp` | Cuándo se marcó como reembolsado |
| `created_at` | `timestamp` | Cuándo se verificó la compra |
| `anonymized_at` | `timestamp` | *(T-123, opcional)* Presente solo si el usuario borró su cuenta — ver nota abajo |

> **Nota — T-123 (2026-07-22): anonimización, no borrado.** Cuando el job de purga de cuentas
> (`POST /jobs/purge-deleted-accounts`, T+30 días) procesa a un usuario, sus documentos en esta
> colección **no se borran** — es el registro financiero/transaccional, retenido para auditoría
> contable y disputas de reembolso (GDPR Art.17(3)(b), excepción por obligación legal). En su lugar,
> `uid` se pone en `null` y se agrega `anonymized_at`; el resto del documento (producto, montos,
> tokens, fechas) queda intacto. Contraste con `entitlements/{uid}`, que sí se borra por completo —
> ese es estado operativo derivado, no un registro financiero. Detalle completo:
> `logic/account-deletion.md`.

**Endpoints que usan esta colección:**

| Endpoint | Operación |
|---|---|
| `POST /payments/android/verify` | `get` (idempotencia) + `set` (merge) |
| `POST /payments/ios/verify` | `get` (idempotencia) + `set` (merge) |
| `POST /payments/android/refund-notification` | `get` + `update` (`voided`) |
| `POST /payments/ios/refund-notification` | `get` + `update` (`voided`) |
| `POST /jobs/purge-deleted-accounts` (T-123, T+30 días) | `update` (anonimiza `uid`, agrega `anonymized_at`) |
| `POST /jobs/reconcile-purchases` | `get`/`query` (Android-only: `reconcile_pending_acks`, `detect_refunds`) |

---

### `season_progress/{uid}` *(agregado 2026-06-22)*

Progreso del jugador en la temporada activa. Se actualiza en cada `POST /progress/level-complete`. Se resetea al inicio de cada temporada (documento nuevo por `season_id`).

| Campo | Tipo | Descripción |
|---|---|---|
| `uid` | `string` | = document ID |
| `season_id` | `string` | Temporada activa, ej: `"season_001"` |
| `season_stars` | `number` | Season Stars ⭐ acumuladas en esta temporada |
| `current_tier` | `number` | Tier actual (1–10) — calculado server-side al leer, no almacenado |
| `has_gold_pass` | `boolean` | `true` si compró el Season Pass Gold track |
| `free_rewards_claimed` | `number[]` | Tiers del track Free ya reclamados, ej: `[1, 2, 3]` |
| `gold_rewards_claimed` | `number[]` | Tiers del track Gold ya reclamados |
| `updated_at` | `timestamp` | Última actualización |

> **Threshold de tiers (config-driven, Remote Config):** Tier 1 = 100 stars, Tier 2 = 250, ..., Tier 10 = 2000. El `current_tier` se calcula en cada request leyendo `season_stars` vs. la tabla de umbrales — no se persiste para evitar drift.

**Endpoints que usan esta colección:**

| Endpoint | Operación |
|---|---|
| `POST /progress/level-complete` | `update` (incrementa `season_stars`) |
| `GET /season` | `get` |
| `POST /season/claim-reward` | `update` (agrega tier a `free_rewards_claimed` o `gold_rewards_claimed`) |
| `POST /payments/*/verify` | `update` (set `has_gold_pass = true` si product_id == `"season_pass_gold"`) |

---

### `achievement_progress/{uid}` *(agregado 2026-06-22)*

Progreso del jugador en cada achievement. Un solo documento por usuario con todos sus achievements.

| Campo | Tipo | Descripción |
|---|---|---|
| `uid` | `string` | = document ID |
| `unlocked` | `string[]` | IDs de achievements desbloqueados, ej: `["first_level", "maze_master_5"]` |
| `progress` | `map<string, number>` | Progreso actual por achievement, ej: `{"maze_master_10": 6}` |
| `unlock_timestamps` | `map<string, timestamp>` | Cuándo se desbloqueó cada achievement |
| `updated_at` | `timestamp` | Última escritura |

**Ejemplo de documento:**
```json
{
  "uid": "google-sub-123",
  "unlocked": ["first_level", "maze_master_5"],
  "progress": {
    "maze_master_10": 6,
    "speed_run": 2
  },
  "unlock_timestamps": {
    "first_level": "2026-09-15T10:30:00Z",
    "maze_master_5": "2026-09-17T14:20:00Z"
  },
  "updated_at": "2026-09-17T14:20:00Z"
}
```

> **Escritura:** FastAPI evalúa logros en `POST /progress/level-complete` y otros endpoints relevantes. Si se cumple la condición de un achievement, lo agrega a `unlocked` y registra `unlock_timestamps`.

**Endpoints que usan esta colección:**

| Endpoint | Operación |
|---|---|
| `POST /progress/level-complete` | `update` (evalúa y otorga achievements relacionados con niveles) |
| `GET /achievements` | `get` |

---

### `achievement_rarities/{achievement_id}` *(agregado 2026-06-22)*

Rarity data-driven por achievement. Poblado por Cloud Scheduler cada 24h via BigQuery — no se escribe en tiempo real.

| Campo | Tipo | Descripción |
|---|---|---|
| `achievement_id` | `string` | = document ID |
| `total_players` | `number` | Total de jugadores activos al momento del cálculo |
| `unlocked_by` | `number` | Jugadores que han desbloqueado este achievement |
| `rarity_percent` | `number` | `unlocked_by / total_players * 100` |
| `rarity_tier` | `string` | `"COMMON"` (≥50%) \| `"UNCOMMON"` (20–49%) \| `"RARE"` (8–19%) \| `"EPIC"` (4–7%) \| `"LEGENDARY"` (<4%) |
| `computed_at` | `timestamp` | Timestamp del último cálculo vía BigQuery |

> **Fuente:** Cloud Scheduler job cada 24h consulta BigQuery (`achievement_progress` stream) y escribe estos documentos. `GET /achievements` lee de aquí — sin queries BQ en tiempo real.

**Escritores:**

| Proceso | Operación |
|---|---|
| Cloud Scheduler (cada 24h) | `set` (sobreescribe todos los documentos de rarity) |

**Lectores:**

| Endpoint | Operación |
|---|---|
| `GET /achievements` | `get` (por cada achievement del catálogo) |

---

### `leaderboard_cache/{cache_key}` *(agregado 2026-06-22)*

Rankings precalculados del leaderboard por temporada y tipo. Poblado cada 5 minutos por Cloud Scheduler. La CDN cachea el response del endpoint por 5 minutos (`Cache-Control: public, max-age=300`).

`cache_key` = `{season_id}_{type}`, ej: `season_001_global`, `season_001_weekly`.

| Campo | Tipo | Descripción |
|---|---|---|
| `cache_key` | `string` | = document ID |
| `season_id` | `string` | Temporada correspondiente |
| `type` | `string` | `"global"` \| `"weekly"` |
| `rankings` | `array` | Top 100 jugadores ordenados por `season_stars` DESC |
| `top3_prizes` | `array` | Premios de posiciones 1, 2 y 3 de la temporada |
| `computed_at` | `timestamp` | Timestamp del último cálculo |

**`rankings[i]` (elemento del array):**

| Campo | Tipo | Descripción |
|---|---|---|
| `rank` | `number` | Posición (1-based) |
| `uid` | `string` | ID del jugador |
| `display_name` | `string` | Nombre del jugador |
| `season_stars` | `number` | Season Stars acumuladas |
| `current_tier` | `number` | Tier actual del jugador |

> **`GET /leaderboard` flow:** Lee `leaderboard_cache/{season_id}_{type}`, luego hace un lookup adicional de `season_progress/{uid_del_jugador}` para inyectar el `player_rank` del usuario autenticado (incluso si está fuera del top 100).

**Escritores:**

| Proceso | Operación |
|---|---|
| Cloud Scheduler (cada 5 min) | `set` (sobreescribe el documento de cache) |

**Lectores:**

| Endpoint | Operación |
|---|---|
| `GET /leaderboard` | `get` (cache) + `get` de `season_progress/{uid}` para el rank del jugador |

---

### `shares/{token}` *(agregado 2026-06-22 — T-440)*

Token de share de score creado por `POST /share/create`. El `token` es el document ID (base62, 12 caracteres aleatorios — no derivado del `user_id`).

```
shares/{token}
  uid                 string       ← uid del creador (no expuesto en la URL pública)
  score               integer      ← score al momento de compartir
  level_reached       integer      ← nivel alcanzado (1–30)
  season_id           string       ← ID de la temporada activa
  og_image_url        string       ← URL de Cloudinary (<600 KB WebP, 1200×630 px)
  share_url           string       ← URL pública devuelta al cliente (ver nota)
  created_at          timestamp
  expires_at          timestamp    ← fin de la temporada activa (ver nota)
```

| Campo | Tipo | Descripción |
|---|---|---|
| `uid` | string | UID del jugador creador — solo para auditoría interna, nunca en respuesta pública |
| `score` | integer | Season stars al momento de crear el share |
| `level_reached` | integer | Nivel alcanzado, para el copy de la OG card |
| `season_id` | string | Vincula el share a la temporada — el documento expira con ella |
| `og_image_url` | string | URL Cloudinary de la imagen generada |
| `share_url` | string | URL de Tenjin (`{tenjin_share_tracking_link}?deeplink_url=...`) si está configurado, si no URL directa (`{share_base_url}/s/{token}`) — ver nota |
| `created_at` | timestamp | Cuándo se creó el share |
| `expires_at` | timestamp | Fin de la temporada — after this, `GET /s/{token}` devuelve 404 |

> **Nota — `expires_at` hardcodeado (pendiente de ticket separado, no bloquea T-440):** usa una fecha fija (2026-09-14) en vez de leer la temporada activa (pendiente de un ticket de Season Pass aún sin código formal en Monday, referenciado como "Social-001" en comentarios del código).
>
> **`share_url` / Decision L — resuelto 2026-07-21:** Option A confirmada por Juan (Tenjin tracking link). Implementado en T-311 vía `_tenjin_share_url()` (`app/routers/social.py`) — usa el link estático de Tenjin (`tenjin_share_tracking_link` en `Settings`, configurado una vez en el dashboard de Tenjin, sin llamada a API) con el token embebido como `deeplink_url`. Hace fallback automático a URL directa mientras esa setting esté vacía (todavía lo está — falta que Juan/Saul creen el link en Tenjin).

**Escritores:**

| Proceso | Operación |
|---|---|
| `POST /share/create` | `set` — crea el documento con el token como ID |

**Lectores:**

| Endpoint | Operación |
|---|---|
| `GET /s/{token}` | `get` — lee el documento para generar el HTML con OG tags |

---

## Índices

Para MVP, todos los accesos son por document ID (lookups O(1)). **No se requieren índices compuestos.** Firestore auto-indexa todos los campos individuales por defecto.

**Posibles índices futuros (post-MVP):**

| Colección | Índice | Uso |
|---|---|---|
| `sessions` | `uid ASC, started_at DESC` | Analytics — sesiones recientes por usuario |
| `revoked_jtis` | `expires_at ASC` | Limpieza batch de JTIs expirados |
| `season_progress` | `season_id ASC, season_stars DESC` | Leaderboard fallback si Cloud Scheduler no corre |

---

## TTL y limpieza

| Colección | Retención | Mecanismo |
|---|---|---|
| `revoked_jtis` | 14 días | Cloud Scheduler job cada 24h: elimina `expires_at < now()` |
| `sessions` | Indefinido (MVP) | Se analizan en BigQuery via streaming; no se borran de Firestore en MVP, salvo por borrado de cuenta (T-123, ver fila `users`) |
| `users` | Indefinido, o 30 días si se solicita borrado | `delete_requested_at != null` → periodo de gracia de 30 días (cancelable vía `POST /auth/account/cancel-deletion`) → `POST /jobs/purge-deleted-accounts` (Cloud Scheduler diario) borra el documento y las colecciones asociadas (T-123). Detalle: `logic/account-deletion.md` |
| `season_progress` | Por temporada | Al inicio de cada nueva temporada, se archiva el documento anterior y se crea uno nuevo |
| `achievement_progress` | Indefinido | Acumulativo — no se borra entre temporadas |
| `achievement_rarities` | Indefinido | Sobreescrito cada 24h por Cloud Scheduler |
| `leaderboard_cache` | Por temporada | Sobreescrito cada 5 min durante la temporada activa; archivado al terminar |
| `shares` | Fin de temporada | `expires_at` en el documento; Cloud Scheduler batch delete post-temporada |

---

## Diagrama de colecciones

```
users/{uid}
  └── equipped_skin → referencia a skins en entitlements/{uid}

sessions/{session_id}
  └── uid → users/{uid}

revoked_jtis/{jti}
  └── uid → users/{uid}

progress/{uid}
  └── = misma ID que users/{uid}

lives/{uid}
  └── = misma ID que users/{uid}

entitlements/{uid}
  └── = misma ID que users/{uid}

season_progress/{uid}          ← agregado 2026-06-22
  └── = misma ID que users/{uid}
  └── season_id → identifica la temporada activa

achievement_progress/{uid}     ← agregado 2026-06-22
  └── = misma ID que users/{uid}

achievement_rarities/{achievement_id}  ← agregado 2026-06-22
  └── escrito por Cloud Scheduler (24h)
  └── leído por GET /achievements

leaderboard_cache/{cache_key}  ← agregado 2026-06-22
  └── cache_key = {season_id}_{type}
  └── escrito por Cloud Scheduler (5 min)
  └── leído por GET /leaderboard

shares/{token}                 ← agregado 2026-06-22 (T-440)
  └── token = base62 12-char aleatorio (no contiene uid — LGPD)
  └── escrito por POST /share/create
  └── leído por GET /s/{token}
  └── expira con la temporada (expires_at)
```

---

## Relacionados

- [INFRA-005 changelog](../changelogs/INFRA-005-firestore-schema-security-rules.md)
- [REST-001 contrato](../changelogs/REST-001-rest-api-contract.md)
- [DATA-002 — Firestore → BigQuery streaming](../changelogs/DATA-002-firestore-bigquery-streaming.md)
- [INFRA-002 — Env & secrets design](../changelogs/INFRA-002-env-secrets-design.md)
