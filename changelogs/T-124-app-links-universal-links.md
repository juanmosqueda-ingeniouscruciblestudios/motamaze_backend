# T-124 — HTTPS App Links (Android) / Universal Links (iOS) para share URL deep links

| Field | Value |
|---|---|
| **Type** | Feature / Infra |
| **Priority** | Medium — sin esto los share links de T-440 abren el navegador en vez de la app |
| **Status** | In Progress — ST-02, ST-03 y ST-10 ✅ (2026-07-27). Resto bloqueado por accesos y por T-IOS-3 |
| **Date** | 2026-07-27 |
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

## Follow-ups / notes

**Bloqueado por accesos** (solicitados a Juan por correo 2026-07-27): publicar ambos archivos requiere
acceso al repositorio del sitio web y al proyecto de Firebase Hosting. El redirect `www` → apex
requiere además acceso al panel DNS, que reside en la cuenta de Wix.

**Bloqueado por T-IOS-3:** el AASA necesita `appID` = `TeamID.bundleID`. El Team ID **no existe** — la
inscripción al Apple Developer Program está sin iniciar. Ya se había diferido por la misma causa en
AUTH-004 y PAY-004. La mitad iOS de T-124 no puede cerrarse en la ventana 2026-08-03/04.

**Dependencia de cliente (Juan):** `intent-filter` con `autoVerify` + `pathPrefix="/motamaze/"` en el
`AndroidManifest.xml`. Sin esto la app interceptaría todo el dominio institucional. El equivalente iOS
(entitlement Associated Domains) ya está en T-IOS-12.

**Orden de ejecución:** publicar primero `assetlinks.json`, después generar el build con `autoVerify` —
la verificación se dispara durante la instalación.

**Advertencia para T-442:** los App Links **no verifican en builds de debug**. El debug keystore tiene
un SHA-256 distinto al de la app signing key de Play. Probar con un build de Internal Testing.

**Fuera de alcance, requiere decisión:** `jwt_issuer` y `jwks_url` apuntan a `api.motamaze.com`
(`app/config.py`, `.env.example`, `terraform/modules/motamaze-env/main.tf`). Si tampoco existirá ese
subdominio, hay que decidir su reemplazo — pero `jwt_issuer` va **firmado dentro de los JWT ya
emitidos**, así que el cambio tiene radio de impacto sobre T-111 y T-120, ambas cerradas.

**Documentación de arquitectura desactualizada:** `motamaze-project/rnd_research/2026-06-04_motamaze-architecture-final.md`
asume `motamaze.com` como dominio de deep links en las líneas 58, 517, 1364, 1764 y 2006, incluyendo el
No-Go item 14. La corrección está bloqueada: sin permiso de push en `motamaze-project` (403).
