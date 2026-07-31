# Achievements & Season Points (T-447) — Estado actual

> Última actualización: 2026-07-31

40 achievements (`motamaze-project/docs/project_spec.md` §Achievements), evaluados server-side en
cada `POST /progress/level-complete`, expuestos vía `GET /achievements` junto con progreso y rareza
medida. Los puntos de un achievement desbloqueado alimentan `season_points` vía `achievement_bonus`.

---

## Las 5 piezas (Firestore + BigQuery)

| Pieza | Qué contiene | Detalle de campos |
|---|---|---|
| `config/achievements` | Doc único: catálogo estático de los 40 (nombre, descripción, rarity_tier, points, guard_notes) | `docs/DATA_MODEL.md` |
| `level_stats/{level_id}` | Win rate medido por nivel — input de 26/40 guards | `docs/DATA_MODEL.md` |
| `season_match_stats/{uid}` | Agregados de temporada: racha de wins, niveles calificantes, niveles 3★ | `docs/DATA_MODEL.md` |
| `achievement_progress/{uid}` | Estado de desbloqueo por jugador — acumulativo, nunca se resetea | `docs/DATA_MODEL.md` |
| `achievement_rarities/{achievement_id}` | Rareza medida (% de jugadores activos que lo desbloquearon) — poblada cada 24h | `docs/DATA_MODEL.md` |

Sembrado inicial de `config/achievements` vía `scripts/seed_achievements.py` — idempotente, mismo
patrón que `seed_store_catalog.py`. `achievement_id` (slug legible, ej. `"first_blood"`) es la clave
usada en todas partes; `spec_id` (numérico, no contiguo) solo para trazabilidad a project_spec.md.

---

## Contrato de entrada: `match_stats` (`POST /progress/level-complete`)

Bloque opcional anidado (18 campos) — un cliente viejo que lo omite sigue registrando progreso
normalmente, simplemente no se evalúa ningún achievement esa partida. Validado server-side
(`app/routers/game.py::_is_match_stats_valid`); si falla la validación, **no se rechaza la
request** — progress se guarda igual, pero `season_match_stats` y la evaluación de achievements se
saltan por completo para esa partida (misma regla en ambos lugares).

Un campo ausente o inválido nunca se lee como condición satisfecha — un cliente viejo o con datos
corruptos jamás obtiene un achievement gratis.

---

## Win rate por nivel (`level_stats_service`)

26 de los 40 guards gatean por win rate del nivel (`"WR ≤ 80%"`, `"WR ≤ 20%"`, etc.).

```python
WINDOW_DAYS = 30       # ventana móvil
MIN_SAMPLE_SIZE = 100  # intentos mínimos en la ventana para escribir el nivel
```

`wins = COUNTIF(event_name='level_complete')`, `attempts = COUNTIF(event_name='life_spent')` sobre
`player_behavior` (BigQuery), agrupado por `level_id`, ventana de 30 días. Denominador es intentos
**iniciados** (vidas gastadas), no intentos resueltos — abandonar una partida cuenta como no-victoria.
Un nivel bajo `MIN_SAMPLE_SIZE` intentos en la ventana **no se escribe** (ni se sobreescribe con
algo peor) — un documento ausente o viejo hace que los 26 guards WR-gated fallen cerrado, nunca
que se desbloqueen gratis. `source: "measured"` una vez escrito, nunca degrada a `"simulated"`.

Job: `POST /jobs/recalc-level-stats` (Cloud Scheduler, 24h) → `level_stats_service.recalc_level_stats`.

> **WR ausente = guard no evaluable**, política aplicada en todo el sistema (aquí y en
> `achievements_engine`) — nunca se asume satisfecho por falta de dato.

---

## Agregados de temporada (`season_match_stats_service.apply_match`)

Se llama una vez por level-complete con `match_stats` válido, **después** de que el resto del
request ya procesó progress/lives — antes de evaluar achievements.

```python
season_match_stats/{uid}
  win_streak: { count, levels: [{level_id, win_rate_snapshot}, ...] }
  qualifying_levels: { "{level_id}": {mode, win_rate_snapshot, npcs, hits_taken,
                                       badsmell_hits, max_food_deficit, final_gap,
                                       lead_changes, maze_coverage_pct, recorded_at} }
  three_star_levels: { "{level_id}": {win_rate_snapshot, npcs, recorded_at} }
```

- **`win_streak`**: racha de niveles **distintos** ganados consecutivamente, cada entrada con su
  propio `win_rate_snapshot`. Reganar un nivel ya contado en la racha actual es un no-op (no
  extiende, no resetea). Cualquier derrota resetea a `{count: 0, levels: []}`, incluso sobre un
  nivel repetido. El umbral de WR que cuenta como "calificante" **no vive aquí** — cada uno de los 4
  achievements de racha (`on_a_roll`/`hot_streak`/`relentless`/`unbreakable`) recorta su propia
  racha efectiva al leer, con su propio umbral (ver `_streak_length` abajo).
- **`qualifying_levels`**: un registro por nivel, escrito solo la **primera vez** que se gana esta
  temporada — victorias posteriores del mismo nivel no lo sobreescriben. Preserva el WR/contexto de
  la partida que realmente lo ganó.
- **`three_star_levels`**: separado de `qualifying_levels` porque los 2 achievements de 3★ 
  (`three_star_warrior`, `perfectionist`) cuidan **cuándo se sacaron 3 estrellas**, que puede ser un
  replay distinto de la primera victoria. Gateado solo por `stars_earned == 3`, independiente de
  `match_stats.won`. Mismo primera-vez-only que `qualifying_levels`.

Solo guarda hechos crudos — ningún flag específico de achievement (`is_hit_free`, `is_comeback`...).
Qué satisface a cada guard es responsabilidad exclusiva del motor de evaluación.

---

## Motor de evaluación (`achievements_engine.py`)

`GUARDS: dict[achievement_id, Callable[[GuardContext], bool]]` — 40 predicados puros de Python,
agrupados por rareza (COMMON/UNCOMMON/RARE/EPIC/LEGENDARY) en el propio archivo.

```python
@dataclass
class GuardContext:
    level_id: int
    stars_earned: int
    match_stats: dict
    win_rate_snapshot: float | None
    season_stars: int
    streak_levels: list[dict]
    qualifying_levels: dict[str, dict]
    three_star_levels: dict[str, dict]
    season_points: float | None = None
```

`evaluate_achievements(db, uid, ...)`:
1. Lee `achievement_progress/{uid}.unlocked` (set existente).
2. Filtra `GUARDS` contra ese set — **nunca re-evalúa un achievement ya desbloqueado**.
3. Corre cada guard restante contra el `GuardContext` de esta partida.
4. Si hay nuevos: `set(merge=True)` agrega a `unlocked` + `unlock_timestamps`, retorna la lista.

Solo se llama cuando `match_stats` está presente y es válido — mismo gate que
`season_match_stats_service`.

### Patrones de guard reutilizables

```python
def _streak_length(levels: list[dict], wr_threshold: float) -> int:
    # cuenta la racha final de entradas cuyo win_rate_snapshot <= threshold;
    # WR ausente o > threshold corta la racha en ese punto (recorrido en reversa)
```

- **Guards de un solo match**: leen `match_stats` + `win_rate_snapshot` directo (ej. `first_blood`,
  `speedy`, `double_threat`).
- **Guards de racha**: `_streak_length(streak_levels, umbral_propio)` — cada uno de los 4 recorta
  su propia racha efectiva del mismo `win_streak.levels` crudo.
- **Guards de conteo calificante**: cuentan entradas de `qualifying_levels` que cumplen una
  condición (ej. `ghost` necesita 5 niveles hit-free con Bola/Mancha presente y WR≤50).
- **Guards de 3★**: cuentan sobre `three_star_levels` (ej. `three_star_warrior` necesita 20 totales
  con al menos 10 bajo WR≤50).

### Decisiones no obvias (razón completa en el docstring del módulo)

| Achievement(s) | Decisión |
|---|---|
| `on_a_roll`/`hot_streak`/`relentless`/`unbreakable` | Cada uno recorta la racha cruda a su propio umbral de WR — una victoria por encima del umbral corta la racha *para ese achievement* sin resetear el dato crudo (otro achievement con umbral más laxo puede seguir contándola) |
| `speedy`/`speedster`/`speed_legend` | Exigen `game_mode == "first_bite"` aunque `guard_notes` no lo diga explícito — tiempo-al-objetivo no tiene sentido fuera de ese modo |
| `always_moving`/`maze_master`/`hungry_hungry`/`big_eater` | "Modo comida" = `game_mode != "deep_run"` (único modo con `FOOD_COUNT=0`) |
| `seasonal_legend` | `season_points >= 4000` — falla cerrado si `season_points is None` (nunca antes de ST-08) |

---

## `season_points` (`season_points_service.py`)

```python
STARS_MULTIPLIER = 3
LEVELS_CLEARED_MULTIPLIER = 5

season_points = season_stars * 3 + levels_cleared * 5 + achievement_bonus_points
```

`achievement_bonus_points` se acumula en `season_progress/{uid}` sumando `config/achievements.points`
de cada achievement nuevo desbloqueado esa partida — se suma una sola vez (nunca se re-agrega en
partidas posteriores, el motor ya filtra por `unlocked`). `levels_cleared` cuenta `level_id`s únicos
completados esta temporada (`season_progress.levels_cleared_ids`), no partidas jugadas.

> **No alimenta el ranking del leaderboard todavía** — `GET /leaderboard` sigue ordenando por
> `season_stars` crudo. Gap conocido, no un descuido — ver `docs/DATA_MODEL.md#season_progress`.

---

## `GET /achievements` (`achievements_catalog_service.build_achievements_response`)

Merge puro de 3 fuentes ya leídas — sin I/O propio:

1. `config/achievements` (catálogo, 40 entradas) → `achievement_id`, `title` (=`name`),
   `description`, `icon_id` (= `f"badge_{achievement_id}"`, convención determinística — sin pipeline
   de assets real todavía).
2. `achievement_progress/{uid}` → `unlocked` (bool), `unlocked_at` (de `unlock_timestamps`).
3. `achievement_rarities/{achievement_id}` (si existe) → `rarity`/`rarity_percent` medidos; si no
   existe todavía (job de ST-10 no ha corrido para ese achievement), cae a `config/achievements`'
   `rarity_tier` estático con `rarity_percent: null`.

`progress` siempre `null` — `achievement_progress.progress` (numérico "N de M") nunca se puebla,
decisión de ST-07 (la mayoría de los 40 guards son compuestos booleanos sin fracción bien definida).

---

## Rareza medida (`achievement_rarities_service.py`)

```python
ACTIVE_WINDOW_DAYS = 30

_TIERS = ((50, "COMMON"), (20, "UNCOMMON"), (8, "RARE"), (4, "EPIC"))  # LEGENDARY si ninguno aplica
```

Job: `POST /jobs/recalc-achievement-rarities` (Cloud Scheduler, 24h) →
`recalc_achievement_rarities(db, project_id, dataset_id)`:

1. `fetch_active_uids` — `SELECT DISTINCT user_id` de `player_behavior` (BigQuery) en los últimos
   30 días. `total_players = len(active_uids)`.
2. `count_unlocks_among(db, active_uids)` — **un `get()` de `achievement_progress/{uid}` por cada
   uid activo** (no un scan de toda la colección), tally de qué achievements aparecen en su
   `unlocked`.
3. Por cada achievement del catálogo: `rarity_percent = unlocked_by / total_players * 100`,
   `rarity_tier = compute_rarity_tier(rarity_percent)`, `set()` en `achievement_rarities/{id}`.

**Por qué ambos lados de la fracción usan la misma población:** `achievement_progress` es
acumulativo y nunca se resetea — tiene desbloqueos de jugadores que dejaron de jugar hace meses. Si
`unlocked_by` contara todo el histórico contra un `total_players` limitado a la ventana activa,
`rarity_percent` podría superar 100% en cualquier achievement fácil. Acotar ambos al mismo
`active_uids` garantiza `rarity_percent ∈ [0, 100]`.

Si `total_players == 0` (ningún jugador activo en la ventana), el job **se salta por completo** —
no escribe con denominador cero. Misma filosofía que `level_stats_service.MIN_SAMPLE_SIZE`: señal
insuficiente no es lo mismo que "nadie lo desbloqueó".

---

## Limitaciones conocidas / a revisar

- **Cloud Scheduler de `recalc-level-stats` y `recalc-achievement-rarities` no creados en GCP
  todavía** — ambos endpoints funcionan y están probados, pero no se auto-programan. Trackeado en
  ticket de Infra/DevOps aparte.
- **`level_stats` vacío en todo ambiente hoy** — depende de tráfico real (`MIN_SAMPLE_SIZE=100`
  intentos/nivel) o de correr el harness de simulación T-203 para sembrarlo. Hasta entonces, los 26
  guards WR-gated fallan cerrado — no es un bug.
- **`season_points` no alimenta el leaderboard** — ver sección de `season_points` arriba.
- **`achievement_progress.progress` nunca poblado** — todo `GET /achievements` devuelve
  `progress: null`. No afecta la corrección del desbloqueo, solo una barra de progreso en UI.
- **`icon_id` es convención, no asset real** — pendiente de pipeline de badges.
- **Cliente Godot no envía `match_stats` ni `level_id` en `/lives/spend` todavía** (ST-02/ST-03,
  Juan) — nada se rompe (ambos opcionales), pero sin ellos no hay datos reales que evaluar.
