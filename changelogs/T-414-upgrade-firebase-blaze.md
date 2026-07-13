# T-414 — Upgrade Firebase to Blaze + prod secrets/bindings

| Field | Value |
|---|---|
| **Type** | Infra/DevOps / Administrative |
| **Priority** | High — prerequisite for prod launch |
| **Status** | ✅ Done — Firebase Blaze confirmado + 2 SM secrets poblados (2026-07-13); admob-ssv-hmac-key diferido (SSV no implementado) |
| **Date** | 2026-07-13 |
| **Workstream** | Infra/DevOps |
| **Owner** | Saul Zavala Morin |
| **Monday.com Item ID** | 12272175997 |
| **Depends on** | INFRA-001 ✅ (billing GCP), INFRA-002 ✅ (SM secrets design) |
| **Desbloquea** | Prod launch — Cloud Run en prod puede acceder a google-oauth-client-id/secret desde SM |

---

## Descripción

Dos objetivos:
1. Confirmar que Firebase está en plan Blaze (pay-as-you-go) — requerido para uso de Firestore, Cloud Storage y otros servicios Firebase en producción más allá de los límites gratuitos.
2. Poblar los SM secrets de prod que estaban vacíos: credenciales OAuth de Google Sign-In y HMAC key de AdMob SSV.

---

## Estado previo (antes de este ticket)

| Item | Estado |
|---|---|
| Firebase billing plan | Desconocido — sin confirmar |
| `google-oauth-client-id` en SM prod | Existía el secret (sin versiones) |
| `google-oauth-client-secret` en SM prod | Existía el secret (sin versiones) |
| `admob-ssv-hmac-key` en SM prod | Existía el secret (sin versiones) |

Los tres secrets fueron creados vacíos en INFRA-001 (infraestructura manual inicial) pero nunca poblados con valores reales.

---

## Implementación

### ST-01 — Firebase Blaze (verificación)

**Verificado en Firebase Console → Usage and billing → Details & settings:**

```
Firebase billing plan: Blaze
Pay as you go
Billing account: Managed in Google Cloud Console
Project cost (julio 2026): $4.05
```

El plan Blaze fue activado automáticamente cuando Juan vinculó el billing account `01A127-C8B7E6-B6DEE7` al proyecto `motamaze` en INFRA-001 (2026-06-16). No requirió acción adicional.

### ST-02 — Prod SM secrets

**`google-oauth-client-id`** — Client ID del OAuth 2.0 client `motamaze-player-signin-web` (Web application, creado 2026-07-11):

```
Client: motamaze-player-signin-web
Type:   Web application
Value:  542009654415-45esu8cpo59rann74ulll907uri50ae0.apps.googleusercontent.com
```

Poblado:
```powershell
$tmp = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($tmp, $clientId, [System.Text.UTF8Encoding]::new($false))
gcloud secrets versions add google-oauth-client-id --project=motamaze --data-file=$tmp
# Created version [1] of the secret [google-oauth-client-id].
```

**`google-oauth-client-secret`** — Client secret del mismo client (proporcionado por Juan Mosqueda 2026-07-13):

```powershell
gcloud secrets versions add google-oauth-client-secret --project=motamaze --data-file=$tmp
# Created version [1] of the secret [google-oauth-client-secret].
```

**`admob-ssv-hmac-key`** — Diferido. Ver nota abajo.

---

## AdMob SSV — análisis y decisión

**Estado en AdMob Console:**
```
Apps → MotaMaze (Android) → Ad units → MotaMaze_Rewarded_lives
Ad unit ID: ca-app-pub-9121176819960949/9093914042
Server-side verification: No callback URL provided
```

**Estado en el backend:**

El backend recibe `reward_token` + `ad_unit_id` desde el cliente vía `POST /lives/grant` con `source="rewarded_ad_ssv"`. El token se usa para deduplicación de entitlements (`dedup_entitlement = f"entitlement_ssv_{body.reward_token}"`), pero **no existe verificación HMAC contra la firma de AdMob**.

No hay un endpoint server-to-server SSV implementado (AdMob no tiene callback URL configurada). La implementación actual es client-side simplificada — el cliente pasa el token y el servidor confía en él.

**Decisión (2026-07-13 — Saul):** `admob-ssv-hmac-key` queda vacío en SM. La implementación SSV real (server-to-server callback + verificación HMAC) es un feature futuro. El flujo de rewarded lives pre-launch usa el token como identificador de deduplicación sin verificación criptográfica. Esto es aceptable para MVP — el riesgo de abuso es bajo dado que el beneficio (vidas extra) es cosmético y el `dedup_entitlement` previene replay attacks del mismo token.

---

## OAuth 2.0 clients en prod — referencia

| Client | Tipo | Client ID | Uso |
|---|---|---|---|
| `motamaze-player-signin` | Android | `542009654415-tceh...` | App Android — obtiene Google ID token |
| `motamaze-player-signin-web` | Web application | `542009654415-45esu8cpo59rann74ulll907uri50ae0` | Backend — verifica Google Sign-In tokens; SM secrets |
| `admob-reporting-playground` | Web application | `542009654415-7lkdml45mva0sbje69gnvjqduij3c7ou` | DATA-003 AdMob reporting (pruebas) |
| `admob-reporting-job` | Desktop | `542009654415-hr2c...` | DATA-003 AdMob reporting (Cloud Run Job) |

**Importante:** `google-oauth-client-id` en SM usa `motamaze-player-signin-web`, NO `admob-reporting-playground`. Los clientes AdMob tienen credenciales separadas gestionadas en DATA-003.

---

## Testing

```powershell
# Verificar versions creadas
gcloud secrets versions list google-oauth-client-id --project=motamaze
# NAME                                                  STATE
# projects/542009654415/secrets/google-oauth-client-id/versions/1  enabled

gcloud secrets versions list google-oauth-client-secret --project=motamaze
# projects/542009654415/secrets/google-oauth-client-secret/versions/1  enabled
```

---

## Follow-ups / Notes

- **SSV real implementation** (ticket futuro post-MVP): implementar endpoint `GET /admob/ssv` en el backend que verifique la firma de AdMob usando Google's public keys (`https://www.gstatic.com/admob/reward/verifier-keys.json`). Una vez implementado: generar `admob-ssv-hmac-key` como secret propio para verificación adicional de `custom_data`, configurar callback URL en AdMob Console → MotaMaze_Rewarded_lives → Server-side verification.
- **AdMob Approval status**: en App settings aparece "Requires review" — esto es normal pre-lanzamiento. AdMob aprueba la app automáticamente una vez que está publicada y con tráfico real.
- **App store details en AdMob**: el campo "App store details" está vacío en AdMob (no vinculado a Play Store aún). Se vincula automáticamente después de la primera publicación en Play Store.
- **Dev SM**: `google-oauth-client-id` en dev SM fue actualizado a `542009654415-45esu8cpo59rann74ulll907uri50ae0.apps.googleusercontent.com` en una sesión previa. Dev y prod usan el mismo OAuth client (creado en proyecto prod `motamaze`).
