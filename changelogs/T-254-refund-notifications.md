# T-254 — Refund Notifications (Play Pub/Sub + Apple ASSN v2)

| Field | Value |
|---|---|
| **Type** | Feature — Payments Backend |
| **Priority** | Red — overdue (2026-07-04) |
| **Status** | ✅ Done (2026-07-14) — ST-01 ✅ código completo; ST-02 ✅ GCP infra completa (topic + IAM + push subscription); ST-03 → movida a T-607 (Play Console RTDN config, bloqueada hasta publicación) |
| **Date** | 2026-07-14 |
| **Workstream** | Payments |
| **Owner** | Saul Zavala Morin |
| **Monday Item ID** | 12272254780 |
| **Depends-on** | PAY-001 ✅, PAY-002 ✅ (`revoke_entitlement` en reconcile_service) |
| **Desbloquea** | T-607 (E2E payment flows) |

---

## Descripción

Implementa el endpoint webhook `POST /payments/android/refund-notification` que recibe notificaciones RTDN (Real-Time Developer Notification) de Google Play vía Cloud Pub/Sub, revoca el entitlement del usuario y loguea el evento en BigQuery.

`POST /payments/ios/refund-notification` queda como stub (Apple ASSN v2 — iOS fuera de MVP scope).

**Monday subitems cubiertos:**
1. "Build the Pub/Sub endpoint for Play RTDN refund/voided-purchase notifications" ✅
2. "Revoke the entitlement" ✅ (reutiliza `revoke_entitlement` de `reconcile_service.py`)
3. "Ensure idempotency" ✅ (guard `voided: true` en Firestore)

---

## Estado previo

Los endpoints existían como comentarios stub al final de `app/routers/payments.py`:
```python
# POST /payments/android/refund-notification  — PAY-003
# POST /payments/ios/refund-notification      — PAY-003
```

`_revoke_entitlement` existía en `reconcile_service.py` como función privada (underscore).

---

## Implementación

### `app/config.py`

```python
pubsub_rtdn_sa_email: str = "game-api-backend@motamaze.iam.gserviceaccount.com"
```

Service account cuyo email debe aparecer en el OIDC token del push de Pub/Sub. Configurable vía env var `PUBSUB_RTDN_SA_EMAIL`.

---

### `app/services/reconcile_service.py`

Renombrado `_revoke_entitlement` → `revoke_entitlement` (función pública). La lógica es idéntica; solo se elimina el underscore para que `payments.py` pueda importarla sin violar la convención de privacidad. La llamada interna en `detect_refunds` actualizada.

---

### `app/routers/payments.py`

#### Imports añadidos

```python
import asyncio, base64, json, logging, urllib.parse, urllib.request
from fastapi import Request
from fastapi.responses import Response
from app.services import reconcile_service

logger = logging.getLogger(__name__)
```

#### `_verify_pubsub_oidc(token, expected_email) → bool`

Verifica el OIDC bearer token del push de Pub/Sub contra el endpoint `https://oauth2.googleapis.com/tokeninfo`. Google valida la firma y la expiración del token y retorna los claims. Chequeamos que `email == expected_email` y `email_verified == true`. Implementado con `asyncio.to_thread` + `urllib.request` (no nueva dependencia).

```python
async def _verify_pubsub_oidc(token: str, expected_email: str) -> bool:
    url = "https://oauth2.googleapis.com/tokeninfo?id_token=" + urllib.parse.quote(token, safe="")
    def _fetch() -> bool:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                info = json.loads(r.read())
            return (
                info.get("email") == expected_email
                and info.get("email_verified") in ("true", True)
            )
        except Exception:
            return False
    return await asyncio.to_thread(_fetch)
```

#### `POST /payments/android/refund-notification`

**Auth:** 401 en fallo de OIDC. Para todos los demás errores (token no encontrado, JSON malformado, fallo de Firestore) se retorna **204** para evitar que Pub/Sub reintente indefinidamente (per REST-001 error table).

**Flujo:**
1. Extraer `Authorization: Bearer <OIDC_TOKEN>` → verificar via tokeninfo
2. Parsear envelope Pub/Sub: `body.message.data` (base64url)
3. Decodificar → `DeveloperNotification` JSON
4. Extraer `voidedPurchaseNotification.purchaseToken` (ignorar otros tipos de notificación)
5. `SHA-256(purchaseToken)` → lookup `purchases/{token_hash}` en Firestore
6. Guard de idempotencia: `if data.get("voided"): return 204`
7. Llamar `reconcile_service.revoke_entitlement(db, uid, entitlement_type, product_id, now)`
8. Escribir `{voided: True, voided_at: now}` en el doc de Firestore
9. BQ background: `purchase_events` con `verification_status="refunded"`, `grant_status="revoked"`
10. Retornar `204`

**Manejo de errores per REST-001 spec:**

| Situación | Acción |
|---|---|
| `purchase_token` no encontrado en Firestore | `logger.warning` + retornar 204 |
| Error al revocar entitlement | `logger.error` + continuar (marcar voided de todos modos) |
| JSON malformado en `message.data` | `logger.warning` + retornar 204 |
| `voidedPurchaseNotification` ausente | retornar 204 (puede ser testNotification u otro tipo) |

#### `POST /payments/ios/refund-notification`

Stub que retorna 204. Acepta el request de Apple pero no procesa nada hasta que iOS esté en scope.

---

## GCP Setup (ST-02) ✅ Done (2026-07-14)

Infraestructura Pub/Sub completa. Pasos 1 y 3-4 ejecutados por Saul; paso 2 ejecutado por Juan (requirió override temporal de org policy `iam.allowedPolicyMemberDomains`).

### Paso 1 — Crear el topic RTDN

```powershell
gcloud pubsub topics create play-rtdn --project=motamaze
```

### Paso 2 — Dar permiso de Publisher al SA de Play Console

Google Play usa este SA para publicar en nuestro topic.

```powershell
gcloud pubsub topics add-iam-policy-binding play-rtdn `
  --member="serviceAccount:google-play-developer-notifications@system.gserviceaccount.com" `
  --role="roles/pubsub.publisher" `
  --project=motamaze
```

### Paso 3 — Dar permiso a Pub/Sub para emitir tokens OIDC como game-api-backend

Pub/Sub necesita `roles/iam.serviceAccountTokenCreator` sobre `game-api-backend` para poder adjuntar un OIDC token al push request.

```powershell
gcloud iam service-accounts add-iam-policy-binding `
  "game-api-backend@motamaze.iam.gserviceaccount.com" `
  --member="serviceAccount:service-542009654415@gcp-sa-pubsub.iam.gserviceaccount.com" `
  --role="roles/iam.serviceAccountTokenCreator" `
  --project=motamaze
```

### Paso 4 — Crear la push subscription

```powershell
gcloud pubsub subscriptions create play-rtdn-push `
  --topic=play-rtdn `
  --push-endpoint="https://motamaze-backend-ghubi2atbq-uc.a.run.app/payments/android/refund-notification" `
  --push-auth-service-account="game-api-backend@motamaze.iam.gserviceaccount.com" `
  --ack-deadline=60 `
  --message-retention-duration=7d `
  --project=motamaze
```

> `--ack-deadline=60`: Pub/Sub reintenta si no recibe 200-299 dentro de 60 segundos.
> `--message-retention-duration=7d`: mensajes no-acked se retienen 7 días para debugging.

---

## Play Console Setup (ST-03) — bloqueado hasta publicación en Play Console

Una vez que la app esté publicada en Play Console:

1. Play Console → tu app → **Monetize** → **Monetization setup** → **Real-time developer notifications**
2. En "Topic name" ingresar: `projects/motamaze/topics/play-rtdn`
3. Guardar → Play Console valida que puede publicar en el topic (usa el paso 2 de GCP Setup)
4. Hacer clic en **Send test notification** para verificar que el backend recibe y retorna 204

---

## Testing

### ST-01 — Syntax check (2026-07-14)

```bash
python -c "
import ast
for f in ['app/config.py', 'app/services/reconcile_service.py', 'app/routers/payments.py']:
    ast.parse(open(f).read())
    print(f'SYNTAX OK: {f}')
"
# SYNTAX OK: app/config.py
# SYNTAX OK: app/services/reconcile_service.py
# SYNTAX OK: app/routers/payments.py
```

### ST-02 — Smoke test local (post GCP Setup)

```bash
# Simular push de Pub/Sub con token de prueba
# (requiere un token OIDC válido de game-api-backend — usar gcloud para obtenerlo)
TOKEN=$(gcloud auth print-identity-token --audiences=https://motamaze-backend-ghubi2atbq-uc.a.run.app)

curl -X POST https://motamaze-backend-ghubi2atbq-uc.a.run.app/payments/android/refund-notification \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "data": "eyJ2ZXJzaW9uIjoiMS4wIiwicGFja2FnZU5hbWUiOiJjb20uaW5nZW5pb3VzY3J1Y2libGVzdHVkaW9zLm1vdGFtYXplIiwidm9pZGVkUHVyY2hhc2VOb3RpZmljYXRpb24iOnsicHVyY2hhc2VUb2tlbiI6InRlc3QtdG9rZW4tMTIzIiwicHJvZHVjdFR5cGUiOjF9fQ==",
      "messageId": "1234567890"
    },
    "subscription": "projects/motamaze/subscriptions/play-rtdn-push"
  }'
# Esperado: HTTP 204 (o 404 si test-token-123 no existe en Firestore — ambos son correctos)
```

> El `message.data` decodifica a:
> `{"version":"1.0","packageName":"com.ingeniouscruciblestudios.motamaze","voidedPurchaseNotification":{"purchaseToken":"test-token-123","productType":1}}`

### ST-03 — E2E con Play Console (pendiente T-607)

1. Completar ST-02 (GCP setup)
2. Play Console → Real-time developer notifications → Send test notification
3. Verificar en Cloud Logging: `T-254 RTDN:` entries
4. Si hay una compra real revocada: verificar que `purchases/{hash}.voided == true` y que el entitlement fue removido

---

## Follow-ups / Notes

- **iOS (Apple ASSN v2):** El stub retorna 204. La implementación real requiere verificar la cadena de certificados Apple (JWS) y parsear el `signedPayload`. Diferido a PAY-003 fase 2 cuando iOS entre en scope.
- **`subscriptionNotification` (cancelaciones de suscripción):** El endpoint actualmente solo maneja `voidedPurchaseNotification`. Si MotaMaze agrega suscripciones en el futuro, añadir handling de `subscriptionNotification.notificationType == SUBSCRIPTION_REVOKED`.
- **Alertas en Cloud Monitoring:** Considerar agregar una alerta en T-115 si el endpoint retorna 401 repetidamente (indicaría problemas de auth con el push subscription).
- **PUBSUB_RTD_SA_EMAIL en Secret Manager:** El valor default en config es `game-api-backend@motamaze.iam.gserviceaccount.com`. Si en el futuro se crea un SA dedicado para Pub/Sub push, actualizar la env var en Cloud Run.
