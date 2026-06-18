# INFRA-002 — Environment & Secrets Design Sign-off (dev/staging/prod topology)

| Campo | Valor |
|---|---|
| **Tipo** | Infra / Design Decision |
| **Prioridad** | Alta |
| **Status** | ✅ Done — sign-off Saul + Juan completados 2026-06-17, topología y secrets documentados |
| **Fecha planeada** | 2026-06-18 |
| **Workstream** | Infra/DevOps |
| **Owner** | Saul Zavala Morin |
| **Monday.com Item ID** | 12272268105 |
| **Depends on** | INFRA-001 ✅ |
| **Desbloquea** | INFRA-003 (FastAPI Cloud Run scaffold, 6/25), INFRA-004 (RS256 keys, 6/29), INFRA-006 (Terraform env split, 6/27) |

---

## Descripción

Este documento es el contrato de diseño de infraestructura de entornos para MotaMaze MVP. Define tres cosas que no pueden cambiar ad-hoc sin generar deuda técnica:

1. **Cuántos proyectos GCP** y cómo se llaman
2. **Qué secretos existen**, dónde viven y cómo se nombran
3. **Qué env vars necesita FastAPI** en cada entorno

El "sign-off" es literal: tanto Saul como Juan deben revisar y aprobar este documento antes de que Saul implemente los entornos (INFRA-006) y el scaffold de FastAPI (INFRA-003). Una vez aprobado, cambiar la topología costaría reescribir Terraform, reconfiguraci CloudRun, y actualizar todos los secrets — costo alto.

---

## Criterios de aceptación

- [x] Topología de proyectos GCP documentada y justificada — 3 proyectos separados (Opción B), ver Decisión 1
- [x] Naming convention de Secret Manager definida — `{componente}-{descripcion-kebab}`, sin sufijo de env, ver Decisión 2
- [x] Inventario completo de secrets por categoría — 5 secrets + variables no confidenciales, ver Decisión 3
- [x] Lista de env vars de FastAPI — qué va en Secret Manager vs. variable plana — ver Decisión 4
- [x] Tabla de recursos GCP por entorno (nombres exactos) — ver Decisión 5
- [x] Sign-off explícito de Saul ✍️
- [x] Sign-off explícito de Juan ✍️

---

## Decisión 1 — Topología de proyectos GCP

### Opciones evaluadas

| Opción | Descripción | Pros | Contras |
|---|---|---|---|
| **A — 1 proyecto, recursos namespaced** | Todo en `motamaze`, prefijos `dev-*`, `staging-*`, `prod-*` | Más simple, menos costo inicial | Sin aislamiento real: un bug en dev puede tocar prod; billing mezclado; no escala |
| **B — 3 proyectos separados** | `motamaze-dev`, `motamaze-staging`, `motamaze` (prod) | Aislamiento total: billing, IAM, cuotas, secrets independientes por entorno | Más setup inicial, 3 billing accounts o compartida |
| **C — 2 proyectos (dev+staging / prod)** | `motamaze-nonprod` + `motamaze` | Compromiso: prod aislado, dev y staging comparten | Staging no refleja prod exactamente — riesgo en validaciones |

### Decisión: **Opción B — 3 proyectos separados** ✅

**Justificación:**
- El plan de Monday.com (INFRA-006) ya dice explícitamente "project-per-env + Terraform module" — la decisión estaba implícita en el plan.
- **Compliance requiere aislamiento:** datos de usuarios reales NUNCA deben mezclarse con datos de prueba. Con proyecto separado, es imposible que un error de código apunte al Firestore de prod desde dev.
- **Billing independiente:** permite ver el costo exacto de prod vs. dev/staging sin filtros.
- **IAM independiente:** los accesos de dev (más permisivos para desarrollo rápido) no abren vectores en prod.
- INFRA-006 usa Terraform para replicar la infra mecánicamente — el costo de setup adicional es bajo con IaC.

### Proyectos GCP

| Entorno | Project ID | Estado | Billing |
|---|---|---|---|
| **Production** | `motamaze` | ✅ Existe (INFRA-001) | `01A127-C8B7E6-B6DEE7` (Juan) |
| **Staging** | `motamaze-staging` | ❌ Por crear (INFRA-006) | Misma billing account |
| **Development** | `motamaze-dev` | ❌ Por crear (INFRA-006) | Misma billing account |

**Regla:** `motamaze` = producción. No se crea un proyecto `motamaze-prod` — el proyecto raíz es prod.

---

## Decisión 2 — Naming convention para Secret Manager

### Principio base
Con 3 proyectos separados, **cada proyecto tiene sus propios secrets sin sufijo de entorno**. El aislamiento lo da el proyecto, no el nombre.

```
motamaze-dev       → Secret Manager → jwt-private-key
motamaze-staging   → Secret Manager → jwt-private-key
motamaze           → Secret Manager → jwt-private-key
```

Esto evita que FastAPI tenga lógica de "dame el secret correcto según el env" — simplemente lee `jwt-private-key` y el proyecto GCP garantiza que es el del entorno correcto.

### Formato de nombre de secret
```
{componente}-{descripcion-kebab}
```

Ejemplos:
- `jwt-private-key` — no `motamaze-jwt-private-key-prod` (el proyecto ya indica el env)
- `google-oauth-client-secret`
- `admob-ssv-hmac-key`

### Versioning
Secret Manager maneja versiones automáticamente. Siempre referenciar `latest` en Cloud Run excepto en casos donde se necesite pin a una versión específica (rollback de key rotation).

---

## Decisión 3 — Inventario de Secrets

Secrets que existirán en Secret Manager en **cada uno de los 3 proyectos**:

| Secret ID | Descripción | Quién lo crea | Tarea |
|---|---|---|---|
| `jwt-private-key` | RS256 private key para firmar JWTs | Saul | INFRA-004 |
| `google-oauth-client-id` | OAuth 2.0 client ID de Google Cloud Console | Saul | INFRA-003 |
| `google-oauth-client-secret` | OAuth 2.0 client secret | Saul | INFRA-003 |
| `play-package-name` | Package name del app Android | Juan (define en EXT-001) | EXT-001 |
| `admob-ssv-hmac-key` | Clave para verificar callbacks de AdMob SSV | Saul | EXT-002 / post-AdMob |

### Secrets que NO van a Secret Manager (no son secrets)
Estos valores van como env vars planos en Cloud Run (no son confidenciales):

- `GCP_PROJECT_ID` — es público, no confidencial
- `ENVIRONMENT` — dev / staging / prod
- `BQ_DATASET` — nombre del dataset
- `LOG_LEVEL` — debug / info / warning
- `JWT_ISSUER` — URL pública del issuer
- `JWKS_URL` — URL pública del JWKS endpoint
- `ALLOWED_ORIGINS` — CORS origins (semipúblico)

### ¿Por qué NO usar un archivo `.env` o `credentials.json`?
- Cloud Run + ADC (Application Default Credentials) + Secret Manager es el patrón recomendado por Google para servicios en producción.
- `.env` files en contenedores son un riesgo de seguridad si el contenedor se comparte o se expone.
- `credentials.json` de service accounts NO debe estar en el repositorio ni en la imagen Docker.

---

## Decisión 4 — Environment Variables para FastAPI (Cloud Run)

Separadas en dos categorías:

### A) Variables planas (no confidenciales) — Cloud Run env vars

| Variable | Dev | Staging | Prod | Descripción |
|---|---|---|---|---|
| `ENVIRONMENT` | `dev` | `staging` | `prod` | Identificador del entorno |
| `GCP_PROJECT_ID` | `motamaze-dev` | `motamaze-staging` | `motamaze` | Proyecto GCP activo |
| `FIRESTORE_DATABASE` | `(default)` | `(default)` | `(default)` | Database de Firestore |
| `BQ_DATASET` | `motamaze_analytics` | `motamaze_analytics` | `motamaze_analytics` | Dataset de BigQuery |
| `STORAGE_BUCKET_BUILDS` | `motamaze-dev-builds` | `motamaze-staging-builds` | `motamaze-builds` | Bucket de builds |
| `JWT_ISSUER` | `https://dev.api.motamaze.com` | `https://staging.api.motamaze.com` | `https://api.motamaze.com` | Issuer del JWT |
| `JWKS_URL` | `https://dev.api.motamaze.com/.well-known/jwks.json` | `https://staging.api.motamaze.com/.well-known/jwks.json` | `https://api.motamaze.com/.well-known/jwks.json` | JWKS público |
| `ALLOWED_ORIGINS` | `*` | `https://staging.motamaze.com` | `https://motamaze.com` | CORS |
| `LOG_LEVEL` | `DEBUG` | `INFO` | `WARNING` | Nivel de logging |
| `MAX_INSTANCES` | `2` | `5` | `10` | Cloud Run max-instances |
| `JWT_ALGORITHM` | `RS256` | `RS256` | `RS256` | Algoritmo JWT (constante) |
| `JWT_ACCESS_TOKEN_TTL` | `900` | `900` | `900` | TTL access token en segundos (15 min — alineado con REST-001 ST-02) |
| `JWT_REFRESH_TOKEN_TTL` | `1209600` | `1209600` | `1209600` | TTL refresh token en segundos (14 días — alineado con REST-001 ST-02) |

### B) Variables confidenciales — leídas desde Secret Manager en runtime

| Secret ID | Variable de app | Descripción |
|---|---|---|
| `jwt-private-key` | `JWT_PRIVATE_KEY` | Leído al inicio del servicio via `google.cloud.secretmanager` |
| `google-oauth-client-id` | `GOOGLE_OAUTH_CLIENT_ID` | |
| `google-oauth-client-secret` | `GOOGLE_OAUTH_CLIENT_SECRET` | |
| `admob-ssv-hmac-key` | `ADMOB_SSV_HMAC_KEY` | Solo cuando EXT-002 esté completo |

**Patrón de lectura en FastAPI:**
```python
from google.cloud import secretmanager

def get_secret(secret_id: str) -> str:
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_id}/versions/latest"
    return client.access_secret_version(name=name).payload.data.decode("UTF-8")
```

---

## Decisión 5 — Tabla de recursos GCP por entorno

| Recurso | Dev (`motamaze-dev`) | Staging (`motamaze-staging`) | Prod (`motamaze`) |
|---|---|---|---|
| **Cloud Run service** | `game-api` | `game-api` | `game-api` |
| **Cloud Run URL** | `https://game-api-*.dev.run.app` | `https://game-api-*.staging.run.app` | `https://game-api-*.run.app` |
| **Firestore DB** | `(default)` | `(default)` | `(default)` |
| **BQ Dataset** | `motamaze_analytics` | `motamaze_analytics` | `motamaze_analytics` |
| **Storage — builds** | `motamaze-dev-builds` | `motamaze-staging-builds` | `motamaze-builds` ✅ |
| **Storage — exports** | `motamaze-dev-exports` | `motamaze-staging-exports` | `motamaze-exports` ✅ |
| **Service Account** | `game-api-backend@motamaze-dev.iam.gserviceaccount.com` | `game-api-backend@motamaze-staging.iam.gserviceaccount.com` | `game-api-backend@motamaze.iam.gserviceaccount.com` ✅ |
| **Secret: jwt-private-key** | En `motamaze-dev` SM | En `motamaze-staging` SM | En `motamaze` SM |
| **Budget alert** | $10/mes | $20/mes | $50/mes ✅ |
| **Firebase** | Firebase proyecto `motamaze-dev` | Firebase proyecto `motamaze-staging` | Firebase proyecto `motamaze` ✅ |
| **Artifact Registry** | Imagen: `us-central1-docker.pkg.dev/motamaze-dev/game-api/app` | `…/motamaze-staging/…` | `…/motamaze/…` |

---

## Subtareas

| # | Subtarea | Status | Notas |
|---|---|---|---|
| ST-01 | Saul redacta el diseño — topología, naming, secrets, env vars, tabla de recursos | ✅ Done 2026-06-17 | Decisiones 1–5 documentadas |
| ST-02 | Sign-off de Saul | ✅ Done 2026-06-17 | Aprobado sin cambios |
| ST-03 | Sign-off de Juan | ✅ Done 2026-06-17 | Aprobado sin cambios |
| ST-04 | Topología de proyectos GCP documentada y justificada | ✅ Done 2026-06-17 | Opción B (3 proyectos separados): `motamaze-dev`, `motamaze-staging`, `motamaze` (prod). Justificación: aislamiento de compliance, billing independiente, IAM separado por entorno. |
| ST-05 | Naming convention de Secret Manager definida | ✅ Done 2026-06-17 | Sin sufijo de env — el proyecto GCP aísla, no el nombre. Formato: `{componente}-{descripcion-kebab}`. Versioning via `latest` salvo rollback. Los 5 secrets del inventario validan la convención. |
| ST-06 | Inventario completo de secrets por categoría | ✅ Done 2026-06-17 | 5 secrets en Secret Manager (`jwt-private-key`, `google-oauth-client-id`, `google-oauth-client-secret`, `play-package-name`, `admob-ssv-hmac-key`) + 7 variables planas en Cloud Run (no confidenciales). `.env` y `credentials.json` descartados explícitamente. |
| ST-07 | Lista de env vars de FastAPI — qué va en Secret Manager vs. variable plana | ✅ Done 2026-06-17 | 13 vars planas con valores por entorno (dev/staging/prod) + 4 vars confidenciales leídas de SM en runtime vía `secretmanager` SDK. Patrón de lectura documentado. |

---

## Sign-off

| Persona | Firma | Fecha | Notas |
|---|---|---|---|
| Saul Zavala Morin | ✅ Aprobado | 2026-06-17 | Diseño aprobado sin cambios |
| Juan Mosqueda | ✅ Aprobado | 2026-06-17 | Diseño aprobado sin cambios |

---

## Follow-ups / Notes

- **Dominio personalizado:** `api.motamaze.com` para prod, `staging.api.motamaze.com` para staging. Configurar en Cloud Run después de INFRA-003. Los `JWT_ISSUER` y `JWKS_URL` de arriba asumen ese dominio — confirmar con Juan si ya tienen el dominio registrado.
- **Firebase multi-proyecto:** Firebase Console permite crear proyectos separados para dev/staging. Verificar con Juan si el SDK de Godot soporta cambio de proyecto por build flavor — impacta `google-services.json`.
- **Artifact Registry:** Se usará un único Artifact Registry en prod (`motamaze`) y las imágenes se promueven de dev → staging → prod via CI/CD (INFRA-006). No se crean registries separados por env.
- **ADC en dev local:** Saul y Juan usan `gcloud auth application-default login --impersonate-service-account=game-api-backend@motamaze-dev.iam.gserviceaccount.com` para desarrollo local apuntando a `motamaze-dev`.
