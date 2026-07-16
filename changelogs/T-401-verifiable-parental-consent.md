# T-401 — Verifiable Parental Consent: age-verify endpoint + is_child on LoginResponse

| Field | Value |
|---|---|
| **Type** | Feature / Compliance |
| **Priority** | High — COPPA + LATAM Wave 1 |
| **Status** | In Progress — ST-01 ✅ ST-02 ✅ ST-03 ✅ backend completo (2026-07-15); ST-04–05 ⬜ client (Juan); ST-06 ⬜ E2E |
| **Date** | 2026-07-14 |
| **Workstream** | Compliance / Auth |
| **Owner** | Juan + Saul |
| **Monday Item ID** | 12272094534 |
| **Timeline** | 2026-08-06 — 2026-08-12 |
| **Depends-on** | T-400 ✅ (resolve_country + consent_age_threshold), T-407 ✅ (LATAM Wave 1 thresholds) |
| **Desbloquea** | T-404 (monthly recalc), T-406 ST-02 (coppa_compliant activation) |

---

## Descripción

Implementa el flujo de age-gating para MotaMaze. El cliente envía la fecha de nacimiento del usuario → el backend calcula si es menor según el threshold del país → persiste `is_child` y `restricted_features` en Firestore → el cliente recibe `is_child` en cada LoginResponse para adaptar la UI.

**Modelo legal (email-plus VPC per FTC COPPA guidance):**
- Email-plus es válido solo para data processing de uso interno. NO autoriza: personalized ads, leaderboard público, share-score.
- Menores permanecen en el restricted tier independientemente del status del email-plus (ST-03).
- El sentence en Terms of Service "By allowing a child to use the Game, the parent or guardian accepts..." es contract-formation language únicamente — NO satisface COPPA como VPC method.

---

## ST-01 — `POST /auth/age-verify` ✅ (2026-07-14)

### `app/routers/auth.py`

**Nuevos modelos:**
```python
class AgeVerifyRequest(BaseModel):
    dob: str  # YYYY-MM-DD

class AgeVerifyResponse(BaseModel):
    is_child: bool
    consent_age_threshold: int
```

**Endpoint `POST /auth/age-verify`** (requiere JWT via `verify_jwt`):

1. Parsea `body.dob` con `date.fromisoformat()` → 400 si formato inválido
2. Valida: fecha no puede ser futura, edad no puede superar 120 años
3. Calcula edad exacta: `age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))`
4. Lee `users/{uid}.consent.consent_age_threshold` de Firestore (default 13 si no existe)
5. Computa `is_child = age < threshold`
6. Escribe en Firestore `users/{uid}`:
   - `consent.is_child: bool`
   - `consent.age_verified_at: datetime`
   - `restricted_features: {leaderboard, personalized_ads, share_score}` ← todos `is_child`
7. Retorna `{is_child, consent_age_threshold}`

**Por qué no se almacena el DOB:** Data minimization (COPPA / LGPD Art. 14 / LFPDPPP). Solo se persiste el resultado (`is_child`) y la fecha de verificación. El raw DOB no es necesario post-cálculo.

**`restricted_features` por valor de `is_child`:**

| Feature | is_child=True | is_child=False |
|---|---|---|
| `leaderboard` | `True` (restringido) | `False` |
| `personalized_ads` | `True` (restringido) | `False` |
| `share_score` | `True` (restringido) | `False` |

Restricciones permanecen `True` para menores **incluso después del email-plus VPC** (ST-03) — per FTC guidance, email-plus no autoriza disclosure a terceros ni public display.

---

## ST-02 — `is_child` en LoginResponse ✅ (2026-07-14)

### `app/routers/auth.py`

`LoginResponse` actualizado:
```python
class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 900
    user_id: str
    is_new_user: bool
    is_child: bool | None = None  # None hasta que el usuario complete /age-verify
```

`login()` actualizado para desempacar el tercer valor de `upsert_user`:
```python
user_id, is_new_user, is_child = await auth_service.upsert_user(...)
return LoginResponse(..., is_child=is_child)
```

### `app/services/auth_service.py`

`upsert_user` firma y return type actualizados:
```python
async def upsert_user(...) -> tuple[str, bool, bool | None]:
```

- **Usuario nuevo:** Firestore set incluye `consent.is_child: None`. Retorna `(sub, True, None)`.
- **Usuario existente:** Lee `is_child` del snap pre-existente (0 reads extra — el snap ya fue leído para el `is_new` check). Retorna `(sub, False, is_child)`.

**Por qué 0 reads adicionales:** `upsert_user` ya hace `snap = await ref.get()` para detectar usuario nuevo/existente. `is_child` se extrae de ese mismo snap. No hay segundo round-trip a Firestore en el hot path del login.

---

## Testing (2026-07-14)

### Syntax check

```
SYNTAX OK: app/routers/auth.py
SYNTAX OK: app/services/auth_service.py
```

### Tests lógica pura — 25/25 PASS

```
[PASS] Bad format       ERROR:INVALID_DOB
[PASS] Future date      ERROR:FUTURE_DATE
[PASS] Implausible      ERROR:IMPLAUSIBLE
[PASS] US  10yo < 13   is_child=True
[PASS] PE  10yo < 14   is_child=True
[PASS] AR  10yo < 16   is_child=True
[PASS] BR  10yo < 18   is_child=True
[PASS] US  13yo < 13   is_child=False
[PASS] PE  13yo < 14   is_child=True
[PASS] AR  13yo < 16   is_child=True
[PASS] BR  13yo < 18   is_child=True
[PASS] US  16yo        is_child=False
[PASS] PE  16yo        is_child=False
[PASS] AR  16yo < 16   is_child=False
[PASS] MX  16yo < 18   is_child=True
[PASS] BR  18yo < 18   is_child=False
[PASS] MX  18yo < 18   is_child=False
[PASS] Child: leaderboard=True
[PASS] Child: personalized_ads=True
[PASS] Child: share_score=True
[PASS] Adult: leaderboard=False
[PASS] Adult: personalized_ads=False
[PASS] Adult: share_score=False
[PASS] ST-02 new user is_child=None
[PASS] ST-02 existing is_child propagado

RESULT: 25/25 passed
```

---

## ST-03 — Parental consent email flow ✅ (2026-07-15)

**Servicio:** SendGrid (aprobado Juan+Saul). Dependencia: `sendgrid>=6.11` agregada a `pyproject.toml`.

### `app/config.py`

```python
sendgrid_api_key: str = ""               # env var SENDGRID_API_KEY (Secret Manager)
sendgrid_from_email: str = "noreply@motamaze.com"  # requires SendGrid domain verification
parental_consent_base_url: str = "https://api.motamaze.com"
```

### `app/services/email_service.py` (nuevo)

Función pública `send_parental_consent_email(to_email, child_name, consent_url, api_key, from_email)`.
Llama a SendGrid vía `asyncio.to_thread` para no bloquear el event loop.

**Si Juan aprueba un servicio diferente:** solo cambia el cuerpo de `_send_sync()` — contrato del endpoint y schema Firestore no varían.

### Firestore — colección `parental_consents/{consent_token}`

| Campo | Tipo | Valor |
|---|---|---|
| `uid` | str | UID del menor |
| `parent_email` | str | Email del padre/tutor |
| `created_at` | datetime | Momento de la solicitud |
| `expires_at` | datetime | `created_at + 72h` |
| `status` | str | `"pending"` → `"approved"` |

Token: `secrets.token_urlsafe(32)` — 256 bits de entropía, URL-safe.

### `POST /auth/parental-consent/request` (autenticado — JWT del menor)

Request: `{ "parent_email": "parent@example.com" }`

Flujo:
1. Valida formato de email (`@` + `.` después del `@`)
2. Lee `users/{uid}` — verifica que `consent.is_child == True`
3. Guard: si `consent.coppa_compliant == True`, retorna 200 temprano (idempotente)
4. Crea `parental_consents/{token}` en Firestore
5. Envía email via SendGrid — si falla: 503 `CONSENT_EMAIL_FAILED`
6. Retorna 202 `{"message": "Consent email sent"}`

**Contenido del email:** identifica al operador (Ingenious Crucible Studios), describe qué datos se recopilan, link de verificación (72h), instrucción para ignorar si no esperaban el email.

### `GET /auth/parental-consent/verify?token={token}` (público — link del email)

Retorna HTML. Flujo:

| Estado del token | Respuesta |
|---|---|
| No encontrado | 404 HTML — "Link Not Found" |
| Expirado (`now > expires_at`) | 410 HTML — "Link Expired" |
| `status == "approved"` | 200 HTML — "Already approved" |
| `status == "pending"` | Marca `approved`, actualiza Firestore user, 200 HTML — "Thank you" |

Al aprobar, escribe en `users/{uid}`:
- `consent.coppa_compliant = True`
- `consent.parental_consent_verified_at = now`

**Nota COPPA:** `restricted_features` (leaderboard / personalized_ads / share_score) NO se modifican — permanecen `True` para menores incluso después del VPC, per FTC guidance (email-plus solo autoriza procesamiento interno).

### Testing — 20/20 PASS

```
[PASS] token length >= 43 chars
[PASS] token URL-safe (no +/=)
[PASS] valid email: parent@gmail.com
[PASS] valid email subdomain: a@b.co.uk
[PASS] no @ sign -> invalid
[PASS] no dot after @ -> invalid
[PASS] empty -> invalid
[PASS] expires in 72h (259200s)
[PASS] XSS escaped in email HTML (<script> -> &lt;script&gt;)
[PASS] escaped name present in HTML
[PASS] consent URL format
[PASS] success page: green color (#1a7340)
[PASS] success page: approval message
[PASS] success page: no external JS
[PASS] already_done: different message
[PASS] already_done: detail text
[PASS] error page: red color (#b91c1c)
[PASS] error page: title rendered
[PASS] error page: contact email
[PASS] error page: no external JS
RESULT: 20/20 passed
```

### GCP Secret Manager + Cloud Run deployment (2026-07-15)

```bash
# Paso 1 — Crear secret
gcloud secrets create sendgrid-api-key --project=motamaze
# Created secret [sendgrid-api-key].

# Paso 2 — Agregar API key como versión 1
$key = "<API_KEY>"
[System.Text.Encoding]::UTF8.GetBytes($key) |
  gcloud secrets versions add sendgrid-api-key --data-file=- --project=motamaze
# Created version [1] of the secret [sendgrid-api-key].

# Paso 3 — IAM: secretAccessor para Cloud Run SA
gcloud secrets add-iam-policy-binding sendgrid-api-key `
  --member="serviceAccount:game-api-backend@motamaze.iam.gserviceaccount.com" `
  --role="roles/secretmanager.secretAccessor" `
  --project=motamaze
# Updated IAM policy for secret [sendgrid-api-key].
# bindings: serviceAccount:game-api-backend@motamaze.iam.gserviceaccount.com
#   role: roles/secretmanager.secretAccessor

# Paso 4 — Montar como env var en Cloud Run
gcloud run services update motamaze-backend `
  --update-secrets=SENDGRID_API_KEY=sendgrid-api-key:latest `
  --region=us-central1 `
  --project=motamaze
# Done. Service [motamaze-backend] revision [motamaze-backend-00066-5mb]
# serving 100 percent of traffic.
```

**Verificación post-deployment:**

```
gcloud secrets versions list sendgrid-api-key --project=motamaze
NAME  STATE    CREATED                  DESTROYED
1     enabled  2026-07-16T00:00:39      –

gcloud run services describe motamaze-backend --region=us-central1 --project=motamaze \
  --format="value(spec.template.spec.containers[0].env)"
{'name': 'GCP_PROJECT_ID', 'value': 'motamaze'}
{'name': 'ENVIRONMENT', 'value': 'prod'}
{'name': 'SENDGRID_API_KEY', 'valueFrom': {'secretKeyRef': {'key': 'latest', 'name': 'sendgrid-api-key'}}}
```

`SENDGRID_API_KEY` confirmado en Cloud Run prod. Secret version 1 enabled. Revisión `motamaze-backend-00066-5mb` sirviendo 100% tráfico.

## Pending (ST-04 a ST-06)

- **ST-04/ST-05 — Client (Juan):** Pantalla DOB intake + UI parental consent + waiting state.
- **ST-06 — E2E:** 7 países (US, BR, MX, AR, PE, UY + default).

## Follow-ups / Notes

- **`age_verified` en BQ `login_events`:** Actualmente hardcodeado `False`. Para reflejarlo correctamente en BQ habría que leer `consent.age_verified_at` en cada login — diferido como optimización, no es crítico para MVP.
- **Re-verificación:** Si el usuario completa `/age-verify` más de una vez (cumpleaños, corrección de DOB), `is_child` y `restricted_features` se sobreescriben. No hay historial de cambios — diseño intencional por data minimization.
- **T-404 (monthly recalc):** Cuando un usuario pasa del threshold en su cumpleaños, el monthly recalc job actualizará `is_child` sin que el usuario tenga que re-ingresar el DOB — pero para esto T-404 necesitará almacenar el año de nacimiento. Revisar si se requiere guardar `dob_year` para ese job (decisión diferida a T-404).
