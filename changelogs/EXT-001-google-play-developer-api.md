# EXT-001 — Enable Google Play Developer API + Play Console SA Invite

| Campo | Valor |
|---|---|
| **Tipo** | External Services / Setup |
| **Prioridad** | Alta — 24h lag de activación |
| **Status** | In Progress — ST-01 ✅, ST-02 ✅, ST-03 ✅, ST-04 ✅ SA invitado (2026-06-24), ST-05 🕐 propagación en curso (reintentar 2026-06-26), ST-06 ⬜ pendiente propagación |
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

### ST-05 — Esperar 24h de propagación 🕐 En curso

Google documenta que los cambios de permisos en Play Console pueden tardar hasta 24 horas en ser efectivos para llamadas a la API. Reportes de comunidad indican hasta 48h en algunos casos.

**Invite realizado:** 2026-06-24. **Ventana segura:** 2026-06-26.

---

### ST-06 — Verificar llamada de prueba a Play Developer API 🔴 Bloqueado — app no publicado en ningún track

**Prueba ejecutada 2026-06-25 y reintento 2026-06-30:**

```bash
# Token via IAM Credentials API (scope correcto — gcloud --scopes flag es ignorado en impersonated_account)
USER_TOKEN=$(gcloud auth print-access-token)
SA="game-api-backend@motamaze.iam.gserviceaccount.com"

# Genera token del SA con scope androidpublisher vía REST
SA_TOKEN=$(curl -s -X POST \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scope":["https://www.googleapis.com/auth/androidpublisher"]}' \
  "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/${SA}:generateAccessToken" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['accessToken'])")

PKG="com.ingeniouscruciblestudios.motamaze"

# Prueba 1 — purchases.products.get (dummy values)
curl -s -w "\nHTTP_STATUS: %{http_code}\n" \
  -H "Authorization: Bearer $SA_TOKEN" \
  "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/${PKG}/purchases/products/test_sku/tokens/test_token"

# Prueba 2 — inappproducts.list
curl -s -w "\nHTTP_STATUS: %{http_code}\n" \
  -H "Authorization: Bearer $SA_TOKEN" \
  "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/${PKG}/inappproducts"
```

**Resultados (ambas fechas — idénticos):**

| Llamada | HTTP | Error code | Diagnóstico |
|---|---|---|---|
| `purchases.products.get` (dummy values) | **404** | `applicationNotFound` | App en draft — invisible para la Purchases API |
| `inappproducts.list` | **403** | `PERMISSION_DENIED` | ✅ Esperado — SA no tiene permiso "Manage in-app products" |

**Causa raíz confirmada (2026-06-30):**

`applicationNotFound` **no es un problema de permisos del SA ni de propagación**. La Play Developer Purchases API requiere que el app esté publicado en al menos un track (Internal Testing, Alpha, Beta o Producción). El app `com.ingeniouscruciblestudios.motamaze` fue creado como draft el 2026-06-23 y nunca se ha publicado a ningún track. Un draft es invisible para la API sin importar los permisos del SA.

Referencia: [fastlane issue #14686](https://github.com/fastlane/fastlane/issues/14686) — comportamiento documentado.

**Desbloqueo requerido:**

Opción A (recomendada): Juan exporta APK placeholder firmado de Godot con package name `com.ingeniouscruciblestudios.motamaze` → sube a Play Console → Internal Testing track → añade tester → reintentar ST-06.

Opción B: Esperar T-132 (build flavors). Timeline: varias semanas.

**Resultado esperado post-desbloqueo:** `purchases.products.get` retornará 404 con error `purchaseTokenNotFound` (no `applicationNotFound`), confirmando que el SA ve el app y la autenticación funciona end-to-end.

---

**Acción ejecutada 2026-06-30:**

Juan publicó `0.0.1-placeholder` (AAB — Play Console ya no acepta APK para apps nuevas) a Internal Testing. 2 testers en lista "Internal Testers". App name: `com.ingeniouscruciblestudios.motamaze`.

**Retry 2026-06-30 (mismo día del publish):**

| Llamada | HTTP | Error code | Diagnóstico |
|---|---|---|---|
| `purchases.products.get` | **401** | `permissionDenied` | **Progreso**: ya no es `applicationNotFound` — SA ve la app. Permisos de purchases aún propagando post-publish. |
| `inappproducts.list` | **403** | `PERMISSION_DENIED` | Sin cambio — esperado (SA no tiene "Manage in-app products") |

El cambio de 404 → 401 confirma que publicar a Internal Testing desbloqueó la visibilidad del app en la API. El `permissionDenied` es propagación adicional de los permisos "View financial data" en el contexto de la app publicada.

**Próximo retry:** 2026-07-01. Si persiste 401, Juan verifica en Play Console → Users and permissions → `game-api-backend@motamaze.iam.gserviceaccount.com` que los 4 permisos de MotaMaze siguen activos tras el publish.

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
