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

### ST-02 — JWT spec ⬜ Pending

*(Ver sección pendiente — se llenará en ST-02)*

---

### ST-03 — Payloads Auth ⬜ Pending

*(Ver sección pendiente — se llenará en ST-03)*

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
