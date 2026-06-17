# EXT-002 — AdMob Account + Ad Units (Rewarded / Interstitial / Banner) + Test IDs

| Campo | Valor |
|---|---|
| **Tipo** | External Services / Setup |
| **Prioridad** | Alta |
| **Status** | In Progress — iniciado 2026-06-16 |
| **Fecha planeada** | 2026-06-16 – 2026-06-17 |
| **Workstream** | External Services |
| **Owner** | Saul Zavala Morin |
| **Monday.com Item ID** | 12272254782 |
| **Depends on** | INFRA-001 (GCP base infra) ✅ |
| **Desbloquea** | AdMob client integration en Godot (Juan — EXT-002b, timeline 7/7–7/9), "No Ads" IAP wiring (Juan — 8/6), Ad-revenue reconciliation (DATA-003, 7/10–7/13) |

---

## Descripción

MotaMaze es F2P (free-to-play). La publicidad es una de sus dos fuentes de ingresos junto con los IAP. AdMob es el SDK de Google para monetización por anuncios en apps móviles.

**Tres tipos de anuncios en MotaMaze:**

| Tipo | Cuándo aparece | Propósito en el juego |
|---|---|---|
| **Rewarded Video** | El jugador elige ver el anuncio | Recuperar vidas sin pagar (Anexo §4 del contrato) |
| **Interstitial** | Transición entre nivel completado y level-select | Impresiones pasivas — mayor CPM que banner |
| **Banner** | Pantallas de menú, store, lobby | Ingreso de base constante |

**Por qué urgente:**
1. Juan necesita los **ad unit IDs y el App ID de AdMob** para implementar `Services.ads` en Godot (tarea 7/7–7/9). Si no están listos, bloquea la integración del cliente.
2. La cuenta de AdMob puede tardar **1–3 días hábiles** en ser aprobada por Google para mostrar anuncios reales. Los test ads funcionan inmediatamente, pero el pipeline de revenue real requiere aprobación.
3. El **orden de inicialización del SDK** es crítico y está definido en el plan: `consent → ATT → AdMob init`. Si Juan implementa sin conocer el App ID y los unit IDs, tendría que rehacer la configuración.

**Relación con "No Ads" IAP:**
El flujo correcto en Godot es:
```
App start
  → check entitlement "no_ads" (via /store o cache)
  → si no tiene "no_ads": inicializar AdMob con consent → ATT → init
  → si tiene "no_ads": skip todo AdMob
```
Los IDs de esta tarea son prerequisito para ese flujo.

**Relación con DATA-003 (Ad Revenue Reconciliation):**
AdMob puede vincularse a Firebase para enviar eventos de impresión a BigQuery. Esto alimenta el dashboard de Looker Studio con revenue por región/edad/día. La vinculación AdMob–Firebase se hace en esta tarea (ST-07).

---

## Criterios de aceptación

- [ ] Cuenta AdMob creada y activa bajo cuenta del estudio
- [ ] App "MotaMaze" agregada en AdMob (Android)
- [ ] Ad unit **Rewarded Video** creado → ID documentado
- [ ] Ad unit **Interstitial** creado → ID documentado
- [ ] Ad unit **Banner** creado → ID documentado
- [ ] AdMob **App ID** documentado (distinto de los ad unit IDs)
- [ ] Test IDs de Google documentados para uso en dev
- [ ] AdMob vinculado a Firebase proyecto `motamaze`
- [ ] Tabla de IDs entregada a Juan para integración en `Services.ads`

---

## Estado previo

- Cuenta AdMob: **no existe** para Ingenious Crucible Studios
- API `admob.googleapis.com`: **no habilitada** en proyecto `motamaze` (verificado 2026-06-16)
- Firebase: ✅ habilitado en proyecto `motamaze` (listo para el vínculo)

---

## Implementación — Subtareas

### ST-01 — Crear cuenta AdMob ⬜ Pending (manual en browser)

**URL:** admob.google.com → "Sign up"

**Cuenta Google a usar:** `saulmorin@ingeniouscruciblestudios.com`

**Datos a ingresar:**
- País: México
- Zona horaria: America/Mexico_City
- Moneda de reporte: USD (para consistencia con el dashboard de Looker)
- Nombre de cuenta: `Ingenious Crucible Studios`

**⚠️ Importante:** Al crear la cuenta, Google inicia una revisión. Los **test ads funcionan de inmediato**, pero los anuncios reales de producción se activan solo después de la aprobación (1–3 días hábiles). No esperar aprobación para continuar — usamos test IDs en dev.

**Verificación:** Acceso al dashboard de AdMob sin errores de cuenta pendiente.

---

### ST-02 — Agregar app MotaMaze a AdMob ⬜ Pending (manual en browser)

**Ruta en AdMob:** Apps → Add App

**Opciones:**
- Platform: **Android**
- ¿Está en Google Play?: **No** (aún no publicada) → agregar manualmente
- App name: `MotaMaze`
- App store URL: dejar vacío por ahora (se completa cuando se publique)

**Output esperado:** AdMob genera un **App ID** con formato:
```
ca-app-pub-XXXXXXXXXXXXXXXX~XXXXXXXXXX
```
Este App ID va en el `AndroidManifest.xml` / Godot export settings. **Documentar inmediatamente.**

**Nota:** El package name (`com.ingeniouscrucible.motamaze` o el que defina Juan mañana en EXT-001 ST-02) se puede vincular después cuando exista en Play Store.

---

### ST-03 — Crear ad unit: Rewarded Video ⬜ Pending (manual en browser)

**Ruta en AdMob:** Apps → MotaMaze → Ad units → Add ad unit → Rewarded

**Configuración:**
| Campo | Valor |
|---|---|
| Ad unit name | `motamaze_rewarded_lives` |
| Reward type | `lives` |
| Reward amount | `1` |
| Default reward | Activado |
| Server-side verification (SSV) | **Activar** — el backend verifica via callback antes de otorgar la vida |

**Por qué SSV es crítico:** Sin SSV, un jugador con proxy podría interceptar la respuesta del SDK y simular que vio el anuncio sin verlo. Con SSV, AdMob llama al backend de MotaMaze (`/lives/grant?source=rewarded_ad`) con un token firmado que el backend verifica antes de otorgar la vida.

**Output esperado:** Ad unit ID con formato:
```
ca-app-pub-XXXXXXXXXXXXXXXX/XXXXXXXXXX
```

---

### ST-04 — Crear ad unit: Interstitial ⬜ Pending (manual en browser)

**Ruta en AdMob:** Apps → MotaMaze → Ad units → Add ad unit → Interstitial

**Configuración:**
| Campo | Valor |
|---|---|
| Ad unit name | `motamaze_interstitial_between_levels` |
| Frequency cap | 1 por sesión de juego (configurar en AdMob o en cliente) |

**Cuándo mostrarlo (decisión de Juan en Godot):**
- Al completar un nivel (transición a la pantalla de resultado)
- NO en muerte/game-over (experiencia negativa, afecta retención)
- NO más de 1 cada 3 niveles para evitar fatiga de anuncio

**Output esperado:** Ad unit ID.

---

### ST-05 — Crear ad unit: Banner ⬜ Pending (manual en browser)

**Ruta en AdMob:** Apps → MotaMaze → Ad units → Add ad unit → Banner

**Configuración:**
| Campo | Valor |
|---|---|
| Ad unit name | `motamaze_banner_menu` |
| Banner size | Adaptive banner (recomendado — ajusta al ancho del dispositivo) |

**Dónde mostrarlo (decisión de Juan):**
- Pantalla de level-select
- Pantalla de store (solo si usuario no tiene "No Ads")
- Pantalla de main menu

**Output esperado:** Ad unit ID.

---

### ST-06 — Documentar todos los IDs para Juan ⬜ Pending

Una vez creados ST-02–ST-05, registrar en [logic/admob-config.md](../logic/admob-config.md):

**IDs de producción** (generados por AdMob):
```
AdMob App ID:           ca-app-pub-XXXXXXXXXXXXXXXX~XXXXXXXXXX
Rewarded (lives SSV):   ca-app-pub-XXXXXXXXXXXXXXXX/XXXXXXXXXX
Interstitial:           ca-app-pub-XXXXXXXXXXXXXXXX/XXXXXXXXXX
Banner:                 ca-app-pub-XXXXXXXXXXXXXXXX/XXXXXXXXXX
```

**IDs de test** (universales de Google — usar siempre en dev):
```
AdMob App ID (test):    ca-app-pub-3940256099942544~3347511713  (Android)
Rewarded (test):        ca-app-pub-3940256099942544/5224354917
Interstitial (test):    ca-app-pub-3940256099942544/1033173712
Banner (test):          ca-app-pub-3940256099942544/6300978111
```

**Regla de oro para Juan:** el flag `build_flavor` en Godot determina qué IDs se usan:
```
dev/staging → test IDs  (nunca arriesgar la cuenta AdMob con clicks falsos)
prod        → production IDs
```

---

### ST-07 — Vincular AdMob a Firebase proyecto `motamaze` ⬜ Pending (manual en browser)

**Por qué:** El vínculo AdMob–Firebase activa:
1. Eventos de impresión de ads enviados a Firebase Analytics → BigQuery (via DATA-002)
2. Dashboard de ad revenue en Looker Studio (DATA-003)
3. Audience data para segmentación de anuncios

**Ruta en AdMob:** Apps → MotaMaze → App settings → Link to Firebase

**Seleccionar:** proyecto Firebase `motamaze`

**Verificación:** En Firebase Console → Analytics → Events, debe aparecer el evento `ad_impression` tras la primera impresión de test.

---

## Follow-ups / Notes

- **SSV endpoint:** El backend necesita exponer `GET /lives/grant/admob-ssv` (o similar) que AdMob llamará para verificar rewarded ads completados. Esto es parte de PAY-001 / Game Services Backend. Documentar el URL del endpoint en AdMob → Ad units → Rewarded → Server-side verification URL una vez que Cloud Run esté deployado (INFRA-003).
- **GDPR/CCPA consent:** El consentimiento debe capturarse ANTES de inicializar AdMob. Juan implementa esto en el cliente con Google UMP SDK. Los IDs de esta tarea son input para esa implementación.
- **ATT (iOS):** Si en el futuro hay versión iOS, ATT prompt va antes de `AdMob.initialize()`. No aplica para Android MVP.
- **"No Ads" SKU:** El IAP "no_ads" bloquea la carga del SDK completo en startup. Juan implementa esto (8/6). Los IDs de esta tarea deben estar en el `export_presets.cfg` de Godot antes de esa fecha.
