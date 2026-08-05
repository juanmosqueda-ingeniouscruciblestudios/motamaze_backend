# /jobs/* — Cloud Scheduler Auth (INFRA-007) — Estado actual

> Última actualización: 2026-08-05

Los 7 endpoints de `POST /jobs/*` (`admob-daily-report`, `reconcile-ad-revenue`,
`reconcile-purchases`, `purge-deleted-accounts`, `recalc-age-thresholds`, `recalc-level-stats`,
`recalc-achievement-rarities`) solo los debe poder llamar Cloud Scheduler. Dos capas de defensa,
independientes entre sí:

1. **Cloud Run IAM** (capa primaria) — solo la service account `game-api-backend@{project}` tiene
   `roles/run.invoker` sobre el servicio. Nadie más puede alcanzar la URL, punto.
2. **`verify_cloud_scheduler_oidc`** (defensa en profundidad, `app/routers/jobs.py`) — valida el
   token OIDC real que Cloud Scheduler adjunta, por si la capa 1 alguna vez se relaja (ej.
   `--no-invoker-iam-check`, ver más abajo).

---

## `verify_cloud_scheduler_oidc` — qué valida

```python
async def verify_cloud_scheduler_oidc(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
```

Aplicado a los 7 endpoints vía `dependencies=[Depends(verify_cloud_scheduler_oidc)]`.

1. **Header presente y con forma `Bearer <token>`** — si no, `403 JOBS_FORBIDDEN`.
2. **Firma y vigencia del token** — `google.oauth2.id_token.verify_oauth2_token(token,
   google_requests.Request(), audience=...)`. Descarga los certificados públicos de Google y valida
   firma + expiración + `aud` en una sola llamada (mismo patrón que
   `auth_service.verify_google_token` para Google Sign-In).
3. **`aud` = `settings.cloud_run_service_url`** — debe coincidir exacto con el `--oidc-token-audience`
   configurado en el Cloud Scheduler job. Un valor por ambiente (dev vs prod), confirmado idéntico en
   los 5-6 jobs existentes de cada uno antes de hardcodearlo.
4. **`email` del token = `game-api-backend@{settings.gcp_project_id}.iam.gserviceaccount.com`** y
   `email_verified = true` — no basta con que el token sea de Google, tiene que ser específicamente
   de nuestra service account de Cloud Scheduler. `settings.gcp_project_id` ya existe, así que el
   email esperado sale correcto por ambiente sin config nueva.

Cualquier falla en 1-4 devuelve el mismo `403 JOBS_FORBIDDEN` — no se filtra cuál validación falló.

---

## `--no-invoker-iam-check`

El servicio completo estaba inalcanzable sin token de identidad porque la org policy
`iam.allowedPolicyMemberDomains` bloquea `allUsers` en IAM — `--allow-unauthenticated` falla en
silencio. Eso rompía `GET /s/{token}` y `GET /ogimg/{token}` (T-440), que deben ser públicos para que
los crawlers de redes sociales generen el preview.

Fix (retargeteado por Juan 2026-08-03, verificado): `gcloud run services update motamaze-backend
--no-invoker-iam-check` quita el chequeo de invoker IAM a nivel de servicio — sin tocar la org
policy, sin escalar permisos. Confirmado 2026-08-05: `constraints/run.managed.requireInvokerIam` no
está forzada (`enforce: false`, ni a nivel proyecto ni heredado de la org) — este paso no necesita a
Juan.

**Por qué el orden importa:** este flag hace público *todo* el servicio, no solo `/s/*`. Por eso
`verify_cloud_scheduler_oidc` (arriba) tenía que existir *antes* de correr el comando — si no,
`/jobs/*` quedaría con cero protección real durante la ventana entre el flag y el hardening.

**Estado: aplicado y validado en DEV y PROD (2026-08-05, ST-04/ST-05).** `/jobs/*` sigue rechazando
llamadas sin token válido (`403 JOBS_FORBIDDEN` de la app, ya no de Cloud Run) en ambos ambientes; un
force-run real de Cloud Scheduler resuelve 200 en ambos; `/ogimg/healthcheck` y `/s/{token}` ya
responden con la lógica real de la app (`200`/`404`) en vez del `403` genérico de antes, también en
ambos.

> **Nota de debugging (ST-04, DEV):** el primer force-run real después de aplicar el flag en DEV
> falló (403, sin detalle) — `verify_cloud_scheduler_oidc` tragaba la excepción en silencio. Se
> agregó logging real de la excepción/mismatch (no cambia el comportamiento, solo la visibilidad);
> tras redesplegar, 3/3 force-runs sucesivos dieron 200. Todo apunta a un cold-start puntual bajando
> los certificados públicos de Google en la instancia recién creada tras el `service update` — sin
> confirmar al 100%, pero el fallo no fue reproducible y (a diferencia de PROD, ver abajo) el
> `audience` del token sí coincidía con el esperado. El logging se queda de forma permanente.

> **Bug real encontrado y corregido (ST-05, PROD):** el mismo force-run en PROD falló de forma
> **determinística** (3/3), no intermitente. El log mostró la causa exacta:
> `Token has wrong audience https://motamaze-backend-ghubi2atbq-uc.a.run.app, expected one of
> ['https://motamaze-backend-qxc5bjtn4q-uc.a.run.app']` — la revisión de prod estaba validando contra
> el URL de **DEV**. Causa raíz: `settings.cloud_run_service_url` (`app/config.py`) tiene como default
> el URL de dev, y `.github/workflows/cicd.yml` nunca seteaba `CLOUD_RUN_SERVICE_URL` como env var en
> ninguno de los dos `deploy` jobs (ST-03) — solo `GCP_PROJECT_ID`/`ENVIRONMENT`. DEV pasó ST-04 por
> pura coincidencia (el default hardcodeado resulta ser el URL real de dev); PROD no tuvo esa suerte.
> Corregido en dos pasos: parche en caliente (`gcloud run services update ... --update-env-vars`) para
> validar ST-05 el mismo día, y fix permanente agregando `CLOUD_RUN_SERVICE_URL` explícito a los
> `env_vars` de ambos jobs en `cicd.yml` (cada uno con su propio URL) para que el próximo deploy no
> revierta el parche.

---

## Limitaciones conocidas / a revisar

- **`admob-daily-report` y `reconcile-purchases` sin test dedicado** — gap preexistente, no
  introducido ni cerrado por INFRA-007.
- **5 de 8 jobs de `/jobs/*` están `PAUSED` en Cloud Scheduler de PROD** (`purge-deleted-accounts`,
  `reconcile-ad-revenue`, `recalc-age-thresholds`, `recalc-achievement-rarities`,
  `recalc-level-stats`) — encontrado al validar ST-05, fuera de alcance de este ticket. Varios (ej.
  `purge-deleted-accounts`, `recalc-age-thresholds`) no parecen deberían estar pausados; requiere
  ticket aparte para confirmar con Juan/producto si es intencional.
