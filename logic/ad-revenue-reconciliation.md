# Ad Revenue Reconciliation (T-302) — Estado actual

> Última actualización: 2026-07-23

Compara lo que nosotros mismos registramos como impresiones de anuncios contra lo que AdMob reporta
oficialmente, y marca discrepancias grandes. Objetivo: detectar fraude, fallas de logging, o SDK
mal instrumentado — el revenue debe ser preciso y verificable para el modelo financiero y las
decisiones de kill-criteria (LTV).

---

## Las dos fuentes de datos

| Tabla (BigQuery) | Quién la llena | Qué mide |
|---|---|---|
| `admob_daily_report` | `POST /jobs/admob-daily-report` (DATA-003, diario) — pull directo de la AdMob Reporting API | La verdad oficial de Google: impresiones/clicks/earnings por `ad_unit_id` + país + formato + día |
| `ad_impressions` | `POST /lives/grant` (`app/routers/game.py`), **solo** para `source=rewarded_ad_ssv` | Nuestro propio conteo — hoy **solo captura rewarded ads completados**, ningún otro formato |

---

## Gap conocido y deliberado: solo rewarded está instrumentado

El architecture doc original preveía un evento por-impresión disparado por el callback de revenue
de AdMob (`OnPaidEventListener`) para **todos** los formatos (rewarded, interstitial, banner),
enviado vía Firebase Analytics o un endpoint propio. Eso **no está construido** — ni en Godot
(cliente, Juan) ni como export de Firebase Analytics → BigQuery.

**Consecuencia práctica:** `interstitial`/`banner` van a mostrar ~100% de discrepancia en este job
hasta que ese trabajo de cliente exista — eso es **esperado y documentado**, no un bug de la
reconciliación. La función deliberadamente no oculta ni filtra estos casos; mostrarlos es, en sí
mismo, la prueba de que el pipeline de reconciliación funciona correctamente.

`revenue_usd` en `ad_impressions` también queda siempre en `None` hoy — la reconciliación actual
compara **conteo de impresiones**, no revenue por impresión (no hay de dónde sacar un revenue real
por evento todavía).

---

## El job (`POST /jobs/reconcile-ad-revenue`)

`app/routers/jobs.py`, mismo patrón de header `X-CloudScheduler-JobName` que el resto de `/jobs`.
**Debe programarse para correr después de `admob-daily-report`** — lee `admob_daily_report` para el
mismo `report_date` (ayer), y esa tabla solo la llena el otro job.

### `reconcile_ad_revenue()` (`app/services/ad_revenue_reconciliation_service.py`)

Primer uso de `SELECT` contra BigQuery en este codebase (`bq_streaming.run_select()`, nuevo —
todo lo anterior era streaming insert o DML). Por cada `ad_unit_id` presente en `admob_daily_report`
para el día: suma impresiones de AdMob, cuenta nuestras propias filas de `ad_impressions`, calcula
`discrepancy_percent = abs(admob - nuestro) / admob * 100`.

```python
DISCREPANCY_THRESHOLD_PERCENT = 10.0  # punto de partida, sin tunear contra tráfico real
```

Umbral inicial, no validado contra datos reales — las discrepancias entre un ad network y el conteo
propio de un cliente típicamente rondan unos pocos % por diferencias de timezone/ventanas de
conteo/ad-blockers; 10% es un punto de partida razonable, a revisar cuando haya tráfico real.

**Caso especial: `admob_impressions == 0`.** `discrepancy_percent` es `None`, no `0%` ni `100%` —
ninguno de los dos representaría honestamente "no hay nada que comparar."

---

## Qué pasa cuando se detecta una discrepancia

Se loguea (`logger.warning`, Cloud Logging — buscable/alertable) y se incluye en la respuesta del
endpoint. **No se persiste en una tabla propia** — mismo criterio que `reconcile-purchases`
(PAY-002), que tampoco tiene tabla de auditoría dedicada, solo logs + el resumen de la respuesta.

---

## Limitaciones conocidas / a revisar

- **Solo rewarded ads están instrumentados** — ver sección de arriba. Cierra cuando exista el
  callback de revenue de AdMob en Godot o el export de Firebase Analytics → BigQuery.
- **Umbral de 10% sin validar contra tráfico real** — ajustar una vez haya datos de producción.
- **Reconciliación por conteo, no por revenue** — `revenue_usd` en `ad_impressions` siempre es
  `None` hoy; comparar `admob_earnings_micros` contra un revenue real por impresión requiere el
  mismo trabajo de cliente pendiente arriba.
- **Orden de scheduling no forzado en código** — si `reconcile-ad-revenue` corre antes que
  `admob-daily-report` termine, simplemente no encuentra datos para ese `ad_unit_id` ese día (no
  falla, no falso-positivo) — pero tampoco reconcilia nada útil. Responsabilidad del scheduling en
  Cloud Scheduler, no de este código.
