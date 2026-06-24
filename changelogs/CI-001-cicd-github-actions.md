# CI-001 — CI/CD: GitHub Actions + Artifact Registry single-image promotion pipeline

| Campo | Valor |
|---|---|
| **Tipo** | Infra/DevOps / CI-CD |
| **Prioridad** | Alta |
| **Status** | In Progress — ST-01 ✅, ST-02 ✅ AR+WIF+SA+Environments, ST-03 ✅ Build+push AR (5 runs), ST-04 🔄 billing desbloqueado + run.googleapis.com habilitada (2026-06-24), ST-05 ⬜ |
| **Fecha planeada** | 7/8–7/9/2026 |
| **Fecha real inicio** | 2026-06-19 (ST-01 adelantado) |
| **Workstream** | Infra/DevOps |
| **Owner** | Saul Zavala Morin |
| **Monday.com Item ID** | 12272268267 |
| **Depends on** | INFRA-003 ⬜ (backend repo FastAPI — para ST-03+), INFRA-006 ✅ (proyectos GCP creados) |
| **Desbloquea** | Todos los deploys de backend: AUTH-001, PAY-001, DATA-002, etc. |

---

## Descripción

Pipeline CI/CD de imagen única: el backend FastAPI se construye **una sola vez** por commit y la misma imagen (mismo digest) se promueve de dev → staging → prod sin reconstrucción. Esto garantiza que lo que se probó en staging es exactamente lo que va a prod — no hay diferencias por rebuild.

**Flujo por evento (DEV + PROD — staging diferido a post-lanzamiento):**

| Evento | Resultado |
|---|---|
| `pull_request` a `main` | Build únicamente — valida que el Dockerfile compila |
| `push` a `main` (merge) | Build + push a AR + deploy automático a `dev` |
| Aprobación en GitHub → prod | Mismo digest → deploy a `prod` (sin rebuild) |
| ~~Aprobación en GitHub → staging~~ | **Diferido** — staging se activa ~1 mes post-lanzamiento PROD (2026-06-22) |

**Convención de imagen:**
```
us-central1-docker.pkg.dev/motamaze/backend/motamaze-backend:{git-sha}
us-central1-docker.pkg.dev/motamaze/backend/motamaze-backend:latest
```

El `latest` apunta siempre al último merge a `main`. Los deploys usan el SHA para reproducibilidad.

---

## Criterios de aceptación

- [x] Dockerfile producción-ready (non-root, single worker, layer cache)
- [x] Workflow YAML con build job completo (build en PR, build+push en merge)
- [x] Promoción dev→staging→prod con mismo digest documentada y estructurada
- [x] Artifact Registry repo `backend` creado en `motamaze` us-central1 (2026-06-22)
- [x] Workload Identity Federation configurado: GitHub → GCP — pool `github-pool`, provider `github-provider`, SA `github-actions@motamaze.iam.gserviceaccount.com` (2026-06-22)
- [x] Secrets `WIF_PROVIDER` y `WIF_SERVICE_ACCOUNT` agregados en GitHub repo `motamaze_backend` (Saul, 2026-06-22)
- [x] GitHub Environments `dev` y `prod` configurados (Juan, 2026-06-23) — `dev` sin reviewers, `prod` requiere aprobación Juan + Saul
- [x] Cloud Run Admin API habilitada en `motamaze-dev` (billing vinculado por Juan 2026-06-24, API habilitada por Saul 2026-06-24)
- [ ] Pipeline verde end-to-end: PR build ✅, merge deploy-dev ✅, prod ✅ (ST-05)

---

## Estado previo

| Recurso | Estado antes de CI-001 |
|---|---|
| Dockerfile | Draft en INFRA-003 changelog — sin non-root ni best practices |
| GitHub Actions workflow | No existía |
| Artifact Registry repo `backend` | No existe |
| Workload Identity Federation | No configurado |

---

## Implementación — Subtareas

### ST-01 — Build the GitHub Actions image build ✅ Done (2026-06-19)

**Archivos creados** en `ci-templates/` (se copian al backend repo en INFRA-003):
- `ci-templates/Dockerfile`
- `ci-templates/.github/workflows/cicd.yml`

**Dockerfile** (`ci-templates/Dockerfile`):

```dockerfile
FROM python:3.11-slim

RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

COPY app/ app/

USER app
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
```

**Decisiones del Dockerfile:**

| Decisión | Razón |
|---|---|
| `python:3.11-slim` | Base mínima — sin herramientas de compilación innecesarias |
| Usuario no-root (`app`) | Seguridad: el proceso no corre como root en el contenedor |
| `pyproject.toml` copiado antes que `app/` | Layer cache: dependencias se reinstalan solo si cambia `pyproject.toml`, no en cada cambio de código |
| `--workers 1` | Cloud Run escala vía instancias, no via workers por instancia. Múltiples workers complican el manejo de señales en Cloud Run. |
| `provenance: false` en build-push-action | Evita manifiestos multi-plataforma que Cloud Run rechaza al hacer pull |

**Workflow build job** (`ci-templates/.github/workflows/cicd.yml`):

El workflow completo está en el archivo. Puntos clave del build job:

```yaml
- name: Build and push
  uses: docker/build-push-action@v5
  with:
    push: ${{ github.event_name == 'push' }}   # no push en PRs
    tags: |
      us-central1-docker.pkg.dev/motamaze/backend/motamaze-backend:${{ github.sha }}
      us-central1-docker.pkg.dev/motamaze/backend/motamaze-backend:latest
    cache-from: type=gha
    cache-to:   type=gha,mode=max
```

**Layer cache con GitHub Actions cache (`type=gha`):**
- En builds posteriores, si `pyproject.toml` no cambió, la capa de dependencias se restaura del cache
- Reduce el tiempo de build de ~3 min a ~40 s en el caso común (solo cambió código Python)

**Estructura del workflow (3 jobs — staging diferido):**

```
build → deploy-dev → deploy-prod
         (auto)       (manual approval)
```

Los jobs `deploy-*` usan `google-github-actions/deploy-cloudrun@v2` con la misma imagen del job `build` (via `needs.build.outputs.image`). Esto garantiza que el mismo digest viaja por todos los entornos. El job `deploy-staging` se agregará al workflow cuando staging se active (~1 mes post-lanzamiento PROD).

---

### ST-02 — Create AR repo + configure Workload Identity Federation ✅ Done (2026-06-22)

**Depende de:** Repo backend confirmado — `juanmosqueda-ingeniouscruciblestudios/motamaze_backend` ✅

**Resultados verificados:**

| Recurso | Resultado |
|---|---|
| AR repo `backend` | ✅ `projects/motamaze/locations/us-central1/repositories/backend` (DOCKER, 0 MB) |
| WIF Pool `github-pool` | ✅ `projects/542009654415/locations/global/workloadIdentityPools/github-pool` ACTIVE |
| WIF Provider `github-provider` | ✅ OIDC, condition: `assertion.repository=='juanmosqueda-ingeniouscruciblestudios/motamaze_backend'` |
| SA `github-actions` | ✅ `github-actions@motamaze.iam.gserviceaccount.com` |
| IAM `artifactregistry.writer` | ✅ en `motamaze` |
| IAM `run.developer` | ✅ en `motamaze-dev` + `motamaze` |
| WIF → SA binding | ✅ `roles/iam.workloadIdentityUser` para `motamaze_backend` repo |

**Secrets en `motamaze_backend`:** ✅ Agregados por Saul (2026-06-22)
- `WIF_PROVIDER` = `projects/542009654415/locations/global/workloadIdentityPools/github-pool/providers/github-provider`
- `WIF_SERVICE_ACCOUNT` = `github-actions@motamaze.iam.gserviceaccount.com`

**GitHub Environments:** ✅ Creados por Juan (2026-06-23)
- `dev` — sin reviewers, auto-deploy (creado 03:17 UTC)
- `prod` — required reviewers: Juan + Saul (creado 14:35 UTC)

**Artifact Registry:**
```bash
gcloud artifacts repositories create backend \
  --repository-format=docker \
  --location=us-central1 \
  --project=motamaze \
  --description="MotaMaze backend Docker images"
```

**Workload Identity Federation:**
```bash
# 1. Crear Workload Identity Pool
gcloud iam workload-identity-pools create "github-pool" \
  --project=motamaze \
  --location=global \
  --display-name="GitHub Actions Pool"

# 2. Crear Provider (GitHub OIDC)
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project=motamaze \
  --location=global \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub Provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='juanmosqueda-ingeniouscruciblestudios/motamaze_backend'"

# 3. Crear SA para GitHub Actions
gcloud iam service-accounts create github-actions \
  --project=motamaze \
  --display-name="GitHub Actions CI/CD"

# 4. Dar permisos al SA
gcloud projects add-iam-policy-binding motamaze \
  --member="serviceAccount:github-actions@motamaze.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

# Para deploy en dev y prod (Cloud Run) — staging diferido a post-lanzamiento:
gcloud projects add-iam-policy-binding motamaze-dev \
  --member="serviceAccount:github-actions@motamaze.iam.gserviceaccount.com" \
  --role="roles/run.developer"
# (repetir para motamaze — motamaze-staging se agrega cuando staging se active)

# 5. Enlazar WIF Pool → SA
gcloud iam service-accounts add-iam-policy-binding \
  github-actions@motamaze.iam.gserviceaccount.com \
  --project=motamaze \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/542009654415/locations/global/workloadIdentityPools/github-pool/attribute.repository/juanmosqueda-ingeniouscruciblestudios/motamaze_backend"
```

**Secrets en GitHub repo del backend:**
```
WIF_PROVIDER     = projects/542009654415/locations/global/workloadIdentityPools/github-pool/providers/github-provider
WIF_SERVICE_ACCOUNT = github-actions@motamaze.iam.gserviceaccount.com
```

**GitHub Environments a crear en Settings → Environments:**
- `dev` — sin reviewers, auto-deploy
- `prod` — requiere aprobación de ambos (Saul + Juan)
- ~~`staging`~~ — diferido a post-lanzamiento PROD (2026-06-22)

---

### ST-03 — Push to Artifact Registry ✅ Done (2026-06-22)

Verificado en CI run #1 (`1886ff4`) y #2 (`7889046`) — el job **Build** completó en 47 s y 16 s respectivamente (cache hit en el segundo). La imagen se construyó y publicó correctamente en Artifact Registry:

```
us-central1-docker.pkg.dev/motamaze/backend/motamaze-backend:{sha}
us-central1-docker.pkg.dev/motamaze/backend/motamaze-backend:latest
```

El build job usa `push: ${{ github.event_name == 'push' }}` — solo hace push en merges a `main`, no en PRs.

---

### ST-04 — Implement dev→staging→prod promotion 🔄 En progreso (billing desbloqueado 2026-06-24)

**Fix de workflow aplicado — commit `7889046` (2026-06-22):**

El CI run #1 (`1886ff4`) reveló dos bugs en el YAML inicial del deploy job:

| Bug | Error observado | Fix |
|---|---|---|
| `project:` input inválido en `deploy-cloudrun@v2` | `Unexpected input(s) 'project'` | Movido a `project_id:` en el step `auth@v2` |
| `--allow-unauthenticated` faltante | `This service will require authentication to be invoked` | Agregado en `flags:` del deploy step |

**CI run #2 (`7889046`) — resultado tras el fix:**

| Job | Resultado | Detalle |
|---|---|---|
| Build | ✅ 16 s (cache hit) | Imagen publicada en AR |
| Deploy → dev | ❌ PERMISSION_DENIED | Cloud Run Admin API no habilitada en `motamaze-dev` |
| Deploy → prod | ⊘ Skipped | Depende de deploy-dev |

**Error actual (bloqueador externo):**
```
PERMISSION_DENIED: Cloud Run Admin API has not been used in project motamaze-dev
before or it is disabled.
```

El workflow apunta correctamente a `motamaze-dev` — el error confirma que el project targeting funciona. El bloqueador es que Cloud Run Admin API requiere billing activo en `motamaze-dev`.

**Acción requerida:** Juan debe vincular billing a `motamaze-dev` → habilitar Cloud Run Admin API → re-run del CI.

**Runs #3–#5 (commits `9d392ba`, `59e8dd2`, `27e87d9` — 2026-06-22):** Todos markdown-only. Mismo resultado en los tres: Build ✅ (21–28 s cache hit), Deploy→dev ❌ mismo PERMISSION_DENIED, Deploy→prod ⊘. Confirma que el workflow es estable y el único bloqueador es billing.

**Desbloqueado — 2026-06-24:**
- Causa raíz identificada: `motamaze-dev` creado con cuenta de Saul — Juan no tenía acceso para vincular billing. Saul agregó a Juan como Owner → Juan vinculó billing account `01A127-C8B7E6-B6DEE7`.
- `billingEnabled: true` confirmado vía `gcloud billing projects describe motamaze-dev`.
- `run.googleapis.com` habilitada en `motamaze-dev` — 2026-06-24 (Saul).
- Próximo paso: push a `main` → CI run → Deploy→dev esperado ✅.

---

### ST-05 — Trigger deploy on merge and verify pipeline is green ⬜ Pending ST-04

Ejecutar el primer push real al backend repo y verificar que todos los jobs pasan. Documentar la URL del primer deploy exitoso en Cloud Run.

---

## Follow-ups / Notes

- **`attribute-condition` en WIF:** El `assertion.repository` limita el token de WIF al repo exacto del backend. Si el repo se renombra, hay que actualizar esta condición.
- **`roles/run.developer` en dev/staging/prod:** El SA `github-actions` necesita este rol en los 3 proyectos para hacer `gcloud run deploy`. Confirmar si `motamaze-dev` y `motamaze-staging` ya tienen billing antes de asignar roles.
- **`roles/artifactregistry.writer` solo en `motamaze`:** AR vive en el proyecto prod — el SA solo necesita escribir ahí. Para leer la imagen en dev/staging/prod, Cloud Run usa el SA `game-api-backend` que necesita `roles/artifactregistry.reader` en `motamaze`.
- **Cache `type=gha` vs `type=registry`:** Usamos cache de GitHub Actions (gratuito) en lugar de cache en AR (genera egress). Para MVP es la opción correcta.
- **`pydantic-settings`:** Agregar como dependencia en `pyproject.toml` cuando se cree el backend repo (mencionado en INFRA-003 follow-ups).
- **Nombre del backend repo:** ✅ Confirmado 2026-06-22 — `juanmosqueda-ingeniouscruciblestudios/motamaze_backend` (guión bajo). WIF `attribute-condition` y `principalSet` actualizados. El repo ya existe y tiene acceso del equipo.
- **`deploy-cloudrun@v2` — input `project` eliminado:** La v2 del action no acepta `project` — el proyecto se pasa como `project_id:` en el step `google-github-actions/auth@v2`. Fix aplicado en commit `7889046` (2026-06-22).
- **Cloud Run Admin API en motamaze-dev:** Debe habilitarse antes del primer deploy. Requiere billing activo en el proyecto. Pendiente de Juan.
- **`--allow-unauthenticated`:** Requerido explícitamente en `flags:` del deploy step. Sin este flag, Cloud Run despliega el servicio como privado (requiere token GCP para invocar) en lugar de público.
