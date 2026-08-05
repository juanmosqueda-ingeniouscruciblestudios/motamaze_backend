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

## `--no-invoker-iam-check` (ST-04/ST-05, pendiente)

El servicio completo hoy está inalcanzable sin token de identidad porque la org policy
`iam.allowedPolicyMemberDomains` bloquea `allUsers` en IAM — `--allow-unauthenticated` falla en
silencio. Eso rompe `GET /s/{token}` y `GET /ogimg/{token}` (T-440), que deben ser públicos para que
los crawlers de redes sociales generen el preview.

Fix (retargeteado por Juan 2026-08-03, verificado): `gcloud run services update motamaze-backend
--no-invoker-iam-check` quita el chequeo de invoker IAM a nivel de servicio — sin tocar la org
policy, sin escalar permisos. Confirmado 2026-08-05: `constraints/run.managed.requireInvokerIam` no
está forzada (`enforce: false`, ni a nivel proyecto ni heredado de la org) — este paso no necesita a
Juan.

**Por qué el orden importa:** este flag hace público *todo* el servicio, no solo `/s/*`. Por eso
`verify_cloud_scheduler_oidc` (arriba) tenía que existir *antes* de correr el comando — si no,
`/jobs/*` quedaría con cero protección real durante la ventana entre el flag y el hardening.

---

## Limitaciones conocidas / a revisar

- **`--no-invoker-iam-check` todavía no se ha corrido** ni en dev ni en prod (ST-04/ST-05) — hasta
  entonces, el servicio sigue privado y `/s/{token}`/`/ogimg/{token}` siguen sin funcionar para
  crawlers externos.
- **`admob-daily-report` y `reconcile-purchases` sin test dedicado** — gap preexistente, no
  introducido ni cerrado por INFRA-007.
