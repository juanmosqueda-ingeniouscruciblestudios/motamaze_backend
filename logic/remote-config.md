# Firebase Remote Config Integration (T-244) — Estado actual

> Última actualización: 2026-07-24

`app/services/remote_config_service.py` es el único punto de acceso a Firebase Remote Config del
backend. Ningún router llama a la API de Remote Config directamente — siempre pasa por
`remote_config_service.get_value(...)`.

---

## Diseño del cliente

**REST crudo + `google-auth` (Application Default Credentials), no el SDK `firebase-admin`** — mismo
patrón que `admob_api.py` (OAuth + `urllib.request`, sin SDK). Decisión forzada por
`motamaze_backend/CLAUDE.md`: no agregar dependencias/servicios de terceros nuevos sin aprobación de
Juan+Saul; REST + `google-auth` ya estaban disponibles en el proyecto.

```
GET https://firebaseremoteconfig.googleapis.com/v1/projects/{project_id}/remoteConfig
Scope OAuth: https://www.googleapis.com/auth/firebase.remoteconfig
```

Forma del template (todos los valores son **strings**, casteo es responsabilidad del caller):
```json
{"parameters": {"<key>": {"defaultValue": {"value": "<string>"}}}}
```

---

## `get_value()` — filosofía "nunca lanza, siempre cae a un default"

```python
async def get_value(project_id: str, key: str, default: T, cast: Callable[[str], T] = str) -> T:
```

Cualquier fallo en cualquier punto de la cadena — fetch de red, `google.auth`, template vacío, key
ausente, o el `cast` fallando — **regresa `default` silenciosamente** (con un `logger.warning`, nunca
una excepción). Un endpoint de gameplay (`/lives`) no debe caerse porque Remote Config esté caído o
mal configurado.

## Cache

`TTLCache(maxsize=2, ttl=300)` (5 min) a nivel de módulo, keyed por `project_id` — el template
completo se cachea (no valor por valor), así que 2 lecturas de 2 keys distintos del mismo proyecto en
la misma ventana de 5 min hacen **1 sola llamada de red**, no 2. `maxsize=2` porque hay como máximo 2
proyectos reales (`motamaze-dev`, `motamaze`) — no hay necesidad de más.

## Scope: solo `defaultValue`, sin condiciones

Remote Config soporta "conditions" (overrides por país/versión de app/etc.) pero el backend no las
lee — no tiene contexto de dispositivo/versión de cliente por request para evaluarlas correctamente.
Solo se lee el `defaultValue` plano de cada parámetro. Si en el futuro se necesita segmentación
condicional server-side, es una extensión deliberada de este cliente, no algo que ya soporte.

---

## Parámetros migrados (`app/routers/game.py`)

| Constante anterior (hardcodeada) | Key en Remote Config | Default de fallback |
|---|---|---|
| `REGEN_INTERVAL_SECS = 1800` | `regen_interval_secs` | `1800` |
| `DEFAULT_MAX_LIVES = 5` | `default_max_lives` | `5` |

Ambas constantes **siguen existiendo en el código** — ya no se leen directamente, solo se usan como
el `default=` que se le pasa a `get_value()`. Resueltas una vez por request vía
`_resolve_lives_config(settings)`, llamado al inicio de `GET /lives`, `POST /lives/spend` y
`POST /lives/grant`, y encadenado explícitamente a través de `_apply_regen`/`_next_regen_dt`/
`_spend_txn` (dejaron de leer un global del módulo).

Lista completa de parámetros + qué controla cada uno: `docs/CONFIG_REFERENCE.md`.

---

## "Change auditing"

Satisfecho por el historial de versiones nativo de la consola de Firebase Remote Config (quién
publicó, cuándo, rollback a versión anterior) — **sin código de auditoría adicional en el backend**.
Ver `docs/CONFIG_REFERENCE.md` para la decisión completa.

---

## Limitaciones conocidas

- **`POST /lives/spend` no tiene cobertura de test para su integración con Remote Config** —
  `FakeFirestoreClient` (`tests/conftest.py`) no soporta `.transaction()`, y `_spend_txn` está
  decorado con `@async_transactional` (Firestore real). `_apply_regen`/`_next_regen_dt` (compartidas
  con `GET /lives`, que sí tiene cobertura) sí están probadas contra valores resueltos de Remote
  Config — lo no probado es específicamente el wrapping transaccional de Firestore, no la lógica de
  T-244. Gap pre-existente (el endpoint no tenía tests de ningún tipo antes de este ticket tampoco).
- **Ningún parámetro publicado todavía en la consola de Firebase** (ST-05, aún no completado a la
  fecha de este documento) — el backend corre 100% con los defaults de fallback hasta entonces.
- **No hay parámetros en prod** — solo se planea configurar dev primero.
