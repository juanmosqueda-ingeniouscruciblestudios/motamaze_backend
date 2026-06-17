# INFRA-003 — FastAPI Scaffold en Cloud Run

| Campo | Valor |
|---|---|
| **Tipo** | Infra/DevOps / Backend Foundation |
| **Prioridad** | Alta — desbloquea todo el backend |
| **Status** | In Progress — ST-01 en ejecución 2026-06-17 |
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
- [ ] Repo backend creado con estructura FastAPI + Dockerfile + `pyproject.toml`
- [ ] Endpoint `GET /health` responde `{"status": "ok"}` con HTTP 200
- [ ] Cloud Run service desplegado en `us-central1` con service account `game-api-backend`
- [ ] `curl https://<cloud-run-url>/health` retorna 200 OK desde internet
- [ ] Sin credenciales hardcodeadas — ADC vía service account asignado al servicio

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

### ST-02 — Crear repo backend (FastAPI, Dockerfile, pyproject.toml) ⬜ Pending

**Depende de:** REST API contract (para saber qué routers crear desde el inicio)

**Por qué:** El scaffold define la estructura de carpetas y las dependencias de Python. Hacerlo antes del REST API contract significa refactorizar dos veces.

**Estructura objetivo:**
```
motamaze-backend/
├── app/
│   ├── main.py              # FastAPI app instance + routers
│   ├── routers/
│   │   ├── health.py        # GET /health
│   │   ├── auth.py          # POST /auth/login, DELETE /auth/account
│   │   ├── sessions.py      # POST /sessions/start, /sessions/end
│   │   ├── payments.py      # POST /payments/android/verify
│   │   ├── lives.py         # GET /lives, POST /lives/grant/admob-ssv
│   │   └── entitlements.py  # POST /entitlements/grant
│   └── services/
│       └── bq_streaming.py  # DATA-002 — diseñado en DATA-002 changelog
├── Dockerfile
├── pyproject.toml
└── .env.example
```

**`pyproject.toml` (dependencias mínimas):**
```toml
[project]
name = "motamaze-backend"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.29",
    "google-cloud-firestore>=2.16",
    "google-cloud-bigquery>=3.20",
    "google-auth>=2.29",
    "pydantic>=2.7",
]
```

**`Dockerfile`:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY app/ app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

### ST-03 — Implementar endpoint `GET /health` ⬜ Pending

**Depende de:** ST-02

**Por qué:** Cloud Run necesita un endpoint de health check para saber que el contenedor arrancó correctamente. También es el smoke test de todo el pipeline CI/CD.

**Código:**
```python
# app/routers/health.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok"}
```

```python
# app/main.py
from fastapi import FastAPI
from app.routers import health

app = FastAPI(title="MotaMaze Backend")
app.include_router(health.router)
```

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

### ST-06 — Smoke test: `curl /health` → 200 OK ⬜ Pending

**Depende de:** ST-05

**Verificación final:**
```bash
# Obtener URL del servicio
gcloud run services describe motamaze-backend \
  --region us-central1 \
  --project motamaze \
  --format="value(status.url)"

# Smoke test
curl -s https://<cloud-run-url>/health
# Esperado: {"status":"ok"}
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
- **`min-instances` en prod:** Para el soft launch se recomienda `--min-instances=1` para eliminar cold starts. En desarrollo, `0` (escala a cero) para no incurrir costos.
- **Variables de entorno en runtime:** Los secrets (JWT private key, etc.) se inyectarán vía Secret Manager en ST-04 usando `--set-secrets`. Detalle en INFRA-004.
- **Repo independiente vs. monorepo:** El backend FastAPI vivirá en un repo separado (no en `motamaze_backend` que es el repo de documentación). Decidir el nombre del repo en el REST API contract meeting.
- **`--allow-unauthenticated`:** Significa que Cloud Run no requiere un token Google IAM para recibir requests HTTP — el propio backend valida JWTs MotaMaze. Esto es correcto para un API público accedido desde el cliente Godot.
