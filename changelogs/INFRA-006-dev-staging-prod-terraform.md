# INFRA-006 — Dev/Staging/Prod Environments + Terraform Module

| Campo | Valor |
|---|---|
| **Tipo** | Infra/DevOps / IaC |
| **Prioridad** | Alta |
| **Status** | ✅ Done — ST-01 ✅ proyectos GCP creados, ST-02 ✅ módulo Terraform, ST-03 ✅ remote state, ST-04 ✅ terraform apply dev completo (2026-07-13). Staging diferido a post-lanzamiento. |
| **Fecha planeada** | 6/27–6/28/2026 |
| **Fecha real inicio** | 2026-06-19 (adelantado) |
| **Workstream** | Infra/DevOps |
| **Owner** | Saul Zavala Morin |
| **Monday.com Item ID** | 12272254521 |
| **Depends on** | INFRA-001 ✅, INFRA-002 ✅ (Opción B: 3 proyectos, naming `{componente}-{desc}`) |
| **Desbloquea** | INFRA-004 ST-02 para dev/staging (jwt-private-key en SM), CI-001 (GitHub Actions) |

---

## Descripción

INFRA-001 creó la infraestructura de `motamaze` (prod) con comandos `gcloud` manuales. Este ticket formaliza esa infraestructura como código Terraform y la replica en `motamaze-dev` y `motamaze-staging`. A partir de aquí, cualquier cambio de infraestructura es un PR — no un comando manual.

**Estructura de archivos:**

```
terraform/
├── modules/
│   └── motamaze-env/          ← módulo reutilizable por entorno
│       ├── versions.tf        # Terraform ≥ 1.8, provider google ~> 6.0
│       ├── variables.tf       # project_id, environment, region, cloud_run_image
│       ├── main.tf            # APIs, SA, IAM, Firestore, BQ, GCS, SM, Cloud Run
│       └── outputs.tf         # backend_sa_email, bq_dataset_id, cloud_run_url
└── environments/
    ├── dev/
    │   ├── backend.tf         # GCS backend: motamaze-terraform-state/dev
    │   └── main.tf            # module call: project_id=motamaze-dev
    ├── staging/
    │   ├── backend.tf         # GCS backend: motamaze-terraform-state/staging
    │   └── main.tf            # module call: project_id=motamaze-staging
    └── prod/
        ├── backend.tf         # GCS backend: motamaze-terraform-state/prod
        └── main.tf            # module call: project_id=motamaze (import needed)
```

---

## Criterios de aceptación

- [x] Proyectos GCP `motamaze-dev` y `motamaze-staging` creados
- [x] Bucket `motamaze-terraform-state` creado en `motamaze` con versioning habilitado
- [x] Módulo Terraform cubre: APIs (12), SA, IAM (6 roles), Firestore, BQ dataset + 8 tablas, GCS bucket, 5 secrets SM, Cloud Run (opcional por imagen)
- [x] `backend.tf` configurado para los 3 entornos apuntando a prefijos separados en el bucket de estado
- [x] Billing linked en `motamaze-dev` (Juan — billing account `01A127-C8B7E6-B6DEE7`)
- [x] `terraform apply` exitoso en `dev` — todos los recursos creados (2026-07-13)
- [ ] `terraform import` + `terraform apply` en `prod` — state sincronizado con recursos existentes (pendiente post-lanzamiento)
- [ ] ~~`terraform apply` exitoso en `staging`~~ — **diferido** a ~1 mes post-lanzamiento PROD (2026-06-22)

---

## Estado previo

| Recurso | Estado antes de INFRA-006 |
|---|---|
| `motamaze-dev` | ❌ No existía |
| `motamaze-staging` | ❌ No existía |
| Terraform module | ❌ No existía |
| Remote state backend | ❌ No existía |
| Infra prod (`motamaze`) | ✅ Existe (creada manual en INFRA-001) |

---

## Implementación — Subtareas

### ST-01 — Create dev/staging/prod GCP projects ✅ Parcial (2026-06-19)

**`motamaze` (prod):** ✅ Ya existía desde INFRA-001

**`motamaze-dev` y `motamaze-staging` creados:**
```bash
gcloud projects create motamaze-dev --name="MotaMaze Dev"
# Create in progress... done.

gcloud projects create motamaze-staging --name="MotaMaze Staging"
# Create in progress... done.
```

**Verificación:**
```
motamaze-dev      1072330724928  ACTIVE
motamaze-staging  682669860502   ACTIVE
```

**Billing pendiente (requiere Juan — solo motamaze-dev):**
```bash
# Saul no tiene billing.resourceAssociations.create en la cuenta 01A127-C8B7E6-B6DEE7
# Juan debe ejecutar o autorizar (solo dev — staging diferido a post-lanzamiento):
gcloud billing projects link motamaze-dev --billing-account=01A127-C8B7E6-B6DEE7
```

> `motamaze-staging`: billing NO se enlaza ahora. Staging se activa ~1 mes después del lanzamiento PROD (decisión 2026-06-22).

---

### ST-02 — Write a reusable Terraform module ✅ Done (2026-06-19)

**Archivo:** `terraform/modules/motamaze-env/main.tf`

**Recursos que gestiona el módulo:**

| Recurso Terraform | Descripción |
|---|---|
| `google_project_service` (×12) | APIs: Firestore, BQ, Storage, SM, Cloud Run, Firebase Rules, Trace, Monitoring, Logging, PubSub, Firebase, IAM |
| `google_service_account` | `game-api-backend@{project}.iam.gserviceaccount.com` |
| `google_project_iam_member` (×6) | datastore.user, bigquery.dataEditor, bigquery.jobUser, secretmanager.secretAccessor, storage.objectAdmin, cloudtrace.agent |
| `google_firestore_database` | Native mode, `nam5`, `(default)` |
| `google_bigquery_dataset` | `motamaze_analytics` |
| `google_bigquery_table` (×8) | login_events, session_durations, player_behavior, purchase_events, ad_impressions, entitlement_grants, account_deletions, admob_daily_report |
| `google_storage_bucket` | `motamaze-{env}-storage` con versioning |
| `google_secret_manager_secret` (×5) | jwt-private-key, google-oauth-client-id, google-oauth-client-secret, play-package-name, admob-ssv-hmac-key |
| `google_cloud_run_v2_service` | Solo si `var.cloud_run_image != ""` (post-INFRA-003) |

**Cloud Run (`count = var.cloud_run_image != "" ? 1 : 0`):**
- Pre-INFRA-003: `cloud_run_image = ""` → recurso omitido
- Post-INFRA-003: se pasa la URL de la imagen → recurso creado
- `max_instance_count`: 10 en prod, 3 en dev/staging
- Env vars planas: `GCP_PROJECT_ID`, `ENVIRONMENT`, `BQ_DATASET`, `LOG_LEVEL`, `JWT_ISSUER`, `JWKS_URL`
- Secrets desde SM: `JWT_PRIVATE_KEY`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`

---

### ST-03 — Configure remote state management ✅ Done (2026-06-19)

**Bucket creado en `motamaze` (prod):**
```bash
gcloud storage buckets create gs://motamaze-terraform-state \
  --project=motamaze \
  --location=US \
  --uniform-bucket-level-access

gcloud storage buckets update gs://motamaze-terraform-state --versioning
```

**Estructura de estado por entorno:**
```
gs://motamaze-terraform-state/
├── dev/default.tfstate
├── staging/default.tfstate
└── prod/default.tfstate
```

**`backend.tf` (idéntico para los 3, solo cambia `prefix`):**
```hcl
terraform {
  backend "gcs" {
    bucket = "motamaze-terraform-state"
    prefix = "dev"   # staging | prod según entorno
  }
}
```

---

### ST-04 — Apply and verify on all three environments ✅ Dev Done (2026-07-13)

**Dev — `terraform apply` completado 2026-07-13:**

Resultado: `Apply complete! Resources: 9 imported, 24 added, 9 changed, 0 destroyed.`
Verificación: `terraform plan` → `No changes. Your infrastructure matches the configuration.`

**Recursos importados (existían antes de Terraform):**
- `google_service_account.game_api_backend` (via `terraform import` CLI)
- `google_firestore_database.default` (via `terraform import` CLI)
- `google_secret_manager_secret.secrets["jwt-private-key"]` (via import block)
- `google_bigquery_dataset.analytics` + 7 tablas BQ (via import blocks)

**Recursos creados nuevos:**
- 12 APIs habilitadas (`google_project_service`)
- 6 IAM role bindings (`google_project_iam_member`)
- GCS bucket `motamaze-dev-storage` (versioning enabled)
- 4 SM secrets: `google-oauth-client-id`, `google-oauth-client-secret`, `play-package-name`, `admob-ssv-hmac-key`
- BQ table `admob_daily_report` (no existía en dev)

**Decisión de diseño (2026-07-13):** `firestore_location = "us-central1"` hardcodeado en `terraform/environments/dev/main.tf` para preservar la base de datos dev existente (creada manualmente con us-central1). El módulo usa `nam5` como default para prod.

**Lección aprendida — PowerShell import con for_each keys:** `terraform import 'resource["key"]'` falla en PowerShell 5.1 porque las comillas internas se strip. Solución: usar import blocks en `.tf` temporales (`_imports.tf`) que se eliminan después del apply.

**Outputs:**
```
backend_sa_email = "game-api-backend@motamaze-dev.iam.gserviceaccount.com"
cloud_run_url    = ""
```

---

**Prod — requiere `terraform import` de recursos existentes (INFRA-001) — pendiente post-lanzamiento:**

Usar import blocks en `terraform/environments/prod/_imports.tf` (patrón establecido en dev). Recursos a importar:

```hcl
# terraform/environments/prod/_imports.tf
import { to = module.env.google_bigquery_dataset.analytics; id = "motamaze/motamaze_analytics" }
import { to = module.env.google_bigquery_table.login_events; id = "motamaze/motamaze_analytics/login_events" }
import { to = module.env.google_bigquery_table.session_durations; id = "motamaze/motamaze_analytics/session_durations" }
import { to = module.env.google_bigquery_table.player_behavior; id = "motamaze/motamaze_analytics/player_behavior" }
import { to = module.env.google_bigquery_table.purchase_events; id = "motamaze/motamaze_analytics/purchase_events" }
import { to = module.env.google_bigquery_table.ad_impressions; id = "motamaze/motamaze_analytics/ad_impressions" }
import { to = module.env.google_bigquery_table.entitlement_grants; id = "motamaze/motamaze_analytics/entitlement_grants" }
import { to = module.env.google_bigquery_table.account_deletions; id = "motamaze/motamaze_analytics/account_deletions" }
import { to = module.env.google_bigquery_table.admob_daily_report; id = "motamaze/motamaze_analytics/admob_daily_report" }
import { to = module.env.google_service_account.game_api_backend; id = "projects/motamaze/serviceAccounts/game-api-backend@motamaze.iam.gserviceaccount.com" }
import { to = module.env.google_firestore_database.default; id = "projects/motamaze/databases/(default)" }
import { to = module.env.google_secret_manager_secret.secrets["jwt-private-key"]; id = "projects/motamaze/secrets/jwt-private-key" }
import { to = module.env.google_secret_manager_secret.secrets["google-oauth-client-id"]; id = "projects/motamaze/secrets/google-oauth-client-id" }
import { to = module.env.google_secret_manager_secret.secrets["google-oauth-client-secret"]; id = "projects/motamaze/secrets/google-oauth-client-secret" }
import { to = module.env.google_secret_manager_secret.secrets["play-package-name"]; id = "projects/motamaze/secrets/play-package-name" }
import { to = module.env.google_secret_manager_secret.secrets["admob-ssv-hmac-key"]; id = "projects/motamaze/secrets/admob-ssv-hmac-key" }
```

Prod `firestore_location` usa el default `nam5` (correcto — prod Firestore fue creada con nam5).
`admob-ssv-hmac-key` no existe aún en prod SM — Terraform lo creará vacío.

**Staging — DIFERIDO** a ~1 mes post-lanzamiento PROD. El proyecto `motamaze-staging` existe pero sin billing ni recursos.

---

## Follow-ups / Notes

- **Billing en dev (solo):** Confirmar con Juan — solo `motamaze-dev`. `motamaze-staging` no requiere billing ahora. Una vez enlazado dev, `terraform apply` crea todos los recursos en ~3 minutos.
- **Staging diferido (2026-06-22):** Decisión acordada con Juan — staging se activa ~1 mes post-lanzamiento PROD. El proyecto `motamaze-staging` existe pero sin billing ni recursos. Los archivos Terraform de staging están listos para cuando llegue el momento.
- **`terraform import` en prod:** Los IAM role bindings (`google_project_iam_member`) son más delicados — si la cuenta tiene roles extra vs. el módulo, `terraform plan` mostrará removes. Revisar antes de apply en prod.
- **`google_firestore_database` ya existe en prod:** Terraform puede intentar recrearla si el import no funciona correctamente. Verificar con `terraform plan` que el resultado es "0 to add, 0 to change, 0 to destroy".
- **Cloud Run imagen:** Una vez que INFRA-003 cree el repo y el primer build, actualizar `cloud_run_image` en los 3 `main.tf` de environments. El módulo ya tiene el recurso preparado con `count`.
- **`admob-ssv-hmac-key`:** Este secret no existe aún en Secret Manager prod. El `terraform import` de ese secret fallará — Terraform lo creará vacío y el valor se llena manualmente cuando esté disponible.
- **`play-package-name`:** ✅ Creado manualmente en prod el 2026-06-22 con valor `com.ingeniouscruciblestudios.motamaze` (versión 1). El `terraform import` funcionará correctamente para este secret.
- **Versión de Terraform:** Usar ≥ 1.8 (`required_version` en `versions.tf`). Recomendado instalar via `tfenv` para gestión de versiones.
- **`firebase-admin` SA:** El SA de Firebase Admin (`firebase-adminsdk-fbsvc@motamaze.iam.gserviceaccount.com`) es gestionado por Firebase, no por Terraform. No incluir en el módulo.
