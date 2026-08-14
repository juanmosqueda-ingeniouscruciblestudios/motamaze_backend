# Deep Links — App Links (Android) / Universal Links (iOS) (T-124) — Estado actual

> Última actualización: 2026-08-14
> **Estado: parcialmente configurado.** El dominio existe y resuelve, pero no hay sitio publicado
> todavía y los archivos de verificación no se han creado. Ningún deep link funciona todavía. Detalle
> de lo pendiente al final.

Los links compartidos del juego (`POST /share/create` → `GET /s/{token}`, ver [T-440]) deben abrir la
app nativa en lugar del navegador cuando el usuario la tiene instalada. Eso requiere que el sistema
operativo verifique que el dominio y la app se pertenecen mutuamente, mediante dos archivos servidos
desde la raíz del dominio.

---

## Dominio

| Campo | Valor |
|---|---|
| Host canónico | `motamaze.com` — dominio dedicado, comprado 2026-08-12 |
| Ruta del juego | `https://motamaze.com/` |
| Ruta de share links | `https://motamaze.com/s/{token}` |
| Registro/DNS | Wix. Cuenta exacta **por confirmar con Juan** (2026-08-14) — la cuenta de Wix a la que Saul tiene acceso ("My Site 1", rol Administrador/copropietario) **no tiene el dominio registrado**; `motamaze.com` resuelve por DNS a infraestructura de Wix pero bajo una cuenta distinta. Ver sección "Pendientes". |
| Hosting del sitio/archivos | Sin resolver — depende de qué permite la cuenta de Wix que sí tiene el dominio (ver Pendientes) |

**`ingeniouscruciblestudios.com/motamaze` ya NO es el host de los share links** (lo fue del
2026-07-27 al 2026-08-14, mientras `motamaze.com` no existía). El dominio corporativo sigue siendo el
sitio institucional del estudio — sin relación con esto salvo por haber sido el host interino.

> **Importante para App Links:** la verificación de Android **falla ante cualquier redirect** al pedir
> `assetlinks.json`. El host debe servir los archivos directamente, sin redirect intermedio.

---

## Archivos de verificación

Ambos se sirven desde la **raíz del dominio**. Esto no es configurable: Android y Apple solo los
buscan ahí.

| Archivo | URL objetivo | Estado actual |
|---|---|---|
| Android | `https://motamaze.com/.well-known/assetlinks.json` | `404` — nada publicado (verificado 2026-08-14, sirve la página de error genérica de Wix) |
| iOS | `https://motamaze.com/apple-app-site-association` | `404` — nada publicado |

El de iOS se sirve **sin extensión** y con `Content-Type: application/json` — requisito que Apple
rechaza si no se cumple. **Sin confirmar todavía si Wix puede servir esto** — ver Pendientes.

---

## Android — `assetlinks.json`

Contenido definitivo, pendiente de publicar:

```json
[
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "com.ingeniouscruciblestudios.motamaze",
      "sha256_cert_fingerprints": [
        "9A:08:7E:AA:FF:17:45:10:66:43:69:E0:24:38:0F:9E:AF:2E:C8:65:13:B0:BC:8D:FD:0E:C8:6B:FD:D2:38:58"
      ]
    }
  }
]
```

`package_name` coincide con `Settings.play_package_name` en `app/config.py`.

### Fingerprints de la app signing key

Obtenidos de Play Console el 2026-07-27. Corresponden a la **app signing key** gestionada por Google
(Play App Signing), **no** a la upload key — usar la upload key hace que la verificación falle
silenciosamente.

| Algoritmo | Fingerprint |
|---|---|
| SHA-256 | `9A:08:7E:AA:FF:17:45:10:66:43:69:E0:24:38:0F:9E:AF:2E:C8:65:13:B0:BC:8D:FD:0E:C8:6B:FD:D2:38:58` |
| SHA-1 | `5A:50:35:9B:46:54:3A:AA:2C:45:02:3D:59:D5:11:6F:FA:FE:82:AE` |
| MD5 | `C2:62:1D:71:C5:22:AA:A5:04:FE:72:F9:25:93:8F:7E` |

**Dónde consultarlos en Play Console:** la ruta por menú cambió (App Integrity migró a la página
"Protected with Play", que **no** contiene la firma). La vía confiable es la URL directa:

```
play.google.com/console/u/0/developers/5099504302304988454/app/4972765424320823000/keymanagement
```

`5099504302304988454` es el Account ID de Ingenious Crucible Studios; `4972765424320823000` es el ID
interno de la app en Play Console (distinto del package name, solo legible desde la URL).

### El acotamiento de rutas ya no aplica

`assetlinks.json` usa la relación `delegate_permission/common.handle_all_urls` y concede el manejo de
URLs para **todo el dominio**. Con `motamaze.com` dedicado 100% al juego (nada más vive ahí), esto ya
no es un riesgo — a diferencia del plan interino bajo el dominio corporativo, donde conceder el dominio
completo habría entregado el sitio institucional entero.

Consistente con esto, el `intent-filter` del cliente Android (`AndroidManifest.xml`, T-124 ST-07,
hecho 2026-08-14 en `motamaze-game`) **ya no usa `pathPrefix`**:

```xml
<intent-filter android:autoVerify="true">
  <action android:name="android.intent.action.VIEW" />
  <category android:name="android.intent.category.DEFAULT" />
  <category android:name="android.intent.category.BROWSABLE" />
  <data android:scheme="https"
        android:host="motamaze.com" />
</intent-filter>
```

1. **`android:autoVerify="true"` sigue siendo requisito, no opcional** — sin esto Android no consulta
   `assetlinks.json` en absoluto y los deep links nunca se abren en la app.
2. **Orden de ejecución:** publicar primero el archivo en el dominio, después generar el build con
   `autoVerify` — la verificación se dispara durante la instalación.

### Validación posterior a la publicación

```
https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://motamaze.com&relation=delegate_permission/common.handle_all_urls
```

> **Los App Links no verifican en builds de debug.** El debug keystore local tiene un SHA-256
> distinto al de la app signing key de Play. Las pruebas en dispositivo requieren un build descargado
> de Play (Internal Testing) o firmado con la misma clave.

---

## iOS — `apple-app-site-association`

**Ya no bloqueado por el Team ID** (T-IOS-3, resuelto 2026-08-12): Team ID `V6LS3VX234`, bundle ID
`com.ingeniouscruciblestudios.motamaze` (`Settings.apple_bundle_id`).

```json
{
  "applinks": {
    "apps": [],
    "details": [
      {
        "appID": "V6LS3VX234.com.ingeniouscruciblestudios.motamaze"
      }
    ]
  }
}
```

**Ya no lleva el campo `paths`** — antes acotaba a `["/motamaze/*"]`; con `motamaze.com` dedicado al
juego no hay nada que excluir. Omitir `paths` (o usar `["*"]`) concede el dominio completo, igual que
`assetlinks.json` en Android.

El equivalente cliente en iOS es el entitlement Associated Domains (`applinks:motamaze.com`, sin
acotamiento de ruta), pendiente en T-IOS-12 (Juan).

> **Propagación:** desde iOS 14 Apple sirve el AASA a través de su propia CDN. Los cambios pueden
> tardar hasta 24 h en reflejarse — publicar con margen respecto a cualquier fecha de prueba.

---

## Relación con el callback de OAuth

El título original de T-124 menciona el callback de OAuth, pero **el flujo de login no usa deep
links**. Según el contrato REST-001, el callback es un flujo de polling (RFC 8252):

```
[Godot] abre browser → [Google] redirige a /auth/callback → [Godot] hace polling a
GET /auth/pending/{state_token} cada 2s hasta recibir los tokens
```

Los deep links de T-124 aplican únicamente a los **share links** (`/s/*`).

---

## Pendientes

| Pendiente | Bloqueo |
|---|---|
| Confirmar en qué cuenta de Wix vive el dominio `motamaze.com` | **Con Juan** — la cuenta de Saul ("My Site 1") no lo tiene registrado, esperando respuesta (2026-08-14) |
| Confirmar si esa cuenta de Wix puede servir `assetlinks.json`/AASA como archivos estáticos crudos en la raíz, con `Content-Type` exacto | Depende de lo anterior. Si no se puede, evaluar la alternativa ya discutida: subdominio dedicado (ej. `share.motamaze.com`) mapeado directo a Cloud Run vía Global External ALB — mismo patrón que `api.motamaze.com` (ver `logic/jobs-scheduler-auth.md`/INFRA-007 para el ALB) |
| Publicar `assetlinks.json` y `apple-app-site-association` con el contenido de arriba | Depende de los dos anteriores |
| Entitlement Associated Domains en iOS (`applinks:motamaze.com`) | T-IOS-12 (Juan) |
| Redirect `www.motamaze.com` → apex, si aplica | Verificado 2026-08-14: `www.motamaze.com` responde distinto al apex (`Server: cloudflare` vs. headers de Wix) — revisar si está configurado a propósito o es un descuido |

### Configuración de URLs en este repo

`Settings.share_base_url` = `https://motamaze.com` (actualizado 2026-08-14, T-124 ST-10 — antes
`https://ingeniouscruciblestudios.com/motamaze`, interino desde 2026-07-27 mientras `motamaze.com` no
existía). Consumido por `_tenjin_share_url()`, `_og_proxy_url()` y `share_view()` en
`app/routers/social.py`, siempre como `f"{share_base_url}/<path>/{token}"`.

> **Debe permanecer sin slash final.** Un slash produciría `//s/{token}`, una ruta distinta que
> rompería tanto el deep link como la preview de OG. Hay un test que lo fija:
> `test_share_base_url_is_the_dedicated_domain` en `tests/test_social_router.py`.

`Settings.company_website_url` también se actualizó a `https://motamaze.com/` (mismo commit) — antes
apuntaba al mismo valor interino que `share_base_url`.

### Deuda pendiente — resuelta

`Settings.jwt_issuer` y `Settings.jwks_url` apuntan a `https://api.motamaze.com`. Confirmado por Juan
(2026-08-12): ese subdominio sí existirá — la vía es un Global External Application Load Balancer (no
el domain mapping de Cloud Run, que sigue en Preview). **Sin cambio necesario** en `jwt_issuer`/
`jwks_url` — ya apuntaban al valor correcto. Detalle de la decisión: T-124 ST-12 (cerrada sin acción).
