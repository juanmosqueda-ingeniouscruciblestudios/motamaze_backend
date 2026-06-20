# INFRA-004 — RS256 Keypair en Secret Manager + JWKS endpoint

| Campo | Valor |
|---|---|
| **Tipo** | Infra/DevOps / Security |
| **Prioridad** | Alta — desbloquea AUTH-001 (firma de JWTs) |
| **Status** | In Progress — ST-01 ✅, ST-02 ✅, ST-03–05 pendientes INFRA-003 |
| **Fecha planeada** | 6/29/2026 |
| **Fecha real inicio** | 2026-06-19 (ST-01–02 adelantados) |
| **Workstream** | Infra/DevOps |
| **Owner** | Saul Zavala Morin |
| **Monday.com Item ID** | 12272254519 |
| **Depends on** | INFRA-001 ✅ (SA + IAM), INFRA-002 ✅ (naming convention: `jwt-private-key`), INFRA-003 ⬜ (para ST-03+: JWKS endpoint necesita FastAPI) |
| **Desbloquea** | AUTH-001 (POST /auth/login — firma JWT), todos los endpoints que requieren verificación de JWT |

---

## Descripción

MotaMaze usa RS256 (RSA-SHA256) para firmar los JWT de acceso y refresh. RS256 fue elegido sobre HS256 porque:

- **Asimétrico:** FastAPI firma con la clave privada; el cliente Godot y terceros verifican con la pública (expuesta vía JWKS) — la clave privada nunca sale de Secret Manager.
- **JWKS estándar:** El endpoint `/.well-known/jwks.json` permite rotación de claves sin despliegues del cliente — el cliente descarga el JWKS y usa el `kid` correcto.
- **Auditable:** Cada JWT lleva un `kid` que identifica qué versión de la clave lo firmó.

**Decisión de scope:**
- Un keypair por entorno (dev, staging, prod) — aislamiento total. Un JWT de dev no puede verificarse en prod.
- Dev y staging: keypairs se generan cuando se crean los proyectos GCP (INFRA-006).
- Hoy: solo prod (`motamaze`).

---

## Criterios de aceptación

- [x] `secretmanager.googleapis.com` habilitada en proyecto `motamaze`
- [x] Keypair RS256 2048-bit generado y subido a Secret Manager como `jwt-private-key` (version 1)
- [x] Archivos locales eliminados inmediatamente después del upload — clave privada solo existe en Secret Manager
- [x] SA `game-api-backend` tiene `roles/secretmanager.secretAccessor` → puede leer el secret en runtime
- [ ] Endpoint `GET /.well-known/jwks.json` implementado en FastAPI (pendiente INFRA-003)
- [ ] Signing FastAPI usa clave privada desde Secret Manager vía ADC (pendiente INFRA-003)
- [ ] Documentar path de rotación de claves

---

## Estado previo

| Recurso | Estado antes de INFRA-004 |
|---|---|
| `secretmanager.googleapis.com` en `motamaze` | ❌ No habilitada |
| Secret `jwt-private-key` | ❌ No existe |
| SA con `secretAccessor` | ✅ Ya tenía el rol (INFRA-001 ST-07) |
| JWKS endpoint | ❌ No existe (FastAPI no existe aún) |

---

## Implementación — Subtareas

### ST-01 — Habilitar `secretmanager.googleapis.com` ✅ Done (2026-06-19)

**Contexto:** INFRA-001 ST-03 habilitó las APIs core de GCP (BigQuery, Firestore, Storage, PubSub, Monitoring, Logging, Firebase), pero Secret Manager no estaba en esa lista. Se habilitó como parte de INFRA-004 al intentar el primer `gcloud secrets describe`.

**Comando ejecutado:**
```bash
gcloud services enable secretmanager.googleapis.com --project=motamaze
# Operation "operations/acat.p2-542009654415-be0487ed-fd74-4376-a6cf-cc1345757522" finished successfully.
```

**Verificación:**
```bash
gcloud services list --enabled --filter="config.name:secretmanager.googleapis.com" --project=motamaze
```

---

### ST-02 — Generar keypair RS256 + subir a Secret Manager ✅ Done (2026-06-19)

**Por qué 2048 bits:** Tamaño estándar mínimo para RS256 en producción. 4096 bits añadiría ~4ms de latencia en firma sin beneficio práctico para un MVP con < 10k usuarios.

**Por qué `PRIVATE KEY` (PKCS#8) y no `RSA PRIVATE KEY` (PKCS#1):** `openssl genrsa` produce PKCS#8 por defecto en OpenSSL 3.x — es el formato que espera la librería `python-jose` / `cryptography` que usará FastAPI.

**Comandos ejecutados:**
```bash
mkdir -p /tmp/motamaze-keys

# ST-02a: Generar private key
openssl genrsa -out /tmp/motamaze-keys/jwt_private.pem 2048

# ST-02b: Extraer public key (para verificación local)
openssl rsa -in /tmp/motamaze-keys/jwt_private.pem -pubout -out /tmp/motamaze-keys/jwt_public.pem

# ST-02c: Verificar integridad
openssl rsa -in /tmp/motamaze-keys/jwt_private.pem -check -noout
# RSA key ok

# Crear secret en Secret Manager
gcloud secrets create jwt-private-key \
  --project=motamaze \
  --replication-policy=automatic

# Subir private key
gcloud secrets versions add jwt-private-key \
  --project=motamaze \
  --data-file=/tmp/motamaze-keys/jwt_private.pem

# Eliminar archivos locales inmediatamente
rm -rf /tmp/motamaze-keys
```

**Parámetros:**
| Parámetro | Valor | Razón |
|---|---|---|
| Algoritmo | RSA 2048-bit | Estándar mínimo para RS256 JWT |
| Secret ID | `jwt-private-key` | Per INFRA-002 naming: `{componente}-{descripcion-kebab}`, sin sufijo de env |
| Replication policy | `automatic` | GCP gestiona la replicación entre regiones |
| Versión subida | `1` (enabled) | Primera versión, estado activo |

---

### ST-03 — Implementar `GET /.well-known/jwks.json` ⬜ Pending INFRA-003

**Depende de:** INFRA-003 (FastAPI scaffold + Cloud Run service)

**Descripción del endpoint:**
El endpoint extrae la clave pública de la privada en runtime (Secret Manager → python-jose → JWK) y la devuelve en formato JWKS estándar RFC 7517.

```python
# app/routers/auth.py (fragmento — se implementa en AUTH-001)
from fastapi import APIRouter
from google.cloud import secretmanager
from jose import jwk
import json

router = APIRouter()

@router.get("/.well-known/jwks.json")
async def jwks():
    client = secretmanager.SecretManagerServiceClient()
    name = "projects/motamaze/secrets/jwt-private-key/versions/latest"
    response = client.access_secret_version(request={"name": name})
    private_key_pem = response.payload.data.decode("utf-8")

    key = jwk.construct(private_key_pem, algorithm="RS256")
    public_jwk = key.public_key().to_dict()
    public_jwk["kid"] = "motamaze-2026-v1"
    public_jwk["use"] = "sig"

    return {"keys": [public_jwk]}
```

**Formato de respuesta esperado:**
```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "motamaze-2026-v1",
      "n": "<base64url-encoded RSA modulus>",
      "e": "AQAB"
    }
  ]
}
```

---

### ST-04 — Wire signing con clave privada de Secret Manager ⬜ Pending INFRA-003

**Depende de:** ST-03, INFRA-003

**Patrón en FastAPI (AUTH-001):**
```python
# app/services/jwt_service.py
from google.cloud import secretmanager
from jose import jwt
from datetime import datetime, timedelta, timezone

def _get_private_key() -> str:
    client = secretmanager.SecretManagerServiceClient()
    name = "projects/motamaze/secrets/jwt-private-key/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")

def create_access_token(sub: str, jti: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(seconds=900),  # 15 min
        "iss": "https://api.motamaze.com",
        "kid": "motamaze-2026-v1",
    }
    return jwt.encode(payload, _get_private_key(), algorithm="RS256")
```

**Nota de performance:** La lectura de Secret Manager tiene ~50ms de latencia. Se implementará un cache en memoria (`functools.lru_cache` o `cachetools.TTLCache` con TTL=300s) para no llamar a Secret Manager en cada request.

---

### ST-05 — Documentar path de rotación de claves ⬜ Pending (puede hacerse antes de INFRA-003)

**Proceso de rotación:**

1. **Generar nueva clave** (sin eliminar la vieja):
   ```bash
   openssl genrsa -out /tmp/jwt_private_v2.pem 2048
   gcloud secrets versions add jwt-private-key \
     --project=motamaze \
     --data-file=/tmp/jwt_private_v2.pem
   rm /tmp/jwt_private_v2.pem
   # → Secret Manager crea version 2 (enabled), version 1 sigue enabled
   ```

2. **Actualizar `kid`** en el código (de `motamaze-2026-v1` a `motamaze-2026-v2`) y desplegar.

3. **JWKS endpoint**: servir ambas versiones por 24h (mientras tokens v1 expiran). Después de 24h, deshabilitar version 1:
   ```bash
   gcloud secrets versions disable 1 --secret=jwt-private-key --project=motamaze
   ```

4. **Tokens refresh (14 días):** Los refresh tokens v1 no pueden reverificarse con la clave v2. Estrategia MVP: forzar logout de todos los usuarios al rotar (aceptable para MVP — comunicar en notas de versión).

---

## Resultados verificados

```bash
# Verificar versión en Secret Manager
gcloud secrets versions list jwt-private-key --project=motamaze
NAME  STATE    CREATED              DESTROYED
1     enabled  2026-06-20T01:33:40  -

# Verificar que la clave es legible (primeras 2 líneas del PEM)
gcloud secrets versions access 1 --secret=jwt-private-key --project=motamaze | head -2
-----BEGIN PRIVATE KEY-----
MIIEvwIBADANBgkqhkiG9w0BAQEFAAOCAQ8A...

# Verificar roles del SA (secretAccessor ya presente desde INFRA-001)
gcloud projects get-iam-policy motamaze \
  --flatten="bindings[].members" \
  --filter="bindings.members:game-api-backend" \
  --format="table(bindings.role)"
ROLE
roles/bigquery.dataEditor
roles/cloudtrace.agent
roles/datastore.user
roles/secretmanager.secretAccessor   ← ✅ puede leer jwt-private-key
roles/storage.objectAdmin
```

---

## Follow-ups / Notes

- **Dev y staging (`motamaze-dev`, `motamaze-staging`):** Keypairs pendientes — se generan cuando INFRA-006 cree esos proyectos. Cada entorno debe tener su propia clave; un JWT de dev nunca debe verificarse en prod.
- **`bigquery.jobUser` role:** El SA tiene `bigquery.dataEditor` pero no `bigquery.jobUser`. Para streaming inserts (DATA-002, `insertAll` API), `dataEditor` es suficiente — `jobUser` solo es necesario para query jobs y load jobs. Verificar cuando DATA-002 ST-03 ejecute el primer streaming insert.
- **`kid` valor:** `"motamaze-2026-v1"` es el `kid` planeado para la primera versión. Cambiar el año si la rotación ocurre en 2027+.
- **Cache de Secret Manager:** En AUTH-001 agregar `TTLCache` con TTL=300s para no leer SM en cada request de JWT. Cold start de Cloud Run ya lee la clave al iniciar el proceso si se usa `@lru_cache`.
- **INFRA-001 audit:** Agregar `secretmanager.googleapis.com` a la lista de APIs habilitadas en el INFRA-001 changelog (se habilitó aquí, no allá — documentar para que el inventario sea preciso).
