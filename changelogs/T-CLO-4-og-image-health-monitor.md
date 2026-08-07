# T-CLO-4 — Health monitor OG images (Cloud Monitoring uptime check + alert)

| Field | Value |
|---|---|
| **Type** | Infra/DevOps |
| **Priority** | Medium — detecta si el flujo de share-preview (T-440) se rompe en producción antes de que un jugador lo reporte |
| **Status** | ✅ Done — ST-01, ST-02, ST-03 |
| **Date** | 2026-08-07 |
| **Workstream** | Infra/DevOps |
| **Owner** | Saul Zavala Morin |
| **Monday.com Item ID** | 12397971832 |
| **Depends on** | INFRA-007 ✅ (sin él, `/ogimg/*` daba 403 genérico de Cloud Run sin importar el token — el health check no habría podido distinguir "servicio caído" de "org policy bloqueando todo") |
| **Project** | `motamaze` (prod) |

---

## Descripción

`GET /ogimg/{token}` (T-440) es un proxy de redirect: si el token no existe en Firestore, cae a una
imagen base de Cloudinary vía `302`. `/ogimg/healthcheck` explota eso a propósito — `"healthcheck"`
nunca va a existir como token real, así que siempre toma la rama de fallback. Es la URL canaria
perfecta para un uptime check: si alguna vez deja de responder `302`, algo se rompió en el proxy
(Firestore, la construcción de la URL, o acceso público al servicio — exactamente lo que pasó con
INFRA-007).

Bloqueado desde 2026-07-30 porque esa misma URL daba `403` sin importar el token mientras
INFRA-007 estuviera sin resolver — no tenía sentido armar el monitor hasta que el 403 dejara de ser
el comportamiento normal. Cerrado INFRA-007 (2026-08-05/07), retomado hoy.

---

## Implementación

### ST-01 — Confirmar que la URL canaria responde 200 (via 302 → Cloudinary)

```bash
curl -s -o /dev/null -w "HTTP:%{http_code}\n" -L "https://motamaze-backend-ghubi2atbq-uc.a.run.app/ogimg/healthcheck"
# HTTP:200 (redirect chain)
```

Confirmado en prod y dev.

### ST-02 — Uptime check en Cloud Monitoring

Mismo patrón que T-115's `/health` check, con una diferencia importante: **los uptime checks de GCP
no siguen redirects** — por default solo aceptan `2xx`, así que un `302` real se vería como falla.
Configurado para aceptar `302` explícitamente en vez de perseguir el `200` final de Cloudinary — eso
prueba que *nuestra* lógica de redirect funciona (que es lo que este ticket existe para vigilar);
que Cloudinary en sí esté arriba es un dominio de falla distinto, con su propio SLA, fuera de
nuestro control.

```bash
gcloud monitoring uptime create "motamaze-backend-ogimg-healthcheck" \
  --resource-type=uptime-url \
  --resource-labels="host=motamaze-backend-ghubi2atbq-uc.a.run.app,project_id=motamaze" \
  --path=//ogimg/healthcheck \
  --port=443 --protocol=https --validate-ssl=true \
  --status-codes=302 \
  --period=5 --timeout=10 \
  --regions=usa-oregon,usa-virginia,europe,asia-pacific \
  --project=motamaze
```

**Nota sobre `--path=//ogimg/healthcheck` (doble slash):** Git Bash (MSYS) reescribe automáticamente
cualquier argumento que empiece con `/` como una ruta de Windows antes de pasarlo a `gcloud` — el
primer intento con `--path=/ogimg/healthcheck` terminó guardado literalmente como
`/C:/Program Files/Git/ogimg/healthcheck`. El truco estándar de MSYS (`//` en vez de `/`) evita la
reescritura; verificado con `curl` que el backend resuelve `//ogimg/healthcheck` idéntico a
`/ogimg/healthcheck` (normalización estándar de slashes), así que el check funciona correctamente
con la ruta con doble slash tal como quedó guardada.

**Bug real encontrado de paso:** el check de `/health` de T-115 (2026-06-30) tenía el mismo problema
— corriendo desde hace más de un mes con `path = "/C:/Program Files/Git/health"` en vez de
`/health`. Corregido en el mismo pase:

```bash
gcloud monitoring uptime update "projects/motamaze/uptimeCheckConfigs/motamaze-backend-health-XHKYcpapSgM" \
  --path="//health" --project=motamaze
```

### ST-03 — Alert policy

Mismo notification channel que T-115 (`saulmorin@ingeniouscruciblestudios.com`,
`projects/motamaze/notificationChannels/16560505641067632536`), vía Cloud Monitoring REST API
(mismo patrón que T-115 ST-02/ST-04).

**Hallazgo al crear esta alerta:** el filtro original de la alerta de `/health` (`resource.type=
"uptime_url"` agrupado por `resource.labels.host`) no distinguía por `check_id` — con un solo uptime
check en el host no importaba, pero al agregar un segundo check en el mismo host (`ogimg`), ambas
alertas habrían empezado a dispararse por fallas del otro check. Corregido agregando
`metric.label."check_id"="<check-id>"` al filtro de **ambas** alertas (la nueva y la de T-115), no
solo la nueva.

```bash
# Alerta nueva (ogimg)
curl -X POST "https://monitoring.googleapis.com/v3/projects/motamaze/alertPolicies" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" -H "Content-Type: application/json" \
  -d '{
    "displayName": "motamaze-backend: /ogimg/healthcheck down",
    "combiner": "OR",
    "conditions": [{
      "displayName": "/ogimg/healthcheck unreachable from 2+ regions",
      "conditionThreshold": {
        "filter": "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\" AND metric.label.\"check_id\"=\"motamaze-backend-ogimg-healthcheck-TdlbkY0nIgk\"",
        "comparison": "COMPARISON_LT", "thresholdValue": 1, "duration": "60s",
        "aggregations": [{"alignmentPeriod": "60s", "perSeriesAligner": "ALIGN_NEXT_OLDER",
          "crossSeriesReducer": "REDUCE_COUNT_TRUE", "groupByFields": ["resource.labels.host"]}]
      }
    }],
    "notificationChannels": ["projects/motamaze/notificationChannels/16560505641067632536"],
    "enabled": true
  }'

# Retrofit de la alerta existente de /health (T-115) con el mismo filtro por check_id
curl -X PATCH "https://monitoring.googleapis.com/v3/projects/motamaze/alertPolicies/9166439286601640760?updateMask=conditions" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" -H "Content-Type: application/json" \
  -d '{"conditions": [{"displayName": "/health unreachable from 2+ regions", "conditionThreshold": {
    "filter": "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\" AND metric.label.\"check_id\"=\"motamaze-backend-health-XHKYcpapSgM\"",
    "comparison": "COMPARISON_LT", "thresholdValue": 1, "duration": "60s",
    "aggregations": [{"alignmentPeriod": "60s", "perSeriesAligner": "ALIGN_NEXT_OLDER",
      "crossSeriesReducer": "REDUCE_COUNT_TRUE", "groupByFields": ["resource.labels.host"]}]
  }}]}'
```

---

## Recursos creados/modificados en `motamaze` (prod)

| Recurso | Nombre / ID | Descripción |
|---|---|---|
| Uptime check (nuevo) | `motamaze-backend-ogimg-healthcheck-TdlbkY0nIgk` | GET `//ogimg/healthcheck` cada 5 min desde 4 regiones, acepta `302` |
| Alert policy (nueva) | `10844126409489282318` | `/ogimg/healthcheck` down → email, filtrada por `check_id` |
| Uptime check (corregido) | `motamaze-backend-health-XHKYcpapSgM` | Path arreglado: `/C:/Program Files/Git/health` → `/health` |
| Alert policy (corregida) | `9166439286601640760` | Filtro ahora incluye `check_id` para no mezclarse con la alerta de ogimg |

---

## Testing

```bash
gcloud monitoring uptime list-configs --project=motamaze
gcloud monitoring uptime describe "projects/motamaze/uptimeCheckConfigs/motamaze-backend-ogimg-healthcheck-TdlbkY0nIgk" --project=motamaze --format=json
```

Verificado manualmente que `//ogimg/healthcheck` y `//health` resuelven idéntico a sus rutas de un
solo slash (`302` y `200` respectivamente) — la normalización de slashes del servidor hace que la
ruta con doble slash guardada en el check funcione igual que la real.

No se corrió test automatizado (no hay código de repo involucrado — todo es configuración de GCP).

---

## Follow-ups / notes

- **Primer ciclo real de chequeo pendiente de observar** — el período es de 5 min desde 4 regiones;
  recién creado, no hay todavía datos históricos que confirmar en el dashboard.
- **Solo en PROD** — mismo patrón que T-115 (su propio follow-up ya decía "aplicar las mismas
  configuraciones a `motamaze-dev` cuando INFRA-006 ST-04 complete el `terraform apply dev`" — sigue
  sin hacerse, no es parte de este ticket).
- **El bug del path mangleado por Git Bash puede repetirse** — cualquier comando futuro de `gcloud`
  con un flag que empiece con `/` corre este mismo riesgo en este entorno. Usar `//` como prefijo o
  verificar con `describe` después de crear/actualizar.
