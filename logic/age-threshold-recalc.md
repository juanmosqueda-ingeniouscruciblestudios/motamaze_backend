# Age Threshold Recalc (T-404) — Estado actual

> Última actualización: 2026-07-23
> Complementa [age-assurance.md](age-assurance.md) — no repite el contexto de umbrales por país,
> las dos ramas (DOB vs. señal BR), ni el helper `age_gate_update`. Léelo primero si hace falta ese
> contexto.

Un usuario cuyo `is_child` se determinó por DOB (Rama 1 de `age-assurance.md`) queda con ese valor
congelado para siempre, a menos que algo lo recalcule — pero la edad de una persona cambia con el
tiempo. Este sistema cierra ese hueco: un job mensual detecta cuándo un usuario cruzó el umbral de
edad de su país desde que se verificó, y lo voltea a adulto sin pedirle que se re-verifique.

---

## Por qué esto no existía hasta ahora

El architecture doc especificaba el diseño exacto desde el principio (línea 1140): *"Store
birth_month + birth_year only for annual recalculation. Never write birth_day to any database."*
Nunca se implementó — `POST /auth/age-verify` (T-401) ya parseaba el DOB completo del cliente para
calcular `age`, pero la variable se descartaba enteramente después de eso. No había nada guardado de
lo que un job pudiera recalcular.

## Los 3 pasos (ST-01, ST-02, ST-03)

### 1. Persistencia — `birth_month`/`birth_year` (`app/routers/auth.py`, `age_verify`)

Se agregan al `update` dict existente, derivados de `dob.month`/`dob.year` — sin pedir nada nuevo al
cliente, el DOB completo ya llegaba en el request. **Nunca se guarda el día.**

**Solo se escriben en la rama donde el DOB decidió `is_child`** (`signal_is_minor is None`) — nunca
en la rama donde la señal de tienda de Brasil ya lo decidió. Esto es deliberado: la sola *presencia*
de `birth_month`/`birth_year` debe significar "este `is_child` viene del DOB", para que el job de
recálculo (paso 3) pueda confiar en eso sin tener que además cruzar `country_code`. Un usuario BR
cuyo `is_child` vino de la señal de tienda nunca debe ser re-derivado por DOB.

Se guardan tanto para niños como para adultos verificados por DOB — no solo para niños — porque un
adulto de hoy también sirve como ancla para futuros recálculos si su umbral cambiara (no aplica hoy,
pero no hay razón para excluirlos).

### 2. Función pura — `geo_service.has_aged_out(birth_month, birth_year, threshold, today)`

```python
ages_out_year = birth_year + threshold
if birth_month == 12:
    ages_out_on = date(ages_out_year + 1, 1, 1)
else:
    ages_out_on = date(ages_out_year, birth_month + 1, 1)
return today >= ages_out_on
```

**Redondeo conservador, no arbitrario.** Como solo se guarda mes+año (nunca el día), el día exacto
de cruce dentro del mes es ambiguo. Se resuelve a favor de proteger de más: el usuario sigue siendo
"child" durante *todo* su mes de nacimiento (incluso después de su cumpleaños real, que
desconocemos), y recién se considera "aged out" el día 1 del mes siguiente. Mismo sesgo que
`store_age_signal_is_minor` y el resto del sistema de age-assurance — nunca adelantar a alguien a
adulto antes de tiempo.

### 3. El job — `POST /jobs/recalc-age-thresholds` (`app/routers/jobs.py`)

Mismo patrón de header `X-CloudScheduler-JobName` que el resto de `/jobs`. Cadencia **mensual**
(no diaria como la mayoría de los otros jobs) — el evento subyacente (cumpleaños) es una vez al año,
correr más seguido no aporta nada.

`age_threshold_recalc_service.find_and_recalc_aged_out_users()`:
- Scan completo de `users`, filtrado en Python (misma razón de escala MVP que
  `find_users_due_for_purge` de T-123: evita índice compuesto y una query de desigualdad contra un
  campo mayormente ausente).
- Filtra a `consent.is_child == True` con `birth_month`/`birth_year` presentes — **esa sola
  presencia ya excluye a los usuarios BR de señal de tienda**, sin chequeo explícito de
  `country_code` (ver punto 1).
- Por cada uno, si `has_aged_out(...)` → aplica `geo_service.age_gate_update(False, now)` (mismo
  helper que ya usan `age-verify` y `upsert_user` — `is_child`, `restricted_features`,
  `coppa_compliant`, forma idéntica sin importar qué señal decidió).

**Idempotente por construcción, no por código defensivo extra:** una vez que `is_child` pasa a
`False`, el mismo filtro (`is_child == True`) excluye al usuario de cualquier corrida futura — no
hace falta marcador de "ya procesado" ni lógica de dedup.

---

## Alcance: solo Rama 1 (DOB), nunca Rama 2 (señal BR)

Un usuario de Brasil cuyo `is_child` se determinó por `store_age_signal` (una *banda* como
`"13-15"`, no una fecha exacta) no tiene `birth_month`/`birth_year` — no hay de qué recalcular. Este
job no los toca, ni tiene forma de hacerlo con el dato disponible hoy. Si esos usuarios necesitan
reevaluación periódica, sería un mecanismo distinto (volver a consultar la API de la tienda), fuera
del alcance de T-404.

---

## Limitaciones conocidas / a revisar

- **Precisión de mes, no de día** — ver la sección de redondeo conservador arriba. Puede haber hasta
  ~1 mes de retraso entre el cumpleaños real y el momento en que el sistema lo refleja — trade-off
  deliberado por minimización de datos, no un bug.
- **Cloud Scheduler solo en DEV** al momento de escribir esto — promoción a PROD pendiente (ST-06).
- **Usuarios BR (señal de tienda) fuera de alcance** — ver sección de arriba.
