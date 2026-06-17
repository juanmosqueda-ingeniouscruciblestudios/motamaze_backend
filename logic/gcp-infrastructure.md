# GCP Infrastructure — Estado actual

> Última verificación: 2026-06-16 via `gcloud` (saulmorin@ingeniouscruciblestudios.com)
> INFRA-001 completado — todos los componentes base verificados y operativos.

---

## Proyecto

| Campo | Valor |
|---|---|
| Project ID | `motamaze` |
| Project Number | `542009654415` |
| Owners | `saulmorin@ingeniouscruciblestudios.com`, `juanmosqueda@ingeniouscruciblestudios.com` |
| Billing | ✅ Habilitado — `billingAccounts/01A127-C8B7E6-B6DEE7` (cuenta de Juan) |
| Región principal | `nam5` (US multi-region) |

---

## Firestore

| Campo | Valor |
|---|---|
| Database | `(default)` |
| Modo | `FIRESTORE_NATIVE` |
| Región | `nam5` |
| Estado | `READY` |
| Reglas | Firebase Security Rules (modo producción pendiente — ver INFRA-003) |

**Collections planeadas** (a crear en INFRA-003):
- `users/{uid}` — perfil, país, edad, flags de compliance
- `sessions/{sessionId}` — tokens JWT activos
- `revoked_jtis/{jti}` — JTIs revocados (logout, cuenta eliminada)
- `progress/{uid}` — nivel desbloqueado, estrellas
- `lives/{uid}` — contador de vidas, último regen timestamp
- `entitlements/{uid}` — IAPs y skins adquiridos

---

## BigQuery

| Campo | Valor |
|---|---|
| API | Habilitada |
| Datasets | `motamaze_analytics` (US) ✅ |
| Dataset planeado | `motamaze_analytics` (región US) |

**Tablas planeadas** (a crear en DATA-001):
- `login_events`
- `session_events`
- `behavior_events`
- `purchase_events`
- `ad_events`
- `entitlement_events`
- `deletion_queue`

---

## Cloud Storage

| Campo | Valor |
|---|---|
| API | Habilitada |
| Buckets | `motamaze-builds` (STANDARD, US) ✅, `motamaze-exports` (NEARLINE, US) ✅ |

**Buckets planeados:**
- `motamaze-builds` — STANDARD, US multi-region
- `motamaze-exports` — NEARLINE, US multi-region

---

## IAM — Service Accounts

### game-api-backend
| Campo | Valor |
|---|---|
| Email | `game-api-backend@motamaze.iam.gserviceaccount.com` |
| UID actual | `110040847351402798366` |
| Roles efectivos | **NINGUNO** ← gap crítico |
| Causa | SA fue eliminado y recreado; bindings del IAM policy apuntan al UID anterior `102918731959288492127` (marked `deleted:`) |

**Roles asignados** (2026-06-16):
```
roles/datastore.user           ✅
roles/bigquery.dataEditor      ✅
roles/storage.objectAdmin      ✅
roles/secretmanager.secretAccessor ✅
roles/cloudtrace.agent         ✅
```

### firebase-adminsdk-fbsvc
| Campo | Valor |
|---|---|
| Email | `firebase-adminsdk-fbsvc@motamaze.iam.gserviceaccount.com` |
| Roles | `roles/firebase.sdkAdminServiceAgent`, `roles/iam.serviceAccountTokenCreator` |
| Estado | OK — gestionado por Firebase |

### ADC Impersonation chain
`serviceAccountTokenCreator` asignado a `saulmorin` y `juanmosqueda`. Permite:
```bash
gcloud auth application-default login \
  --impersonate-service-account=game-api-backend@motamaze.iam.gserviceaccount.com
```
**Estado:** El mecanismo de impersonation está configurado, pero es inútil hasta que se fijen los roles del SA (ST-06).

---

## APIs habilitadas

```
bigquery.googleapis.com          ✅
firestore.googleapis.com         ✅
storage.googleapis.com           ✅
pubsub.googleapis.com            ✅
monitoring.googleapis.com        ✅
logging.googleapis.com           ✅
firebase.googleapis.com          ✅
firebaseremoteconfig.googleapis.com ✅
iamcredentials.googleapis.com    ✅
identitytoolkit.googleapis.com   ✅
securetoken.googleapis.com       ✅
run.googleapis.com               ❌ (habilitar en INFRA-004)
secretmanager.googleapis.com     ❌ (habilitar en INFRA-005)
```

---

## Budget Alerts

| Estado | Detalle |
|---|---|
| Billing habilitado | ✅ `billingAccounts/01A127-C8B7E6-B6DEE7` |
| Budget configurado | ✅ ID: `f888196a-9508-4c1c-a2d3-25375fb21b16` |
| Monto | $50 USD/mes |
| Thresholds | 50% → email, 90% → email, 100% → email |
| Notificaciones | Project-level recipients (owners del proyecto) |

---

## INFRA-001 completado — Próximas tareas

1. **INFRA-002** — Environment & secrets design sign-off (dev/staging/prod) — vence 6/18
2. **DATA-001** — BigQuery analytics tables (esquema completo) — dataset `motamaze_analytics` ya existe
3. **INFRA-003** — FastAPI scaffold en Cloud Run — vence 6/25
4. **INFRA-004** — RS256 keypair en Secret Manager + JWKS — vence 6/29
