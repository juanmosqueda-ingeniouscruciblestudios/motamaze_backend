# Deep Links — App Links (Android) / Universal Links (iOS) (T-124) — Estado actual

> Última actualización: 2026-07-27
> **Estado: parcialmente configurado.** Los archivos de verificación existen en el dominio pero
> están vacíos. Ningún deep link funciona todavía. Detalle de lo pendiente al final.

Los links compartidos del juego (`POST /share/create` → `GET /s/{token}`, ver [T-440]) deben abrir la
app nativa en lugar del navegador cuando el usuario la tiene instalada. Eso requiere que el sistema
operativo verifique que el dominio y la app se pertenecen mutuamente, mediante dos archivos servidos
desde la raíz del dominio.

---

## Dominio

| Campo | Valor |
|---|---|
| Host canónico | `ingeniouscruciblestudios.com` — **apex, sin `www`** |
| Ruta del juego | `https://ingeniouscruciblestudios.com/motamaze/` |
| Ruta de share links | `https://ingeniouscruciblestudios.com/motamaze/s/{token}` |
| Hosting | Firebase Hosting (decisión documentada en `motamaze-project/rnd_research/2026-06-26_hosting-firebase-vs-netlify.md`) |

**No existe dominio propio `motamaze.com`.** El juego vive bajo el dominio del estudio.

El host canónico es el apex porque su certificado TLS declara `SAN: DNS:ingeniouscruciblestudios.com`
únicamente — no cubre `www`. Además `www.ingeniouscruciblestudios.com` **sigue apuntando a Wix** y es
un sitio distinto: responde `400` en `/.well-known/assetlinks.json` y `301` en `/motamaze/`. No hay
redirect entre ambos hosts.

> **Importante para App Links:** la verificación de Android **falla ante cualquier redirect** al pedir
> `assetlinks.json`. Por eso el host debe fijarse al apex y los archivos servirse ahí directamente.

---

## Archivos de verificación

Ambos se sirven desde la **raíz del dominio**. Esto no es configurable: Android y Apple solo los
buscan ahí. **No pueden vivir en `/motamaze/.well-known/`.**

| Archivo | URL | Estado actual |
|---|---|---|
| Android | `https://ingeniouscruciblestudios.com/.well-known/assetlinks.json` | `200`, `application/json`, contenido `[]` |
| iOS | `https://ingeniouscruciblestudios.com/.well-known/apple-app-site-association` | `200`, `application/json`, contenido `{"applinks":{"apps":[],"details":[]}}` |

Ambos responden sin redirects. El de iOS se sirve **sin extensión** y con `Content-Type:
application/json`, que es el requisito que Apple rechaza si no se cumple — Firebase Hosting lo maneja
correctamente.

Los archivos se editan en el **repositorio del sitio web** (no en este repo) y se publican con
`firebase deploy`.

---

## Android — `assetlinks.json`

Contenido definitivo, pendiente de publicar (reemplaza el `[]` actual):

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

### El acotamiento de rutas NO vive en este archivo

`assetlinks.json` usa la relación `delegate_permission/common.handle_all_urls` y **no tiene campo de
paths**: concede el manejo de URLs para **todo el dominio**.

La restricción a `/motamaze/*` en Android depende exclusivamente del `intent-filter` en el
`AndroidManifest.xml` de la app (responsabilidad del cliente Godot — Juan):

```xml
<intent-filter android:autoVerify="true">
  <action android:name="android.intent.action.VIEW" />
  <category android:name="android.intent.category.DEFAULT" />
  <category android:name="android.intent.category.BROWSABLE" />
  <data android:scheme="https"
        android:host="ingeniouscruciblestudios.com"
        android:pathPrefix="/motamaze/" />
</intent-filter>
```

Dos consecuencias:

1. **Publicar `assetlinks.json` sin este `intent-filter` daría a la app permiso para interceptar
   cualquier URL de `ingeniouscruciblestudios.com`**, incluido el sitio institucional completo.
2. **Sin `android:autoVerify="true"` Android no consulta `assetlinks.json` en absoluto** y los deep
   links nunca se abren en la app. Es requisito, no opcional.

**Orden de ejecución:** publicar primero el archivo en el dominio, después generar el build con
`autoVerify` — la verificación se dispara durante la instalación.

### Validación posterior a la publicación

```
https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://ingeniouscruciblestudios.com&relation=delegate_permission/common.handle_all_urls
```

> **Los App Links no verifican en builds de debug.** El debug keystore local tiene un SHA-256
> distinto al de la app signing key de Play. Las pruebas en dispositivo requieren un build descargado
> de Play (Internal Testing) o firmado con la misma clave.

---

## iOS — `apple-app-site-association`

**Bloqueado: no se puede generar todavía.** El archivo requiere el campo `appID` con formato
`TeamID.bundleID`, y el **Team ID no existe** — la inscripción al Apple Developer Program (T-IOS-3)
está sin iniciar al 2026-07-27.

El bundle ID sí se conoce: `com.ingeniouscruciblestudios.motamaze` (`Settings.apple_bundle_id` en
`app/config.py`).

Forma que tendrá el archivo una vez disponible el Team ID:

```json
{
  "applinks": {
    "apps": [],
    "details": [
      {
        "appID": "<TEAM_ID>.com.ingeniouscruciblestudios.motamaze",
        "paths": ["/motamaze/*"]
      }
    ]
  }
}
```

A diferencia de Android, **el AASA sí acota rutas dentro del propio archivo** vía el campo `paths`.
El equivalente cliente en iOS es el entitlement Associated Domains
(`applinks:ingeniouscruciblestudios.com`), contemplado en T-IOS-12.

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

Los deep links de T-124 aplican únicamente a los **share links** (`/motamaze/s/*`).

---

## Pendientes

| Pendiente | Bloqueo |
|---|---|
| Publicar `assetlinks.json` con el contenido real | Acceso al repo del sitio web + proyecto de Firebase Hosting |
| Generar y publicar `apple-app-site-association` | Team ID de Apple — T-IOS-3 sin iniciar |
| `intent-filter` con `autoVerify` + `pathPrefix` en el manifest Android | Cliente Godot (Juan) |
| Entitlement Associated Domains en iOS | T-IOS-12 (Juan) |
| Redirect `www` → apex | DNS en cuenta de Wix + Firebase Hosting |
| Rewrite de `/motamaze/s/{token}` hacia Cloud Run en `firebase.json` | Acceso al repo del sitio web |

### Deuda en este repo

`Settings.share_base_url` en `app/config.py` sigue apuntando a `https://motamaze.com`, dominio que no
existe. Debe pasar a `https://ingeniouscruciblestudios.com/motamaze`. Afecta a `_tenjin_share_url()`,
`_og_proxy_url()` y `share_view()` en `app/routers/social.py`.

`Settings.company_website_url` ya está correcto (`https://ingeniouscruciblestudios.com/motamaze/`).

`Settings.jwt_issuer` y `Settings.jwks_url` apuntan a `https://api.motamaze.com`. Si ese subdominio
tampoco existirá, requiere decisión aparte — `jwt_issuer` va firmado dentro de los JWT ya emitidos,
por lo que el cambio tiene radio de impacto sobre T-111 y T-120 (ambas cerradas).
