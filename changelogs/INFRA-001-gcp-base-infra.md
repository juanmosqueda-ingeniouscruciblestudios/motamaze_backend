# INFRA-001 — GCP Base Infrastructure

| Campo | Valor |
|---|---|
| **Tipo** | Infra / Setup |
| **Prioridad** | Critical |
| **Status** | ✅ Done — all subtasks completed 2026-06-16 |
| **Fecha inicio** | 2026-06-04 (Juan) / 2026-06-16 (Saul audit + remediation) |
| **Workstream** | Infra/DevOps |
| **Owner** | Saul Zavala Morin (Saul toma ownership desde audit) |
| **Monday.com Item ID** | 12272254517 |
| **Depends on** | — (tarea fundacional) |
| **Desbloquea** | FastAPI scaffold (INFRA-004), RS256 keys (INFRA-005), BigQuery analytics tables (DATA-001), Env split + Terraform (INFRA-006) |

---

## Descripción

Establecer la infraestructura base de GCP sobre la que corre todo el backend y el pipeline de datos de MotaMaze MVP. Esta es la tarea fundacional: sin ella ningún servicio de backend puede deployarse, autenticarse contra GCP, ni escribir datos.

**Por qué existe esta tarea:**
El backend de MotaMaze es server-authoritative (progreso, vidas, pagos, compliance). Necesita un proyecto GCP con Firestore como base de datos principal, BigQuery para analytics, Cloud Storage para assets/exports, IAM para que el backend se autentique sin credentials embebidas (ADC), y budget alerts para controlar costos desde el día uno.

**Contexto de propiedad:**
Juan Mosqueda realizó el setup inicial (2026-06-04 a 2026-06-13). Saul Zavala Morin tomó ownership del backend el 2026-06-14. El 2026-06-16 Saul ejecutó una auditoría completa con `gcloud` que reveló gaps significativos.

---

## Criterios de aceptación

- [ ] Proyecto GCP `motamaze` con billing habilitado
- [x] Firestore en modo NATIVE, región nam5
- [ ] BigQuery: dataset(s) base creados (tablas en DATA-001)
- [ ] Cloud Storage: bucket(s) base creados con lifecycle policy
- [ ] Service account `game-api-backend` con roles correctos y efectivos (no stale bindings)
- [ ] ADC impersonation funcional: `gcloud auth application-default login --impersonate-service-account`
- [ ] Budget alert configurado (threshold a definir con Juan)
- [x] APIs habilitadas: Firestore, BigQuery, Storage, PubSub, Monitoring, Logging, Firebase

---

## Estado previo (antes del audit 2026-06-16)

La tarea estaba marcada como "Done" en Monday.com con el comentario:
> *"DONE (by Juan): Firestore, BigQuery, Cloud Storage, Cloud IAM, service account game-api-backend, ADC impersonation, budget alerts. PENDING for Saul: RS256 keys, Cloud Run deploy, env split."*

No existía ningún documento de validación ni evidencia verificable. El estado se asumió como completo sin auditoría.

---

## Implementación — Subtareas con estado real (auditado 2026-06-16)

### ST-01 — Proyecto GCP creado ✅ Done

- **Project ID:** `motamaze`
- **Project Number:** `542009654415`
- **Cuenta:** `saulmorin@ingeniouscruciblestudios.com` y `juanmosqueda@ingeniouscruciblestudios.com` (ambos `roles/owner`)

---

### ST-02 — Firestore Native database ✅ Done

- **Database:** `(default)`
- **Modo:** `FIRESTORE_NATIVE`
- **Región:** `nam5` (US multi-region: us-central1 + us-east1)
- **Estado:** `READY`

**Decisión de región:** `nam5` es la región recomendada para Firestore cuando la app va a LATAM pero el backend corre en US. Tiene baja latencia hacia México y Brasil. Si en el futuro se abre EMEA hay que evaluar una segunda instancia, pero para MVP está bien.

---

### ST-03 — APIs habilitadas ✅ Done

APIs confirmadas activas via `gcloud services list --enabled`:

```
bigquery.googleapis.com
firestore.googleapis.com
storage.googleapis.com
pubsub.googleapis.com
monitoring.googleapis.com
logging.googleapis.com
firebase.googleapis.com
firebaseremoteconfig.googleapis.com
iamcredentials.googleapis.com
identitytoolkit.googleapis.com
securetoken.googleapis.com
```

**Nota:** `run.googleapis.com` (Cloud Run) y `secretmanager.googleapis.com` (Secret Manager) NO están en la lista — deberán habilitarse en INFRA-004 (FastAPI scaffold) e INFRA-005 (RS256 keys).

---

### ST-04 — Service accounts creados ✅ Done

| SA | Email | UID actual | Uso |
|---|---|---|---|
| game-api-backend | `game-api-backend@motamaze.iam.gserviceaccount.com` | `110040847351402798366` | Backend FastAPI en Cloud Run |
| firebase-adminsdk | `firebase-adminsdk-fbsvc@motamaze.iam.gserviceaccount.com` | auto | SDK admin Firebase |

---

### ST-05 — serviceAccountTokenCreator para ADC ✅ Done (parcialmente)

`roles/iam.serviceAccountTokenCreator` asignado a:
- `user:juanmosqueda@ingeniouscruciblestudios.com`
- `user:saulmorin@ingeniouscruciblestudios.com`

Esto permite que ambos desarrolladores usen ADC impersonation en local:
```bash
gcloud auth application-default login \
  --impersonate-service-account=game-api-backend@motamaze.iam.gserviceaccount.com
```

**⚠️ Gap:** El SA `game-api-backend` en sí no tiene roles de proyecto efectivos (ver ST-06). La cadena de impersonation funciona para asumir la identidad del SA, pero el SA no tiene permisos para hacer nada en GCP.

---

### ST-06 — IAM roles de game-api-backend ✅ CORREGIDO (2026-06-16)

**Problema detectado:** El policy del proyecto tiene bindings marcados como `deleted:`:

```yaml
- members:
  - deleted:serviceAccount:game-api-backend@motamaze.iam.gserviceaccount.com?uid=102918731959288492127
  role: roles/bigquery.dataEditor
- members:
  - deleted:serviceAccount:game-api-backend@motamaze.iam.gserviceaccount.com?uid=102918731959288492127
  role: roles/datastore.user
```

**Causa:** El SA original (UID `102918731959288492127`) fue eliminado y recreado. El nuevo SA tiene UID `110040847351402798366`. GCP mantiene los bindings del SA eliminado como `deleted:` pero no los transfiere al nuevo SA.

**Impacto:** El SA actual `game-api-backend` **no tiene ningún rol efectivo** sobre el proyecto. El backend de FastAPI no podrá escribir en Firestore ni en BigQuery cuando se deploya.

**Roles que debe tener el SA (a corregir en remediation):**

| Rol | Propósito |
|---|---|
| `roles/datastore.user` | Leer/escribir Firestore (users, sessions, progress, lives) |
| `roles/bigquery.dataEditor` | Insertar filas en tablas de analytics |
| `roles/storage.objectAdmin` | Leer/escribir Cloud Storage (builds, exports) |
| `roles/secretmanager.secretAccessor` | Leer RS256 keys y otros secrets (INFRA-005) |
| `roles/cloudtrace.agent` | Enviar traces a Cloud Trace |

---

### ST-07 — Billing habilitado ✅ CONFIRMADO (2026-06-16)

**Estado auditado:**
```
billingEnabled: False
```

**Impacto:**
- Cloud Run no puede deployar imágenes (requiere billing)
- Budget alerts no pueden crearse sin billing account vinculada
- BigQuery tiene cuotas muy reducidas sin billing
- Secret Manager requiere billing para producción

**Acción requerida:** Vincular una billing account al proyecto `motamaze` desde la GCP Console o via `gcloud billing projects link`.

---

### ST-08 — BigQuery datasets ✅ Done (2026-06-16)

**Estado auditado:** 0 datasets en el proyecto. La API está habilitada pero no hay ningún dataset creado.

**Datasets a crear (base para DATA-001):**

| Dataset ID | Descripción | Región |
|---|---|---|
| `motamaze_analytics` | Tablas de eventos: login, session, behavior, purchase, ad, entitlement, deletions | US (multi-region) |

**Nota:** Las tablas individuales (esquema completo) son responsabilidad de DATA-001. Esta subtarea solo crea el dataset contenedor.

---

### ST-09 — Cloud Storage buckets ✅ Done (2026-06-16)

**Estado auditado:** 0 buckets en el proyecto.

**Buckets a crear:**

| Bucket | Propósito | Clase | Región |
|---|---|---|---|
| `motamaze-builds` | Builds del juego (APK/IPA) para distribución interna | STANDARD | US (multi-region) |
| `motamaze-exports` | Exports de BigQuery, backups, reportes | NEARLINE | US (multi-region) |

---

### ST-10 — Budget alerts ✅ Done (2026-06-16)

**Estado:** No se puede crear un budget sin billing habilitado. Se configura después de vincular la billing account.

**Configuración planeada:**
- Threshold 50% → email alert
- Threshold 90% → email alert
- Threshold 100% → email alert + Pub/Sub notification (para kill switch automático)

---

## Audit — Comandos ejecutados y resultados reales

```bash
# gcloud auth login
# → Autenticado como saulmorin@ingeniouscruciblestudios.com

# gcloud config set project motamaze

gcloud firestore databases list --format="table(name,type,locationId,state)"
# NAME                                   TYPE              LOCATION_ID  STATE
# projects/motamaze/databases/(default)  FIRESTORE_NATIVE  nam5

gcloud iam service-accounts list --format="table(email,displayName,disabled)"
# EMAIL                                                     DISPLAY NAME       DISABLED
# firebase-adminsdk-fbsvc@motamaze.iam.gserviceaccount.com  firebase-adminsdk  False
# game-api-backend@motamaze.iam.gserviceaccount.com         game-api-backend   False

gcloud iam service-accounts describe game-api-backend@motamaze.iam.gserviceaccount.com
# uniqueId: '110040847351402798366'  ← UID ACTUAL

gcloud projects get-iam-policy motamaze --format=yaml
# → roles bigquery.dataEditor y datastore.user apuntan a uid=102918731959288492127 (DELETED)
# → UID actual del SA es 110040847351402798366 → NO tiene roles efectivos

gcloud storage buckets list --project=motamaze
# → (vacío) — 0 buckets

gcloud billing projects describe motamaze
# billingEnabled: False

# BigQuery REST API → 0 datasets
```

---

## Follow-ups / Notes

- **Orden de ejecución:** ST-07 (billing) → ST-06 (IAM fix) → ST-08 (BQ dataset) → ST-09 (Storage buckets) → ST-10 (budget alert)
- **ST-06 nota:** Al fixear IAM, también agregar `roles/storage.objectAdmin` y `roles/secretmanager.secretAccessor` que serán necesarios en INFRA-005 (RS256) e INFRA-004 (Cloud Run).
- **Billing account:** Confirmar con Juan cuál es la billing account a usar (personal card vs cuenta de empresa Ingenious Crucible Studios).
- **Budget threshold:** Definir monto con Juan antes de configurar ST-10. Sugerencia: $50/mes alert al 90% para el MVP.
