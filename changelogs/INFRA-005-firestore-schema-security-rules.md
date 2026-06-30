# INFRA-005 — Firestore Schema + Security Rules (Production mode)

| Campo | Valor |
|---|---|
| **Tipo** | Infra/DevOps / Data Model |
| **Prioridad** | Alta — define la estructura de datos del backend |
| **Status** | ✅ Done — ST-01 ✅ schema definido, ST-02 ✅ rules desplegadas, ST-03 ✅ 8/8 tests passed (2026-06-30), ST-04 ✅ DATA_MODEL.md creado |
| **Fecha planeada** | 6/29–6/30/2026 |
| **Fecha real inicio** | 2026-06-19 (adelantado — no bloquea en INFRA-003 para diseño) |
| **Workstream** | Infra/DevOps |
| **Owner** | Saul Zavala Morin |
| **Monday.com Item ID** | 12272254520 |
| **Depends on** | REST-001 ✅ (para saber qué colecciones necesita cada endpoint) |
| **Desbloquea** | AUTH-001 (usa `users`, `sessions`, `revoked_jtis`), PAY-001 (usa `entitlements`), GAME-001 (usa `progress`, `lives`) |

---

## Descripción

Firestore es la base de datos operacional de MotaMaze — almacena sesiones activas, progresión del jugador, vidas, y entitlements. Todos los accesos van a través de FastAPI (Admin SDK), que bypasea las security rules. Las security rules actúan como red de seguridad para prevenir acceso directo desde clientes comprometidos o no autorizados.

**Por qué deny-all:**
- El cliente Godot nunca accede directamente a Firestore — solo hace HTTP a FastAPI
- Si el APK es decompiladado, el atacante no encuentra credenciales de Firestore
- FastAPI con Admin SDK tiene acceso total independientemente de las rules

**Scope de INFRA-005:**
- 6 colecciones: `users`, `sessions`, `revoked_jtis`, `progress`, `lives`, `entitlements`
- Rules en modo producción: `allow read, write: if false` para todos los documentos
- Schema completo documentado en `docs/DATA_MODEL.md`
- Tests de rules: pendientes hasta que INFRA-003 tenga el emulador configurado

---

## Criterios de aceptación

- [x] 6 colecciones definidas con todos sus campos y tipos — ver `docs/DATA_MODEL.md`
- [x] `firestore.rules` con deny-all deployado en proyecto `motamaze` (prod)
- [x] Test: escritura directa desde un cliente sin Admin SDK falla con `PERMISSION_DENIED` — 8/8 tests passed vía Firebase Rules REST API (2026-06-30)
- [x] Schema documentado en `docs/DATA_MODEL.md`

---

## Estado previo

| Recurso | Estado antes de INFRA-005 |
|---|---|
| `firestore.rules` en `motamaze` | Reglas default (allow si autenticado con Firebase Auth — inseguro para nuestro caso) |
| Schema de colecciones | No documentado |
| `docs/DATA_MODEL.md` | No existía |

---

## Implementación — Subtareas

### ST-01 — Definir colecciones (fields + indexes) ✅ Done (2026-06-19)

**Colecciones definidas:**

| Colección | Document ID | Uso principal |
|---|---|---|
| `users/{uid}` | Google OAuth `sub` | Perfil + consent + skin equipada |
| `sessions/{session_id}` | UUID v4 | Tracking de sesiones — duración para BQ |
| `revoked_jtis/{jti}` | JWT `jti` claim | Lista negra de tokens — logout / delete account |
| `progress/{uid}` | = `uid` | Niveles completados + estrellas + scores |
| `lives/{uid}` | = `uid` | Contador de vidas + regen server-authoritative |
| `entitlements/{uid}` | = `uid` | IAP: no_ads, skins, life packs |

**Decisión de schema para `sessions`:**
- `session_id` se genera en `POST /auth/login` y se incluye como claim `sid` en el JWT
- `POST /auth/logout` extrae `sid` del JWT → lookup directo sin query
- Evita índice compuesto `uid+started_at` para el MVP

**Índices:**
- MVP: ningún índice compuesto necesario — todos los accesos son por document ID
- Índices futuros documentados en `docs/DATA_MODEL.md`

**Schema completo:** → [docs/DATA_MODEL.md](../docs/DATA_MODEL.md)

---

### ST-02 — Security Rules en modo producción ✅ Done (2026-06-19)

**Archivo:** `firestore.rules` (en raíz del repo de documentación — se copiará al repo backend INFRA-003)

```javascript
rules_version = '2';

// MotaMaze — Firestore Security Rules
// Todas las lecturas/escrituras van por FastAPI (Admin SDK) — el cliente Godot nunca
// accede a Firestore directamente. Deny-all es la postura correcta aquí.
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

**Deploy vía Firebase Rules REST API** (firebase-tools v15.22 incompatible con Node 24):

```bash
# 1. Habilitar Firebase Rules API
gcloud services enable firebaserules.googleapis.com --project=motamaze

# 2. Crear ruleset
TOKEN=$(gcloud auth print-access-token --project=motamaze)
RESPONSE=$(curl -s -X POST \
  "https://firebaserules.googleapis.com/v1/projects/motamaze/rulesets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "x-goog-user-project: motamaze" \
  -d '{"source": {"files": [{"name": "firestore.rules", "content": "rules_version = '\''2'\'';\nservice cloud.firestore {\n  match /databases/{database}/documents {\n    match /{document=**} {\n      allow read, write: if false;\n    }\n  }\n}\n"}]}}')
# → rulesetName: projects/motamaze/rulesets/523e539f-cc05-4028-a718-344fdcfd8cf0

# 3. Actualizar release cloud.firestore para activar las rules
curl -s -X PATCH \
  "https://firebaserules.googleapis.com/v1/projects/motamaze/releases/cloud.firestore" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "x-goog-user-project: motamaze" \
  -d '{"release": {"name": "projects/motamaze/releases/cloud.firestore", "rulesetName": "projects/motamaze/rulesets/523e539f-cc05-4028-a718-344fdcfd8cf0"}}'
```

---

### ST-03 — Test de rules ✅ Done (2026-06-30)

**Depende de:** INFRA-003 (FastAPI repo con Firebase emulator configurado)

**Tests planeados:**

**Implementación real (2026-06-30) — Firebase Rules REST API:**

No se usó emulador (firebase-tools incompatible con Node 24). Alternativa: `projects.test` endpoint del Firebase Rules REST API, que acepta reglas inline + requests simulados y devuelve ALLOW/DENY sin runtime real.

**Archivo:** `tests/test_firestore_rules.py`

```bash
# Ejecutar:
GCLOUD_TOKEN=$(gcloud auth print-access-token) pytest tests/test_firestore_rules.py -v

# Salida (2026-06-30):
# tests/test_firestore_rules.py::TestAuthenticatedUserDenied::test_read_denied PASSED
# tests/test_firestore_rules.py::TestAuthenticatedUserDenied::test_write_create_denied PASSED
# tests/test_firestore_rules.py::TestAuthenticatedUserDenied::test_write_update_denied PASSED
# tests/test_firestore_rules.py::TestAuthenticatedUserDenied::test_delete_denied PASSED
# tests/test_firestore_rules.py::TestUnauthenticatedDenied::test_unauthenticated_read_denied PASSED
# tests/test_firestore_rules.py::TestUnauthenticatedDenied::test_unauthenticated_write_denied PASSED
# tests/test_firestore_rules.py::TestDeployedRuleset::test_deployed_rules_are_deny_all PASSED
# tests/test_firestore_rules.py::TestDeployedRuleset::test_deployed_rules_have_no_permissive_clauses PASSED
# 8 passed in 3.60s
```

**Qué testean los 8 tests:**

| Test clase | Qué verifica |
|---|---|
| `TestAuthenticatedUserDenied` | GET/CREATE/UPDATE/DELETE denegados para usuario Firebase con auth (`uid: "test-uid-001"`) en las 7 colecciones |
| `TestUnauthenticatedDenied` | GET/CREATE denegados sin ningún auth context (request anónimo) |
| `TestDeployedRuleset` | Content del ruleset desplegado en prod contiene `allow read, write: if false` y no tiene cláusulas permisivas |

---

### ST-04 — Documentar schema en `docs/DATA_MODEL.md` ✅ Done (2026-06-19)

**Archivo creado:** [docs/DATA_MODEL.md](../docs/DATA_MODEL.md)

Documenta:
- 6 colecciones con todos los campos, tipos, y ejemplos
- Lógica de edge cases (sesiones sin logout, TTL de JTIs)
- Tabla de endpoints → operaciones Firestore
- Índices actuales vs. futuros
- Política de retención y TTL
- Diagrama de relaciones entre colecciones

---

## Resultados verificados

```bash
# Verificar que las rules están activas en prod
TOKEN=$(gcloud auth print-access-token --project=motamaze)
curl -s "https://firebaserules.googleapis.com/v1/projects/motamaze/releases/cloud.firestore" \
  -H "Authorization: Bearer $TOKEN" \
  -H "x-goog-user-project: motamaze"

# Output:
# {
#   "name": "projects/motamaze/releases/cloud.firestore",
#   "rulesetName": "projects/motamaze/rulesets/523e539f-cc05-4028-a718-344fdcfd8cf0",
#   "updateTime": "2026-06-20T02:02:05.178970Z"
# }
```

---

## Follow-ups / Notes

- **ST-03 tests:** Ejecutar cuando INFRA-003 tenga el Firebase emulator configurado (`firebase emulators:start --only firestore`). Los tests usan un cliente Firestore sin Admin SDK para verificar que las deny-all rules funcionan.
- **firebase-tools incompatible con Node 24:** `firebase-tools@15.22` falla al importar `winston` en Node 24 (missing `wrapAsync.js`). Alternativas para el futuro: (1) usar `nvm` para Node 18/20 LTS, (2) instalar firebase-tools globalmente con Node 18, (3) usar el script de deploy REST que ya tenemos. Documentar en CI-001 para el pipeline de GitHub Actions.
- **Rules en dev/staging:** Se crean con INFRA-006 cuando existan los proyectos. Usar el mismo `firestore.rules` — deny-all aplica en todos los entornos.
- **`session_id` en JWT:** El claim `sid` del access token contiene el `session_id`. Agregar a la spec de JWT en REST-001 cuando Juan firme el sign-off (actualmente el JWT spec de REST-001 no incluye `sid` explícitamente — pendiente confirmación).
- **Regen interval de vidas:** `REGEN_INTERVAL_SECS` (default 1800 = 30 min) viene de Remote Config — no está hardcodeado en el schema. FastAPI lo lee vía Remote Config en cada llamada a `GET /lives`.
