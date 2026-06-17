# EXT-001 — Enable Google Play Developer API + Play Console SA Invite

| Campo | Valor |
|---|---|
| **Tipo** | External Services / Setup |
| **Prioridad** | Alta — 24h lag de activación |
| **Status** | In Progress — iniciado 2026-06-16 (1 día de retraso sobre plan) |
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

- [ ] `androidpublisher.googleapis.com` habilitada en proyecto `motamaze`
- [ ] SA `game-api-backend` invitado en Play Console con permisos de verificación de compras
- [ ] Confirmación de que Play Console está vinculado al proyecto GCP `motamaze` (o al proyecto correcto)
- [ ] 24h de espera transcurridas desde el invite
- [ ] Llamada de prueba a la API retorna 200 (no 401/403)

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

**Resultado parcial (2026-06-17):** Cuenta Google Play Developer creada por Juan bajo Ingenious Crucible Studios.
- **Developer Account ID:** `5099504302304988454`
- **Package name:** `com.ingeniouscruciblestudios.motamaze` ✅ Definido 2026-06-17

---

### ST-03 — Vincular proyecto GCP a Play Console ⬜ Pending

**Por qué:** Play Console necesita saber qué proyecto GCP puede hacer llamadas a la API en nombre de la cuenta. Esto se configura en Play Console → Setup → API access.

**Flujo en consola (manual):**
1. Play Console → **Setup** → **API access**
2. Sección "Link to a Google Cloud Project" → seleccionar proyecto `motamaze`
3. Confirmar el vínculo

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
