# MotaMaze MVP — Implementation Tracker (Saul)

Seguimiento de todas las tareas asignadas a Saul Zavala Morin.
Ordenadas por workstream y dependencia de ejecución.

> Última actualización: 2026-06-19
> Fuente de verdad: Monday.com board "motamaze mvp - project plan"

---

## REST-001 — Client↔Backend REST API Contract ★ CRITICAL

**Monday ID:** 12272268104 | **RAG:** Amber | **Timeline:** 6/19–6/24/2026 | **Critical Path:** ★ CRITICAL

**Storytelling:** → [changelogs/REST-001-rest-api-contract.md](../changelogs/REST-001-rest-api-contract.md)

**Status:** 🔄 In Progress — ST-01–07 ✅, ST-08 🔴 Stuck (Juan marcó Stuck en Monday 2026-06-19, deadline 2026-06-24)

### Subtareas

| # | Subtarea | Status | Notas |
|---|---|---|---|
| ST-01 | Lista completa de endpoints por dominio (20 endpoints, 4 dominios) | ✅ Done 2026-06-17, actualizado 2026-06-18 | Auth(6), Game Services(8), Payments(4), Infra(2). POST /events/behavior agregado como #14 (DATA-002 ST-02) |
| ST-02 | JWT spec (claims, headers, TTLs, JWKS) | ✅ Done 2026-06-17 | RS256, 15 min access / 14 días refresh, JTI revocation, JWKS kid rotation |
| ST-03 | Payloads — Auth endpoints | ✅ Done 2026-06-17 | 6 endpoints: login, refresh, logout, delete account, pending poll, JWKS |
| ST-04 | Payloads — Game Services endpoints | ✅ Done 2026-06-17, actualizado 2026-06-18 | 8 endpoints: progress GET/POST, lives GET/spend/grant, store catalog, equip-skin, POST /events/behavior |
| ST-05 | Payloads — Payments endpoints | ✅ Done 2026-06-17 | 4 endpoints: android/verify, ios/verify (StoreKit 2), android/refund, ios/refund webhooks |
| ST-06 | Payloads — Infrastructure endpoints | ✅ Done 2026-06-17 | /health (liveness, no external checks) + /ready (readiness, Firestore ping) |
| ST-07 | Error taxonomy (formato estándar + catálogo de códigos) | ✅ Done 2026-06-17 | 10 HTTP codes, 27 error codes, guía de manejo para cliente Godot |
| ST-08 | Sign-off de Juan | 🔴 Stuck | Juan marcó Stuck en Monday 2026-06-19 — pendiente revisión del documento |

---

## INFRA-001 — GCP Base Infra: Firestore, BigQuery, Cloud Storage, Cloud IAM, Budget Alerts

**Monday ID:** 12272254517 | **RAG:** Blue (was), Amber (post-audit) | **Critical Path:** No

**Storytelling:** → [changelogs/INFRA-001-gcp-base-infra.md](../changelogs/INFRA-001-gcp-base-infra.md)
**Logic doc:** → [logic/gcp-infrastructure.md](../logic/gcp-infrastructure.md)

### Subtareas

| # | Subtarea | Status | Dependencias | Prioridad |
|---|---|---|---|---|
| ST-01 | Proyecto GCP `motamaze` creado (ID: motamaze, Num: 542009654415) | ✅ Done | — | — |
| ST-02 | Firestore Native `(default)` en región `nam5` | ✅ Done | — | — |
| ST-03 | APIs habilitadas (BigQuery, Firestore, Storage, PubSub, Monitoring, Logging, Firebase) | ✅ Done | — | — |
| ST-04 | Service accounts creados (`game-api-backend`, `firebase-adminsdk-fbsvc`) | ✅ Done | — | — |
| ST-05 | `serviceAccountTokenCreator` asignado a Juan + Saul (ADC impersonation chain) | ✅ Done | ST-04 | — |
| ST-06 | Habilitar Billing en proyecto `motamaze` | ✅ Done | — | — |
| ST-07 | Fix IAM roles `game-api-backend` (5 roles asignados, deleted bindings eliminados) | ✅ Done | ST-06 | — |
| ST-08 | Crear BigQuery dataset `motamaze_analytics` (región US) | ✅ Done | ST-03, ST-06 | — |
| ST-09 | Crear Cloud Storage buckets (`motamaze-builds` STANDARD, `motamaze-exports` NEARLINE) | ✅ Done | ST-03, ST-06 | — |
| ST-10 | Configurar Budget alert $50/mes — 50%/90%/100% thresholds | ✅ Done | ST-06 | — |

**Verificación de cierre (2026-06-16):** ✅ Firestore Native (nam5) ✅ IAM 5 roles sin `deleted:` ✅ BQ dataset `motamaze_analytics` ✅ Buckets `motamaze-builds` + `motamaze-exports` ✅ Billing `01A127-C8B7E6-B6DEE7` ✅ Budget `f888196a` $50/mes.

---

## INFRA-002 — Environment & Secrets Design Sign-off (dev/staging/prod topology)

**Monday ID:** 12272268105 | **RAG:** Green | **Timeline:** 6/18/2026 | **Critical Path:** No

**Storytelling:** → [changelogs/INFRA-002-env-secrets-design.md](../changelogs/INFRA-002-env-secrets-design.md)

**Status:** ✅ Done 2026-06-17 — ST-01–08 completos, todos los sign-offs y criterios de aceptación cerrados

### Subtareas

| # | Subtarea | Status | Notas |
|---|---|---|---|
| ST-01 | Redactar documento de diseño (topología, naming, secrets, env vars, tabla de recursos) | ✅ Done 2026-06-17 | 5 decisiones documentadas: proyectos, naming, inventario, env vars, recursos por entorno |
| ST-02 | Sign-off Saul ✍️ | ✅ Done 2026-06-17 | Aprobado sin cambios |
| ST-03 | Sign-off Juan ✍️ | ✅ Done 2026-06-17 | Aprobado sin cambios |
| ST-04 | Topología de proyectos GCP documentada y justificada | ✅ Done 2026-06-17 | Opción B — 3 proyectos separados: `motamaze-dev`, `motamaze-staging`, `motamaze` (prod). JWT TTL corregido: 900s access / 1209600s refresh (alineado con REST-001). |
| ST-05 | Naming convention de Secret Manager definida | ✅ Done 2026-06-17 | Sin sufijo de env, formato `{componente}-{descripcion-kebab}`, versioning via `latest`. |
| ST-06 | Inventario completo de secrets por categoría | ✅ Done 2026-06-17 | 5 secrets en SM + 7 vars planas en Cloud Run. `.env` y `credentials.json` descartados. |
| ST-07 | Lista de env vars de FastAPI — SM vs. variable plana | ✅ Done 2026-06-17 | 13 vars planas con valores dev/staging/prod + 4 confidenciales leídas de SM en runtime. |
| ST-08 | Tabla de recursos GCP por entorno (nombres exactos) | ✅ Done 2026-06-17 | 11 recursos × 3 entornos documentados: Cloud Run, Firestore, BQ, Storage, SA, Artifact Registry, budgets. |

---

## INFRA-003 — FastAPI Scaffold en Cloud Run

**Monday ID:** 12272254518 | **RAG:** Amber | **Timeline:** 6/25–6/26/2026 | **Critical Path:** No

**Storytelling:** → [changelogs/INFRA-003-fastapi-scaffold-cloud-run.md](../changelogs/INFRA-003-fastapi-scaffold-cloud-run.md)

**Status:** 🔄 In Progress — ST-01 en ejecución 2026-06-17, ST-02–06 bloqueados en REST API contract (vence 2026-06-24)

### Subtareas

| # | Subtarea | Status | Dependencias |
|---|---|---|---|
| ST-01 | Habilitar `run.googleapis.com` en proyecto `motamaze` | ✅ Done 2026-06-17 | INFRA-001 billing ✅ |
| ST-02 | Crear repo backend (FastAPI, Dockerfile, pyproject.toml) | ⬜ Pending | REST API contract |
| ST-03 | Implementar health check endpoint `/health` | ⬜ Pending | ST-02 |
| ST-04 | Configurar Cloud Run service (max-instances=10, us-central1, SA game-api-backend) | ⬜ Pending | ST-01, ST-02 |
| ST-05 | Verificar ADC en Cloud Run (roles IAM del SA) | ⬜ Pending | ST-04 |
| ST-06 | Smoke test: `curl https://<cloud-run-url>/health` → 200 OK | ⬜ Pending | ST-05 |

---

## INFRA-004 — RS256 Keypair en Secret Manager + JWKS endpoint

**Monday ID:** 12272254519 | **RAG:** Gray | **Timeline:** 6/29/2026 | **Critical Path:** No

**Status:** 🔄 In Progress — ST-01 ✅, ST-02 ✅, ST-03–05 pendientes INFRA-003

**Storytelling:** → [changelogs/INFRA-004-rs256-keypair-secret-manager.md](../changelogs/INFRA-004-rs256-keypair-secret-manager.md)

### Subtareas

| # | Subtarea (Monday) | Status | Notas |
|---|---|---|---|
| ST-01 | Generate the RS256 signing keypair | ✅ Done 2026-06-19 | RSA 2048-bit, OpenSSL 3.5.5, PKCS#8 — `secretmanager.googleapis.com` habilitada en `motamaze` |
| ST-02 | Store it in Secret Manager | ✅ Done 2026-06-19 | Secret ID: `jwt-private-key`, version 1 enabled, proyecto `motamaze` (prod). Archivos locales eliminados inmediatamente. SA `game-api-backend` ya tiene `secretAccessor` (INFRA-001). |
| ST-03 | Implement the `/.well-known/jwks.json` endpoint | ⬜ Pending INFRA-003 | Extrae public key de la private en runtime → JWK con `kid=motamaze-2026-v1` |
| ST-04 | Wire signing to the private key | ⬜ Pending INFRA-003 | FastAPI lee `jwt-private-key` desde SM en `create_access_token()` + cache TTL=300s |
| ST-05 | Document the key-rotation path | ⬜ Pending | Proceso en changelog INFRA-004. Ejecutar formalmente antes de soft launch. |

---

## INFRA-005 — Firestore Schema + Security Rules (Production mode)

**Monday ID:** 12272254520 | **RAG:** Gray | **Timeline:** 6/29–6/30/2026 | **Critical Path:** No

**Status:** 🔄 In Progress — ST-01 ✅, ST-02 ✅, ST-03 ⬜ pendiente INFRA-003, ST-04 ✅

**Storytelling:** → [changelogs/INFRA-005-firestore-schema-security-rules.md](../changelogs/INFRA-005-firestore-schema-security-rules.md)

**Data model:** → [docs/DATA_MODEL.md](DATA_MODEL.md)

### Subtareas

| # | Subtarea (Monday) | Status | Notas |
|---|---|---|---|
| ST-01 | Define users/sessions/revoked_jtis collections (fields + indexes) | ✅ Done 2026-06-19 | 6 colecciones: `users`, `sessions`, `revoked_jtis`, `progress`, `lives`, `entitlements`. Sin índices compuestos para MVP. |
| ST-02 | Write production-mode security rules (deny-by-default) | ✅ Done 2026-06-19 | `firestore.rules` deploy vía Firebase Rules REST API. Ruleset `523e539f` activo en `motamaze`. |
| ST-03 | Test the rules | ⬜ Pending INFRA-003 | Tests con Firebase emulator — escritura directa debe fallar con PERMISSION_DENIED |
| ST-04 | Document the schema in docs/DATA_MODEL.md | ✅ Done 2026-06-19 | → [docs/DATA_MODEL.md](DATA_MODEL.md) |

---

## INFRA-006 — Dev/Staging/Prod Environments + Terraform Module

**Monday ID:** 12272254521 | **RAG:** Gray | **Timeline:** 6/27–6/28/2026 | **Critical Path:** No

**Status:** 🔄 In Progress — ST-01 ✅ proyectos + state bucket, ST-02 ✅ módulo Terraform, ST-03 ✅ remote state, ST-04 ⬜ apply pendiente billing + INFRA-003

**Storytelling:** → [changelogs/INFRA-006-dev-staging-prod-terraform.md](../changelogs/INFRA-006-dev-staging-prod-terraform.md)

### Subtareas

| # | Subtarea (Monday) | Status | Notas |
|---|---|---|---|
| ST-01 | Create dev/staging/prod GCP projects | ✅ Parcial 2026-06-19 | `motamaze-dev` (1072330724928) y `motamaze-staging` (682669860502) creados. Billing pendiente Juan (billing.resourceAssociations.create requerido) |
| ST-02 | Write a reusable Terraform module | ✅ Done 2026-06-19 | `terraform/modules/motamaze-env/` — APIs, SA, IAM, Firestore, BQ (8 tablas), GCS, SM (5 secrets), Cloud Run (count condicional) |
| ST-03 | Configure remote state management | ✅ Done 2026-06-19 | Bucket `motamaze-terraform-state` (US, versioning on). Prefijos: dev/, staging/, prod/ |
| ST-04 | Apply and verify on all three environments | ⬜ Pending | dev/staging: bloqueado por billing. prod: requiere `terraform import` de 15+ recursos existentes (INFRA-001). Cloud Run requiere INFRA-003. |

---

## CI-001 — CI/CD: GitHub Actions + Artifact Registry

**Monday ID:** 12272268267 | **RAG:** Gray | **Timeline:** 7/8–7/9/2026 | **Critical Path:** No

**Status:** ⬜ Not Started — depende de INFRA-006

---

## MON-001 — Cloud Monitoring / Alerts / Pub/Sub Kill Switch

**Monday ID:** 12272268268 | **RAG:** Gray | **Timeline:** 7/1–7/2/2026 | **Critical Path:** No

**Status:** ⬜ Not Started — depende de INFRA-003

---

## DATA-001 — BigQuery Analytics Tables

**Monday ID:** 12272094753 | **RAG:** Amber | **Timeline:** 6/18–6/19/2026 | **Critical Path:** No

**Storytelling:** → [changelogs/DATA-001-bigquery-analytics-tables.md](../changelogs/DATA-001-bigquery-analytics-tables.md)

**Status:** 🔄 In Progress

### Subtareas

| # | Subtarea | Status | Notas |
|---|---|---|---|
| ST-01 | Crear tabla `login_events` | ✅ Done | partition: event_date / cluster: user_id |
| ST-02 | Crear tabla `session_durations` | ✅ Done 2026-06-17 | renombrada de `session_events` |
| ST-03 | Crear tabla `player_behavior` | ✅ Done 2026-06-17 | renombrada de `behavior_events` |
| ST-04 | Crear tabla `purchase_events` | ✅ Done | partition: event_date / cluster: user_id |
| ST-05 | Crear tabla `ad_impressions` | ✅ Done 2026-06-17 | renombrada de `ad_events` |
| ST-06 | Crear tabla `entitlement_grants` | ✅ Done 2026-06-17 | renombrada de `entitlement_events` |
| ST-07 | Crear tabla `account_deletions` | ✅ Done 2026-06-17 | renombrada de `deletion_queue` |
| ST-08 | Crear tabla `admob_daily_report` | ✅ Done 2026-06-17 | nueva — partition: report_date / cluster: ad_unit_id + country |
| ST-09 | Verificar 8 tablas en `motamaze_analytics` | ✅ Done 2026-06-17 | 8 tablas confirmadas |

---

## DATA-002 — Firestore → BigQuery Async Streaming

**Monday ID:** 12272094755 | **RAG:** Amber | **Timeline:** 6/22–6/23/2026

**Storytelling:** → [changelogs/DATA-002-firestore-bigquery-streaming.md](../changelogs/DATA-002-firestore-bigquery-streaming.md)

**Status:** 🔄 In Progress — ST-01 ✅ diseño, ST-02 ✅ endpoint mapping reconciliado, ST-03–12 pendientes de INFRA-003

### Subtareas

| # | Subtarea | Status | Dependencias | Notas |
|---|---|---|---|---|
| ST-01 | Diseño de arquitectura: BackgroundTasks + BQ Streaming Insert | ✅ Done 2026-06-17 | DATA-001 ✅ | Descartadas Pub/Sub y Firebase Extension para MVP |
| ST-02 | Alinear endpoint → tabla mapping con REST-001 | ✅ Done 2026-06-18 | REST-001 ✅ | 3 gaps resueltos: sessions→auth/login+logout, player_behavior→nuevo /events/behavior (REST-001 #14), entitlement_grants→operaciones internas |
| ST-03 | Implementar `app/services/bq_streaming.py` con retry logic | ⬜ Pending | INFRA-003 repo | Código pre-diseñado en changelog |
| ST-04 | Definir dedup keys y backfill-safety strategy | ⬜ Pending | ST-03 | |
| ST-05 | Integrar `POST /auth/login` → `login_events` + `session_durations` (session_start) | ⬜ Pending | ST-03, INFRA-003 | |
| ST-06 | Integrar `POST /auth/logout` → `session_durations` (session_end + duration_secs) | ⬜ Pending | ST-03, INFRA-003 | |
| ST-07 | Integrar `POST /events/behavior` → `player_behavior` (batch) | ⬜ Pending | ST-03, INFRA-003 | |
| ST-08 | Integrar `POST /payments/*/verify` → `purchase_events` + `entitlement_grants` | ⬜ Pending | ST-03, INFRA-003 | Android + iOS |
| ST-09 | Integrar `POST /lives/grant` → `ad_impressions` (SSV) + `entitlement_grants` | ⬜ Pending | ST-03, INFRA-003 | |
| ST-10 | Integrar `DELETE /auth/account` → `account_deletions` | ⬜ Pending | ST-03, INFRA-003 | |
| ST-11 | Integrar `POST /progress/level-complete` → `player_behavior` (event: level_complete) | ⬜ Pending | ST-03, INFRA-003 | |
| ST-12 | Monitor y confirmar que datos llegan a BigQuery | ⬜ Pending | ST-05–11, INFRA-003 deployed | Query de verificación por las 8 tablas |

---

## EXT-001 — Enable Google Play Developer API (24h activation)

**Monday ID:** 12272254776 | **RAG:** Amber | **Timeline:** 6/15/2026 (+1 día retraso) | **Critical Path:** No

**Storytelling:** → [changelogs/EXT-001-google-play-developer-api.md](../changelogs/EXT-001-google-play-developer-api.md)

**Status:** 🔄 In Progress

### Subtareas

| # | Subtarea | Status | Dependencias | Notas |
|---|---|---|---|---|
| ST-01 | Habilitar `androidpublisher.googleapis.com` en proyecto `motamaze` | ✅ Done | INFRA-001 ✅ | `Google Play Android Developer API` ENABLED |
| ST-02 | Crear cuenta Google Play Developer (org: Ingenious Crucible Studios, $25 USD) + definir package name | ✅ Done 2026-06-17 | — | Org: Ingenious Crucible Studios, Account ID: `5099504302304988454`, package: `com.ingeniouscruciblestudios.motamaze` |
| ST-03 | Vincular proyecto GCP `motamaze` a Play Console (Settings → API access) | 🔴 Bloqueado | ST-02 | API access no aparece hasta tener app registrada; "Create app" deshabilitado por verificación de cuenta pendiente |
| ST-04 | Invitar SA `game-api-backend` a Play Console — permiso "Manage orders and subscriptions" | 🔴 Bloqueado | ST-03 | **Inicia el countdown 24h** — espera ST-03 |
| ST-05 | Esperar 24h de propagación de permisos | ⏳ Pending | ST-04 | Registrar timestamp de ST-04 |
| ST-06 | Verificar llamada de prueba a Play Developer API (esperado: 404/400, no 401/403) | ⏳ Pending | ST-05 | Requiere package name y ADC |

---

## EXT-002 — AdMob Account + Ad Units

**Monday ID:** 12272254782 | **RAG:** Amber | **Timeline:** 6/16–6/17/2026 | **Critical Path:** No

**Storytelling:** → [changelogs/EXT-002-admob-account-ad-units.md](../changelogs/EXT-002-admob-account-ad-units.md)
**Logic doc:** → [logic/admob-config.md](../logic/admob-config.md)

**Status:** 🔄 In Progress

### Subtareas

| # | Subtarea | Status | Owner | Notas |
|---|---|---|---|---|
| ST-01 | Crear cuenta AdMob bajo cuenta de la organización ICS | ✅ Done 2026-06-17 | Publisher ID: `pub-9121176819960949` |
| ST-02 | Agregar app MotaMaze a AdMob (Android, manual) | ✅ Done 2026-06-17 | App ID: `ca-app-pub-9121176819960949~9751218738` |
| ST-03 | Crear ad unit Rewarded Video (`motamaze_rewarded_lives`) con SSV activado | ✅ Done 2026-06-17 | `ca-app-pub-9121176819960949/9093914042` |
| ST-04 | Crear ad unit Interstitial (`motamaze_interstitial_between_levels`) | ✅ Done 2026-06-17 | `ca-app-pub-9121176819960949/4963097342` |
| ST-05 | Crear ad unit Banner (`motamaze_banner_menu`) — Adaptive Banner | ✅ Done 2026-06-17 | `ca-app-pub-9121176819960949/3593004496` |
| ST-06 | Documentar App ID + 3 production ad unit IDs en `logic/admob-config.md` | ✅ Done 2026-06-17 | IDs documentados y en GitHub |
| ST-07 | Vincular AdMob a Firebase proyecto `motamaze` | ✅ Done 2026-06-17 | Package: `com.ingeniouscruciblestudios.motamaze`, `google-services.json` descargado |

---

## Orden de ejecución global (Saul) — por dependencia + prioridad

```
HOY (6/16):
  1. EXT-001 — Google Play Developer API (activar YA — 24h lag)
  2. INFRA-001 ST-06 — Habilitar Billing
  3. INFRA-001 ST-07 — Fix IAM roles game-api-backend
  4. INFRA-001 ST-08 — Crear BQ dataset
  5. INFRA-001 ST-09 — Crear Storage buckets
  6. INFRA-001 ST-10 — Budget alerts

ESTA SEMANA (6/17–6/18):
  7. EXT-002 — AdMob account
  8. DATA-001 — BigQuery analytics tables (esquema completo)
  9. INFRA-002 — Env & secrets design sign-off (con Juan)

SEMANA 6/19–6/24:
  10. REST API contract (con Juan) — ★ CRITICAL
  11. DATA-002 — Firestore → BQ streaming

SEMANA 6/25–6/30:
  12. INFRA-003 — FastAPI Cloud Run scaffold
  13. INFRA-005 — Firestore schema + Security Rules
  14. INFRA-004 — RS256 + JWKS endpoint
  15. INFRA-006 — Env split + Terraform
```
