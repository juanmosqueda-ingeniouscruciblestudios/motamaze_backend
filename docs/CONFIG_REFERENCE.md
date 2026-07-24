# Config Reference — Firebase Remote Config Parameters

> Última actualización: 2026-07-24 (T-244)
> Referenciado desde el ticket original de T-244; no existía hasta ahora.

Lista cada parámetro de Firebase Remote Config que el backend lee. Detalle de implementación
(cliente REST, cache, fallback): `logic/remote-config.md`.

---

## Parámetros

| Key | Tipo | Default (fallback si Remote Config no responde) | Qué controla | Leído por |
|---|---|---|---|---|
| `regen_interval_secs` | integer (segundos) | `1800` (30 min) | Cada cuánto se regenera 1 vida | `GET /lives`, `POST /lives/spend`, `POST /lives/grant` |
| `default_max_lives` | integer | `5` | Máximo de vidas por usuario (tope de regen y de grants) | `GET /lives`, `POST /lives/spend`, `POST /lives/grant` |

**Ninguno de los dos está publicado todavía en Remote Config** (2026-07-24) — el backend corre
100% con los defaults de fallback hasta que ST-05 los cree en la consola de Firebase.

---

## Fuera de alcance de T-244 (decisión de scope, no un olvido)

| Tunable mencionado en el ticket original | Por qué no está aquí |
|---|---|
| Catálogo / promociones | T-240 ya los hace live-tunable vía Firestore (`config/catalog`, `promotions`) — Remote Config no es buen fit para su estructura anidada de productos, y agregarlo encima sería redundante |
| Niveles (`LevelData`) | Viven en recursos `.tres` de Godot — 100% cliente, el backend no tiene ningún parámetro de nivel que ajustar |

---

## Cómo agregar un nuevo parámetro

1. Crearlo en Firebase Console → Remote Config → proyecto correspondiente (dev primero, luego prod)
2. Publicar el template
3. Backend: `await remote_config_service.get_value(settings.gcp_project_id, "<key>", <default>, cast=<tipo>)`
   — siempre con un default de fallback explícito, nunca asumir que el parámetro existe
4. Agregar la fila a la tabla de arriba

---

## "Change auditing"

El ticket original pedía "change auditing" como criterio de aceptación. Se interpretó como
satisfecho por el **historial de versiones nativo de Firebase Remote Config** (consola → Remote
Config → History — cada publicación queda registrada con quién y cuándo, con posibilidad de
rollback) — **sin código de auditoría adicional en el backend**. Decisión de alcance explícita, no
un criterio omitido por accidente.
