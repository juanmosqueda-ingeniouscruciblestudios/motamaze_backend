# INFRA-003 — FastAPI Scaffold en Cloud Run

| Campo | Valor |
|---|---|
| **Tipo** | Infra/DevOps / Backend Foundation |
| **Prioridad** | Alta — desbloquea todo el backend |
| **Status** | In Progress — ST-01 ✅, ST-02 ✅ scaffold + Dockerfile (2026-06-22), ST-03 ✅ /health + /ready implementados, ST-04–06 ⬜ bloqueados billing motamaze-dev |
| **Fecha planeada** | 2026-06-25 – 2026-06-26 |
| **Fecha real inicio** | 2026-06-17 (ST-01 adelantado) |
| **Workstream** | Infra/DevOps |
| **Owner** | Saul Zavala Morin |
| **Monday.com Item ID** | 12272254518 |
| **Depends on** | INFRA-001 ✅ (GCP base infra, billing, SA), INFRA-002 ✅ (env/secrets design firmado), REST API contract ⬜ (para ST-02+) |
| **Desbloquea** | DATA-002 ST-02–09 (bq_streaming.py), INFRA-004 (RS256 + JWKS), INFRA-005 (Firestore rules), MON-001 (Cloud Monitoring) |

---

## Descripción

MotaMaze necesita un backend HTTP que reciba peticiones del cliente Godot, verifique compras en Google Play, gestione vidas, y emita JWTs. Todos estos endpoints viven en un servidor FastAPI desplegado en Cloud Run.

INFRA-003 crea ese servidor desde cero: el scaffold mínimo viable — un contenedor Docker con FastAPI, un endpoint `/health`, y el deploy inicial en Cloud Run con las credenciales correctas. Sin este scaffold, ningún otro ticket de backend (pagos, sesiones, analytics streaming, auth) puede ser implementado ni probado.

**Por qué FastAPI:**
- Async nativo — compatible con `BackgroundTasks` para el pipeline BQ de DATA-002
- Tipado fuerte con Pydantic — reduce bugs en contratos de API
- OpenAPI automático — útil para el REST API contract con Juan
- Ecosystem GCP: `google-cloud-*` libraries son first-class en Python

**Por qué Cloud Run:**
- Serverless — escala a cero fuera del soft launch, costo mínimo en desarrollo
- Integración nativa con GCP IAM — el service account `game-api-backend` se asigna directamente al servicio, sin manejar credenciales manualmente
- Cold start aceptable para móvil (< 2s) con `min-instances=1` en producción
- Compatible con Secret Manager para leer secrets en runtime

**Separación de responsabilidades con el cliente Godot:**
```
[Godot Client]
    │  HTTP requests (JWT en Authorization header)
    ▼
[Cloud Run — FastAPI]
    │  verifica JWT, escribe Firestore, llama Play API, dispara BQ background tasks
    ▼
[GCP Services: Firestore / BigQuery / Secret Manager / Play Developer API]
```

---

## Criterios de aceptación

- [ ] `run.googleapis.com` habilitada en proyecto `motamaze`
- [x] Repo backend creado con estructura FastAPI + Dockerfile + `pyproject.toml` (commit `1886ff4`, 2026-06-22)
- [x] Endpoint `GET /health` responde `{"status": "ok"}` con HTTP 200 (implementado, pendiente smoke test post-deploy)
- [ ] Cloud Run service desplegado en `us-central1` con service account `game-api-backend`
- [ ] `GET /health` y `GET /ready` retornan 200 OK desde internet
- [ ] Sin credenciales hardcodeadas — ADC vía service account asignado al servicio
- [ ] Deploy reproducible vía CI (ver nota en Follow-ups)

---

## Estado previo

- `run.googleapis.com`: **NO habilitada** en proyecto `motamaze`
- Repo backend FastAPI: **no existe**
- Cloud Run service: **no existe**
- Endpoints disponibles: ninguno

---

## Implementación — Subtareas

### ST-01 — Habilitar `run.googleapis.com` ✅ Done (2026-06-17)

**Por qué:** Cloud Run no puede recibir deploys hasta que la API esté habilitada en el proyecto GCP. Esta es la única subtarea que no depende del REST API contract — se puede hacer hoy.

**Comando ejecutado:**
```bash
gcloud services enable run.googleapis.com --project=motamaze
# Operation "operations/acf.p2-542009654415-c93f2956-103c-4c06-8f34-e01301f7a54c" finished successfully.
```

**Verificación:**
```bash
gcloud services list --enabled --filter="config.name:run.googleapis.com" --project=motamaze
NAME                TITLE                STATE
run.googleapis.com  Cloud Run Admin API  ENABLED
```

---

### ST-02 — Crear repo backend (FastAPI, Dockerfile, pyproject.toml) ✅ Done (2026-06-22)

**Commit:** `1886ff4` — pusheado a `juanmosqueda-ingeniouscruciblestudios/motamaze_backend`

**Estructura creada:**
```
motamaze_backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app + 5 routers incluidos
│   ├── config.py            # Settings via pydantic-settings
│   ├── dependencies.py      # DI: Firestore, BigQuery, Settings
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── health.py        # GET /health, GET /ready — implementados (ST-03)
│   │   ├── auth.py          # stub — Dominio 1
│   │   ├── game.py          # stub — Dominio 2
│   │   ├── payments.py      # stub — Dominio 3
│   │   └── social.py        # stub — Dominio 5
│   └── services/
│       ├── __init__.py
│       └── bq_streaming.py  # placeholder — DATA-002 ST-03
├── Dockerfile               # non-root, layer cache, provenance:false
├── pyproject.toml           # dependencias con pydantic-settings
├── .env.example
└── .github/
    └── workflows/
        └── cicd.yml         # CI/CD pipeline (CI-001)
```

**Patrón DI — `app/dependencies.py`:**
```python
from functools import lru_cache
from google.cloud import bigquery, firestore
from app.config import Settings

@lru_cache
def get_settings() -> Settings:
    return Settings()

def get_firestore_client() -> firestore.AsyncClient:
    return firestore.AsyncClient()

def get_bq_client() -> bigquery.Client:
    return bigquery.Client()
```
`lru_cache` en Settings garantiza que `.env` se lee una sola vez. Los clientes Firestore/BQ se crean por request — Cloud Run no garantiza que una instancia persista entre requests.

**`pyproject.toml`:**
```toml
[project]
name = "motamaze-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.29",
    "google-cloud-firestore>=2.16",
    "google-cloud-bigquery>=3.20",
    "google-auth>=2.29",
    "pydantic>=2.7",
    "pydantic-settings>=2.2",
]
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "httpx>=0.27"]
```

**Dockerfile:**
```dockerfile
FROM python:3.11-slim
RUN addgroup --system app && adduser --system --ingroup app app
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .
COPY app/ app/
USER app
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
```

**Verificado en CI (CI-001 run #1 y #2):** Build ✅ — imagen construida y pusheada a AR en ~16 s (cache hit).

---

### ST-03 — Implementar endpoints `GET /health` y `GET /ready` ✅ Done (2026-06-22)

Implementados dentro del mismo commit `1886ff4` junto con ST-02.

```python
# app/routers/health.py
from fastapi import APIRouter
router = APIRouter(tags=["infrastructure"])

@router.get("/health")
async def health():
    return {"status": "ok"}

@router.get("/ready")
async def ready():
    return {"status": "ready"}
```

Registrados en `app/main.py` junto con los otros 4 routers. Smoke test (curl → 200 OK) pendiente hasta que ST-04 complete el deploy en Cloud Run.

---

### ST-04 — Configurar Cloud Run service ⬜ Pending

**Depende de:** ST-01, ST-02

**Por qué:** El servicio Cloud Run define los recursos, la región, y el service account que usará el backend en producción. La configuración desde el inicio evita redeploys por olvidar parámetros.

**Comando de deploy:**
```bash
gcloud run deploy motamaze-backend \
  --source . \
  --region us-central1 \
  --project motamaze \
  --service-account game-api-backend@motamaze.iam.gserviceaccount.com \
  --max-instances 10 \
  --allow-unauthenticated \
  --port 8080
```

**Parámetros clave:**
| Parámetro | Valor | Razón |
|---|---|---|
| `--region` | `us-central1` | Coubicación con Firestore `nam5` (latencia baja) |
| `--service-account` | `game-api-backend@motamaze.iam.gserviceaccount.com` | ADC sin credenciales hardcodeadas |
| `--max-instances` | `10` | Límite de costo en soft launch (< 1,000 usuarios) |
| `--allow-unauthenticated` | — | El backend valida JWTs propio — no necesita Google IAM en la capa HTTP |
| `--port` | `8080` | Puerto estándar de Cloud Run |

---

### ST-05 — Verificar ADC en Cloud Run ⬜ Pending

**Depende de:** ST-04

**Por qué:** Application Default Credentials (ADC) en Cloud Run funcionan automáticamente cuando el service account está asignado al servicio. Pero hay que verificar que los roles IAM del SA permitan acceder a Firestore y BQ — ya asignados en INFRA-001 ST-07.

**Verificación de roles del SA (ya deben estar presentes desde INFRA-001):**
```bash
gcloud projects get-iam-policy motamaze \
  --flatten="bindings[].members" \
  --filter="bindings.members:game-api-backend" \
  --format="table(bindings.role)"
```

**Roles esperados:**
- `roles/datastore.user` — Firestore read/write
- `roles/bigquery.dataEditor` — BQ streaming insert
- `roles/bigquery.jobUser` — BQ job execution
- `roles/storage.objectAdmin` — Cloud Storage
- `roles/secretmanager.secretAccessor` — Secret Manager

---

### ST-06 — Smoke test: `/health` y `/ready` → 200 OK ⬜ Pending

**Depende de:** ST-05

**Verificación final:**
```bash
# Obtener URL del servicio
URL=$(gcloud run services describe motamaze-backend \
  --region us-central1 \
  --project motamaze \
  --format="value(status.url)")

curl -s "$URL/health"
# Esperado: {"status":"ok"}

curl -s "$URL/ready"
# Esperado: {"status":"ready"}
```

---

## Audit — Estado inicial (previo a ST-01)

```bash
gcloud services list --enabled --filter="config.name:run.googleapis.com" --project=motamaze
# (vacío) → run.googleapis.com NO habilitada
```

---

## Follow-ups / Notes

- **REST API contract es el bloqueador real:** ST-01 se puede hacer hoy, pero ST-02–06 esperan el contrato. La reunión con Juan está programada para el lunes siguiente (o antes si hay dependencia urgente). La fecha límite del contrato es 2026-06-24.
- **CI en el AC de Juan:** El criterio "deploys via CI" de Juan implica que el primer deploy de INFRA-003 debería pasar por GitHub Actions, no ser un deploy manual one-off. En la práctica, el deploy manual de ST-04 valida que el scaffold funciona, y CI-001 (task separada, 7/8–7/9) lo automatiza. Si Juan quiere CI como parte del AC de INFRA-003, CI-001 deberá adelantarse — pendiente aclarar en la reunión del contrato.
- **Referencias externas de Juan:** El storytelling de Juan cita `docs/DATA_MODEL.md` y `Architecture spec §9A`. Estos documentos no están en el repo aún — pendiente obtenerlos de Juan para cruzar referencias en ST-02.
- **`pydantic-settings`:** Agregar como dependencia en ST-02 para manejar la config vía env vars con tipado fuerte.
- **`min-instances` en prod:** Para el soft launch se recomienda `--min-instances=1` para eliminar cold starts. En desarrollo, `0` (escala a cero) para no incurrir costos.
- **Variables de entorno en runtime:** Los secrets (JWT private key, etc.) se inyectarán vía Secret Manager en ST-04 usando `--set-secrets`. Detalle en INFRA-004.
- **Repo backend confirmado:** ✅ `juanmosqueda-ingeniouscruciblestudios/motamaze_backend` (guión bajo) — confirmado 2026-06-22. El scaffold FastAPI de INFRA-003 se crea dentro de ese repo. CI-001 ST-02 ya tiene el WIF `attribute-condition` apuntando a este repo exacto.
- **Mapeo Monday subitems → STs del changelog** (los nombres en Monday son los de Juan — no modificar):

  | Monday subitem | ST(s) en este changelog |
  |---|---|
  | Scaffold FastAPI (structure, config, DI) | ST-02 (parcial — estructura + config + DI) |
  | Containerize as a single image | ST-02 (parcial — Dockerfile) |
  | Deploy to Cloud Run (max-instances=10, ADC) | ST-04 + ST-05 (el "ADC" del nombre = ST-05) |
  | Add /health + /ready (200) and wire CI deploy | ST-03 (/health) + CI-001 (wire CI) |
  | Smoke-test the deployed /health | ST-06 |
  | T-440: Share score backend | subtarea adicional, fuera de numeración ST |

  ST-01 (habilitar `run.googleapis.com`) no tiene subitem en Monday — fue prerequisito implícito ejecutado 2026-06-17.

- **Estructura de subitems en Monday:** Juan mantiene y controla los subitems del board. No agregar ni renombrar subitems sin coordinarlo con él — confirmado 2026-06-22 cuando eliminó un subitem agregado sin coordinación.
- **`--allow-unauthenticated`:** Significa que Cloud Run no requiere un token Google IAM para recibir requests HTTP — el propio backend valida JWTs MotaMaze. Esto es correcto para un API público accedido desde el cliente Godot.
