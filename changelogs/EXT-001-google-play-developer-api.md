# EXT-001 — Enable Google Play Developer API + Play Console SA Invite

| Campo | Valor |
|---|---|
| **Tipo** | External Services / Setup |
| **Prioridad** | Alta — 24h lag de activación |
| **Status** | In Progress — ST-01 ✅, ST-02 ✅, ST-03 🔄 parcial (app draft creada, vínculo GCP bloqueado — Juan owner requerido), ST-04–06 ⬜ |
| **Fecha planeada** | 2026-06-15 |
| **Fecha real inicio** | 2026-06-16 |
| **Workstream** | External Services |
| **Owner** | Saul Zavala Morin |
| **Monday.com Item ID** | 12272254776 |
| **Depends on** | INFRA-001 (GCP base infra) ✅ |
| **Desbloquea** | POST /payments/android/verify (PAY-001, timeline 7/7–7/8), Daily reconciliation job (PAY-002) |

---

## Descripción

El backend de MotaMaze necesita verificar server-side cada compra de Android antes de otorgar entitlements. El flujo es:

```
[Godot Client]
    │  compra via Play Billing SDK → purchase_token
    ▼
[POST /payments/android/verify]
    │  llama Google Play Developer API
    ▼
[Play Developer API]
    │  verifica: token válido, no consumido, no refund
    ▼
[Backend]  otorga entitlement + acknowledge en Play
```

Sin la API activa y el service account autorizado en Play Console, el backend no puede llamar a la API — cualquier IAP sería unverifiable y la arquitectura server-authoritative de pagos quedaría sin implementar.

**Por qué "Day 1" y por qué urge:**
Google Play Console tarda **hasta 24 horas** en propagar los permisos de un service account recién invitado. Si no se hace hoy, el trabajo de PAY-001 (que empieza el 7/7) podría bloquearse esperando que los permisos propaguen. Además, la API `androidpublisher.googleapis.com` misma puede tomar minutos en activarse. Cada hora de retraso hoy comprime el margen de maniobra en julio.

---

## Criterios de aceptación

- [x] `androidpublisher.googleapis.com` habilitada en proyecto `motamaze` (2026-06-16)
- [x] Cuenta Google Play Developer verificada por Google (2026-06-23) — botón "Create app" activo
- [ ] App draft creada en Play Console + proyecto GCP `motamaze` vinculado (ST-03 — listo para ejecutar)
- [ ] SA `game-api-backend` invitado en Play Console con permisos de verificación de compras (ST-04)
- [ ] 24h de espera transcurridas desde el invite (ST-05)
- [ ] Llamada de prueba a la API retorna 200 (no 401/403) (ST-06)

---

## Estado previo

- `androidpublisher.googleapis.com`: **NO habilitada** (verificado 2026-06-16)
- SA `game-api-backend`: sin acceso a Play Console
- Play Console: estado desconocido — necesita verificación

---

## Implementación — Subtareas

### ST-01 — Habilitar `androidpublisher.googleapis.com` en GCP ✅ Done (2026-06-16)

**Comando ejecutado:**
```bash
gcloud services enable androidpublisher.googleapis.com --project=motamaze
# Operation finished successfully.
```

**Verificación:**
```
NAME                             TITLE                              STATE
androidpublisher.googleapis.com  Google Play Android Developer API  ENABLED
```

---

### ST-02 — Confirmar existencia de cuenta Google Play Developer y app en Play Console 🔄 In Progress (2026-06-17)

**Por qué:** Necesitamos saber:
1. ¿Existe ya una cuenta de Google Play Developer para Ingenious Crucible Studios?
2. ¿Existe la app MotaMaze (aunque sea en estado draft)?
3. ¿Cuál es el `packageName` de la app? (necesario para todas las llamadas a la API, ej: `com.ingeniouscrucible.motamaze`)

**Acción:** Revisar en **play.google.com/console** con la cuenta del estudio. Si no hay cuenta, hay que crear una (costo único: $25 USD).

**Resultado (2026-06-17):** ✅ Cuenta Google Play Developer creada y verificada.
- **Org name:** Ingenious Crucible Studios (Organization account)
- **Developer Account ID:** `5099504302304988454`
- **Package name:** `com.ingeniouscruciblestudios.motamaze` ✅ Definido 2026-06-17
- **Estado:** Google verificando identidad — documentos subidos, puede tomar algunos días
- **Pendiente (Juan):** Verify organization's website + Verify phone numbers
- **Acceso Saul:** ✅ confirmado vía Play Console

---

### ST-03 — Vincular proyecto GCP a Play Console ⬜ Listo para ejecutar (desbloqueado 2026-06-23)

**Por qué:** Play Console necesita saber qué proyecto GCP puede hacer llamadas a la API en nombre de la cuenta. Esto se configura en Settings → API access (la sección aparece solo cuando hay al menos una app registrada).

**Historial del bloqueador:**
- 2026-06-17: Botón "Create app" deshabilitado — Google verificando identidad de ICS
- 2026-06-22: Juan completó "Verify organization's website" + "Verify phone numbers" — bloqueador 100% externo
- **2026-06-23: ✅ Google completó la verificación** — botón "Create app" activo confirmado por Saul (Play Console → Home, org "Ingenious Crucible Studios", Account ID `5099504302304988454`)

**App draft creada (2026-06-23):** MotaMaze / `com.ingeniouscruciblestudios.motamaze` / Game / Free — app visible en Play Console Dashboard.

**Paso 2 bloqueado — API access requiere owner:** La sección Settings → Developer account → API access no aparece para colaboradores, solo para el owner de la cuenta (Juan). Juan debe vincular el proyecto GCP `motamaze` desde su sesión.

**Flujo en consola (manual — una vez desbloqueado):**
1. Crear app draft: Play Console → Home → "Create app" → MotaMaze / Game / Free / `com.ingeniouscruciblestudios.motamaze`
2. Play Console → **Settings** → **API access**
3. Sección "Link to a Google Cloud Project" → seleccionar proyecto `motamaze`
4. Confirmar el vínculo

**Nota importante:** Solo se puede vincular **un proyecto GCP por cuenta de Play Console**. Si Juan ya vinculó otro proyecto, hay que evaluarlo.

---

### ST-04 — Invitar `game-api-backend` SA a Play Console ⬜ Pending

**Por qué:** Habilitar la API en GCP no es suficiente — Play Console tiene su propio sistema de permisos sobre quién puede llamar a la API. El SA debe ser "invitado" explícitamente con los permisos mínimos necesarios.

**Permisos requeridos para verificación de IAP:**

| Permiso en Play Console | Para qué |
|---|---|
| View app information (read-only) | Listar apps, ver package names |
| Manage orders and subscriptions | Verificar tokens, acknowledge compras, detectar refunds |

**Flujo en consola (manual):**
1. Play Console → **Setup** → **API access** → **Service Accounts**
2. Buscar `game-api-backend@motamaze.iam.gserviceaccount.com`
3. Clic en **"Grant access"**
4. Seleccionar permisos: **"Manage orders and subscriptions"**
5. Aplicar a la app MotaMaze

**⏱ A partir de aquí comienzan las 24h de propagación.**

---

### ST-05 — Esperar 24h de propagación ⬜ Pending

Google documenta que los cambios de permisos en Play Console pueden tardar hasta 24 horas en ser efectivos para llamadas a la API. No hay forma de acelerar esto.

**Acción:** Registrar el timestamp exacto del invite (ST-04) y no intentar la verificación hasta 24h después.

---

### ST-06 — Verificar llamada de prueba a Play Developer API ⬜ Pending

**Después de las 24h**, hacer una llamada de prueba para confirmar que el SA tiene acceso:

```bash
# Obtener token del SA via ADC impersonation
gcloud auth print-access-token \
  --impersonate-service-account=game-api-backend@motamaze.iam.gserviceaccount.com

# Llamada de prueba: listar APKs del app (requiere packageName real)
curl -H "Authorization: Bearer TOKEN" \
  "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/PACKAGE_NAME/purchases/products/TEST_SKU/tokens/TEST_TOKEN"
```

**Resultado esperado:** `404` (producto no encontrado) o `400` (token inválido) — NO `401` ni `403`. Un 4xx de "not found" confirma que la autenticación funciona.

---

## Audit — Estado inicial verificado (2026-06-16)

```bash
gcloud services list --enabled --filter="config.name:androidpublisher"
# (vacío) → API NO habilitada

gcloud services list --enabled --filter="config.name:play OR config.name:publisher"
# (vacío) → Ninguna API de Play habilitada
```

---

## Follow-ups / Notes

- **Package name:** Confirmar con Juan el `packageName` definitivo del app antes de ST-06. Convención sugerida: `com.ingeniouscrucible.motamaze`
- **Play Console account:** Confirmar con Juan si ya existe cuenta de desarrollador ($25 USD si no).
- **ST-03 bloqueador potencial:** Si Juan ya vinculó otro proyecto GCP a Play Console, hay que evaluar si cambiar el vínculo o si se puede manejar con el proyecto actual.
- **Relación con EXT-002 (AdMob):** AdMob también necesita vinculación a Play Console. Hacerlo todo junto cuando estemos en la consola.
