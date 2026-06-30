# T-115 — Cloud Monitoring + Alertas + Kill Switch

| Field | Value |
|---|---|
| **Type** | Infra/DevOps |
| **Priority** | High — visibilidad operacional antes del lanzamiento |
| **Status** | Done — ST-01 ✅ dashboard, ST-02 ✅ alertas, ST-03 ✅ kill switch, ST-04 ✅ notificaciones |
| **Date** | 2026-06-30 |
| **Workstream** | INFRA-003 (Cloud Run), GCP infra |
| **Depends-on** | INFRA-003 ✅ (Cloud Run service live), INFRA-001 ✅ (GCP base infra) |
| **Project** | `motamaze` (prod) |

---

## Descripción

Instrumentación de observabilidad del backend de producción. Cubre: dashboard de métricas Cloud Run, alertas en errores 5xx y latencia alta, uptime check del endpoint `/health`, y un mecanismo de kill switch via Pub/Sub para desactivar el servicio en una emergencia.

**APIs requeridas (ya habilitadas en INFRA-001):**
- `monitoring.googleapis.com` ✅
- `logging.googleapis.com` ✅
- `pubsub.googleapis.com` ✅

**Nota:** Cloud Run exporta automáticamente logs a Cloud Logging y métricas a Cloud Monitoring — sin configuración adicional.

---

## Recursos creados en `motamaze` (prod)

| Recurso | Nombre / ID | Descripción |
|---|---|---|
| Notification channel | `projects/motamaze/notificationChannels/16560505641067632536` | Email → `saulmorin@ingeniouscruciblestudios.com` |
| Uptime check | `motamaze-backend-health-XHKYcpapSgM` | GET /health cada 5 min desde 4 regiones |
| Alert: uptime | `9166439286601640760` | /health down → email inmediato |
| Alert: 5xx spike | `5604600316883774785` | >5 errores 5xx/min sostenidos 5 min |
| Alert: latency | `4761460836571750795` | p99 > 5000 ms sostenido 5 min |
| Dashboard | `59e0ad9d-36c9-48b3-893d-10e945f1f75b` | Request rate, 5xx, latency p50/p95/p99, instances |
| Pub/Sub topic | `projects/motamaze/topics/motamaze-kill-switch` | Kill switch activation channel |
| Pub/Sub subscription | `motamaze-kill-switch-monitor` | Monitor de activaciones del kill switch |

---

## Implementación — Subtareas

### ST-01 — Cloud Monitoring dashboard + centralized logs ✅ Done (2026-06-30)

**Logs:** Cloud Run exporta automáticamente a Cloud Logging — sin setup adicional.
Para ver logs: `gcloud logging read 'resource.type="cloud_run_revision"' --project=motamaze --limit=50`

**Dashboard:** `MotaMaze Backend` creado via Cloud Monitoring Dashboards API v1.

4 widgets:
1. **Request Rate** — req/s por `response_code_class` (2xx, 4xx, 5xx, etc.)
2. **5xx Error Rate** — solo 5xx en req/s
3. **Request Latency** — p50, p95, p99 en ms
4. **Active Instances** — instancias Cloud Run activas

Dashboard ID: `projects/542009654415/dashboards/59e0ad9d-36c9-48b3-893d-10e945f1f75b`

```bash
# Acceder via Cloud Console:
# https://console.cloud.google.com/monitoring/dashboards?project=motamaze
```

---

### ST-02 — Alertas en 5xx y uptime ✅ Done (2026-06-30)

**Uptime check creado:**
```bash
gcloud monitoring uptime create "motamaze-backend-health" \
  --resource-type=uptime-url \
  --resource-labels="host=motamaze-backend-ghubi2atbq-uc.a.run.app,project_id=motamaze" \
  --path=/health \
  --port=443 \
  --protocol=https \
  --validate-ssl=true \
  --period=5 \
  --timeout=10 \
  --regions=usa-oregon,usa-virginia,europe,asia-pacific \
  --project=motamaze
```

**3 alert policies creadas via Cloud Monitoring REST API:**

| Alert | Condición | Duración |
|---|---|---|
| `/health down` | check_passed < 1 en uptime check | 60s |
| `5xx spike` | 5xx > 5/min (ALIGN_RATE + REDUCE_SUM) | 300s sostenido |
| `p99 latency > 5s` | request_latencies REDUCE_PERCENTILE_99 > 5000ms | 300s sostenido |

Todas las alertas → `saulmorin@ingeniouscruciblestudios.com` vía channel `16560505641067632536`.

---

### ST-03 — Pub/Sub kill switch ✅ Done (2026-06-30)

**Topic y subscription creados:**

```bash
gcloud pubsub topics create motamaze-kill-switch --project=motamaze
gcloud pubsub subscriptions create motamaze-kill-switch-monitor \
  --topic=motamaze-kill-switch \
  --ack-deadline=60 \
  --project=motamaze
```

**Para activar el kill switch (desactivar el backend):**

```bash
# Paso 1: Notificar via Pub/Sub (genera audit trail en Cloud Logging)
gcloud pubsub topics publish motamaze-kill-switch \
  --message='{"action":"disable","reason":"<motivo>","triggered_by":"<nombre>"}' \
  --project=motamaze

# Paso 2: Escalar Cloud Run a 0 instancias
gcloud run services update motamaze-backend \
  --max-instances=0 \
  --project=motamaze \
  --region=us-central1

# Para reactivar:
gcloud run services update motamaze-backend \
  --max-instances=100 \
  --project=motamaze \
  --region=us-central1
```

**Audit trail:** El mensaje en el topic queda en Cloud Logging vía `data_access` audit logs. La subscription `motamaze-kill-switch-monitor` retiene los mensajes 7 días.

**Evolución v1.1 (opcional):** Agregar Eventarc trigger que ejecute el scale-down automáticamente al recibir el mensaje — elimina el paso manual.

---

### ST-04 — Routing de alertas al equipo ✅ Done (2026-06-30)

**Notification channel creado:**

```bash
# Via Cloud Monitoring REST API:
POST https://monitoring.googleapis.com/v3/projects/motamaze/notificationChannels
{
  "type": "email",
  "displayName": "MotaMaze Alerts — Saul",
  "labels": {"email_address": "saulmorin@ingeniouscruciblestudios.com"},
  "enabled": true
}
# → projects/motamaze/notificationChannels/16560505641067632536
```

**Para agregar a Juan:**
```bash
# Obtener token y ejecutar:
curl -X POST https://monitoring.googleapis.com/v3/projects/motamaze/notificationChannels \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -d '{"type":"email","displayName":"MotaMaze Alerts — Juan","labels":{"email_address":"<juan-email>"},"enabled":true}'

# Luego actualizar cada alert policy para incluir el nuevo channel:
# Cloud Console → Monitoring → Alerting → editar cada política → añadir notification channel
```

---

## Verificación final

```bash
# Uptime checks
gcloud monitoring uptime list-configs --project=motamaze
# → motamaze-backend-health-XHKYcpapSgM

# Alert policies
# → motamaze-backend: /health down
# → motamaze-backend: 5xx spike
# → motamaze-backend: high latency p99 > 5s

# Pub/Sub
gcloud pubsub topics list --project=motamaze
# → projects/motamaze/topics/motamaze-kill-switch
gcloud pubsub subscriptions list --project=motamaze
# → motamaze-kill-switch-monitor (ACTIVE)
```

---

## Follow-ups / Notes

- **Juan al canal de alertas:** Agregar email de Juan al notification channel cuando se confirme su email.
- **Kill switch automático (v1.1):** Eventarc trigger en `motamaze-kill-switch` topic → Cloud Run job que ejecuta scale-to-0 automáticamente.
- **Log-based alerts:** Para alertas específicas por endpoint (ej: `/auth/login` 5xx vs `/payments` 5xx), usar log-based metrics + alertas adicionales — fuera de scope MVP.
- **SLO:** Definir SLO formal (ej: 99.5% uptime, p95 < 1s) en v1.1 con Cloud Monitoring SLO feature.
- **Alertas en dev:** Aplicar las mismas configuraciones al proyecto `motamaze-dev` cuando INFRA-006 ST-04 complete el `terraform apply dev`.
