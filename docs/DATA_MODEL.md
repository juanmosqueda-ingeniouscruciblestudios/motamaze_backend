# MotaMaze — Firestore Data Model

> Última actualización: 2026-06-22
> Fuente: INFRA-005 ST-04 + REST-001 actualización 2026-06-22 (Season Pass, Achievements, Leaderboard)
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

Perfil del jugador. Se crea/actualiza en `POST /auth/login` (upsert por Google `sub`).

| Campo | Tipo | Descripción |
|---|---|---|
| `uid` | `string` | = document ID = Google OAuth `sub` |
| `email` | `string` | Email de Google |
| `display_name` | `string` | Nombre de Google |
| `photo_url` | `string \| null` | URL de foto de perfil |
| `created_at` | `timestamp` | Primera vez que inició sesión |
| `updated_at` | `timestamp` | Último upsert |
| `equipped_skin` | `string \| null` | Skin activo: `"skin_gold"`, `"skin_silver"`, `null` = default |
| `consent` | `map` | Ver campos anidados abajo |
| `delete_requested_at` | `timestamp \| null` | `null` = activo; non-null = en cola de borrado (DELETE /auth/account) |

**`consent` (anidado):**

| Campo | Tipo | Descripción |
|---|---|---|
| `coppa_compliant` | `boolean` | `true` si usuario ≥ 13 años (US) / ≥ 18 (BR) |
| `gdpr_consent` | `boolean \| null` | `null` si no está en EU |
| `ccpa_opt_out` | `boolean` | `false` = opt-in (default) |
| `age_verified_at` | `timestamp \| null` | Cuándo se verificó la edad |

**Endpoints que usan esta colección:**

| Endpoint | Operación |
|---|---|
| `POST /auth/login` | `set` (upsert) |
| `DELETE /auth/account` | `update` (set `delete_requested_at`) + BQ deletion queue |
| `POST /profile/equip-skin` | `update` (`equipped_skin`) |

---

### `sessions/{session_id}`

Registro de sesiones de juego. Sirve para calcular `session_duration_secs` en BigQuery.

| Campo | Tipo | Descripción |
|---|---|---|
| `session_id` | `string` | = document ID = UUID v4, generado por FastAPI en login |
| `uid` | `string` | Referencia a `users/{uid}` |
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
| `sessions` | Indefinido (MVP) | Se analizan en BigQuery via streaming; no se borran de Firestore en MVP |
| `users` | Indefinido | `delete_requested_at != null` → BQ deletion queue → borrado en 30 días |
| `season_progress` | Por temporada | Al inicio de cada nueva temporada, se archiva el documento anterior y se crea uno nuevo |
| `achievement_progress` | Indefinido | Acumulativo — no se borra entre temporadas |
| `achievement_rarities` | Indefinido | Sobreescrito cada 24h por Cloud Scheduler |
| `leaderboard_cache` | Por temporada | Sobreescrito cada 5 min durante la temporada activa; archivado al terminar |

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
```

---

## Relacionados

- [INFRA-005 changelog](../changelogs/INFRA-005-firestore-schema-security-rules.md)
- [REST-001 contrato](../changelogs/REST-001-rest-api-contract.md)
- [DATA-002 — Firestore → BigQuery streaming](../changelogs/DATA-002-firestore-bigquery-streaming.md)
- [INFRA-002 — Env & secrets design](../changelogs/INFRA-002-env-secrets-design.md)
