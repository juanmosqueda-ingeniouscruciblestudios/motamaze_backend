# T-243 — Backend `/profile/equip-skin` (entitlement-checked) + persistencia de `equipped_skin`

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | Medium — desbloquea T-242 (UI de skins, cliente) |
| **Status** | ✅ Done — ST-01–05 ✅ (2026-07-28) |
| **Date** | 2026-07-28 |
| **Workstream** | Game Services Backend |
| **Depends-on** | T-240 ✅ (`config/catalog` + `store_service`), PAY-001/PAY-004 ✅ (`entitlements/{uid}`) |
| **Blocks** | T-242 (cliente: equipar skin + aplicar al arrancar) |

---

## Description

Implementa `POST /profile/equip-skin` (REST-001 endpoint #13, `Game-005`), que hasta ahora solo
existía como comentario placeholder en `game.py`.

Lo que empezó como un endpoint de tres validaciones terminó cambiando el modelo de datos de
`entitlements/{uid}.skins`, porque una pregunta durante la revisión reveló que el diseño original
asumía algo falso: que las skins solo se compran.

### Acceptance criteria

- [x] Valida que el `skin_id` sea una skin conocida → `400 SKIN_NOT_FOUND`
- [x] Valida posesión → `403 SKIN_NOT_OWNED`
- [x] Persiste `users/{uid}.equipped_skin`
- [x] `skin_default` permite volver al aspecto por defecto sin poseer nada
- [x] Un reembolso no deja al jugador luciendo una skin que ya no posee
- [x] Un reembolso no despoja de una skin ganada
- [x] Compatible con documentos escritos antes del cambio de forma

---

## Previous state (before this change)

`app/routers/game.py` terminaba en dos líneas de comentario:

```python
# GET  /profile                 — GAME-004
# POST /profile/equip-skin      — GAME-004 (T-243)
```

Ambas estaban mal. `GET /profile` **no existe** en el contrato — los 8 endpoints de Game Services de
REST-001 son progress (×2), lives (×3), `store/catalog`, `equip-skin` y `events/behavior`. Y
`equip-skin` es `GAME-005`; `GAME-004` es `GET /store/catalog`, entregado en T-240.

`entitlements/{uid}.skins` era una lista plana de ids, escrita por `_grant_entitlement`:

```python
{"skins": ArrayUnion([product_id]), "updated_at": now}
```

`users/{uid}.equipped_skin` ya existía en el esquema e `auth_service` lo inicializaba en `None`,
pero **ningún endpoint lo escribía**.

---

## Implementation

### ST-01 — el endpoint (`app/routers/game.py`, commit `0daada0`)

Tres validaciones en orden, más `store_service.catalog_skin_ids()` como función nueva junto a
`owned_product_ids()`, para que la regla de "qué cuenta como skin" viviera en un solo lugar en vez
de re-derivarse en cada punto de llamada. Sigue la convención de
`reconcile_service._infer_entitlement`: una skin es un `non_consumable` cuyo `product_id` empieza
con `skin_`.

Efecto colateral deliberado: eso también rechaza `no_ads`, un no-consumible poseíble que no es skin.

**`skin_default` ≡ `null`** (decisión de Saul, 2026-07-28). El endpoint acepta ese nombre y persiste
`null`; salta ambas validaciones porque no es un producto del catálogo y condicionarlo a la posesión
dejaría a un jugador sin poder volver al aspecto original.

**`update()` y no `set(merge=True)`.** Un JWT válido implica que el perfil existe, así que `merge`
solo serviría para tapar una anomalía recreando un documento con únicamente `equipped_skin`. Ese
caso es alcanzable: el job de purga de T-123 borra `users/{uid}` mientras un access token puede
seguir vigente dentro de su TTL de 15 minutos.

### ST-03 — origen de adquisición (commit `a2e30b6`)

**El hallazgo que forzó el cambio.** Saul preguntó si el diseño contemplaba skins gratuitas,
razonando que un jugador que no tiene su aspecto original necesariamente cambió de skin, y si lo
hizo sin comprar nada, la obtuvo gratis. La documentación lo confirma en tres lugares:

- Season Pass, track Free: cosméticos por tier — bufanda, goggles, corona, bandana, capa, sombrero,
  botas (`project_spec.md`).
- Season Pass, Tier 10 Gold: "Garden Rush Mota", skin legendaria.
- Leaderboard top-3: *"1st = legendary skin + Gold Pass"*.

Ninguna es producto de tienda. Eso rompía dos cosas de la ST-01:

1. La validación de existencia contra el catálogo habría rechazado una skin **legítimamente ganada**
   con `400 SKIN_NOT_FOUND`.
2. `revoke_entitlement` eliminaba la skin por `product_id` sin importar su origen, así que reembolsar
   una compra podía despojar al jugador de una skin que **además** se había ganado.

`entitlements.skins` pasa de `list[str]` a mapa indexado por `skin_id`:

```json
"skins": {
  "skin_gold":        { "source": "purchase", "acquired_at": "..." },
  "skin_garden_rush": { "source": "earned",   "acquired_at": "..." }
}
```

**Mapa y no lista de objetos:** `ArrayUnion` compara objetos completos, así que volver a otorgar la
misma skin con distinto `acquired_at` habría agregado un duplicado. El mapa es idempotente por
construcción.

**Sin migración.** `store_service.normalize_skins()` lee la forma antigua como compras — en ese
momento comprar era la única vía que otorgaba una skin, así que la inferencia es exacta.

**En la revocación se usa `update()` y no `set()`:** merge solo puede agregar o sobrescribir claves,
nunca eliminar una, y `merge=False` se habría llevado el resto del documento (`no_ads`,
`life_packs_total`).

### ST-02 — limpieza del equipado en reembolso (absorbida en ST-03)

Al revocar una skin comprada, si era la equipada también se limpia `users/{uid}.equipped_skin`. El
cliente aplica el skin equipado al arrancar, así que sin esto el jugador seguiría luciendo una skin
reembolsada. Se absorbió porque comparte el mismo bloque de código: separarlas obligaba a tocar dos
veces la misma función.

### Bug encontrado en el doble de pruebas

`FakeDocRef.set(merge=True)` en `conftest.py` hacía un `update()` superficial de diccionario,
mientras Firestore real hace merge profundo en mapas anidados. Con el modelo nuevo, otorgar una skin
**aparentaría borrar todas las demás** del jugador. Corregido con `_deep_merge`.

---

## Testing

```bash
python -m pytest tests/test_equip_skin_router.py tests/test_skin_revocation.py -q
python -m pytest tests/test_store_service.py tests/test_payments_router.py -q
python -m pytest -q
```

**ST-04 partió de una observación incómoda:** la suite pasó completa durante el cambio de forma de la
ST-03, lo que resultó ser evidencia débil y no buena señal. Dos huecos:

`test_payments_router` afirmaba `"skin_gold" in entitlements["skins"]`. Eso es verdadero para una
lista **y** para un mapa, porque `in` verifica claves — pasaba sin importar qué contuviera el valor.
Ahora afirma `source == "purchase"` y `acquired_at` no nulo, que es lo que lee la ruta de reembolso.

`test_store_service` solo ejercitaba `owned_product_ids` contra la lista legacy.

Cobertura final: 10 tests del endpoint, 4 de revocación, 9 unitarios de `store_service`.

---

## Results

```
$ python -m pytest -q
222 passed, 8 skipped in 25.05s
```

Casos que fijan las decisiones no obvias:

- `test_skin_default_persists_null_without_ownership` — usuario **sin ninguna compra** equipando
  `skin_default`.
- `test_equip_earned_skin_absent_from_catalog` — skin de Season Pass / leaderboard, ausente de todo
  catálogo.
- `test_refund_leaves_earned_skin_alone` — un reembolso no toca lo ganado.
- `test_refund_of_one_skin_does_not_unequip_another` — el caso que rompe la corrección ingenua de
  "limpiar siempre".
- `test_legacy_list_shape_still_equips` / `test_refund_of_legacy_list_shape_still_revokes` —
  compatibilidad hacia atrás.

---

## Follow-ups / notes

**Bloqueo para la prueba end-to-end del cliente:** `scripts/seed_store_catalog.py` siembra únicamente
`lives_pack_5` y `no_ads`. `skin_gold` y `skin_silver` están excluidos a propósito porque su precio
sigue en TBD en la tabla de la arquitectura, y el script advierte que inventar uno mostraría un cargo
incorrecto a jugadores reales. **Hasta que Juan confirme precios, el único `skin_id` aceptado en dev
y prod es `skin_default`.** No bloquea el backend; sí bloquea T-242.

**Quien implemente Season Pass o los premios de leaderboard debe escribir en el mapa nuevo**, con
`source: "earned"` o `"free"` según corresponda. Escribir la forma antigua de lista haría que esas
skins se leyeran como compras y quedaran expuestas a revocación por reembolso.

**`GET /profile` no existe** y no está en el contrato. El comentario que lo anunciaba se eliminó; si
alguien lo necesita, es un endpoint nuevo que hay que agregar a REST-001 primero.

**No se creó `logic/equip-skin.md`.** El endpoint es pequeño y su lógica de posesión vive en
`store_service`, ya documentado en `logic/store-catalog.md`; el modelo de datos y la regla de
revocación quedaron en `docs/DATA_MODEL.md`, que es donde alguien los buscaría.
