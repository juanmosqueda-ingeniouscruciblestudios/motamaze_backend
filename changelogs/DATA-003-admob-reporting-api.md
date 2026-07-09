# DATA-003 — AdMob Reporting API Daily Job

| Field | Value |
|---|---|
| **Type** | Dataflow / External Integration |
| **Priority** | High — revenue KPI para go/no-go 2026-09-14 |
| **Status** | In Progress — ST-01 ✅ OAuth credentials en Secret Manager (2026-07-08); ST-02 ✅ Cloud Run job + Cloud Scheduler live (2026-07-09); ST-03 ⬜ verificar datos reales post soft-launch (2026-09-14) |
| **Date** | 2026-07-08 |
| **Workstream** | Dataflow & Outputs |
| **Depends-on** | EXT-002 ✅ (AdMob account), DATA-001 ✅ (BQ tables), INFRA-002 ✅ (Secret Manager) |
| **Desbloquea** | T-303 ST-03 (dashboards con datos reales de AdMob) |

---

## Descripción

Job diario que consulta la AdMob Reporting API y escribe los resultados en la tabla BQ `admob_daily_report`. La API no soporta service accounts — requiere OAuth 2.0 user credentials del propietario de la cuenta AdMob.

**Publisher ID:** `pub-9121176819960949`

---

## ST-01 — OAuth credentials setup ✅ Done (2026-07-08)

### Contexto: por qué OAuth 2.0 y no service account

La AdMob Reporting API requiere que el request esté autorizado por un usuario con acceso a la cuenta AdMob. Los service accounts no están soportados. Se usa OAuth 2.0 con refresh token de larga duración almacenado en Secret Manager.

### Clientes OAuth creados en GCP Console

| Cliente | Tipo | Propósito |
|---|---|---|
| `admob-reporting-job` | Desktop app | Reservado para uso futuro del job en runtime si se necesita re-autorizar |
| `admob-reporting-playground` | Web application | Usado en OAuth Playground para obtener el refresh token inicial |

**Redirect URI configurada en `admob-reporting-playground`:**
`https://developers.google.com/oauthplayground`

**JSON guardado en:** `C:\Empresas\ICS\motamaze\client_secret_OAuth_WebApplication.json` (fuera del repo, protegido)

### Scope autorizado

```
https://www.googleapis.com/auth/admob.readonly
```

### Cuenta que autorizó

`saulmorin@ingeniouscruciblestudios.com` (admin con acceso a la cuenta AdMob `pub-9121176819960949`)

### Secrets creados en Secret Manager (proyecto `motamaze`)

| Secret name | Versión activa | Contenido |
|---|---|---|
| `admob-oauth-client-id` | v2 | client_id del Web application client |
| `admob-oauth-client-secret` | v1 | client_secret del Web application client |
| `admob-oauth-refresh-token` | v1 | refresh_token obtenido vía OAuth Playground |

**Nota:** `admob-oauth-client-id` v1 tiene placeholder `TU_CLIENT_ID_AQUI` — deshabilitada el 2026-07-08.

### IAM — secretAccessor

Service Account `game-api-backend@motamaze.iam.gserviceaccount.com` tiene rol `roles/secretmanager.secretAccessor` en los 3 secrets.

### Comandos ejecutados

```powershell
# Habilitar API
gcloud services enable admob.googleapis.com --project=motamaze

# Secrets
echo $CLIENT_ID     | gcloud secrets versions add admob-oauth-client-id --data-file=- --project=motamaze
echo $CLIENT_SECRET | gcloud secrets create admob-oauth-client-secret --data-file=- --project=motamaze
echo $REFRESH_TOKEN | gcloud secrets create admob-oauth-refresh-token --data-file=- --project=motamaze

# Deshabilitar versión con placeholder
gcloud secrets versions disable 1 --secret=admob-oauth-client-id --project=motamaze

# IAM
$SA = "game-api-backend@motamaze.iam.gserviceaccount.com"
foreach ($secret in @("admob-oauth-client-id","admob-oauth-client-secret","admob-oauth-refresh-token")) {
  gcloud secrets add-iam-policy-binding $secret `
    --member="serviceAccount:$SA" `
    --role="roles/secretmanager.secretAccessor" `
    --project=motamaze
}
```

---

## ST-02 — Cloud Run job + Cloud Scheduler ✅ Done (2026-07-09)

Endpoint `POST /jobs/admob-daily-report` implementado en FastAPI:
1. Lee 3 secrets de Secret Manager (client_id, client_secret, refresh_token)
2. Construye `google.oauth2.credentials.Credentials` con el refresh token
3. Llama a `admob.v1.accounts.networkReport.generate` para `pub-9121176819960949`
4. Transforma la respuesta y hace batch insert en BQ `admob_daily_report` vía `stream_events`
5. Re-lee credenciales de SM automáticamente si el refresh falla (credential rotation)

**Cloud Scheduler:** job `admob-daily-report` en `us-central1`, schedule `0 8 * * *` UTC.
**Auth:** OIDC con SA `game-api-backend@motamaze.iam.gserviceaccount.com` → `*.run.app` URL.
**Verified:** force-run manual 2026-07-09 → 200 OK, 0 rows (esperado — sin impresiones reales aún).

**Gotchas resueltos:**
- Cloud Scheduler service agent debe crearse explícitamente: `gcloud beta services identity create --service=cloudscheduler.googleapis.com`
- OIDC audience debe ser el URL `*.run.app`, no el custom domain
- SA necesita `roles/run.invoker` en el Cloud Run service
- Secrets almacenados con pipe de PowerShell se truncan a 2 chars — usar `WriteAllText` con UTF8 sin BOM + `--data-file=<tempfile>`

---

## ST-03 — Verificar datos en BQ ⬜ Pendiente

Verificar que `admob_daily_report` recibe filas con datos reales de AdMob tras el primer run del job.

```sql
SELECT report_date, country, SUM(estimated_earnings_micros)/1e6 AS revenue_usd
FROM `motamaze.motamaze_analytics.admob_daily_report`
WHERE report_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY 1, 2
ORDER BY 1 DESC, 3 DESC
```
