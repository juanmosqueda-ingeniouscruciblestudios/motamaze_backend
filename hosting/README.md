# hosting/ — motamaze.com (Firebase Hosting)

Fuente versionada del sitio estático servido en `motamaze.com` vía Firebase Hosting
(proyecto GCP `motamaze`, sitio `motamaze`). Cubre únicamente los archivos de
verificación de App Links/Universal Links que necesita T-124 — no es un sitio de
marketing.

Movido aquí 2026-08-15 (antes se desplegaba manualmente desde un directorio local
no versionado). Ver `changelogs/T-124-app-links-universal-links.md` para el
contexto completo del ticket.

## Contenido

- `public/index.html` — placeholder ("coming soon"), no hay landing page real todavía.
- `public/apple-app-site-association` — Universal Links (T-124 ST-06). `appID` usa
  el Team ID de Apple (`V6LS3VX234`).
- `public/.well-known/assetlinks.json` — App Links (T-124 ST-05). SHA-256 es el de
  la app signing key de Play Console.
- `firebase.json` — fuerza `Content-Type: application/json` en ambos archivos
  (sin esto, el AASA sin extensión se sirve como `text/plain`/`octet-stream` y
  Apple lo rechaza).
- `.firebaserc` — fija el proyecto default a `motamaze` para que `firebase deploy`
  no dependa de `--project` a mano.

## Deploy

```bash
cd hosting
firebase deploy --only hosting --project motamaze
```

Requiere estar autenticado (`firebase login`) con una cuenta que tenga acceso al
proyecto `motamaze`.

## Por qué no hay versión dev/staging

A diferencia del resto de la infraestructura (`terraform/environments/{dev,staging,prod}`),
este sitio no tiene equivalente en `motamaze-dev`/`motamaze-staging`. Motivo: la
verificación de App Links/Universal Links de Android/iOS es contra el dominio y el
certificado de firma **reales** — un sitio de prueba en otro dominio no verificaría
nada útil, y estos 3 archivos no llaman al backend ni dependen de ningún entorno.
Si `motamaze.com` alguna vez aloja algo más que estos archivos de verificación
(landing page real, etc.), vale la pena reconsiderar esto.

## Validar después de un deploy

```bash
curl -sD - -o /dev/null https://motamaze.com/.well-known/assetlinks.json
curl -sD - -o /dev/null https://motamaze.com/apple-app-site-association
```

Esperado en ambos: `HTTP/1.1 200`, `Content-Type: application/json`, sin
`Location` (0 redirects) — cualquier redirect rompe la verificación de Android.
