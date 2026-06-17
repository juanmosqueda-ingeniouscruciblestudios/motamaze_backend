# MotaMaze MVP — Implementation Tracker (Saul)

Seguimiento de todas las tareas asignadas a Saul Zavala Morin.
Ordenadas por workstream y dependencia de ejecución.

> Última actualización: 2026-06-16
> Fuente de verdad: Monday.com board "motamaze mvp - project plan"

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

**Monday ID:** 12272268105 | **RAG:** Amber | **Timeline:** 6/18/2026 | **Critical Path:** No

**Storytelling:** → [changelogs/INFRA-002-env-secrets-design.md](../changelogs/INFRA-002-env-secrets-design.md)

**Status:** ✅ Done 2026-06-17 — Saul ✅ + Juan ✅ firmados

### Subtareas

| # | Subtarea | Status | Notas |
|---|---|---|---|
| ST-01 | Topología: 3 proyectos GCP separados (`motamaze-dev`, `motamaze-staging`, `motamaze`) | ✅ Decidido | Documento de diseño redactado |
| ST-02 | Naming convention secrets: sin sufijo env (el proyecto aísla), formato `{componente}-{desc-kebab}` | ✅ Decidido | |
| ST-03 | Inventario de 5 secrets por proyecto + separación Secret Manager vs. env vars planas | ✅ Decidido | |
| ST-04 | Tabla de 13 env vars de FastAPI por entorno (dev/staging/prod) | ✅ Decidido | |
| ST-05 | Tabla de recursos GCP por entorno (Cloud Run, Firestore, BQ, Storage, SA, Budgets) | ✅ Decidido | |
| ST-06 | Sign-off Saul ✍️ | ✅ Done 2026-06-17 | Aprobado sin cambios |
| ST-07 | Sign-off Juan ✍️ | ✅ Done 2026-06-17 | Aprobado sin cambios — commit en GitHub |

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

**Status:** ⬜ Not Started

**Storytelling:** pendiente

### Subtareas

| # | Subtarea | Status | Dependencias |
|---|---|---|---|
| ST-01 | Habilitar `secretmanager.googleapis.com` | ❌ Pending | INFRA-001 billing |
| ST-02 | Generar keypair RS256 (`openssl genrsa -out private.pem 2048` + extract public) | ❌ Pending | — |
| ST-03 | Subir `private.pem` a Secret Manager como `motamaze-jwt-private-key` | ❌ Pending | ST-01, ST-02 |
| ST-04 | Implementar endpoint `GET /.well-known/jwks.json` en FastAPI | ❌ Pending | INFRA-003, ST-02 |
| ST-05 | Verificar: `curl https://<url>/.well-known/jwks.json` retorna JWK con `kid`, `kty=RSA`, `use=sig` | ❌ Pending | ST-04 |

---

## INFRA-005 — Firestore Schema + Security Rules (Production mode)

**Monday ID:** 12272254520 | **RAG:** Gray | **Timeline:** 6/29–6/30/2026 | **Critical Path:** No

**Status:** ⬜ Not Started

**Storytelling:** pendiente

### Subtareas

| # | Subtarea | Status | Dependencias |
|---|---|---|---|
| ST-01 | Definir colecciones: `users`, `sessions`, `revoked_jtis`, `progress`, `lives`, `entitlements` | ❌ Pending | REST API contract |
| ST-02 | Crear Firebase Security Rules en modo producción (deny-all default) | ❌ Pending | ST-01 |
| ST-03 | Escribir rules que permiten solo al backend SA leer/escribir (no client directo) | ❌ Pending | ST-02 |
| ST-04 | Deploy rules via `firebase deploy --only firestore:rules` | ❌ Pending | ST-03 |
| ST-05 | Test: intento de escritura directa desde cliente falla con PERMISSION_DENIED | ❌ Pending | ST-04 |

---

## INFRA-006 — Dev/Staging/Prod Environments + Terraform Module

**Monday ID:** 12272254521 | **RAG:** Gray | **Timeline:** 6/27–6/28/2026 | **Critical Path:** No

**Status:** ⬜ Not Started

**Storytelling:** pendiente

### Subtareas

| # | Subtarea | Status | Dependencias |
|---|---|---|---|
| ST-01 | Decidir estrategia env split (depende de INFRA-002 sign-off) | ❌ Pending | INFRA-002 ST-04 |
| ST-02 | Crear módulo Terraform para infra base replicable por env | ❌ Pending | INFRA-003 completo |
| ST-03 | Aplicar Terraform en `dev` | ❌ Pending | ST-02 |
| ST-04 | Aplicar Terraform en `staging` | ❌ Pending | ST-03 |
| ST-05 | Variables de entorno separadas por env en Secret Manager | ❌ Pending | ST-02 |

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
| ST-02 | Crear tabla `session_events` | ✅ Done | partition: event_date / cluster: user_id |
| ST-03 | Crear tabla `behavior_events` | ✅ Done | partition: event_date / cluster: user_id + event_name |
| ST-04 | Crear tabla `purchase_events` | ✅ Done | partition: event_date / cluster: user_id |
| ST-05 | Crear tabla `ad_events` | ✅ Done | partition: event_date / cluster: user_id + ad_type |
| ST-06 | Crear tabla `entitlement_events` | ✅ Done | partition: event_date / cluster: user_id |
| ST-07 | Crear tabla `deletion_queue` | ✅ Done | partition: request_date / cluster: user_id + status |
| ST-08 | Verificar 7 tablas en `motamaze_analytics` | ✅ Done | totalItems: 7 confirmado |

---

## DATA-002 — Firestore → BigQuery Async Streaming

**Monday ID:** 12272094755 | **RAG:** Amber | **Timeline:** 6/22–6/23/2026

**Storytelling:** → [changelogs/DATA-002-firestore-bigquery-streaming.md](../changelogs/DATA-002-firestore-bigquery-streaming.md)

**Status:** 🔄 In Progress — ST-01 diseño ✅, ST-02–09 pendientes de INFRA-003

### Subtareas

| # | Subtarea | Status | Dependencias | Notas |
|---|---|---|---|---|
| ST-01 | Diseño de arquitectura: BackgroundTasks + BQ Streaming Insert | ✅ Decidido 2026-06-17 | DATA-001 ✅ | Descartadas Pub/Sub y Firebase Extension para MVP |
| ST-02 | Implementar `app/services/bq_streaming.py` con retry logic | ⬜ Pending | INFRA-003 (repo FastAPI) | Código diseñado en changelog — listo para integrar |
| ST-03 | Integrar background_task en `POST /auth/login` → `login_events` | ⬜ Pending | ST-02 | |
| ST-04 | Integrar background_task en `POST /sessions/*` → `session_events` | ⬜ Pending | ST-02 | |
| ST-05 | Integrar background_task en `POST /events/behavior` → `behavior_events` | ⬜ Pending | ST-02 | |
| ST-06 | Integrar background_task en `POST /payments/android/verify` → `purchase_events` | ⬜ Pending | ST-02 | |
| ST-07 | Integrar background_task en SSV callback + `/entitlements/grant` | ⬜ Pending | ST-02 | |
| ST-08 | Integrar background_task en `DELETE /auth/account` → `deletion_queue` | ⬜ Pending | ST-02 | |
| ST-09 | Test de integración end-to-end: evento → tabla BQ verificada | ⬜ Pending | ST-03–08, INFRA-003 desplegado | |

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
