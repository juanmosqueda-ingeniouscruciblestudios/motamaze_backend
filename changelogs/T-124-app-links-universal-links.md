# T-124 — HTTPS App Links (Android) / Universal Links (iOS) para share URL deep links

| Field | Value |
|---|---|
| **Type** | Feature / Infra |
| **Priority** | Medium — sin esto los share links de T-440 abren el navegador en vez de la app |
| **Status** | In Progress — ST-01.2/02/03/04/05/06/07/10/11/12 ✅. ST-01.1 (repo del sitio) resuelto, sitio movido a `hosting/`. ST-13 bloqueada por ST-14, esperando que Juan aplique la org policy acotada |
| **Date** | 2026-07-27 (última actualización: 2026-08-15) |
| **Workstream** | Auth Backend |
| **Depends-on** | T-120 ✅ (`POST /auth/login`), T-440 ✅ (`POST /share/create`), EXT-001 ST-02 ✅ (package name) |
| **Blocks** | T-442 (smoke test de deep links), T-441 (share client) |

---

## Scope note — este pase no cierra el ticket

El ticket de Monday se reestructuró hoy de 3 subtareas a 11 (detalle en el update del ticket padre).
Este pase entrega **3 de las 11**:

| ST | Entregado hoy |
|---|---|
| ST-02 | Host canónico definido y verificado |
| ST-03 | SHA-256 de la app signing key obtenido |
| ST-10 | `share_base_url` corregido + tests |

**Lo demás no depende de código de este repo:** publicar los dos archivos requiere acceso al
repositorio del sitio web y al proyecto de Firebase Hosting (solicitados a Juan por correo el
2026-07-27); el AASA además está bloqueado por T-IOS-3 (Apple Developer Program sin iniciar); y el
acotamiento a `/motamaze/*` en Android depende del `AndroidManifest.xml` del cliente Godot (Juan).

---

## Description

Los share links de T-440 (`POST /share/create` → `GET /s/{token}`) deben abrir la app nativa en lugar
del navegador cuando el usuario la tiene instalada. Eso exige que el SO verifique la relación entre
dominio y app mediante dos archivos servidos desde la **raíz del dominio**.

El ticket arrastraba dos supuestos que resultaron falsos y que se corrigieron antes de escribir código:

1. **El dominio.** El plan asumía `motamaze.com`. Ese dominio **nunca se registró** — el juego vive en
   `https://ingeniouscruciblestudios.com/motamaze/`, bajo el dominio del estudio.
2. **El callback de OAuth.** El título del ticket menciona App Links para el callback, pero REST-001
   define ese flujo como polling RFC 8252 (`GET /auth/pending/{state_token}`), sin deep link. Los deep
   links aplican únicamente a los share links.

### Acceptance criteria

- [x] Host canónico definido con evidencia (ST-02)
- [x] SHA-256 de la app signing key obtenido y documentado (ST-03)
- [x] `share_base_url` apunta al dominio real, con tests que fijan el literal (ST-10)
- [ ] `assetlinks.json` publicado y validado contra la Digital Asset Links API (ST-05)
- [ ] `apple-app-site-association` publicado y validado (ST-06)
- [ ] Deep links abren la app en dispositivo real (T-442, ticket aparte)

---

## Previous state (before this change)

`app/config.py`:
```python
share_base_url: str = "https://motamaze.com"
```

Todo `share_url` y `og_image_url` devuelto por `POST /share/create` apuntaba a un dominio que no
resuelve. `app/routers/social.py` los construye así:

```python
def _og_proxy_url(settings: Settings, token: str) -> str:
    return f"{settings.share_base_url}/ogimg/{token}"

def _tenjin_share_url(settings: Settings, token: str) -> str:
    direct_url = f"{settings.share_base_url}/s/{token}"
    ...
```

Los tests de T-440 no podían detectarlo, porque comparaban contra el propio setting:

```python
assert body["share_url"] == f"{test_settings.share_base_url}/s/{body['token']}"
```

Esa aserción es **autorreferencial**: pasa con cualquier valor, incluido un dominio inexistente. Por
eso el error sobrevivió desde T-440 (2026-06-30) hasta hoy.

En el dominio, ambos archivos de verificación ya existían como scaffolds vacíos:
`assetlinks.json` → `[]`, `apple-app-site-association` → `{"applinks":{"apps":[],"details":[]}}`.

---

## Implementation

### `app/config.py` — ST-10

```python
# T-124 (2026-07-27): motamaze.com was never registered — the game lives
# under the studio domain. Must stay without a trailing slash: social.py
# builds URLs as f"{share_base_url}/s/{token}". The /motamaze path segment
# is part of the base, so App Links/AASA scope to /motamaze/* accordingly.
share_base_url: str = "https://ingeniouscruciblestudios.com/motamaze"
```

El valor nuevo lleva **segmento de ruta**, donde el anterior era solo un origin. Dos consecuencias:

- Un slash final produciría `//s/{token}` — ruta distinta — rompiendo deep link y preview de OG.
- El prefijo `/motamaze` es exactamente lo que acotarán `assetlinks.json` y el AASA.

Ambas restricciones quedaron fijadas por tests (ver sección siguiente).

`terraform/modules/motamaze-env/main.tf` **no requirió cambios**: solo contiene `JWT_ISSUER` y
`JWKS_URL`, fuera de alcance (ver Follow-ups).

### `logic/deep-links.md` (nuevo) + `logic/README.md` — ST-11 parcial

Doc de estado actual del sistema: dominio, archivos de verificación, contenido definitivo del
`assetlinks.json`, forma del AASA, el `intent-filter` de Android, y la aclaración sobre el callback
de OAuth.

### Hallazgos de investigación que cambiaron el diseño

**1. Los archivos van en la raíz del dominio, no bajo `/motamaze/`.** Android y Apple solo los buscan
en `/.well-known/` del host. No es configurable. Esto convierte T-124 en dependencia cruzada con quien
administre el sitio corporativo del estudio.

**2. `assetlinks.json` no admite acotar rutas.** Usa la relación
`delegate_permission/common.handle_all_urls` y no tiene campo de paths: concede el manejo de URLs para
**todo el dominio**. El acotamiento a `/motamaze/*` en Android vive exclusivamente en el
`AndroidManifest.xml` de la app. Publicar el archivo sin ese `intent-filter` daría a MotaMaze permiso
para interceptar cualquier URL de `ingeniouscruciblestudios.com`. El AASA de iOS **sí** acota dentro
del propio archivo, vía el campo `paths`.

**3. Sin `android:autoVerify="true"` Android no consulta `assetlinks.json` en absoluto.** Es requisito,
no opcional.

**4. Apex y `www` son dos sitios distintos vivos en paralelo.** El apex está en Firebase Hosting; `www`
sigue en Wix. No hay redirect entre ellos. El cert TLS del apex declara SAN solo para el apex. Como la
verificación de Android falla ante cualquier redirect, el host canónico debe ser el apex.

**5. Ruta de Play Console cambiada.** App Integrity migró a "Protected with Play", que **no** contiene
la firma de la app. La vía confiable es la URL directa `/keymanagement`.

---

## Testing

Verificación del dominio (ST-01/ST-02) — sondeo HTTP de solo lectura:

```bash
for u in "https://ingeniouscruciblestudios.com/.well-known/assetlinks.json" \
         "https://www.ingeniouscruciblestudios.com/.well-known/assetlinks.json" \
         "https://ingeniouscruciblestudios.com/.well-known/apple-app-site-association" \
         "https://ingeniouscruciblestudios.com/motamaze/" \
         "https://www.ingeniouscruciblestudios.com/motamaze/" \
         "https://ingeniouscruciblestudios.com/robots.txt"; do
  printf "%-72s " "$u"
  curl -s -o /dev/null -w "HTTP %{http_code}  type=%{content_type}  redirects=%{num_redirects}\n" --max-time 20 "$u"
done
```

Cobertura del certificado TLS (ST-02):

```bash
echo | openssl s_client -connect ingeniouscruciblestudios.com:443 \
  -servername ingeniouscruciblestudios.com 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
```

Tests de ST-10:

```bash
python -m pytest tests/test_social_router.py -q
python -m pytest -q
```

Tests nuevos agregados en `tests/test_social_router.py`:

```python
def test_share_base_url_is_the_studio_domain():
    from app.config import Settings

    s = Settings(gcp_project_id="motamaze-test")
    assert s.share_base_url == "https://ingeniouscruciblestudios.com/motamaze"
    assert not s.share_base_url.endswith("/")


async def test_share_urls_carry_the_motamaze_path_segment(client, fake_db, test_settings):
    resp = await client.post(
        CREATE_URL, json=_valid_body(), headers=_auth_headers(test_settings)
    )
    body = resp.json()
    token = body["token"]

    assert body["share_url"] == f"https://ingeniouscruciblestudios.com/motamaze/s/{token}"
    assert body["og_image_url"] == f"https://ingeniouscruciblestudios.com/motamaze/ogimg/{token}"
```

Además se corrigió el fixture obsoleto de `test_share_view_expired`, que sembraba
`"share_url": "https://motamaze.com/s/expiredtoken"`.

---

## Results

Sondeo del dominio:

```
https://ingeniouscruciblestudios.com/.well-known/assetlinks.json         HTTP 200  type=application/json; charset=utf-8  redirects=0
https://www.ingeniouscruciblestudios.com/.well-known/assetlinks.json     HTTP 400  type=text/html; charset=UTF-8  redirects=0
https://ingeniouscruciblestudios.com/.well-known/apple-app-site-association HTTP 200  type=application/json; charset=utf-8  redirects=0
https://ingeniouscruciblestudios.com/motamaze/                           HTTP 200  type=text/html; charset=utf-8  redirects=0
https://www.ingeniouscruciblestudios.com/motamaze/                       HTTP 301  type=  redirects=0
https://ingeniouscruciblestudios.com/robots.txt                          HTTP 404  type=text/html; charset=utf-8  redirects=0
```

Contenido de los scaffolds:

```
=== assetlinks.json ===
[]
=== apple-app-site-association ===
{"applinks":{"apps":[],"details":[]}}
```

Certificado TLS del apex:

```
subject=CN=ingeniouscruciblestudios.com
issuer=C=US, O=Google Trust Services, CN=WR3
notBefore=Jun 27 03:47:50 2026 GMT
notAfter=Sep 25 04:47:11 2026 GMT
X509v3 Subject Alternative Name:
    DNS:ingeniouscruciblestudios.com
```

**SAN cubre únicamente el apex** → host canónico = apex, sin `www`.

Tests:

```
$ python -m pytest tests/test_social_router.py -q
..............                                                           [100%]
14 passed in 0.82s

$ python -m pytest -q
........................................................................ [ 34%]
.............ssssssss................................................... [ 68%]
..................................................................       [100%]
202 passed, 8 skipped in 21.13s
```

### SHA-256 de la app signing key (ST-03)

Obtenido de Play Console vía
`play.google.com/console/u/0/developers/5099504302304988454/app/4972765424320823000/keymanagement`,
bloque **"App signing key certificate"** (no el de upload — usar la upload key hace que la
verificación falle silenciosamente):

```
SHA-256: 9A:08:7E:AA:FF:17:45:10:66:43:69:E0:24:38:0F:9E:AF:2E:C8:65:13:B0:BC:8D:FD:0E:C8:6B:FD:D2:38:58
SHA-1:   5A:50:35:9B:46:54:3A:AA:2C:45:02:3D:59:D5:11:6F:FA:FE:82:AE
MD5:     C2:62:1D:71:C5:22:AA:A5:04:FE:72:F9:25:93:8F:7E
```

32 pares hexadecimales = 32 bytes, longitud correcta para SHA-256.

Contenido definitivo de `assetlinks.json`, listo para publicar (reemplaza el `[]` actual):

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

---

## Actualización 2026-08-14 — motamaze.com comprado, el dominio vuelve a cambiar

El supuesto #1 de la sección Description ("el dominio nunca se registró") se revirtió: Juan compró
`motamaze.com` el 2026-08-12 (vía Wix, renueva 2029-08-12). El plan de dominio dedicado que este ticket
había descartado en julio vuelve a ser el plan real — no es un tercer diseño distinto, es el original.

**Reabre ST-05/06/10/11 (cerradas contra el valor interino) y ST-01 (nuevo acceso a confirmar).**
ST-08/09 (repuntar `www` del sitio corporativo) quedan obsoletas: el juego nunca vivió ahí bajo el plan
de dominio dedicado, así que no hay nada que repuntar.

### `share_base_url` — ST-10, segunda vez

```python
share_base_url: str = "https://motamaze.com"
```

Sin segmento `/motamaze` — el dominio es 100% del juego, no hay nada más que excluir. Los dos tests de
la sección Testing original se reescribieron: `test_share_base_url_is_the_studio_domain` →
`test_share_base_url_is_the_dedicated_domain` (mismo propósito, nuevo literal), y
`test_share_urls_carry_the_motamaze_path_segment` se **invirtió** a
`test_share_urls_have_no_path_segment` — antes guardaba que hubiera un path, ahora guarda que no vuelva
a aparecer uno. Suite: 361 passed (los 8 que antes se saltaban por falta de token de `gcloud` ahora
corren, sin relación con este cambio — fue efecto de reautenticar `gcloud` para T-124 ST-14).

### Team ID ya no bloquea el AASA — T-IOS-3 ST-04

`V6LS3VX234` (membresía de Apple Developer Program activada 2026-08-12). `appID` para el AASA:
`V6LS3VX234.com.ingeniouscruciblestudios.motamaze`. El AASA ya no lleva el campo `paths` — mismo
razonamiento que `assetlinks.json`: dominio dedicado, nada que acotar.

### Wix no puede servir los archivos de verificación — investigado, no solo asumido

Antes de mover DNS se validó explícitamente (no se asumió): Wix no permite escribir archivos en la raíz
del sitio. El único workaround documentado usa un redirect 301/302 vía Wix Velo HTTP Functions +
URL Redirect Manager — y Android **rechaza cualquier redirect** al verificar `assetlinks.json` (ya
documentado en la sección de Hallazgos original, punto 4). Descartado sin necesidad de probarlo en la
cuenta real.

Fuentes: [How to add apple-app-site-association file to your Wix website](https://haashem.medium.com/how-to-add-apple-app-site-association-file-to-your-wix-website-e39f30d25ac9),
[Deep Link Hosting for Shopify, Wix and Locked-Down Hosts](https://siteassociation.com/).

### Firebase Hosting conectado y desplegado — ST-05/ST-06 del lado del código

Proyecto `motamaze` (GCP), sitio de Hosting `motamaze` (`motamaze.web.app`, ya existía como sitio por
defecto aunque nunca se había desplegado nada). Desplegado vía Firebase CLI (instalado y autenticado
en la misma sesión):

```
firebase.json
public/
  index.html                        (placeholder)
  apple-app-site-association        (Content-Type: application/json forzado por header)
  .well-known/
    assetlinks.json                 (Content-Type: application/json forzado por header)
```

Verificado en vivo contra `motamaze.web.app` — ambos archivos devuelven `200`, `Content-Type:
application/json`, cero redirects:

```
$ curl -sI https://motamaze.web.app/apple-app-site-association | grep -i content-type
Content-Type: application/json
$ curl -sI https://motamaze.web.app/.well-known/assetlinks.json | grep -i content-type
Content-Type: application/json
```

Dominio personalizado `motamaze.com` conectado en la consola de Firebase Hosting (modo Quick setup).
Registros DNS que Firebase pidió, enviados a Juan por correo el mismo día — pendientes de que los
aplique en el panel de Wix:

**Agregar:** `A motamaze.com 199.36.158.100`, `TXT motamaze.com hosting-site=motamaze`
**Eliminar:** los 3 `A` actuales de Wix (`185.230.63.107`, `.171`, `.186`)

Certificado TLS y verificación son automáticos una vez que el DNS propague — sin pasos adicionales de
nuestro lado.

### `AndroidManifest.xml` sin `pathPrefix` — T-124 ST-07 (`motamaze-game`)

Reasignada de Juan a Saul el 2026-08-12 (antes T-IOS-3 bloqueaba, ahora no). Implementada sin esperar a
que el DNS propague — el código no depende de que el archivo esté publicado, solo la verificación en
dispositivo real sí:

```xml
<intent-filter android:autoVerify="true">
  <action android:name="android.intent.action.VIEW" />
  <category android:name="android.intent.category.DEFAULT" />
  <category android:name="android.intent.category.BROWSABLE" />
  <data android:scheme="https" android:host="motamaze.com" />
</intent-filter>
```

**Hallazgo de paso, sin relación con el dominio:** `android/` estaba completo en `.gitignore` de
`motamaze-game` (el ignore estándar de plantilla Godot). Este cambio se habría perdido silenciosamente
en cualquier clone nuevo o reinstalación de la plantilla — corregido con una excepción específica para
`AndroidManifest.xml`, más una colisión aparte donde la regla genérica de "builds exportados" (`build/`,
sin anclar) también atrapaba `android/build/` por coincidencia de nombre.

### Pendiente nuevo — cuenta de Wix

La cuenta de Wix a la que Saul tiene acceso ("My Site 1", confirmado Administrador/copropietario) **no
tiene `motamaze.com` registrado** — el dominio resuelve a Wix mediante otra cuenta. No bloquea nada de
lo anterior (Firebase Hosting no necesita esa cuenta), pero sí bloqueaba saber quién podía cambiar el
DNS — resuelto pidiéndole a Juan que ejecute el cambio él mismo, en vez de pedir acceso.

---

## Follow-ups / notes

**Resueltos desde el 2026-08-14 (dejados aquí como registro, no como pendientes):**

- ~~Bloqueado por accesos~~ — Firebase Hosting resuelto del lado del código (ver actualización arriba);
  el push a `motamaze-project` ya no da 403.
- ~~Bloqueado por T-IOS-3 (Team ID)~~ — `V6LS3VX234` obtenido 2026-08-12, AASA ya no bloqueado por esto.
- ~~Dependencia de cliente: `intent-filter`~~ — implementado 2026-08-14 (`motamaze-game`, commit
  `d1a7bb5`), sin `pathPrefix` (dominio dedicado, ver actualización arriba).
- ~~`jwt_issuer`/`jwks_url` en duda~~ — Juan confirmó 2026-08-12 que `api.motamaze.com` sí existirá (vía
  Global External ALB, no domain mapping de Cloud Run — sigue en Preview). Sin cambio de código
  necesario, ya apuntaban ahí. Detalle: T-124 ST-12 (cerrada sin acción).
- ~~Documentación de arquitectura desactualizada~~ — Juan la corrigió directamente 2026-08-12 (commits
  `5944d28`, `362233a` en `motamaze-project`): encontró y arregló bundle ID mal escrito en 10 sitios
  (`com.ingeniouscrucible.motamaze`, faltaba "studios") y el host de OAuth mal descrito como App Link.

**Pendiente real, hoy:**

- **T-124 ST-14** (org policy `iam.allowedPolicyMemberDomains`, necesaria para `api.motamaze.com`) —
  pedido enviado a Juan en Monday 2026-08-14; Juan respondió 2026-08-15 pidiendo el binding exacto
  (ver actualización 2026-08-15 abajo). En espera de que aplique la policy acotada que propuso.
- **ST-01.1** (acceso al repo fuente del sitio) — resuelto en la práctica el 2026-08-15: Juan confirmó
  que es `motamaze_backend` (ver actualización abajo). Cerrada.
- **Cuenta de Wix real** — la de Saul ("My Site 1") no tiene `motamaze.com` registrado. No bloquea
  nada activo (el sitio del juego ya no depende de Wix salvo el DNS, que Juan ya aplicó), sigue sin
  resolver solo de cara a quién administra el registro del dominio en sí.

**Advertencia para T-442:** los App Links **no verifican en builds de debug**. El debug keystore tiene
un SHA-256 distinto al de la app signing key de Play. Probar con un build de Internal Testing.

---

## Actualización 2026-08-15 — DNS aplicado, sitio movido a `hosting/` en este repo

**DNS de `motamaze.com` — aplicado y verificado.** Juan confirmó 2026-08-14 que aplicó los registros
enviados por correo (A `199.36.158.100` + TXT `hosting-site=motamaze`, los 3 A de Wix eliminados).
Verificado de forma independiente 2026-08-15: `nslookup` confirma el A/TXT correctos; `curl` a ambos
archivos de verificación → `200`, `Content-Type: application/json`, 0 redirects, certificado HTTPS
emitido. **ST-05/ST-06 cerradas.**

**Repo del sitio — resuelto: es `motamaze_backend`, no un repo externo.** Se le preguntó a Juan por
correo si existía un repo dedicado al sitio (con la evidencia de que el historial de releases de
Firebase Hosting mostraba un único deploy, manual, mío, sin CI). Su respuesta corrigió un supuesto que
venía arrastrando desde la investigación original del dominio corporativo (2026-07-27, cuando el sitio
sí vivía en un repo Next.js externo): con el dominio dedicado, todo el backend/implementación —
incluido esto — pertenece a `motamaze_backend`. `motamaze-project` es el repo de front-end/proyecto de
Claude, no de infraestructura de backend.

Contenido movido a `hosting/` en este repo (antes vivía solo en un directorio local no versionado):

```
hosting/
├── firebase.json      # Content-Type: application/json forzado en ambos archivos
├── .firebaserc         # proyecto default: motamaze
├── README.md           # instrucciones de deploy + por qué no hay dev/staging
└── public/
    ├── index.html                        # placeholder, no hay landing page real
    ├── apple-app-site-association        # T-124 ST-06
    └── .well-known/assetlinks.json       # T-124 ST-05
```

Re-desplegado desde esta ubicación versionada (`firebase deploy --only hosting --project motamaze`)
para probar el flujo completo — verificado en vivo, sin regresión, mismo resultado que el deploy
manual anterior.

**Por qué no hay `motamaze-dev`/`motamaze-staging` para este sitio:** documentado en `hosting/README.md`
— la verificación de App Links/Universal Links es contra el dominio y certificado reales, un sitio de
prueba en otro dominio no verificaría nada útil, y estos archivos no llaman al backend. Juan preguntó
por esto directamente (por qué no pasa por dev primero); esta es la respuesta que se le dio.

**ST-14 — respuesta de Juan.** Cuestionó correctamente el pedido original: el binding `allUsers` de
`motamaze-backend` (INFRA-007) sigue vivo porque la org policy solo se evalúa al escribir un binding
nuevo, no retroactivamente — probó esto pegándole directo al `run.app`. Pero el motivo real de ST-14
nunca fue ese Cloud Run: es preventivo para `api.motamaze.com` (ST-13, Global External ALB), que sigue
sin construirse (`api.motamaze.com` no resuelve en DNS todavía — confirmado). Juan propuso una policy
acotada (`principalSet://goog/public:all` con `inheritFromParent: true`) en vez de otorgar
`roles/orgpolicy.policyAdmin` a Saul — mejor solución, resuelve de raíz sin depender de que alguien la
aplique después. Confirmado que es correcta, en espera de que la aplique.
