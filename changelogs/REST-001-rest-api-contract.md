# REST-001 — Client↔Backend REST API Contract

| Campo | Valor |
|---|---|
| **Tipo** | Planning / Backend Contract |
| **Prioridad** | Alta ★ CRITICAL |
| **Status** | In Progress — ST-01 ✅, ST-02–08 pendientes |
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

#### Dominio 2 — Game Services (7 endpoints)

| # | Método | Path | Auth | Descripción | Monday task |
|---|---|---|---|---|---|
| 7 | `GET` | `/progress` | 🔒 JWT | Devuelve el progreso del usuario: `highest_unlocked_level`, `total_stars` | Game-001 |
| 8 | `POST` | `/progress/level-complete` | 🔒 JWT | Registra nivel completado, valida score server-side, desbloquea siguiente nivel | Game-001 |
| 9 | `GET` | `/lives` | 🔒 JWT | Devuelve vidas actuales + timestamp de próxima regeneración | Game-002 |
| 10 | `POST` | `/lives/spend` | 🔒 JWT | Decremento server-authoritative de vidas (safe — no puede ir a negativo) | Game-002 |
| 11 | `POST` | `/lives/grant` | 🔒 JWT | Otorga vidas al usuario — fuente: `iap` \| `rewarded_ad_ssv` \| `promo` | Game-003 |
| 12 | `GET` | `/store/catalog` | 🔒 JWT | Catálogo de productos resuelto server-side con precios y promociones activas | Game-004 |
| 13 | `POST` | `/profile/equip-skin` | 🔒 JWT | Equipa un skin — verifica entitlement antes de escribir en Firestore | Game-005 |

---

#### Dominio 3 — Payments (4 endpoints)

| # | Método | Path | Auth | Descripción | Monday task |
|---|---|---|---|---|---|
| 14 | `POST` | `/payments/android/verify` | 🔒 JWT | Verifica `purchaseToken` con Play Developer API → otorga entitlement → acknowledge/consume | PAY-001 |
| 15 | `POST` | `/payments/ios/verify` | 🔒 JWT | Verifica `transactionId` con App Store Server API (JWS chain) → otorga entitlement | PAY-001 |
| 16 | `POST` | `/payments/android/refund-notification` | 🔓 firmado (Play Pub/Sub) | Recibe notificación RTDN de refund/voided-purchase de Google Play | PAY-003 |
| 17 | `POST` | `/payments/ios/refund-notification` | 🔓 firmado (Apple ASSN v2 JWS) | Recibe notificación de refund de Apple App Store Server Notifications v2 | PAY-003 |

---

#### Dominio 4 — Infrastructure (2 endpoints)

| # | Método | Path | Auth | Descripción | Monday task |
|---|---|---|---|---|---|
| 18 | `GET` | `/health` | 🔓 público | Liveness probe — Cloud Run reinicia el contenedor si falla | INFRA-003 |
| 19 | `GET` | `/ready` | 🔓 público | Readiness probe — Cloud Run no envía tráfico hasta que devuelva 200 | INFRA-003 |

---

#### Resumen por dominio

| Dominio | Endpoints | Públicos | Requieren JWT |
|---|---|---|---|
| Auth | 6 | 3 | 2 + 1 (refresh token en body) |
| Game Services | 7 | 0 | 7 |
| Payments | 4 | 2 (firmados por store) | 2 |
| Infrastructure | 2 | 2 | 0 |
| **Total** | **19** | **7** | **11** |

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

### ST-04 — Payloads Game Services ⬜ Pending

*(Ver sección pendiente — se llenará en ST-04)*

---

### ST-05 — Payloads Payments ⬜ Pending

*(Ver sección pendiente — se llenará en ST-05)*

---

### ST-06 — Payloads Infrastructure ⬜ Pending

*(Ver sección pendiente — se llenará en ST-06)*

---

### ST-07 — Error taxonomy ⬜ Pending

*(Ver sección pendiente — se llenará en ST-07)*

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
