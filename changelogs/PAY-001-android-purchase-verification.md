# PAY-001 — POST /payments/android/verify (Play Developer API)

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | Critical — server-authoritative IAP verification |
| **Status** | ✅ Done — ST-01 ✅ implementation + commit `cd9ad1e` (2026-07-02); ST-02 ✅ error-path tests PASS (2026-07-09); ST-03 ✅ movida a T-607 (2026-07-13) |
| **Date** | 2026-07-02 |
| **Workstream** | Payments |
| **Commit** | `cd9ad1e` |
| **Depends-on** | EXT-001 ✅ (Play Developer API + SA permissions), INFRA-005 ✅ (Firestore schema), T-220 ✅ (lives Firestore pattern) |
| **Desbloquea** | T-253 / PAY-002 (Daily reconciliation job) |

---

## Descripción

Reemplaza el stub de `POST /payments/android/verify` con implementación real. El flujo es:

```
[Godot] compra via Play Billing SDK → recibe purchaseToken
[Godot] POST /payments/android/verify { purchase_token, product_id, session_id }
[Backend] Play Developer API: purchases.products.get(purchase_token)
[Backend] verifica purchaseState == 0 (PURCHASED)
[Backend] Firestore: otorga entitlement al usuario
[Backend] Play Developer API: consume (consumable) o acknowledge (non-consumable)
[Backend] BigQuery: inserta purchase_events + entitlement_grants (background)
[Backend] responde 200 al cliente con el entitlement otorgado
```

**iOS** (`POST /payments/ios/verify`) se queda como stub — iOS fuera de scope MVP fase 1.

---

## Estado previo (stub DATA-002 ST-08)

```python
# android_verify devolvía siempre:
verification_status = "verified"
grant_status = "granted"
# Sin llamada a Play Developer API. Sin writes a Firestore. Sin validación de purchaseToken.
# order_id: None  # no había
# current_lives: None  # no había
```

---

## Implementación

### `app/services/play_api.py` (nuevo)

Cliente REST para Google Play Developer API. Sin nueva dependencia en `pyproject.toml`:
- Auth: `google.auth.default(scopes=["https://www.googleapis.com/auth/androidpublisher"])` — en Cloud Run usa el SA `game-api-backend` automáticamente. Token cacheado en módulo, refresca solo cuando `_credentials.valid == False`.
- HTTP: `urllib.request` (stdlib) + `asyncio.to_thread()` para async wrapping.

```python
async def get_product_purchase(pkg, product_id, purchase_token) -> dict
async def acknowledge_product_purchase(pkg, product_id, purchase_token) -> None
async def consume_product_purchase(pkg, product_id, purchase_token) -> None
```

Errors: `PlayAPIError(http_status, error_body)` — el router mapea 4xx → 402 `PAY_VERIFICATION_FAILED`, 5xx / network → 503 `PAY_STORE_UNAVAILABLE`.

### `app/config.py`

```python
play_package_name: str = "com.ingeniouscruciblestudios.motamaze"
```

### `app/routers/payments.py`

**`_infer_entitlement()` — actualizado:**

| product_id | entitlement_type | product_type | quantity |
|---|---|---|---|
| `lives_pack_N` | `life_pack` | `consumable` | N |
| `no_ads` | `no_ads` | `non_consumable` | None |
| `skin_*` | `skin` | `non_consumable` | None |
| `season_pass_gold` | `season_pass` | `non_consumable` | None |
| desconocido | None | None | None → 400 PAY_PRODUCT_NOT_FOUND |

**`_grant_lives_iap(db, user_id, quantity, now) -> int`** (nuevo helper):
- Lee `lives/{uid}`, aplica cap: `actual = min(quantity, max_lives - count)`
- Escribe `count`, `next_regen_at`, `updated_at` con `merge=True` (mismo patrón que T-220 POST /lives/grant)
- Returns `new_count` (current_lives en la respuesta)

**`android_verify()` — flujo completo:**

```
1. _infer_entitlement() → 400 PAY_PRODUCT_NOT_FOUND si desconocido
2. play_api.get_product_purchase() → 503 PAY_STORE_UNAVAILABLE (network/5xx)
                                    → 402 PAY_VERIFICATION_FAILED (4xx)
3. purchaseState == 2 → 202 PENDING
   purchaseState == 1 → 402 PAY_VERIFICATION_FAILED
   purchaseState == 0 → PURCHASED, continúa
4. Idempotencia: consumptionState==1 (consumable) o acknowledgementState==1 (non-consumable)
   → retorna grant_status="already_granted" con current_lives actual de Firestore
5. Grant Firestore:
   - life_pack → _grant_lives_iap()
   - no_ads → entitlements/{uid}.no_ads = True (merge)
   - skin → entitlements/{uid}.skins = ArrayUnion([product_id]) (merge)
   - season_pass → season_progress/{uid}.has_gold_pass = True (merge)
6. consume() o acknowledge() — non-fatal si falla (PAY-002 reconcilia)
7. BQ background: purchase_events + entitlement_grants (solo si grant_status=="granted")
8. Response 200 con order_id real, verification_status, grant_status, entitlement
```

**Errores:**

| HTTP | error_code | Cuándo |
|---|---|---|
| 400 | `PAY_PRODUCT_NOT_FOUND` | product_id no reconocido por `_infer_entitlement` |
| 402 | `PAY_VERIFICATION_FAILED` | Play API rechaza el token (4xx) o purchaseState != 0 |
| 503 | `PAY_STORE_UNAVAILABLE` | Play API 5xx o network error |

---

## Testing

### ST-01 — Code review y commit

Commit `cd9ad1e` — 3 archivos:
- `app/services/play_api.py` — nuevo (57 líneas)
- `app/routers/payments.py` — refactor completo (236 líneas totales, +212 netas vs stub)
- `app/config.py` — agrega `play_package_name`

**Syntax check (2026-07-02):**
```bash
python3 -c "
import ast
for f in ['app/services/play_api.py', 'app/routers/payments.py', 'app/config.py']:
    ast.parse(open(f).read())
    print(f'SYNTAX OK: {f}')
"
# SYNTAX OK: app/services/play_api.py
# SYNTAX OK: app/routers/payments.py
# SYNTAX OK: app/config.py
```

### ST-02 — Tests error-path contra Cloud Run prod ✅ Done (2026-07-09)

Tests ejecutados via `gcloud run services proxy motamaze-backend --port=8082 --region=us-central1 --project=motamaze`
+ JWT generado localmente con la clave RS256 de Secret Manager.

**Test 1 — product_id desconocido → HTTP 400 PAY_PRODUCT_NOT_FOUND**

```json
POST /payments/android/verify
{"purchase_token": "tok", "product_id": "fake_sku", "session_id": "st02-test1"}
```

Resultado real:
```json
HTTP 400
{"detail": {"error_code": "PAY_PRODUCT_NOT_FOUND"}}
```
PASS

**Test 2 — purchaseToken con formato invalido → HTTP 402 PAY_VERIFICATION_FAILED**

```json
POST /payments/android/verify
{"purchase_token": "invalid_token_format", "product_id": "lives_pack_5", "session_id": "st02-test2"}
```

Resultado real:
```json
HTTP 402
{"detail": {"error_code": "PAY_VERIFICATION_FAILED"}}
```
PASS

### ST-03 — Test grant real (purchaseToken del Play Billing SDK) ✅ Movida a T-607 (2026-07-13)

**Decisión (2026-07-13 — Juan Mosqueda):** ST-03 trasladada a **T-607** (revisión E2E end-to-end). Juan generó T-607 específicamente para la validación de flujo completo de compra. T-251/PAY-001 queda cerrado — la implementación del backend está completa y verificada con error-path tests (ST-02).

---

## Follow-ups / Notes

- **iOS verify:** Stub intacto — App Store Server API + JWS verification se implementa en PAY-001 fase 2 (post soft-launch Android).
- **Acknowledge failure recovery:** Si el acknowledge/consume falla (network transient), el entitlement ya fue otorgado en Firestore. PAY-002 (reconciliation job) detecta purchases PURCHASED pero no acknowledged y reintenta.
- **Token cache thread safety:** `_credentials` es global en `play_api.py`. Cloud Run usa multi-proceso (no multi-thread) por default — no hay contención. Si se cambia a multi-thread workers, agregar `threading.Lock`.
- **`play_package_name` en .env:** No es necesario override para dev/prod — el package name es el mismo en ambos entornos.

---

## Fix T-405 — purchaseToken hashing (2026-07-13)

**Gap detectado por Juan Mosqueda (2026-07-13):** La implementación original usaba el raw `purchaseToken` directamente como document ID en Firestore (`purchases/{purchase_token}`) y como valor en BigQuery `purchase_events.purchase_token`. La arquitectura spec requiere SHA-256 hash del token como identificador.

**Riesgos del raw token:**
1. **Correctness:** Firestore document IDs tienen límite de 1500 bytes. Un purchaseToken largo podría excederlo y fallar el write.
2. **Seguridad:** El raw token es una credencial live — si se filtra en un crash log o reporte de error, podría ser replayed contra Play Developer API.

**Fix aplicado (commit pendiente):** `app/routers/payments.py`

```python
token_hash = hashlib.sha256(body.purchase_token.encode()).hexdigest()
```

Cambios:
- Firestore: `purchases/{token_hash}` (doc ID) + campo `"purchase_token": body.purchase_token` almacenado dentro del doc para que PAY-002 reconciliation job pueda obtener el token original al re-llamar Play API.
- BQ `purchase_events.purchase_token`: ahora almacena el hash (no el token raw).
- BQ `row_id`: `f"purchase_android_{token_hash}"` — deduplicación sigue siendo determinista.

**PAY-002:** El reconciliation job usa `doc.id` (que era el raw token) para llamar Play API. Con este fix, el token está en `doc["purchase_token"]` — PAY-002 debe actualizarse para leer ese campo en lugar del doc ID.
