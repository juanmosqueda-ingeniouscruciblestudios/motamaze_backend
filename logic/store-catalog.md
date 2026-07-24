# Store Catalog & Promotions (T-240) — Estado actual

> Última actualización: 2026-07-24

`GET /store/catalog` resuelve el catálogo server-side (architecture doc §9A.4): precios, ownership
y promociones activas segmentadas por audiencia. El cliente Godot nunca hardcodea precios ni calcula
qué promoción aplica — siempre consume este endpoint.

---

## Las 2 colecciones (Firestore)

| Colección | Contenido | Detalle de campos |
|---|---|---|
| `config/catalog` | Doc único: `catalog_version` + `products[]` (precio base, sin promoción) | `docs/DATA_MODEL.md` |
| `promotions/{promo_id}` | Promociones activas/inactivas, una por documento | `docs/DATA_MODEL.md` |

Sembrado inicial vía `scripts/seed_store_catalog.py` — idempotente, reutilizable, **no** un script
de datos de prueba (a diferencia de `seed_bq_test_data.py`, esto es configuración real de
producción). Solo siembra productos con precio confirmado (`lives_pack_5`, `no_ads`) — ver el propio
script para la lista de lo excluido y por qué.

---

## Segmentación de audiencia (`store_service.resolve_user_segment`)

Server-side, nunca confía en un segmento declarado por el cliente. 4 segmentos posibles:

```python
NEW_USER_WINDOW_DAYS = 3    # cuenta creada hace <= N días
LAPSED_WINDOW_DAYS = 14     # sin sesión hace >= N días
```

| Segmento | Condición |
|---|---|
| `non_payer` | Sin ninguna compra (`entitlements/{uid}` vacío o sin `no_ads`/`skins`/`life_packs_total`) |
| `lapsed` | Última sesión (`sessions`, la más reciente por `started_at`) hace ≥14 días. `last_session_at=None` (sin sesión registrada) **no** cuenta como lapsed — ausencia de dato no es evidencia de abandono |
| `new` | Cuenta creada (`users.created_at`) hace ≤3 días |
| `all` | Fallback si no aplica ninguno de los anteriores |

**Prioridad si un usuario califica para varios a la vez:** `non_payer > lapsed > new > all` — el más
específico gana, chequeado en ese orden exacto.

> **Umbrales iniciales, no definitivos** (decisión 2026-07-23) — ajustables después vía T-244
> (Remote Config) sin tocar código.

---

## Resolución del catálogo (`store_service.resolve_catalog_products`)

Por cada producto de `config/catalog.products`:

1. **`owned`** — solo aplica a `non_consumable` (`store_service.owned_product_ids`). Un consumible
   nunca está "owned" (REST-001 siempre muestra `owned: false` para `lives_pack_5`). Mapeo:
   `no_ads` → `entitlements.no_ads`; `skin_*` → está en `entitlements.skins`.
2. **Promoción activa** — candidatas: `active == true` AND `starts_at <= now <= ends_at` (rango
   inclusivo, servidor decide `now`, nunca el cliente) AND `audience` coincide con el segmento del
   usuario o es `"all"`.
3. **Desempate** si más de una promoción activa aplica al mismo producto: audiencia más específica
   gana primero (mismo sesgo que la segmentación — un match no-`"all"` le gana a uno `"all"`); si
   siguen empatadas en especificidad, gana el mayor `discount_percent` (determinístico).
4. Si hay promoción elegida: `price_usd` efectivo = `original_price_usd * (1 - discount_percent/100)`,
   redondeado a 2 decimales. `promotion` en la respuesta trae `discount_percent`,
   `original_price_usd` y `expires_at` (= `ends_at` de la promo elegida).
5. Una promoción que referencia un `product_id` que no existe en `config/catalog` se ignora en
   silencio — no rompe la resolución del resto del catálogo.

---

## `price_tier` (architecture doc) vs. `price_usd` (implementado)

El architecture doc original (§9A.4) especifica `products[].price_tier` — una referencia a un tier
de precio de tienda, no un monto directo, con la idea de que el backend nunca fija precios, solo
selecciona qué tier de la tienda mostrar. Se implementó con `price_usd` plano en su lugar porque
**REST-001 es el contrato ya firmado por Juan** (commit `9216611`) y su ejemplo de respuesta ya usa
`price_usd`/`currency` directamente — se siguió el contrato aprobado, no la especificación de
arquitectura más temprana que quedó superada por él.

---

## Limitaciones conocidas / a revisar

- **`skin_gold`, `skin_silver`, life pack grande sin sembrar** — precio `TBD` en el architecture doc,
  pendiente de que Juan confirme precios reales antes de agregarlos a `config/catalog`.
- **Sin promociones activas todavía** — `promotions` existe vacía; el primer promo real que se cree
  será la primera prueba end-to-end de la lógica de desempate contra datos reales.
- **Umbrales de segmentación sin validar contra tráfico real** — ver sección de arriba.
- **`config/promotions/{promo_id}` del architecture doc se implementó como colección plana
  `promotions`**, no anidada — ver nota en `docs/DATA_MODEL.md`.
