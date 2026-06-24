# EXT-001 — Enable Google Play Developer API + Play Console SA Invite

| Campo | Valor |
|---|---|
| **Tipo** | External Services / Setup |
| **Prioridad** | Alta — 24h lag de activación |
| **Status** | In Progress — ST-01 ✅, ST-02 ✅, ST-03 ✅ (app draft + flujo actualizado), ST-04 ✅ SA invitado (2026-06-24), ST-05 🕐 propagación 24h (verificar 2026-06-25), ST-06 ⬜ |
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

### ST-03 — Vincular proyecto GCP a Play Console ✅ Done (2026-06-24 — flujo actualizado)

**Nota:** La sección "API access" fue eliminada de Play Console (confirmado por Google Community threads, 2024). El vínculo GCP ya no se configura desde Play Console — el flujo actual consiste en invitar el SA directamente como usuario con permisos de Financial data. ST-03 queda obsoleto como paso separado; cubierto dentro de ST-04.

**Historial del bloqueador:**
- 2026-06-17: Botón "Create app" deshabilitado — Google verificando identidad de ICS
- 2026-06-22: Juan completó "Verify organization's website" + "Verify phone numbers" — bloqueador 100% externo
- **2026-06-23: ✅ Google completó la verificación** — botón "Create app" activo
- **2026-06-23: ✅ App draft creada** — MotaMaze / `com.ingeniouscruciblestudios.motamaze` / Game / Free

---

### ST-04 — Invitar `game-api-backend` SA a Play Console ✅ Done (2026-06-24)

**Flujo ejecutado (actualizado — sin "API access" page):**
1. Play Console → **Users and permissions** → **Invite new users**
2. Email: `game-api-backend@motamaze.iam.gserviceaccount.com`
3. Pestaña **App permissions** → Add app → **MotaMaze**
4. Permisos seleccionados (scoped a MotaMaze):

| Permiso | Sección | Para qué |
|---|---|---|
| ✅ View app information (read-only) | App access | Ver info de la app |
| ✅ View app quality information (read-only) | App access | Auto-seleccionado |
| ✅ View financial data | Financial data | Acceso a Purchases API |
| ✅ Manage orders and subscriptions | Financial data | Acknowledge compras, refunds |

**Resultado:** 4 permisos aplicados a MotaMaze (`com.ingeniouscruciblestudios.motamaze`).

**⏱ Propagación iniciada 2026-06-24 — no verificar antes de 2026-06-25.**

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
