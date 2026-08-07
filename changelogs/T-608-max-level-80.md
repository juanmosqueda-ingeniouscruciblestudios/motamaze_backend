# T-608 — Fix: límite de nivel hardcodeado en 30, MVP va a 80

| Field | Value |
|---|---|
| **Type** | Bug fix |
| **Priority** | Medium — no bloquea hoy (el cliente tampoco manda niveles > 30 todavía), pero bloqueará en cuanto haya contenido real de niveles 31-80 |
| **Status** | ✅ Done |
| **Date** | 2026-08-07 |
| **Workstream** | Game Services Backend |
| **Owner** | Saul Zavala Morin |
| **Monday.com Item ID** | 12743424690 |
| **Depends on** | Ninguno |

---

## Descripción

Encontrado por Juan (2026-08-05) mientras validaba la telemetría de T-232, verificado contra el
código 2026-08-06/07. El alcance del MVP pasó de 30 a 80 niveles desde 2026-07-07
(`sims/2026-07-13_season_recalibration/season_spread_new_modes.xlsx`, título "80 Level
Configurations"), pero el backend nunca se actualizó: seguía validando `1 <= level_id <= 30` de
forma hardcodeada en 5 lugares independientes de 2 archivos.

**Acceptance criteria:**
- [x] Localizar todos los puntos con el límite hardcodeado (ST-01)
- [x] Elevar el límite de 30 a 80 en `game.py` y `social.py` (ST-02)
- [x] Tests de boundary para niveles 31-80 (ST-03)
- [x] Actualizar REST-001 y docs (ST-04)

---

## Estado previo (antes de este fix)

Cinco ocurrencias de `30` hardcodeado, todas en `app/routers/`:

| Archivo:línea | Qué hacía |
|---|---|
| `game.py:339` | `POST /lives/spend` — rechaza `level_id` fuera de 1-30 |
| `game.py:589` | `GET /progress` — `highest_unlocked_level` clamped a 30 |
| `game.py:609` | `POST /progress/level-complete` — rechaza `level_id` fuera de 1-30 |
| `game.py:778-779` | `POST /progress/level-complete` — `next_level_unlocked`/`highest_unlocked_level` clamped a 30 |
| `social.py:80` | `POST /share/create` — rechaza `level_reached` fuera de 1-30 |

Impacto: cualquier llamada real para los niveles 31-80 devolvía `400` en los tres endpoints con
validación, y ningún jugador podía desbloquear más allá del nivel 30 aunque hubiera contenido.

---

## Implementación

Centralizada en una sola constante — `MAX_LEVEL = 80` en `app/routers/game.py`, junto a los demás
fallback defaults del archivo (`REGEN_INTERVAL_SECS`, `DEFAULT_MAX_LIVES`) — importada por
`social.py`. Elimina el riesgo de que el valor vuelva a divergir entre archivos como pasó aquí.

```python
# T-608: MVP scope moved to 80 levels (2026-07-07, sims/2026-07-13_season_
# recalibration/season_spread_new_modes.xlsx). Was hardcoded to 30 in five
# places across game.py/social.py; centralized here so it can't drift again.
MAX_LEVEL = 80
```

Los 5 puntos reemplazados por `MAX_LEVEL`, incluyendo los mensajes de error (`f"level_id must be
between 1 and {MAX_LEVEL}"}`) para que no queden con "30" hardcodeado en el texto aunque la
validación ya use la constante.

No hubo import circular: `game.py` no importa `social.py`, así que `from app.routers.game import
MAX_LEVEL` en `social.py` es seguro.

---

## Testing

```bash
python -m pytest -q
```

- `tests/test_game_lives_router.py::test_lives_spend_rejects_out_of_range_level_id` — actualizado,
  el valor "fuera de rango" de prueba pasó de `31` (ahora válido) a `81`.
- `tests/test_social_router.py::test_share_create_invalid_level_reached` — mismo ajuste, `31` → `81`
  en el set de valores inválidos `(0, 81, -1)`.
- `tests/test_level_complete_match_stats_router.py` (nuevos):
  - `test_level_complete_rejects_out_of_range_level_id` — cubre `PROGRESS_INVALID_LEVEL`, sin
    cobertura previa (gap preexistente documentado en el docstring del módulo).
  - `test_level_complete_accepts_level_80` — prueba end-to-end de que el nivel 80 se acepta y
    `highest_unlocked_level` responde `80`. Requiere sembrar `progress` con `best_level=79` — de lo
    contrario `PROGRESS_LEVEL_LOCKED` (game.py:638, "completa niveles anteriores primero") dispara
    primero para cualquier usuario nuevo, sin relación con el límite superior que este ticket corrige.

---

## Results

```
349 passed, 8 skipped
```

Full suite, sin regresiones.

---

## Follow-ups / notes

- **`match_stats` sigue sin llegar del cliente** — hallazgo aparte de Juan en la misma revisión
  (T-232/T-448): el motor de achievements no tiene nada que lo alimente todavía. No es parte de
  este fix.
- **`lives_spend()` del cliente no manda `level_id`** — otro hallazgo aparte (T-222). El campo es
  opcional en el backend, así que no rompe nada, pero el denominador de win-rate de `level_stats`
  queda inutilizable hasta que se agregue del lado del cliente.
