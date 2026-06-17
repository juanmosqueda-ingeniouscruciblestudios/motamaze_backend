# AdMob Configuration — Estado actual

> Última actualización: 2026-06-17
> Completar con IDs reales una vez que EXT-002 esté ejecutado.

---

## Cuenta AdMob

| Campo | Valor |
|---|---|
| Cuenta Google | Cuenta de organización Ingenious Crucible Studios (`juanmosqueda@ingeniouscruciblestudios.com`) |
| Estado | ✅ Creada 2026-06-17 |
| Publisher ID | `pub-9121176819960949` |

---

## App: MotaMaze (Android)

| Campo | Valor |
|---|---|
| AdMob App ID (producción) | `ca-app-pub-9121176819960949~9751218738` |
| AdMob App ID (test — Android) | `ca-app-pub-3940256099942544~3347511713` |
| Package name | `com.ingeniouscruciblestudios.motamaze` |
| Vinculado a Firebase | ✅ Done 2026-06-17 — `google-services.json` descargado |

---

## Ad Units — IDs de Producción

| Tipo | Nombre en AdMob | Ad Unit ID | SSV |
|---|---|---|---|
| Rewarded Video | `motamaze_rewarded_lives` | `ca-app-pub-9121176819960949/9093914042` | ✅ SSV activado — URL endpoint: TBD (post INFRA-003) |
| Interstitial | `motamaze_interstitial_between_levels` | `ca-app-pub-9121176819960949/4963097342` | — |
| Banner | `motamaze_banner_menu` | `ca-app-pub-9121176819960949/3593004496` | — |

---

## Ad Units — IDs de Test (Google oficiales — usar en dev/staging)

| Tipo | Test Ad Unit ID |
|---|---|
| Rewarded Video | `ca-app-pub-3940256099942544/5224354917` |
| Interstitial | `ca-app-pub-3940256099942544/1033173712` |
| Banner | `ca-app-pub-3940256099942544/6300978111` |

> **Regla:** build flavor `dev` y `staging` → test IDs. Build `prod` → production IDs.
> Usar IDs de producción en dev puede resultar en banning de la cuenta AdMob por clicks inválidos.

---

## Integración en Godot (responsabilidad de Juan — EXT-002b)

Archivo donde van los IDs: `export_presets.cfg` (Android) o `Services/ads/AdMobConfig.gd`

```gdscript
# dev/staging
const ADMOB_APP_ID     = "ca-app-pub-3940256099942544~3347511713"
const REWARDED_AD_ID   = "ca-app-pub-3940256099942544/5224354917"
const INTERSTITIAL_ID  = "ca-app-pub-3940256099942544/1033173712"
const BANNER_ID        = "ca-app-pub-3940256099942544/6300978111"

# prod
const ADMOB_APP_ID     = "ca-app-pub-9121176819960949~9751218738"
const REWARDED_AD_ID   = "ca-app-pub-9121176819960949/9093914042"
const INTERSTITIAL_ID  = "ca-app-pub-9121176819960949/4963097342"
const BANNER_ID        = "ca-app-pub-9121176819960949/3593004496"
```

**Orden de init obligatorio (plan Anexo §5):**
```
1. Consent (UMP SDK — GDPR/CCPA)
2. ATT prompt (solo iOS — no aplica Android MVP)
3. MobileAds.initialize(app_id)
```

---

## SSV (Server-Side Verification) — Rewarded ads

El backend recibirá callbacks de AdMob cuando un usuario complete un rewarded ad.

| Campo | Valor |
|---|---|
| Endpoint | TBD — `GET https://<cloud-run-url>/lives/grant/admob-ssv` (post INFRA-003) |
| Parámetros | `reward_item`, `reward_amount`, `user_id` (custom data), `ad_network`, `timestamp`, `signature` |
| Verificación | Backend valida firma HMAC de AdMob antes de otorgar vida |

Configurar URL en AdMob → Apps → MotaMaze → Ad units → Rewarded → Server-side verification.
