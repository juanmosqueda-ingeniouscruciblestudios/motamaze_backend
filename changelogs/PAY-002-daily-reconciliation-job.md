# PAY-002 — Daily Reconciliation Job (Cloud Scheduler)

| Field | Value |
|---|---|
| **Type** | Background Job / Reliability |
| **Priority** | High — garantiza integridad de pagos y detección de refunds |
| **Status** | In Progress — ST-01 ✅ implementación completa (2026-07-09); ST-02 ✅ Cloud Scheduler job live (2026-07-09); ST-03 ⬜ test end-to-end pendiente T-252 |
| **Date** | 2026-07-09 |
| **Workstream** | Payments Backend |
| **Depends-on** | PAY-001 ✅ (purchases Firestore collection), EXT-001 ✅ (Play Developer API) |
| **Desbloquea** | T-254 (Refund notifications — complementario, no bloqueado) |

---

## Descripción

Job diario que corre dos tareas en secuencia:

1. **Pending ack reconciliation**: Busca en `purchases/{token}` los tokens con `acknowledged == false` y `created_at < hace 23h`, reintenta el acknowledge/consume en Play API y actualiza Firestore.
2. **Refund detection**: Llama a `voidedpurchases.list` en Play API con ventana de 24h, revoca entitlements en Firestore para los tokens voided.

**Por qué 23h y no 24h para el pending ack:** El job corre a las 6:00 UTC. Un token creado a las 7:00 del día anterior tendría 23h. Ventana conservadora para no actuar sobre tokens aún en tránsito de red.

---

## Cambios por archivo

### `app/services/play_api.py` — nuevo: `list_voided_purchases()`

```python
async def list_voided_purchases(pkg: str, start: datetime, end: datetime) -> list[dict]:
    """Returns voided purchases between start and end (UTC datetimes)."""
    # GET /purchases/voidedpurchases?startTime=<ms>&endTime=<ms>&maxResults=1000
```

Mismo SA + scope `androidpublisher` que el resto de Play API. Sin nueva dependencia.

### `app/routers/payments.py` — PAY-001 patch: `purchases/{token}` write

Dos cambios en `android_verify()`:

**Rama `already_done`** (Play API ya confirma consumed/acknowledged):
```python
await db.collection("purchases").document(body.purchase_token).set({
    "uid": user_id, "product_id": ..., "product_type": ..., "order_id": ...,
    "acknowledged": True, "acknowledged_at": now, "created_at": now,
}, merge=True)
```

**Rama grant normal** — antes del ack/consume:
```python
await db.collection("purchases").document(body.purchase_token).set({
    "uid": user_id, "product_id": ..., "product_type": ..., "order_id": ...,
    "acknowledged": False, "created_at": now,
}, merge=True)
```

Después del ack/consume exitoso (dentro del try):
```python
await db.collection("purchases").document(body.purchase_token).set(
    {"acknowledged": True, "acknowledged_at": now}, merge=True
)
```

Si el ack falla, el documento queda con `acknowledged: False` → T-253 lo encuentra.

### `app/services/reconcile_service.py` — nuevo

| Función | Descripción |
|---|---|
| `reconcile_pending_acks(pkg, db, settings)` | Query Firestore `acknowledged==False AND created_at < cutoff`, reintenta ack/consume, actualiza `acknowledged_at` |
| `detect_refunds(pkg, db, settings)` | `voidedpurchases.list` últimas 24h, revoca entitlements, marca `voided: True` |
| `_revoke_entitlement(db, uid, type, product_id, now)` | Revoca según tipo: `no_ads→False`, `skin→ArrayRemove`, `season_pass→False`. `life_pack` no se revoca (ya consumido) |
| `_infer_entitlement(product_id)` | Mismo mapeo que `payments.py` — duplicado intencionalmente (no premature abstraction) |

### `app/routers/jobs.py` — nuevo endpoint

```python
@router.post("/reconcile-purchases")
async def run_reconcile_purchases(
    x_cloudscheduler_jobname: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
    db: AsyncClient = Depends(get_firestore_client),
):
    # Misma guarda de header que admob-daily-report
    ack_result  = await reconcile_service.reconcile_pending_acks(pkg, db, settings)
    refund_result = await reconcile_service.detect_refunds(pkg, db, settings)
    return {"pending_acks": ack_result, "refunds": refund_result}
```

---

## Esquema Firestore — `purchases/{purchaseToken}`

| Campo | Tipo | Descripción |
|---|---|---|
| `uid` | string | user_id del comprador |
| `product_id` | string | e.g. `lives_pack_5`, `no_ads` |
| `product_type` | string | `consumable` / `non_consumable` |
| `order_id` | string | orderId de Play API |
| `acknowledged` | bool | `false` hasta ack/consume exitoso |
| `acknowledged_at` | timestamp | cuándo se completó el ack (null si pendiente) |
| `created_at` | timestamp | cuándo se procesó en `/payments/android/verify` |
| `voided` | bool | `true` si Play API reporta refund |
| `voided_at` | timestamp | cuándo se detectó el refund |

---

## ST-02 — Cloud Scheduler

```powershell
gcloud scheduler jobs create http reconcile-purchases `
  --schedule="0 6 * * *" `
  --uri="https://motamaze-backend-ghubi2atbq-uc.a.run.app/jobs/reconcile-purchases" `
  --http-method=POST `
  --oidc-service-account-email="game-api-backend@motamaze.iam.gserviceaccount.com" `
  --oidc-token-audience="https://motamaze-backend-ghubi2atbq-uc.a.run.app" `
  --location=us-central1 `
  --project=motamaze
```

**Schedule:** `0 6 * * *` UTC — 6 AM diario (1 AM CST). Elegido para que Play API haya procesado todos los eventos del día anterior antes del run.

**Verificado (2026-07-09):** Job creado en `us-central1`, state=ENABLED, próximo run 2026-07-10T06:00:00Z.

---

## ST-03 — Test end-to-end ⬜ Pending

Requiere `purchaseToken` real (mismo blocker que PAY-001 ST-03 → T-252).

Test a ejecutar:
1. Compra con Play Billing SDK → token en `purchases/{token}` con `acknowledged: false`
2. Forzar fallo del ack (mock o corte de red) → verificar que el doc queda `acknowledged: false`
3. Force-run del job → verificar que el doc se actualiza a `acknowledged: true`
4. Simular refund en Play Console → force-run → verificar entitlement revocado en Firestore

---

## Testing — ST-01 syntax check (2026-07-09)

```bash
python -c "
import ast
for f in ['app/routers/payments.py','app/services/play_api.py',
          'app/services/reconcile_service.py','app/routers/jobs.py']:
    ast.parse(open(f).read())
    print(f'SYNTAX OK: {f}')
"
# SYNTAX OK: app/routers/payments.py
# SYNTAX OK: app/services/play_api.py
# SYNTAX OK: app/services/reconcile_service.py
# SYNTAX OK: app/routers/jobs.py
```

---

## Follow-ups / Notes

- **T-254 complementario:** T-254 (Play Pub/Sub RTDN) cubre refunds en tiempo real. T-253 es el catch-all diario para casos que T-254 no capturó. Ambos pueden coexistir — T-253 verifica `voided: true` antes de revocar dos veces.
- **life_pack revocation:** Los packs de vidas son consumables — ya se consumieron en el juego. Un refund de life_pack no se puede "deshacer" en Firestore de forma significativa. Se registra el `voided: true` para auditoría, pero no se modifican `lives/{uid}`.
- **Firestore security rules:** `purchases/{token}` solo se escribe desde el backend (Admin SDK). Las reglas de INFRA-005 ya deniegan acceso de clientes a esta colección por deny-by-default.
