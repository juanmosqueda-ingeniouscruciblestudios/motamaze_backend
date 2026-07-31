# MotaMaze MVP — Implementation Tracker (Saul)

Seguimiento de todas las tareas asignadas a Saul Zavala Morin.
Ordenadas por workstream y dependencia de ejecución.

> Última actualización: 2026-07-31
> Fuente de verdad: Monday.com board "motamaze mvp - project plan"
>
> **Convención de numeración (2026-07-28):** los subitems de Monday llevan el prefijo `ST-##:` en su
> nombre, de modo que el número existe en el tablero y no solo aquí. Al agregar una subtarea a mitad
> de un ticket, se le asigna el número que le corresponde por orden de ejecución y **se renumeran las
> posteriores en ambos lados** — tablero y este archivo.

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

**Status:** 🔄 In Progress — ST-01 ✅ Dockerfile + workflow build job, ST-02–05 pendientes INFRA-003

**Storytelling:** → [changelogs/CI-001-cicd-github-actions.md](../changelogs/CI-001-cicd-github-actions.md)

### Subtareas

| # | Subtarea (Monday) | Status | Notas |
|---|---|---|---|
| ST-01 | Build the GitHub Actions image build | ✅ Done 2026-06-19 | Dockerfile (non-root, layer cache, single worker) + workflow YAML con build job. Archivos en `ci-templates/`. Layer cache via `type=gha`. Commit `NEXT`. |
| ST-02 | Create AR repo + configure Workload Identity Federation | ⬜ Pending INFRA-003 | AR repo `backend` en `motamaze`. WIF pool + provider + SA `github-actions`. Comandos documentados en changelog. |
| ST-03 | Push to Artifact Registry | ⬜ Pending ST-02 | Cubierto en workflow — push activo cuando `event_name == push`. |
| ST-04 | Implement dev→staging→prod promotion | ⬜ Pending ST-02 + billing | Cubierto en workflow — jobs `deploy-staging/prod` con `environment:` GitHub y aprobación manual. Mismo digest en los 3 envs. |
| ST-05 | Trigger deploy on merge and verify pipeline green | ⬜ Pending INFRA-003 | First real push al backend repo. |

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

## T-124 — HTTPS App Links (Android) / Universal Links (iOS) para share URL deep links (`/motamaze/s/*`)

**Monday ID:** 12272121946 | **RAG:** Gray | **Timeline:** 8/3–8/4/2026 | **Critical Path:** No

**Storytelling:** → [changelogs/T-124-app-links-universal-links.md](../changelogs/T-124-app-links-universal-links.md)
**Logic doc:** → [logic/deep-links.md](../logic/deep-links.md)

**Status:** 🔄 In Progress — ST-02 y ST-03 ✅. El resto bloqueado por accesos (repo del sitio web +
Firebase Hosting + DNS en Wix, solicitados a Juan por correo 2026-07-27) o por T-IOS-3.

> **Cambio de alcance 2026-06-22 + cambio de dominio 2026-07-27.** No habrá dominio `motamaze.com`;
> el juego vive en `https://ingeniouscruciblestudios.com/motamaze/`. Las 3 subtareas originales de
> Monday (2026-06-17) quedaron obsoletas y fueron reemplazadas — una de ellas duplicaba T-442 y otra
> asumía un deep link para el callback de OAuth, que en realidad usa polling RFC 8252 (REST-001).

### Subtareas

| # | Subtarea | Status | Dependencias | Notas |
|---|---|---|---|---|
| ST-01 | Confirmar hosting y control de `ingeniouscruciblestudios.com` + capacidad de escribir en `/.well-known/` del root | 🔄 In Progress | — | Hosting confirmado: Firebase Hosting. Ambos archivos ya se sirven con `200` + `application/json`, el de iOS sin extensión. Falta el acceso de publicación |
| ST-02 | Definir host canónico (apex vs `www`) y ruta final de share links | ✅ Done 2026-07-27 | — | Apex, sin `www`. El cert TLS declara SAN solo para el apex; `www` sigue en Wix y responde `400` en `/.well-known/` |
| ST-03 | Obtener SHA-256 de la app signing key desde Play Console | ✅ Done 2026-07-27 | EXT-001 ST-02 ✅ | `9A:08:7E:...:D2:38:58` (32 bytes). App signing key, no upload key. Vía URL `/keymanagement` — la ruta por menú cambió (App Integrity → "Protected with Play") |
| ST-04 | Obtener Team ID de Apple | 🔴 Stuck | **T-IOS-3** | No es problema de acceso: la inscripción al Apple Developer Program está sin iniciar, el Team ID no existe |
| ST-05 | Generar y publicar `assetlinks.json` en el root + validar con Digital Asset Links API | ⏳ Pending | ST-03 ✅, acceso repo/Firebase | Contenido definitivo ya armado en `logic/deep-links.md`. Reemplaza el scaffold `[]` actual |
| ST-06 | Generar y publicar `apple-app-site-association` en el root + validar | ⏳ Pending | ST-04 🔴, acceso repo/Firebase | Requiere `appID` = `TeamID.bundleID`. Scaffold vacío ya desplegado y sirviéndose correctamente |
| ST-07 | `intent-filter` con `autoVerify` + `pathPrefix=/motamaze/` en `AndroidManifest.xml` | ⏳ Pending | ST-05 | **Owner: Juan** (cliente Godot). `assetlinks.json` no acota rutas — sin esto la app interceptaría todo el dominio. Sin `autoVerify` Android ni consulta el archivo |
| ST-08 | Repuntar registro DNS de `www` de Wix hacia Firebase Hosting + verificar propagación | ⏳ Pending | Acceso DNS (Wix) | Propagación hasta 24–48 h. Operación más delicada: toca el sitio corporativo en producción |
| ST-09 | Agregar `www` como dominio en Firebase Hosting + redirect `301` al apex en `firebase.json` | ⏳ Pending | ST-08 | Provisiona el cert TLS para `www`, que hoy no está cubierto |
| ST-10 | Actualizar `share_base_url` y referencias a `motamaze.com` en código, config y Terraform + tests | ✅ Done 2026-07-27 | — | `share_base_url` → `https://ingeniouscruciblestudios.com/motamaze`. +2 tests (literal del dominio y slash final; los existentes se autorreferenciaban al setting y no detectaban un dominio incorrecto). Suite: 202 passed, 8 skipped. Terraform sin cambios: solo contiene `JWT_ISSUER`/`JWKS_URL` (`api.motamaze.com`), fuera de alcance |
| ST-11 | Documentación (changelog T-124, `logic/deep-links.md`, corregir arquitectura que asume `motamaze.com`) | 🔄 In Progress | — | `logic/deep-links.md` ✅ y changelog T-124 ✅ (2026-07-27). Corrección del doc de arquitectura bloqueada: sin permiso de push en `motamaze-project` (403) |

---

## T-243 — Backend `/profile/equip-skin` (entitlement-checked) + persistencia de `equipped_skin`

**Monday ID:** 12272254774 | **RAG:** Gray | **Timeline:** 8/5/2026 | **Critical Path:** No

**Storytelling:** → [changelogs/T-243-equip-skin.md](../changelogs/T-243-equip-skin.md)

**Status:** ✅ Done — ST-01–05 ✅ (2026-07-28)

### Subtareas

| # | Subtarea | Status | Dependencias | Notas |
|---|---|---|---|---|
| ST-01 | `POST /profile/equip-skin` — validación de catálogo (400) + ownership (403) + persistencia | ✅ Done 2026-07-28 | T-240 ✅ | Commit `0daada0`. Reusa `store_service.owned_product_ids()`; `skin_default` ≡ `null` y salta ambas validaciones |
| ST-02 | Limpiar `users/{uid}.equipped_skin` en `revoke_entitlement` al reembolsar | ✅ Done 2026-07-28 | ST-03 | **Absorbida en ST-03** — mismo bloque de código, separarlas obligaba a tocar dos veces la misma función. Commit `a2e30b6` |
| ST-03 | Modelar origen de adquisición de skins (`purchase`/`earned`/`free`) + revocación consciente del origen | ✅ Done 2026-07-28 | — | Commit `a2e30b6`. Surge de detectar que Season Pass y leaderboard otorgan skins que nunca son productos vendibles |
| ST-04 | Tests completos | ✅ Done 2026-07-28 | ST-03 ✅ | Commit `6bdd508`. Descubrió que la aserción de pagos era agnóstica a la forma por accidente (`in` verifica claves en lista y mapa) y que `store_service` solo probaba la forma legacy |
| ST-05 | Documentación (changelog T-243, alinear REST-001 con `skin_default` = `null`) | ✅ Done 2026-07-28 | — | `DATA_MODEL.md` se actualizó en ST-03 y `game.py` se limpió en ST-01 |

> **Bloqueo externo para prueba end-to-end:** `config/catalog` solo siembra `lives_pack_5` y `no_ads` —
> `skin_gold` y `skin_silver` están excluidos porque su precio sigue en TBD. Hasta que Juan confirme
> precios, el único `skin_id` aceptado en dev y prod es `skin_default`. No bloquea el backend, sí la
> prueba del cliente (T-242).

---

## T-311 — Tenjin SDK integration (client) + backend fraud filtering

**Monday ID:** 12272094807 | **RAG:** Gray | **Timeline:** 8/3–8/14/2026 (reprogramado 2026-07-28) | **Critical Path:** No

**Storytelling:** → [changelogs/T-311-tenjin-share-tracking-link.md](../changelogs/T-311-tenjin-share-tracking-link.md)

**Status:** 🔄 In Progress — ST-01–02 ✅. Ruta crítica en ST-03 (Juan)

### Subtareas

| # | Subtarea | Status | Owner | Notas |
|---|---|---|---|---|
| ST-01 | Backend: envolver `share_url` en tracking link de Tenjin con fallback a URL directa | ✅ Done 2026-07-21 | Saul | Decision L Opción A |
| ST-02 | Crear cuenta + app en dashboard de Tenjin | ✅ Done 2026-07-21 | Saul | |
| ST-03 | Godot: integrar SDK de Tenjin — install + revenue events | ⏳ Pending | **Juan** | **Bloqueante de toda la cadena** |
| ST-04 | Crear campaign + tracking link orgánico/referral | 🔴 Stuck | Saul | Soporte de Tenjin confirmó que el SDK debe ir primero — invierte la dependencia asumida |
| ST-05 | Godot: manejar `deeplink_url` al abrir la app | ⏳ Pending | **Juan** | Depende de ST-03 |
| ST-06 | Configurar fraud filtering en Tenjin | ⏳ Pending | Saul | Requiere campaign activa (ST-04) |
| ST-07 | Revisar Data Safety (Play Store) para el flujo de Tenjin | ⏳ Pending | Saul | Requiere el flujo de datos activo |

---

## T-IOS-3 — App Store Connect: Developer Program enrollment + API key ★ CRITICAL

**Monday ID:** 12566196505 | **RAG:** Gray | **Timeline:** sin fecha | **Critical Path:** ★ CRITICAL

**Status:** ⬜ Not Started — bloqueado en ST-01

> **Ticket de habilitación, no de construcción.** Bloquea 9 de los 13 tickets T-IOS más T-124 ST-04/ST-06.
> T-IOS-1 y T-IOS-9 están Done pero no pueden pasar a producción: `apple_app_apple_id` sigue en `None`
> y `apple_environment` en `Sandbox`.

### Subtareas

| # | Subtarea | Status | Owner | Notas |
|---|---|---|---|---|
| ST-01 | Confirmar si ICS tiene D-U-N-S; si no, solicitarlo a Dun & Bradstreet | ⏳ Pending | **Juan** | **GATE de todo el ticket.** Trámite de días a semanas, independiente de Apple. No mencionado en ningún repo antes del 2026-07-28 |
| ST-02 | Inscripción al Apple Developer Program como organización ($99/año) | ⏳ Pending | **Juan** | Requiere ST-01 |
| ST-03 | Invitar a Saul al equipo con acceso a Keys y App Store Connect | ⏳ Pending | **Juan** | Requiere ST-02 |
| ST-04 | Registrar App ID + capabilities (Associated Domains, Sign in with Apple, IAP) | ⏳ Pending | Saul | Alimenta T-IOS-11 y T-IOS-12 |
| ST-05 | Crear el registro del app en App Store Connect → `apple_app_apple_id` | ⏳ Pending | Saul | Desbloquea T-IOS-4, T-IOS-6, T-IOS-13 |
| ST-06 | Generar App Store Connect API key (Issuer ID + Key ID + `.p8`) + Secret Manager | ⏳ Pending | Saul | **El `.p8` se descarga una sola vez** (GOTCHA 15 / OA-10) |
| ST-07 | Documentar Team ID, Issuer ID y Key IDs en `logic/` + `.env.example` | ⏳ Pending | Saul | |
| ST-08 | Poblar `apple_app_apple_id` y evaluar `apple_environment` → Production | ⏳ Pending | Saul | Sandbox es correcto durante TestFlight |
| ST-09 | Registrar URL del webhook ASSN v2 en App Store Connect | ⏳ Pending | Saul | Follow-up de PAY-004. Registrar prod **y** sandbox |
| ST-10 | Implementar `AppStoreServerAPIClient` + polling de refund history | ⏳ Pending | Saul | Único ítem con código de aplicación. Diferido en PAY-004 |

> **La llave `.p8` de Sign in with Apple no se necesita** (decisión 2026-07-28): se eligió el Camino B
> para el borrado de cuenta — no guardar tokens de Apple e indicar al usuario que revoque en Ajustes.
> Ese pendiente de UI vive en T-IOS-14.

---

## T-447 — Achievement unlock tracking + season-points bonus

**Monday ID:** 12534452191 | **RAG:** Gray | **Critical Path:** No | **Started:** 2026-07-29

**Storytelling:** → [changelogs/T-447-achievements-season-points.md](../changelogs/T-447-achievements-season-points.md)
**Logic doc:** → [logic/achievements.md](../logic/achievements.md)

**Status:** ✅ Done (scope backend, Saul) — ST-01, ST-04–ST-12 ✅. ST-02/ST-03 (Godot, Juan) ⏳ Pending

### Subtareas

| # | Subtarea | Status | Owner | Notas |
|---|---|---|---|---|
| ST-01 | Definir contrato de datos por partida que exigen los guards + documentar en REST-001 | ✅ Done 2026-07-29 | Saul | `match_stats` opcional, 18 campos |
| ST-02 | Godot: enviar los campos nuevos de partida en `POST /progress/level-complete` | ⏳ Pending | **Juan** | Backend ya acepta el campo (opcional, no rompe clientes viejos) |
| ST-03 | Godot: agregar `level_id` al payload de `POST /lives/spend` | ⏳ Pending | **Juan** | Bloquea que `level_stats` tenga datos reales — backend ya acepta el campo |
| ST-04 | Definir y poblar la fuente del win rate por nivel (26/40 guards dependen de WR) | ✅ Done 2026-07-29 | Saul | `level_stats_service` + job `recalc-level-stats` |
| ST-05 | Seed de las 40 definiciones de achievements (`config/achievements`) + estado de unlock por jugador | ✅ Done 2026-07-29 | Saul | `scripts/seed_achievements.py` |
| ST-06 | Persistir stats por partida + agregados de temporada (rachas, hits, cobertura, comebacks, modos) | ✅ Done 2026-07-30 | Saul | `season_match_stats_service` |
| ST-07 | Motor de evaluación de guards + desbloqueo en `achievement_progress` | ✅ Done 2026-07-30 | Saul | `achievements_engine.py`, 40 predicados |
| ST-08 | Implementar fórmula `season_points` + integrar el término `achievement_bonus` | ✅ Done 2026-07-30 | Saul | No wired al leaderboard todavía — gap conocido |
| ST-09 | `GET /achievements` (desbloqueados + progreso + rarity) | ✅ Done 2026-07-30 | Saul | `achievements_catalog_service.py` |
| ST-10 | Job de rarity cada 24h (Cloud Scheduler + BigQuery) → `achievement_rarities` | ✅ Done 2026-07-30 | Saul | Cloud Scheduler real pendiente de crear en GCP (ticket aparte) |
| ST-11 | Tests completos (evaluación de guards, agregados de temporada, season_points, endpoint) | ✅ Done 2026-07-31 | Saul | 40/40 guards con cobertura directa (antes 12/40) |
| ST-12 | Documentación (changelog T-447, `logic/achievements.md`, DATA_MODEL, REST-001) | ✅ Done 2026-07-31 | Saul | Este changelog + logic doc; DATA_MODEL/REST-001 mantenidos al día incrementalmente por ST |

> **Cloud Scheduler de `recalc-level-stats` (ST-04) y `recalc-achievement-rarities` (ST-10) no
> creados en GCP todavía** — trackeado en un ticket de Infra/DevOps aparte con 2 subtareas
> (creado 2026-07-31), mismo patrón ya usado con `recalc-age-thresholds`.

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
