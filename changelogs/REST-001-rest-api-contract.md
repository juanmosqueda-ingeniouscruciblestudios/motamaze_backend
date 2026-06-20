# REST-001 — Client↔Backend REST API Contract

| Campo | Valor |
|---|---|
| **Tipo** | Planning / Backend Contract |
| **Prioridad** | Alta ★ CRITICAL |
| **Status** | In Progress — ST-01–07 ✅, ST-08 🔴 Stuck (Juan pendiente revisar y aprobar, marcado Stuck en Monday 2026-06-19) |
| **Fecha planeada** | 2026-06-19 – 2026-06-24 |
| **Workstream** | Planning |
| **Owner** | Saul Zavala Morin (derivar contrato) + Juan Mosqueda (sign-off) |
| **Monday.com Item ID** | 12272268104 |
| **Depends on** | Architecture spec (`rnd_research/2026-06-04_motamaze-architecture-final.md`) ✅ |
| **Desbloquea** | INFRA-003 ST-02+ (repo FastAPI), INFRA-005 (Firestore rules), AUTH-001+, PAY-001+ — todo el backend |

---

## Descripción

El architecture spec de Juan define los sistemas, el data model de Firestore, y los flujos de pago. Lo que falta es traducirlo a un **contrato HTTP concreto**: qué endpoints existen, qué JSON reciben y devuelven, cómo se autentica cada llamada, y qué errores puede producir.

Este documento es el **contrato vinculante** entre el cliente Godot (Juan) y el backend FastAPI (Saul). Una vez firmado por ambos:
- Juan implementa el cliente Godot contra este contrato
- Saul implementa el backend FastAPI contra este contrato
- Los dos pueden trabajar en paralelo sin necesidad de sincronizarse en cada endpoint

**Fuente de verdad:** Architecture spec §4 (Auth), §5b (IAP), §6 (Firestore schema), §7 (Payment flow), §9A (MVP Gap Systems — progress, lives, store, profile).

---

## Criterios de aceptación

- [ ] Lista completa de endpoints con método HTTP, path, y dominio
- [ ] JWT spec definida (claims, headers, TTLs, JWKS)
- [ ] Request/response payloads para todos los endpoints
- [ ] Error taxonomy definida (formato estándar + catálogo de códigos)
- [ ] Sign-off de Juan ✍️

---

## Implementación — Subtareas

### ST-01 — Lista completa de endpoints por dominio ✅ Done (2026-06-17)

**19 endpoints en 4 dominios.** Derivados del architecture spec.

#### Convenciones globales

| Convención | Valor |
|---|---|
| Base URL (prod) | `https://api.motamaze.com` |
| Base URL (dev) | `https://api-dev.motamaze.com` (post INFRA-006) |
| Protocol | HTTPS únicamente |
| Content-Type | `application/json` en todos los requests con body |
| Auth header | `Authorization: Bearer <access_token>` (JWT RS256) |
| Auth requerida | Todos los endpoints excepto los marcados 🔓 |

---

#### Dominio 1 — Auth (6 endpoints)

| # | Método | Path | Auth | Descripción | Monday task |
|---|---|---|---|---|---|
| 1 | `POST` | `/auth/login` | 🔓 público | Verifica OAuth token (Google/Apple), hace upsert del usuario en Firestore, emite JWT pair (access + refresh) | AUTH-001 |
| 2 | `POST` | `/auth/refresh` | 🔓 público (lleva refresh token en body) | Rota el refresh token (bcrypt hash), emite nuevo access token | AUTH-002 |
| 3 | `POST` | `/auth/logout` | 🔒 JWT | Revoca la sesión activa, agrega el JTI al set de revocados en Firestore | AUTH-002 |
| 4 | `DELETE` | `/auth/account` | 🔒 JWT | Borra todos los datos del usuario (GDPR Art.17 + Apple 5.1.1), inserta en `account_deletions` BQ | AUTH-003 |
| 5 | `GET` | `/auth/pending/{state_token}` | 🔓 público | Godot hace polling para obtener el resultado del callback OAuth (state → JWT pair) | AUTH-001 |
| 6 | `GET` | `/.well-known/jwks.json` | 🔓 público | Devuelve la clave pública RS256 para verificación de JWTs (JWKS format) | INFRA-004 |

---

#### Dominio 2 — Game Services (8 endpoints)

| # | Método | Path | Auth | Descripción | Monday task |
|---|---|---|---|---|---|
| 7 | `GET` | `/progress` | 🔒 JWT | Devuelve el progreso del usuario: `highest_unlocked_level`, `total_stars` | Game-001 |
| 8 | `POST` | `/progress/level-complete` | 🔒 JWT | Registra nivel completado, valida score server-side, desbloquea siguiente nivel | Game-001 |
| 9 | `GET` | `/lives` | 🔒 JWT | Devuelve vidas actuales + timestamp de próxima regeneración | Game-002 |
| 10 | `POST` | `/lives/spend` | 🔒 JWT | Decremento server-authoritative de vidas (safe — no puede ir a negativo) | Game-002 |
| 11 | `POST` | `/lives/grant` | 🔒 JWT | Otorga vidas al usuario — fuente: `iap` \| `rewarded_ad_ssv` \| `promo` | Game-003 |
| 12 | `GET` | `/store/catalog` | 🔒 JWT | Catálogo de productos resuelto server-side con precios y promociones activas | Game-004 |
| 13 | `POST` | `/profile/equip-skin` | 🔒 JWT | Equipa un skin — verifica entitlement antes de escribir en Firestore | Game-005 |
| 14 | `POST` | `/events/behavior` | 🔒 JWT | Reporte batch de eventos de gameplay desde Godot (level_start, level_fail, maze_shift, npc_caught, etc.) — write-only, alimenta `player_behavior` BQ | Game-006 |

> **Endpoint #14 agregado 2026-06-18** como resultado del análisis DATA-002 ST-02: ningún endpoint previo capturaba eventos granulares de gameplay. Ver DATA-002 ST-02 para justificación completa.

---

#### Dominio 3 — Payments (4 endpoints)

| # | Método | Path | Auth | Descripción | Monday task |
|---|---|---|---|---|---|
| 15 | `POST` | `/payments/android/verify` | 🔒 JWT | Verifica `purchaseToken` con Play Developer API → otorga entitlement → acknowledge/consume | PAY-001 |
| 16 | `POST` | `/payments/ios/verify` | 🔒 JWT | Verifica `transactionId` con App Store Server API (JWS chain) → otorga entitlement | PAY-001 |
| 17 | `POST` | `/payments/android/refund-notification` | 🔓 firmado (Play Pub/Sub) | Recibe notificación RTDN de refund/voided-purchase de Google Play | PAY-003 |
| 18 | `POST` | `/payments/ios/refund-notification` | 🔓 firmado (Apple ASSN v2 JWS) | Recibe notificación de refund de Apple App Store Server Notifications v2 | PAY-003 |

---

#### Dominio 4 — Infrastructure (2 endpoints)

| # | Método | Path | Auth | Descripción | Monday task |
|---|---|---|---|---|---|
| 19 | `GET` | `/health` | 🔓 público | Liveness probe — Cloud Run reinicia el contenedor si falla | INFRA-003 |
| 20 | `GET` | `/ready` | 🔓 público | Readiness probe — Cloud Run no envía tráfico hasta que devuelva 200 | INFRA-003 |

---

#### Resumen por dominio

| Dominio | Endpoints | Públicos | Requieren JWT |
|---|---|---|---|
| Auth | 6 | 3 | 2 + 1 (refresh token en body) |
| Game Services | 8 | 0 | 8 |
| Payments | 4 | 2 (firmados por store) | 2 |
| Infrastructure | 2 | 2 | 0 |
| **Total** | **20** | **7** | **12** |

---

### ST-02 — JWT spec ✅ Done (2026-06-17)

#### Resumen ejecutivo

MotaMaze usa **dos tokens distintos** para autenticación:

| | Access Token | Refresh Token |
|---|---|---|
| Formato | JWT firmado RS256 | Opaco (UUID v4) |
| TTL | **15 minutos** | **14 días** |
| Almacenamiento servidor | Stateless (verifica con public key) | Hash bcrypt en Firestore `sessions/{session_id}` |
| Transmisión | `Authorization: Bearer <token>` header | Body de `POST /auth/refresh` únicamente |
| Revocación | JTI en `revoked_jtis/{jti}` (TTL = 15 min) | Firestore session delete |

**Por qué RS256 y no HS256:**
HS256 requiere que cada servicio que verifique tokens tenga la clave secreta. RS256 usa clave privada solo para firmar (en Secret Manager) y clave pública para verificar (en `/.well-known/jwks.json`, accesible por cualquiera). Esto permite que el cliente Godot verifique tokens localmente si lo necesita. Adicionalmente, el whitelist explícito del algoritmo en el verify call previene ataques de confusion RS256→HS256.

---

#### Access Token — estructura JWT

**Header:**
```json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "motamaze-key-v1"
}
```

`kid` (Key ID) permite identificar qué clave pública usar para verificar — esencial para key rotation sin downtime.

**Payload (claims):**
```json
{
  "iss": "https://api.motamaze.com",
  "sub": "usr_abc123def456",
  "aud": "motamaze-api",
  "exp": 1750000000,
  "iat": 1749999100,
  "jti": "550e8400-e29b-41d4-a716-446655440000",
  "uid": "usr_abc123def456",
  "provider": "google"
}
```

| Claim | Tipo | Descripción |
|---|---|---|
| `iss` | string | Issuer — siempre `"https://api.motamaze.com"` |
| `sub` | string | Subject — `user_id` del documento Firestore `users/{user_id}` |
| `aud` | string | Audience — siempre `"motamaze-api"` (validar en cada request) |
| `exp` | int | Unix timestamp de expiración — `iat + 900` (15 min) |
| `iat` | int | Unix timestamp de emisión |
| `jti` | string | JWT ID único — UUID v4 — usado para revocación inmediata |
| `uid` | string | Copia de `sub` — acceso directo sin ambigüedad en el backend |
| `provider` | string | `"google"` \| `"apple"` — proveedor OAuth de origen |

**Reglas de validación (backend FastAPI en cada request protegido):**
1. Verificar firma RS256 con la public key del JWKS endpoint
2. Verificar `alg == "RS256"` explícitamente — rechazar cualquier otro valor
3. Verificar `aud == "motamaze-api"`
4. Verificar `exp` no expirado (con tolerancia de clock skew de ±30 segundos)
5. Verificar `iss == "https://api.motamaze.com"`
6. Consultar Firestore `revoked_jtis/{jti}` — rechazar si existe

---

#### Refresh Token — estructura

El refresh token es un **string opaco** (UUID v4), no un JWT. Nunca se almacena en texto plano.

```
Valor en tránsito:  "f47ac10b-58cc-4372-a567-0e02b2c3d479"
Almacenado en Firestore sessions/{session_id}:
  token_hash: "$2b$12$xyz..."  ← bcrypt hash del UUID
```

**Flujo de rotación (en cada llamada a `POST /auth/refresh`):**
1. Cliente envía el refresh token opaco en el body
2. Backend busca la sesión en Firestore — verifica `bcrypt.verify(token, token_hash)`
3. Invalida la sesión actual (Firestore delete)
4. Genera nuevo access token (JWT) + nuevo refresh token (UUID v4)
5. Crea nueva sesión en Firestore con hash del nuevo refresh token
6. Retorna los dos nuevos tokens al cliente

**Protección contra replay:** Si el refresh token ya fue consumido (sesión no existe), el request retorna `401 UNAUTHORIZED`. El cliente debe redirigir al login.

---

#### Authorization header

```
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Im1vdGFtYXplLWtleS12MSJ9...
```

- Formato exacto: `Bearer ` + JWT (un espacio, sin comillas)
- Presente en **todos los endpoints protegidos** (🔒)
- Ausente en endpoints públicos (🔓) — el backend los ignora si están presentes

---

#### JWKS endpoint — formato de respuesta

`GET /.well-known/jwks.json` devuelve:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "motamaze-key-v1",
      "n": "<base64url-encoded modulus>",
      "e": "AQAB"
    }
  ]
}
```

| Campo | Valor | Descripción |
|---|---|---|
| `kty` | `"RSA"` | Key type |
| `use` | `"sig"` | Usage — solo firma, nunca cifrado |
| `alg` | `"RS256"` | Algoritmo explícito |
| `kid` | `"motamaze-key-v1"` | Key ID — debe coincidir con el header del JWT |
| `n` | string | Módulo RSA en base64url |
| `e` | `"AQAB"` | Exponente público RSA (65537) |

Durante key rotation, el array `keys` puede contener temporalmente **dos claves** (la antigua y la nueva) para que los tokens emitidos antes de la rotación sigan siendo válidos durante su TTL de 15 minutos.

---

#### Key rotation path

1. Generar nuevo keypair RS256 en Secret Manager (nueva versión del secret `motamaze-jwt-private-key`)
2. Actualizar JWKS endpoint para devolver **ambas claves** (old `kid` + new `kid`)
3. Configurar el backend para firmar nuevos tokens con la nueva clave
4. Esperar 15 minutos (TTL de access tokens) — todos los tokens con la clave antigua expiran
5. Remover la clave antigua del JWKS endpoint
6. Desactivar la versión antigua del secret en Secret Manager

Tiempo total de rotación sin downtime: **~15 minutos**.

---

### ST-03 — Payloads Auth ✅ Done (2026-06-17)

> **Convención de errores:** Todos los errores siguen el formato `{"error_code": "...", "message": "..."}`. El catálogo completo va en ST-07.

---

#### `POST /auth/login` — Login con Google / Apple OAuth

**Auth:** 🔓 público

**Request body:**
```json
{
  "provider":     "google",
  "id_token":     "eyJhbGci...",
  "platform":     "android",
  "app_version":  "1.0.0",
  "device_model": "Pixel 7",
  "os_version":   "Android 14",
  "country":      "MX"
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `provider` | string | ✅ | `"google"` \| `"apple"` |
| `id_token` | string | ✅ | Token OAuth del proveedor. Google: `id_token` de GoogleSignIn. Apple: `identity_token` de `ASAuthorizationAppleIDCredential` |
| `platform` | string | ✅ | `"android"` \| `"ios"` |
| `app_version` | string | ✅ | Versión semántica, ej: `"1.0.0"` |
| `device_model` | string | ⬜ | Modelo de dispositivo, ej: `"Pixel 7"` |
| `os_version` | string | ⬜ | Versión de OS, ej: `"Android 14"` |
| `country` | string | ⬜ | ISO 3166-1 alpha-2, ej: `"MX"`, `"BR"`. Si ausente, backend lo infiere del IP. |

**Response `200 OK`:**
```json
{
  "access_token":  "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Im1vdGFtYXplLWtleS12MSJ9...",
  "refresh_token": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "token_type":    "Bearer",
  "expires_in":    900,
  "user_id":       "usr_abc123def456",
  "is_new_user":   false
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `access_token` | string | JWT RS256 firmado — TTL 15 min |
| `refresh_token` | string | UUID v4 opaco — TTL 14 días |
| `token_type` | string | Siempre `"Bearer"` |
| `expires_in` | int | Segundos hasta expiración del access token (`900`) |
| `user_id` | string | ID del usuario en Firestore `users/{user_id}` |
| `is_new_user` | bool | `true` en el primer login (para onboarding en cliente) |

**Errores:**

| HTTP | `error_code` | Cuándo |
|---|---|---|
| `400` | `AUTH_MISSING_FIELDS` | Falta `provider`, `id_token`, `platform`, o `app_version` |
| `401` | `AUTH_TOKEN_INVALID` | El `id_token` no pasa la verificación del proveedor OAuth |
| `401` | `AUTH_TOKEN_EXPIRED` | El `id_token` ya expiró (típico si el usuario tardó en confirmar) |
| `422` | `VALIDATION_ERROR` | FastAPI rechaza el body por tipos incorrectos |
| `500` | `INTERNAL_ERROR` | Error al escribir en Firestore o emitir JWT |

---

#### `POST /auth/refresh` — Rotar refresh token

**Auth:** 🔓 público (lleva refresh token en el body, no JWT header)

**Request body:**
```json
{
  "refresh_token": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `refresh_token` | string | ✅ | UUID v4 opaco obtenido de `/auth/login` o de un refresh anterior |

**Response `200 OK`:**
```json
{
  "access_token":  "eyJhbGci...",
  "refresh_token": "9b2c3d47-0e02-4b2c-a567-f47ac10b58cc",
  "token_type":    "Bearer",
  "expires_in":    900
}
```

> ⚠️ El `refresh_token` retornado es **siempre uno nuevo**. El anterior queda invalidado inmediatamente. El cliente debe reemplazarlo en su storage persistente.

**Errores:**

| HTTP | `error_code` | Cuándo |
|---|---|---|
| `400` | `AUTH_MISSING_FIELDS` | Falta el campo `refresh_token` |
| `401` | `AUTH_REFRESH_INVALID` | Token no existe en Firestore (ya consumido, nunca existió, o manipulado) |
| `401` | `AUTH_REFRESH_EXPIRED` | La sesión en Firestore existe pero la marca de tiempo supera los 14 días |
| `422` | `VALIDATION_ERROR` | FastAPI rechaza el body |

---

#### `POST /auth/logout` — Cerrar sesión

**Auth:** 🔒 JWT

**Request body:** vacío `{}`

**Response `200 OK`:**
```json
{
  "message": "Session revoked"
}
```

> El backend agrega el `jti` del access token al documento `revoked_jtis/{jti}` en Firestore (con TTL = tiempo de expiración del token) y elimina la sesión de `sessions/{session_id}`.

**Errores:**

| HTTP | `error_code` | Cuándo |
|---|---|---|
| `401` | `AUTH_JWT_MISSING` | Header `Authorization` ausente |
| `401` | `AUTH_JWT_INVALID` | JWT malformado, firma inválida, o `jti` ya revocado |
| `401` | `AUTH_JWT_EXPIRED` | Token expirado — cliente debe llamar a `/auth/refresh` primero |

---

#### `DELETE /auth/account` — Borrar cuenta (GDPR / Apple 5.1.1)

**Auth:** 🔒 JWT

**Request body:** vacío `{}`

**Response `202 Accepted`:**
```json
{
  "message":     "Account deletion queued",
  "deletion_id": "del_7f3a9c12"
}
```

> `202` en lugar de `200` porque la eliminación es **asíncrona**: el backend inserta una fila en `account_deletions` BQ con `status='pending'` y una Cloud Function la procesa en segundo plano (COMP-001, 7/27). El usuario queda efectivamente sin sesión activa de forma inmediata (la sesión se invalida en el mismo request), pero los datos tardan minutos en purgarse.

| Campo | Tipo | Descripción |
|---|---|---|
| `deletion_id` | string | ID de referencia para auditoría — corresponde al registro en `account_deletions` BQ |

**Errores:**

| HTTP | `error_code` | Cuándo |
|---|---|---|
| `401` | `AUTH_JWT_MISSING` | Header `Authorization` ausente |
| `401` | `AUTH_JWT_INVALID` | JWT inválido o revocado |
| `401` | `AUTH_JWT_EXPIRED` | Token expirado |
| `409` | `AUTH_DELETION_PENDING` | Ya existe una solicitud de borrado en curso para este usuario |

---

#### `GET /auth/pending/{state_token}` — Polling de resultado OAuth

**Auth:** 🔓 público

**Path param:**

| Parámetro | Tipo | Descripción |
|---|---|---|
| `state_token` | string (UUID v4) | Token de estado OAuth generado por Godot antes de abrir el browser. TTL: 10 minutos. |

**Request body:** ninguno (GET)

**Response `200 OK` — login completado:**
```json
{
  "status":        "complete",
  "access_token":  "eyJhbGci...",
  "refresh_token": "f47ac10b-...",
  "token_type":    "Bearer",
  "expires_in":    900,
  "user_id":       "usr_abc123def456",
  "is_new_user":   false
}
```

**Response `200 OK` — aún esperando:**
```json
{
  "status": "pending"
}
```

**Response `200 OK` — OAuth falló en el callback:**
```json
{
  "status":     "error",
  "error_code": "AUTH_OAUTH_FAILED"
}
```

> El cliente Godot llama a este endpoint cada **2 segundos** hasta recibir `status: "complete"` o `status: "error"`. Después de recibir cualquier estado final, debe dejar de hacer polling. Si recibe 404, el usuario tardó demasiado y debe reiniciar el flujo.

**Flujo completo:**
```
[Godot] genera state_token (UUID v4)
[Godot] abre browser: https://accounts.google.com/...&state=<state_token>
[Godot] inicia polling: GET /auth/pending/<state_token> cada 2s
[Google] redirige a: https://api.motamaze.com/auth/callback?code=...&state=<state_token>
[Backend] verifica code → upsert user → almacena tokens en Firestore keyed por state_token
[Godot] polling devuelve status:"complete" → extrae tokens → cierra browser
```

**Errores:**

| HTTP | `error_code` | Cuándo |
|---|---|---|
| `404` | `AUTH_STATE_NOT_FOUND` | El `state_token` no existe o expiró (TTL 10 min). Godot debe reiniciar el flujo. |

---

#### `GET /.well-known/jwks.json` — Clave pública JWT

**Auth:** 🔓 público

**Request body:** ninguno (GET)

**Response `200 OK`:**
```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "motamaze-key-v1",
      "n":   "<base64url-encoded modulus>",
      "e":   "AQAB"
    }
  ]
}
```

> Durante key rotation, el array `keys` contiene dos entradas (old `kid` + new `kid`) por una ventana de 15 minutos. Ver ST-02 para el proceso completo de rotación.

**Errores:** ninguno esperado — este endpoint no tiene dependencias externas en el request path.

---

### ST-04 — Payloads Game Services ✅ Done (2026-06-17)

> Todos los endpoints de este dominio requieren `Authorization: Bearer <access_token>`.

---

#### `GET /progress` — Progreso del jugador

**Auth:** 🔒 JWT

**Request body:** ninguno (GET)

**Response `200 OK`:**
```json
{
  "user_id":                 "usr_abc123def456",
  "highest_unlocked_level":  5,
  "total_stars":             12,
  "levels": [
    {
      "level_id":      1,
      "stars_earned":  3,
      "best_score":    9500,
      "completed_at":  "2026-06-15T12:00:00Z"
    },
    {
      "level_id":      2,
      "stars_earned":  2,
      "best_score":    6200,
      "completed_at":  "2026-06-15T12:45:00Z"
    }
  ]
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `highest_unlocked_level` | int | Nivel más alto al que el jugador tiene acceso (1–30). Nuevo usuario = `1`. |
| `total_stars` | int | Suma de estrellas en todos los niveles (máximo 90 = 30 niveles × 3 estrellas) |
| `levels` | array | Solo niveles que el jugador ha completado al menos una vez |
| `levels[].level_id` | int | Identificador del nivel (1–30) |
| `levels[].stars_earned` | int | 1, 2, o 3 — mejor resultado histórico en ese nivel |
| `levels[].best_score` | int | Mejor puntuación histórica |
| `levels[].completed_at` | string (ISO 8601) | Timestamp del primer completion |

**Errores:**

| HTTP | `error_code` | Cuándo |
|---|---|---|
| `401` | `AUTH_JWT_MISSING` / `AUTH_JWT_INVALID` / `AUTH_JWT_EXPIRED` | Token inválido o ausente |
| `404` | `USER_NOT_FOUND` | El `user_id` del JWT no existe en Firestore (inconsistencia) |

---

#### `POST /progress/level-complete` — Registrar nivel completado

**Auth:** 🔒 JWT

**Request body:**
```json
{
  "level_id":      5,
  "score":         9200,
  "stars_earned":  3,
  "duration_secs": 142,
  "session_id":    "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `level_id` | int | ✅ | Nivel completado (1–30) |
| `score` | int | ✅ | Puntuación obtenida (≥ 0) |
| `stars_earned` | int | ✅ | Estrellas obtenidas (1, 2, o 3) |
| `duration_secs` | int | ✅ | Duración de la partida en segundos |
| `session_id` | string | ✅ | Session ID activo — necesario para el event de `player_behavior` en BQ |

**Validaciones server-side:**
- `level_id` entre 1 y 30
- `level_id` ≤ `highest_unlocked_level + 1` (no puede saltarse niveles)
- `stars_earned` entre 1 y 3
- `score` ≥ 0

**Response `200 OK`:**
```json
{
  "level_id":                5,
  "stars_earned":            3,
  "best_score":              9200,
  "new_best":                true,
  "next_level_unlocked":     6,
  "highest_unlocked_level":  6,
  "total_stars":             15
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `new_best` | bool | `true` si este score supera el mejor histórico del nivel |
| `next_level_unlocked` | int \| null | Número del nivel recién desbloqueado, o `null` si ya estaba desbloqueado |
| `highest_unlocked_level` | int | Valor actualizado tras este completion |
| `total_stars` | int | Total actualizado |

**Errores:**

| HTTP | `error_code` | Cuándo |
|---|---|---|
| `400` | `PROGRESS_LEVEL_LOCKED` | El `level_id` supera `highest_unlocked_level + 1` |
| `400` | `PROGRESS_INVALID_STARS` | `stars_earned` fuera del rango 1–3 |
| `400` | `PROGRESS_INVALID_LEVEL` | `level_id` fuera del rango 1–30 |
| `401` | `AUTH_JWT_MISSING` / `AUTH_JWT_INVALID` / `AUTH_JWT_EXPIRED` | Token inválido |

---

#### `GET /lives` — Estado de las vidas

**Auth:** 🔒 JWT

**Request body:** ninguno (GET)

**Response `200 OK` — jugador por debajo del máximo:**
```json
{
  "current_lives":     3,
  "max_lives":         5,
  "next_regen_at":     "2026-06-17T14:30:00Z",
  "regen_interval_secs": 1800
}
```

**Response `200 OK` — jugador con máximo de vidas:**
```json
{
  "current_lives":     5,
  "max_lives":         5,
  "next_regen_at":     null,
  "regen_interval_secs": 1800
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `current_lives` | int | Vidas actuales (0–`max_lives`) |
| `max_lives` | int | Máximo de vidas (5 en MVP) |
| `next_regen_at` | string \| null | ISO 8601 — cuándo se regenera la próxima vida. `null` si `current_lives == max_lives` |
| `regen_interval_secs` | int | Segundos entre regeneraciones (1800 = 30 min) |

**Errores:**

| HTTP | `error_code` | Cuándo |
|---|---|---|
| `401` | `AUTH_JWT_*` | Token inválido o expirado |

---

#### `POST /lives/spend` — Gastar una vida

**Auth:** 🔒 JWT

**Request body:**
```json
{
  "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `session_id` | string | ✅ | Session activo — para trazar la pérdida de vida en `player_behavior` BQ |

> El servidor decrementa atómicamente. Si `current_lives == 0`, retorna error — el cliente **no debe** llamar a este endpoint si sabe que no hay vidas.

**Response `200 OK`:**
```json
{
  "remaining_lives": 2,
  "next_regen_at":   "2026-06-17T14:30:00Z"
}
```

**Errores:**

| HTTP | `error_code` | Cuándo |
|---|---|---|
| `400` | `LIVES_INSUFFICIENT` | `current_lives == 0` — no hay vidas para gastar |
| `401` | `AUTH_JWT_*` | Token inválido |

---

#### `POST /lives/grant` — Otorgar vidas

**Auth:** 🔒 JWT

**Request body — source `iap`:**
```json
{
  "source":     "iap",
  "product_id": "lives_pack_5",
  "session_id": "f47ac10b-..."
}
```

**Request body — source `rewarded_ad_ssv`:**
```json
{
  "source":        "rewarded_ad_ssv",
  "reward_token":  "<token firmado por AdMob SDK>",
  "ad_unit_id":    "ca-app-pub-3940256099942544/5354046379",
  "session_id":    "f47ac10b-..."
}
```

**Request body — source `promo`:**
```json
{
  "source":     "promo",
  "promo_code": "BETA_LAUNCH",
  "session_id": "f47ac10b-..."
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `source` | string | ✅ | `"iap"` \| `"rewarded_ad_ssv"` \| `"promo"` |
| `product_id` | string | Condicional | Requerido si `source == "iap"` — SKU del producto, ej: `"lives_pack_5"` |
| `reward_token` | string | Condicional | Requerido si `source == "rewarded_ad_ssv"` — token firmado que entrega el AdMob SDK |
| `ad_unit_id` | string | Condicional | Requerido si `source == "rewarded_ad_ssv"` |
| `promo_code` | string | Condicional | Requerido si `source == "promo"` |
| `session_id` | string | ✅ | Para trazar el grant en `entitlement_grants` BQ |

> **`source: "iap"`** — Este path solo se llama cuando el grant viene directamente del flujo de IAP y **no** del flujo de verify (es decir, cuando `POST /payments/android/verify` ya otorgó el entitlement). En la práctica, el flujo normal de IAP llama a `/payments/*/verify` que internamente otorga el entitlement. `POST /lives/grant` con `source: "iap"` es para grants directos (ej: admin tools, fallback recovery).
>
> **`source: "rewarded_ad_ssv"`** — El cliente envía el `reward_token` del AdMob SDK. El backend lo verifica criptográficamente con la clave pública de AdMob antes de otorgar.

**Response `200 OK`:**
```json
{
  "granted":       1,
  "current_lives": 4,
  "max_lives":     5,
  "next_regen_at": "2026-06-17T14:30:00Z",
  "capped":        false
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `granted` | int | Vidas realmente otorgadas (puede ser menor al solicitado si el jugador estaba cerca del máximo) |
| `capped` | bool | `true` si se truncó el grant por llegar al máximo (ej: tenía 4 vidas, se intentaron dar 5, solo se dieron 1) |

**Errores:**

| HTTP | `error_code` | Cuándo |
|---|---|---|
| `400` | `LIVES_GRANT_INVALID_SOURCE` | `source` no es uno de los tres valores válidos |
| `400` | `LIVES_GRANT_MISSING_FIELDS` | Falta `product_id`, `reward_token`, o `promo_code` según el source |
| `401` | `AUTH_JWT_*` | Token inválido |
| `402` | `LIVES_SSV_INVALID` | El `reward_token` de AdMob no pasa la verificación criptográfica |
| `409` | `LIVES_GRANT_DUPLICATE` | El `reward_token` ya fue usado (replay attack) |
| `422` | `LIVES_PROMO_INVALID` | El `promo_code` no existe o ya fue canjeado por este usuario |

---

#### `GET /store/catalog` — Catálogo de productos

**Auth:** 🔒 JWT

**Request body:** ninguno (GET)

**Response `200 OK`:**
```json
{
  "catalog_version": "2026-06-17",
  "products": [
    {
      "product_id":    "lives_pack_5",
      "type":          "consumable",
      "display_name":  "5 Extra Lives",
      "description":   "Keep playing with 5 extra lives",
      "price_usd":     0.99,
      "currency":      "USD",
      "lives_granted": 5,
      "owned":         false,
      "promotion":     null
    },
    {
      "product_id":   "no_ads",
      "type":         "non_consumable",
      "display_name": "Remove Ads",
      "description":  "Remove all ads permanently",
      "price_usd":    2.99,
      "currency":     "USD",
      "owned":        false,
      "promotion": {
        "discount_percent": 20,
        "original_price_usd": 3.99,
        "expires_at": "2026-07-01T00:00:00Z"
      }
    },
    {
      "product_id":   "skin_gold",
      "type":         "non_consumable",
      "display_name": "Gold Mota",
      "description":  "A shiny golden skin for Mota",
      "price_usd":    0.99,
      "currency":     "USD",
      "owned":        true,
      "promotion":    null
    }
  ]
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `catalog_version` | string | Fecha de la última actualización del catálogo — el cliente puede cachear si la versión no cambia |
| `type` | string | `"consumable"` (lives) \| `"non_consumable"` (no_ads, skins) |
| `owned` | bool | `true` si el usuario ya tiene este entitlement — el cliente oculta o deshabilita el botón de compra |
| `promotion` | object \| null | Si activo: `discount_percent`, `original_price_usd`, `expires_at`. Los precios en promoción vienen resueltos en `price_usd`. |
| `lives_granted` | int \| null | Solo en productos de tipo `consumable` de tipo lives. |

> **Por qué server-driven:** El precio en `price_usd` y las promociones activas se resuelven en el servidor (vía Remote Config). El cliente Godot nunca tiene precios hardcodeados — siempre consume este endpoint para mostrar la tienda.

**Errores:**

| HTTP | `error_code` | Cuándo |
|---|---|---|
| `401` | `AUTH_JWT_*` | Token inválido |

---

#### `POST /profile/equip-skin` — Equipar skin

**Auth:** 🔒 JWT

**Request body:**
```json
{
  "skin_id": "skin_gold"
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `skin_id` | string | ✅ | ID del skin a equipar, ej: `"skin_gold"`, `"skin_default"` |

> El backend verifica que el usuario tenga el entitlement de ese skin en Firestore `entitlements/{user_id}` antes de actualizar `users/{user_id}.equipped_skin`.

**Response `200 OK`:**
```json
{
  "skin_id":   "skin_gold",
  "equipped":  true
}
```

**Errores:**

| HTTP | `error_code` | Cuándo |
|---|---|---|
| `400` | `SKIN_NOT_FOUND` | El `skin_id` no existe en el catálogo de skins |
| `401` | `AUTH_JWT_*` | Token inválido |
| `403` | `SKIN_NOT_OWNED` | El usuario no tiene el entitlement de ese skin — no lo ha comprado |

---

#### `POST /events/behavior` — Reporte batch de eventos de gameplay *(agregado 2026-06-18)*

**Auth:** 🔒 JWT

**Propósito:** Endpoint write-only para que el cliente Godot reporte eventos granulares de gameplay en batch. Alimenta directamente `player_behavior` en BigQuery. No modifica estado en Firestore — es puro analytics.

> Godot acumula eventos durante la partida y los envía en batch al terminar un nivel o al ir al background — evita una llamada HTTP por cada evento individual.

**Request body:**
```json
{
  "session_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "events": [
    {
      "event_name":    "level_start",
      "level_id":      5,
      "timestamp":     "2026-06-18T14:00:00Z"
    },
    {
      "event_name":    "maze_shift",
      "level_id":      5,
      "timestamp":     "2026-06-18T14:01:23Z"
    },
    {
      "event_name":    "npc_caught",
      "level_id":      5,
      "npc_type":      "bola",
      "timestamp":     "2026-06-18T14:02:05Z"
    },
    {
      "event_name":    "level_fail",
      "level_id":      5,
      "duration_secs": 125,
      "timestamp":     "2026-06-18T14:02:05Z"
    }
  ]
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `session_id` | string | ✅ | Session activo — correlaciona todos los eventos de la misma sesión |
| `events` | array | ✅ | Array de eventos (mínimo 1, máximo 100 por request) |
| `events[].event_name` | string | ✅ | Tipo de evento — ver catálogo abajo |
| `events[].level_id` | int | ⬜ | Nivel donde ocurrió (1–30) |
| `events[].timestamp` | string ISO 8601 | ✅ | Timestamp del evento en el cliente |
| `events[].duration_secs` | int | ⬜ | Duración — aplica en `level_fail` y `level_complete` |
| `events[].score` | int | ⬜ | Score — aplica en `level_complete` |
| `events[].stars_earned` | int | ⬜ | Estrellas — aplica en `level_complete` |
| `events[].npc_type` | string | ⬜ | `"bola"` \| `"mancha"` \| `"huracan"` \| `"conejo"` — aplica en `npc_caught` |
| `events[].extra_json` | string | ⬜ | JSON string para campos variables adicionales |

**`event_name` válidos:** `level_start`, `level_complete`, `level_fail`, `maze_shift`, `npc_caught`, `item_collected`, `tutorial_step`

**Response `200 OK`:**
```json
{ "accepted": 4 }
```

**Errores:**

| HTTP | `error_code` | Cuándo |
|---|---|---|
| `400` | `EVENTS_EMPTY` | Array `events` vacío |
| `400` | `EVENTS_TOO_MANY` | Array supera 100 elementos |
| `400` | `EVENTS_INVALID_NAME` | Algún `event_name` no está en el catálogo válido |
| `401` | `AUTH_JWT_*` | Token inválido |

---

### ST-05 — Payloads Payments ✅ Done (2026-06-17)

> **Principios de este dominio:**
> - **Idempotencia obligatoria:** Si el mismo `purchase_token` / `transaction_id` llega dos veces, el segundo request retorna el mismo resultado sin doblar el grant.
> - **Acknowledge en el mismo request:** El backend llama a la API de la tienda para acknowledge/consume en el mismo flujo antes de responder al cliente — nunca dejar una compra sin acknowledge.
> - **Los refund webhooks son llamados por la tienda**, no por el cliente — su autenticación es por firma criptográfica, no por JWT.

---

#### `POST /payments/android/verify` — Verificar compra de Google Play

**Auth:** 🔒 JWT

**Flujo:**
```
[Godot] compra con Play Billing SDK → recibe purchaseToken
[Godot] POST /payments/android/verify { purchase_token, product_id, session_id }
[Backend] Google Play Developer API: purchases.products.get(purchase_token)
[Backend] verifica purchaseState == PURCHASED (0)
[Backend] Firestore: otorga entitlement al usuario
[Backend] Google Play Developer API: acknowledge (non-consumable) o consume (consumable)
[Backend] BigQuery: inserta en purchase_events + entitlement_grants (background)
[Backend] responde 200 al cliente con el entitlement otorgado
```

**Request body:**
```json
{
  "purchase_token": "mgohjialkdgfj...",
  "product_id":     "lives_pack_5",
  "session_id":     "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `purchase_token` | string | ✅ | Token emitido por Play Billing SDK al completar la compra |
| `product_id` | string | ✅ | SKU del producto, ej: `"lives_pack_5"`, `"no_ads"`, `"skin_gold"` |
| `session_id` | string | ✅ | Para trazar el evento en `purchase_events` BQ |

**Response `200 OK`:**
```json
{
  "order_id":             "GPA.3327-4521-8241-12345",
  "product_id":           "lives_pack_5",
  "product_type":         "consumable",
  "verification_status":  "verified",
  "grant_status":         "granted",
  "entitlement": {
    "type":           "life_pack",
    "quantity":       5,
    "current_lives":  7
  }
}
```

**Response `200 OK` — compra ya procesada (idempotente):**
```json
{
  "order_id":             "GPA.3327-4521-8241-12345",
  "product_id":           "lives_pack_5",
  "product_type":         "consumable",
  "verification_status":  "verified",
  "grant_status":         "already_granted",
  "entitlement": {
    "type":           "life_pack",
    "quantity":       5,
    "current_lives":  3
  }
}
```

**Response `202 Accepted` — compra pendiente (PENDING en Play):**
```json
{
  "order_id":            null,
  "product_id":          "lives_pack_5",
  "verification_status": "pending",
  "grant_status":        "pending",
  "message":             "Purchase is pending approval. Retry when payment is confirmed."
}
```

| Campo en response | Tipo | Descripción |
|---|---|---|
| `order_id` | string \| null | ID de orden de Google Play. `null` si la compra está pendiente |
| `verification_status` | string | `"verified"` \| `"pending"` \| `"invalid"` |
| `grant_status` | string | `"granted"` \| `"already_granted"` \| `"pending"` \| `"failed"` |
| `entitlement.type` | string | `"life_pack"` \| `"no_ads"` \| `"skin"` |
| `entitlement.quantity` | int \| null | Solo para `"life_pack"` — cantidad de vidas otorgadas |
| `entitlement.current_lives` | int \| null | Solo para `"life_pack"` — vidas totales después del grant |
| `entitlement.skin_id` | string \| null | Solo para `"skin"` — ej: `"skin_gold"` |

**Errores:**

| HTTP | `error_code` | Cuándo |
|---|---|---|
| `400` | `PAY_MISSING_FIELDS` | Falta `purchase_token` o `product_id` |
| `400` | `PAY_PRODUCT_NOT_FOUND` | `product_id` no existe en el catálogo |
| `401` | `AUTH_JWT_*` | Token JWT inválido |
| `402` | `PAY_VERIFICATION_FAILED` | Play Developer API rechaza el `purchase_token` (inválido, ya consumido por otro usuario, o manipulado) |
| `503` | `PAY_STORE_UNAVAILABLE` | Google Play Developer API no responde — el cliente debe reintentar |

---

#### `POST /payments/ios/verify` — Verificar compra de Apple StoreKit 2

**Auth:** 🔒 JWT

**Flujo:**
```
[Godot] compra con StoreKit 2 SDK → recibe transactionId (Int64)
[Godot] POST /payments/ios/verify { transaction_id, product_id, session_id }
[Backend] App Store Server API: GET /inApps/v1/transactions/{transactionId}
[Backend] recibe JWS (JSON Web Signature) firmado por Apple
[Backend] verifica la cadena JWS contra el certificado raíz de Apple
[Backend] Firestore: otorga entitlement al usuario
[Backend] BigQuery: inserta en purchase_events + entitlement_grants (background)
[Backend] responde 200 al cliente con el entitlement otorgado
```

> **StoreKit 2 vs. StoreKit 1:** StoreKit 2 usa `transactionId` (Int64) en lugar del `receiptData` de StoreKit 1. No se usa `verifyReceipt` (deprecated) — se usa el App Store Server API con el `transactionId`. El JWS de respuesta se verifica localmente sin llamada adicional.

**Request body:**
```json
{
  "transaction_id": "2000000123456789",
  "product_id":     "lives_pack_5",
  "session_id":     "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `transaction_id` | string | ✅ | Transaction ID de StoreKit 2 — Int64 como string (ej: `"2000000123456789"`) |
| `product_id` | string | ✅ | SKU del producto |
| `session_id` | string | ✅ | Para trazar en BQ |

**Response `200 OK`:**
```json
{
  "transaction_id":       "2000000123456789",
  "product_id":           "lives_pack_5",
  "product_type":         "consumable",
  "verification_status":  "verified",
  "grant_status":         "granted",
  "entitlement": {
    "type":          "life_pack",
    "quantity":      5,
    "current_lives": 7
  }
}
```

> La estructura del response es idéntica a la del endpoint Android, facilitando el manejo unificado en el cliente.

**Errores:**

| HTTP | `error_code` | Cuándo |
|---|---|---|
| `400` | `PAY_MISSING_FIELDS` | Falta `transaction_id` o `product_id` |
| `400` | `PAY_PRODUCT_NOT_FOUND` | `product_id` no existe en el catálogo |
| `401` | `AUTH_JWT_*` | Token JWT inválido |
| `402` | `PAY_VERIFICATION_FAILED` | JWS inválido, firma no corresponde a Apple, o transacción ya revocada |
| `402` | `PAY_TRANSACTION_NOT_FOUND` | `transaction_id` no existe en App Store Server API |
| `503` | `PAY_STORE_UNAVAILABLE` | App Store Server API no responde |

---

#### `POST /payments/android/refund-notification` — Webhook de refund Google Play

**Auth:** 🔓 firmado por Pub/Sub (no JWT)

> Este endpoint **no es llamado por el cliente Godot** — es llamado por Google Cloud Pub/Sub cuando Google Play emite una notificación RTDN (Real-Time Developer Notification). La autenticación se hace via el bearer token de la push subscription de Pub/Sub, verificado automáticamente por GCP.

**Flujo:**
```
[Google Play] emite RTDN (refund / voided purchase)
[Pub/Sub] hace POST a https://api.motamaze.com/payments/android/refund-notification
[Backend] verifica el bearer token del push subscription
[Backend] decodifica base64: message.data → DeveloperNotification JSON
[Backend] si es voidedPurchaseNotification o SUBSCRIPTION_REVOKED:
           → revoca entitlement en Firestore
           → actualiza purchase_events BQ (verification_status = "refunded")
[Backend] retorna 200 para acknowledge — Pub/Sub deja de reintentar
```

**Request body** (estructura de push de Pub/Sub):
```json
{
  "message": {
    "data":        "<base64url-encoded DeveloperNotification JSON>",
    "messageId":   "1234567890",
    "publishTime": "2026-06-17T14:00:00Z"
  },
  "subscription": "projects/motamaze/subscriptions/play-rtdn-sub"
}
```

**`message.data` decodificado — notificación de refund:**
```json
{
  "version":          "1.0",
  "packageName":      "com.ingeniouscruciblestudios.motamaze",
  "eventTimeMillis":  "1750000000000",
  "voidedPurchaseNotification": {
    "purchaseToken": "mgohjialkdgfj...",
    "orderId":       "GPA.3327-4521-8241-12345",
    "productType":   1
  }
}
```

> `productType`: `1` = in-app product, `2` = subscription.

**Response `200 OK`:** body vacío `{}`

> **Crítico:** El backend debe responder `200` dentro de 30 segundos. Si no, Pub/Sub reintentará con backoff exponencial. Responder `200` no significa que el procesamiento esté completo — si hay un error interno, logearlo y responder `200` de todas formas (para evitar reintento infinito). Los errores se resuelven via reconciliación diaria con el reporte de AdMob / Play Console.

**Errores que NO se retornan al llamador (se logean internamente):**

| Situación | Acción |
|---|---|
| `purchase_token` no encontrado en Firestore | Log warning, responder 200 (puede ser de una compra pre-MVP) |
| Error al revocar entitlement | Log error, responder 200 de todas formas |
| JSON malformado en `message.data` | Log error, responder 200 |

---

#### `POST /payments/ios/refund-notification` — Webhook de refund Apple

**Auth:** 🔓 firmado por Apple (JWS — no JWT)

> Este endpoint es llamado directamente por Apple App Store Server Notifications v2. La autenticación es via la firma JWS del payload — el backend verifica la cadena de certificados contra el Apple Root CA.

**Flujo:**
```
[Apple] emite ASSN v2 notification (REFUND / REVOKE)
[Apple] hace POST a https://api.motamaze.com/payments/ios/refund-notification
[Backend] decodifica y verifica signedPayload (JWS firmado por Apple)
[Backend] extrae notificationType del payload
[Backend] si es REFUND o REVOKE:
           → revoca entitlement en Firestore
           → actualiza purchase_events BQ
[Backend] retorna 200 para acknowledge
```

**Request body:**
```json
{
  "signedPayload": "eyJhbGciOiJFUzI1NiIsIng1YyI6WyJNSUlC..."
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `signedPayload` | string | JWS (JSON Web Signature) firmado por Apple. Al decodificar el payload, contiene `notificationType` y `data.signedTransactionInfo`. |

**`signedPayload` decodificado — tipos de notificación relevantes:**

| `notificationType` | Acción requerida |
|---|---|
| `REFUND` | El usuario recibió un reembolso — revocar entitlement |
| `REVOKE` | Compra revocada por Apple (family sharing revoke, etc.) — revocar entitlement |
| `DID_CHANGE_RENEWAL_STATUS` | No aplica en MVP (no hay suscripciones) — ignorar, responder 200 |
| Cualquier otro tipo | Ignorar, responder 200 |

**Response `200 OK`:** body vacío `{}`

> Apple reintenta la notificación hasta 5 veces con backoff exponencial si no recibe `200`. Misma regla que el webhook de Android: responder `200` siempre; los errores internos se logean, no se retornan.

**Errores que NO se retornan al llamador (se logean internamente):**

| Situación | Acción |
|---|---|
| `signedPayload` JWS con firma inválida | Log error de seguridad, responder `200` (evitar que Apple reintente un payload malicioso) |
| `transaction_id` no encontrado en Firestore | Log warning, responder `200` |
| Error al revocar entitlement | Log error, responder `200` |

---

### ST-06 — Payloads Infrastructure ✅ Done (2026-06-17)

> Ambos endpoints ya están implementados en el scaffold de INFRA-003 (`app/routers/health.py`). Esta sección los formaliza como parte del contrato.

---

#### `GET /health` — Liveness probe

**Auth:** 🔓 público

**Propósito:** Cloud Run llama a este endpoint para determinar si el contenedor está vivo. Si retorna `non-2xx` tres veces consecutivas, Cloud Run reinicia el contenedor. No debe hacer ninguna llamada externa — solo confirmar que el proceso Python responde.

**Request body:** ninguno (GET)

**Response `200 OK`:**
```json
{
  "status":  "ok",
  "version": "1.0.0"
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `status` | string | Siempre `"ok"` si el endpoint responde |
| `version` | string | Versión del servicio (inyectada como variable de entorno `APP_VERSION` en el build) |

**Comportamiento de errores:** Si el proceso falla antes de responder, Cloud Run recibe un timeout o connection error — no hay un JSON de error explícito porque el proceso no puede generarlo.

**Configuración Cloud Run (liveness probe):**

```yaml
livenessProbe:
  httpGet:
    path: /health
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 3
```

---

#### `GET /ready` — Readiness probe

**Auth:** 🔓 público

**Propósito:** Cloud Run llama a este endpoint para determinar si el contenedor está listo para recibir tráfico. Si retorna `non-2xx`, Cloud Run no enruta requests a esta instancia hasta que pase. A diferencia de `/health`, puede verificar dependencias externas.

**Request body:** ninguno (GET)

**Response `200 OK` — instancia lista:**
```json
{
  "status":  "ready",
  "version": "1.0.0",
  "checks": {
    "firestore": "ok"
  }
}
```

**Response `503 Service Unavailable` — instancia no lista:**
```json
{
  "status": "not_ready",
  "checks": {
    "firestore": "error"
  }
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `status` | string | `"ready"` \| `"not_ready"` |
| `checks.firestore` | string | `"ok"` si Firestore responde a un ping de lectura; `"error"` si no |

> **MVP:** El check de Firestore es un read de un documento de prueba (`/_health/probe`). Si falla, la instancia no recibe tráfico hasta que Firestore se recupere. BigQuery no se verifica en el readiness check — las escrituras BQ son background tasks y su falla no impide servir requests.

**Configuración Cloud Run (readiness probe):**

```yaml
readinessProbe:
  httpGet:
    path: /ready
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

---

#### Diferencia clave entre `/health` y `/ready`

| | `/health` (liveness) | `/ready` (readiness) |
|---|---|---|
| **Fallo implica** | Reiniciar el contenedor | Dejar de enviarle tráfico |
| **Verifica dependencias externas** | ❌ No — solo que el proceso vive | ✅ Sí — Firestore reachable |
| **Latencia objetivo** | < 10ms | < 500ms |
| **Si falla 3 veces** | Cloud Run reinicia la instancia | Cloud Run quita la instancia del load balancer |

---

### ST-07 — Error taxonomy ✅ Done (2026-06-17)

---

#### Formato estándar de error

Todos los errores generados por el backend MotaMaze siguen esta forma:

```json
{
  "error_code": "AUTH_TOKEN_INVALID",
  "message":    "The provided OAuth token is invalid or could not be verified.",
  "details":    {}
}
```

| Campo | Tipo | Siempre presente | Descripción |
|---|---|---|---|
| `error_code` | string | ✅ | Código de máquina — el cliente Godot ramifica su lógica por este campo |
| `message` | string | ✅ | Descripción en inglés para logging / debugging — no mostrar al usuario final |
| `details` | object | ⬜ Opcional | Contexto adicional (ej: qué campo falló). Puede estar ausente o vacío `{}`. |

> **Regla para el cliente Godot:** Leer siempre `error_code` para la lógica. Nunca parsear `message` — ese campo puede cambiar sin aviso. `details` es solo para debugging.

---

#### Excepción: errores de validación FastAPI (422)

FastAPI genera automáticamente errores 422 con su propio formato cuando el request body no coincide con el schema Pydantic. Este formato es **distinto** del estándar anterior:

```json
{
  "detail": [
    {
      "loc":  ["body", "provider"],
      "msg":  "field required",
      "type": "value_error.missing"
    },
    {
      "loc":  ["body", "id_token"],
      "msg":  "field required",
      "type": "value_error.missing"
    }
  ]
}
```

| Campo | Descripción |
|---|---|
| `detail` | Array de errores de validación |
| `detail[].loc` | Ubicación del campo que falló, ej: `["body", "campo"]` |
| `detail[].msg` | Descripción del fallo |
| `detail[].type` | Código interno de Pydantic |

> El cliente Godot debe manejar `422` como "error de programación" (el request está malformado) y no como un error de usuario. En producción no deberían ocurrir.

---

#### HTTP status codes utilizados

| Código | Nombre | Uso en MotaMaze |
|---|---|---|
| `200` | OK | Request exitoso con respuesta en body |
| `202` | Accepted | Operación asíncrona encolada — `DELETE /auth/account` |
| `400` | Bad Request | Input inválido, regla de negocio violada, campo faltante |
| `401` | Unauthorized | Autenticación requerida o fallida (JWT inválido, OAuth fallo, refresh expirado) |
| `402` | Payment Required | Verificación de compra fallida (token inválido, SSV inválido, transacción no encontrada) |
| `403` | Forbidden | Autenticado pero sin permiso sobre ese recurso (skin no comprada, nivel bloqueado) |
| `404` | Not Found | Recurso no existe (state_token expirado, user_id inexistente) |
| `409` | Conflict | Conflicto de estado (solicitud de borrado ya en curso, reward token ya canjeado) |
| `422` | Unprocessable Entity | FastAPI: body no cumple el schema Pydantic |
| `503` | Service Unavailable | Dependencia externa no disponible (Play Developer API, App Store Server API) |

**Códigos no utilizados y por qué:**
- `404` en endpoints protegidos con JWT: si el `user_id` del JWT no existe en Firestore, se retorna `401` (no `404`) para no confirmar si el usuario existe.
- `429` (Rate Limiting): no implementado en MVP. Se agrega post soft-launch con Cloud Armor o un middleware de FastAPI.
- `500` (Internal Server Error): FastAPI lo emite automáticamente en excepciones no capturadas. El backend no lo retorna explícitamente excepto en casos muy específicos.

---

#### Catálogo de error codes — Globales

Aplican a cualquier endpoint protegido (🔒):

| `error_code` | HTTP | Cuándo |
|---|---|---|
| `AUTH_JWT_MISSING` | 401 | Header `Authorization` ausente en un endpoint protegido |
| `AUTH_JWT_INVALID` | 401 | JWT malformado, firma RS256 inválida, `aud` incorrecto, o `jti` en `revoked_jtis` |
| `AUTH_JWT_EXPIRED` | 401 | JWT expirado (`exp` en el pasado, fuera del clock skew de ±30s) |
| `INTERNAL_ERROR` | 500 | Error inesperado del servidor — ver logs en Cloud Logging |
| `VALIDATION_ERROR` | 422 | Body no cumple el schema Pydantic (generado por FastAPI) |

---

#### Catálogo de error codes — Auth

| `error_code` | HTTP | Endpoint | Cuándo |
|---|---|---|---|
| `AUTH_MISSING_FIELDS` | 400 | `POST /auth/login`, `POST /auth/refresh` | Falta `provider`, `id_token`, `platform`, `app_version`, o `refresh_token` |
| `AUTH_TOKEN_INVALID` | 401 | `POST /auth/login` | El `id_token` no pasa la verificación del proveedor OAuth (Google/Apple) |
| `AUTH_TOKEN_EXPIRED` | 401 | `POST /auth/login` | El `id_token` ya expiró antes de llegar al backend |
| `AUTH_REFRESH_INVALID` | 401 | `POST /auth/refresh` | Refresh token no existe en Firestore (ya consumido, nunca existió, o manipulado) |
| `AUTH_REFRESH_EXPIRED` | 401 | `POST /auth/refresh` | La sesión existe pero el timestamp supera los 14 días |
| `AUTH_DELETION_PENDING` | 409 | `DELETE /auth/account` | Ya existe una solicitud de borrado en curso para este usuario |
| `AUTH_STATE_NOT_FOUND` | 404 | `GET /auth/pending/{state_token}` | El `state_token` no existe o su TTL de 10 minutos expiró |

---

#### Catálogo de error codes — Game Services

| `error_code` | HTTP | Endpoint | Cuándo |
|---|---|---|---|
| `USER_NOT_FOUND` | 404 | `GET /progress` | El `user_id` del JWT no existe en Firestore (inconsistencia — no debería ocurrir en producción) |
| `PROGRESS_INVALID_LEVEL` | 400 | `POST /progress/level-complete` | `level_id` fuera del rango 1–30 |
| `PROGRESS_LEVEL_LOCKED` | 400 | `POST /progress/level-complete` | `level_id` supera `highest_unlocked_level + 1` (intento de saltar nivel) |
| `PROGRESS_INVALID_STARS` | 400 | `POST /progress/level-complete` | `stars_earned` fuera del rango 1–3 |
| `LIVES_INSUFFICIENT` | 400 | `POST /lives/spend` | `current_lives == 0` — no hay vidas para gastar |
| `LIVES_GRANT_INVALID_SOURCE` | 400 | `POST /lives/grant` | `source` no es `"iap"`, `"rewarded_ad_ssv"`, ni `"promo"` |
| `LIVES_GRANT_MISSING_FIELDS` | 400 | `POST /lives/grant` | Falta el campo condicional requerido según el `source` |
| `LIVES_SSV_INVALID` | 402 | `POST /lives/grant` | El `reward_token` de AdMob no pasa la verificación criptográfica |
| `LIVES_GRANT_DUPLICATE` | 409 | `POST /lives/grant` | El `reward_token` ya fue canjeado (replay attack) |
| `LIVES_PROMO_INVALID` | 422 | `POST /lives/grant` | El `promo_code` no existe o ya fue canjeado por este usuario |
| `SKIN_NOT_FOUND` | 400 | `POST /profile/equip-skin` | El `skin_id` no existe en el catálogo de skins |
| `SKIN_NOT_OWNED` | 403 | `POST /profile/equip-skin` | El usuario no tiene el entitlement del skin (no lo ha comprado) |

---

#### Catálogo de error codes — Payments

| `error_code` | HTTP | Endpoint | Cuándo |
|---|---|---|---|
| `PAY_MISSING_FIELDS` | 400 | `POST /payments/*/verify` | Falta `purchase_token`, `transaction_id`, `product_id`, o `session_id` |
| `PAY_PRODUCT_NOT_FOUND` | 400 | `POST /payments/*/verify` | `product_id` no existe en el catálogo de productos del servidor |
| `PAY_VERIFICATION_FAILED` | 402 | `POST /payments/android/verify` | Play Developer API rechaza el `purchase_token` (inválido, ya consumido por otro usuario, fraudulento) |
| `PAY_TRANSACTION_NOT_FOUND` | 402 | `POST /payments/ios/verify` | `transaction_id` no existe en App Store Server API |
| `PAY_STORE_UNAVAILABLE` | 503 | `POST /payments/*/verify` | Google Play Developer API o App Store Server API no responden — el cliente debe reintentar después |

---

#### Guía de manejo de errores para el cliente Godot

```
switch error_code:

  # Redirigir al login
  "AUTH_JWT_EXPIRED", "AUTH_JWT_INVALID", "AUTH_REFRESH_EXPIRED", "AUTH_REFRESH_INVALID":
    → llamar a POST /auth/refresh
    → si falla, redirigir al flujo de login

  # Mostrar mensaje al usuario
  "LIVES_INSUFFICIENT":
    → mostrar "No tienes vidas. ¿Comprar más?"
  "SKIN_NOT_OWNED":
    → mostrar "Necesitas comprar este skin para equiparlo"
  "PROGRESS_LEVEL_LOCKED":
    → mostrar "Completa el nivel anterior primero"

  # Reintentar automáticamente (backoff)
  "PAY_STORE_UNAVAILABLE":
    → esperar 5s, reintentar hasta 3 veces

  # Idempotencia — tratar como éxito
  "LIVES_GRANT_DUPLICATE":
    → el reward ya fue otorgado — ignorar, refrescar estado con GET /lives

  # Errores de programación (no mostrar al usuario, solo logear)
  "VALIDATION_ERROR", "AUTH_MISSING_FIELDS", "PAY_MISSING_FIELDS":
    → logear, no mostrar al usuario final

  # Error genérico de servidor
  "INTERNAL_ERROR":
    → mostrar "Algo salió mal, intenta de nuevo"
    → logear con el request original para debugging
```

---

### ST-08 — Sign-off Juan ⬜ Pending

Circularle el documento completo a Juan para revisión. Deadline: 2026-06-24.

---

## Follow-ups / Notes

- **Endpoints iOS vs. Android:** `/payments/ios/verify` y `/payments/ios/refund-notification` son exclusivos de iOS. En MVP se lanza Android primero — estos endpoints existen desde el inicio para no tener que refactorizar cuando llegue iOS.
- **`/auth/pending/{state_token}`:** Este endpoint es el mecanismo de polling del callback OAuth (RFC 8252 — no custom scheme). El cliente Godot llama a este endpoint cada 2s hasta recibir los tokens o un error de timeout.
- **`/payments/android/refund-notification` y `/payments/ios/refund-notification`:** Estos endpoints no llevan JWT — son llamados por Google/Apple directamente. La autenticación es vía firma criptográfica (Pub/Sub push token para Android, JWS para iOS).
- **`/store/catalog`:** Este endpoint devuelve los precios resueltos server-side — el cliente Godot nunca hardcodea precios. Remote Config puede modificar precios/promociones sin app update.
- **Versioning:** No se implementa versioning (v1/, v2/) en el MVP. Si se necesita en el futuro, se agrega como prefijo (`/v2/auth/login`) sin romper los endpoints existentes.
