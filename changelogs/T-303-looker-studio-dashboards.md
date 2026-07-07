# T-303 — Looker Studio Dashboards (Retention / Revenue / KPI Gates)

| Field | Value |
|---|---|
| **Type** | Analytics / BI |
| **Priority** | High — go/no-go soft launch 2026-09-14 |
| **Status** | In Progress — ST-01 ✅ BQ views creadas (2026-07-02); ST-02 ✅ Looker Studio setup completo (2026-07-07); ST-03 ⬜ uso en decisión go/no-go (2026-09-14) |
| **Date** | 2026-07-07 |
| **Workstream** | Dataflow & Outputs (DATA-004) |
| **Monday Item ID** | 12272094760 |
| **Depends-on** | DATA-001 ✅ (BQ tables), DATA-002 ✅ (streaming), EXT-001 ✅ (purchases data), EXT-002 ✅ (AdMob) |
| **Desbloquea** | Go/no-go soft launch decision (2026-09-14) |

---

## Descripción

Looker Studio es la herramienta de BI de Google ($0/mes), con conector nativo a BigQuery. Los dashboards monitorizan los kill-criteria del soft launch:

| KPI | Gate | Fuente BQ |
|---|---|---|
| D1 retention | ≥ 25–30% | `v_retention_cohorts` |
| D7 retention | ≥ 10% | `v_retention_cohorts` |
| No-Ads conversion | 2–5% | `v_kpi_gates` |
| Total revenue | > UA cost | `v_revenue_daily` |

**Per-age revenue:** pendiente hasta EXT-002 ST-07 (Firebase demographics → BQ). Los dashboards actuales tienen per-región (country). Se agrega age bracket como dimensión cuando el pipeline esté listo.

---

## ST-01 — Crear vistas BQ ✅ Done (2026-07-02)

Archivos SQL en `bq/views/`. Crear con los siguientes comandos después de `gcloud auth login`:

```bash
PROJECT="motamaze"
DATASET="motamaze_analytics"

# Vista 1 — Retention cohorts (D1/D7/D14/D30)
bq query --project_id=$PROJECT --use_legacy_sql=false \
  < bq/views/v_retention_cohorts.sql

# Vista 2 — Revenue diario (IAP + AdMob)
bq query --project_id=$PROJECT --use_legacy_sql=false \
  < bq/views/v_revenue_daily.sql

# Vista 3 — KPI gates scorecard
bq query --project_id=$PROJECT --use_legacy_sql=false \
  < bq/views/v_kpi_gates.sql
```

**Verificar:**
```bash
bq ls motamaze:motamaze_analytics | grep "^v_"
# Esperado: v_retention_cohorts  v_revenue_daily  v_kpi_gates
```

---

## ST-02 — Looker Studio setup ✅ Done (2026-07-07)

### Acceso
- URL: **https://lookerstudio.google.com**
- Login con la misma cuenta Google del proyecto GCP (`motamaze`)
- No requiere instalación ni costo adicional

---

### Paso 1 — Crear data sources (3 total)

Ir a **Looker Studio → Create → Data source**

**Data source 1: `BQ_Retention`**
1. Seleccionar conector **BigQuery**
2. Project: `motamaze` → Dataset: `motamaze_analytics` → Table: `v_retention_cohorts`
3. Nombre: `BQ_Retention`
4. Clic **Connect** → **Done**

**Data source 2: `BQ_Revenue`**
1. Conector **BigQuery** → `motamaze` → `motamaze_analytics` → `v_revenue_daily`
2. Nombre: `BQ_Revenue` → **Connect** → **Done**

**Data source 3: `BQ_KPI_Gates`**
1. Conector **BigQuery** → `motamaze` → `motamaze_analytics` → `v_kpi_gates`
2. Nombre: `BQ_KPI_Gates` → **Connect** → **Done**

---

### Paso 2 — Dashboard 1: Retention

**Crear → Report** → título: `MotaMaze — Retention`
Data source inicial: `BQ_Retention`

#### Chart 1: Tabla de cohorts D1/D7

| Configuración | Valor |
|---|---|
| Tipo | **Table** |
| Dimension | `cohort_date`, `country`, `platform`, `retention_day` |
| Metric | `cohort_size`, `retained_users`, `retention_rate` |
| Sort | `cohort_date` DESC |
| Filter | `retention_day` IN (0, 1, 7) |

#### Chart 2: Scorecard D1 rate (últimos 30 días)

| Configuración | Valor |
|---|---|
| Tipo | **Scorecard** |
| Metric | `retention_rate` |
| Filter | `retention_day = 1` + `cohort_date >= DATE_SUB(TODAY, 30)` |
| Comparison | Target: `0.25` (kill-criteria D1 ≥ 25%) |
| Format | Percent |

#### Chart 3: Scorecard D7 rate (últimos 30 días)

| Configuración | Valor |
|---|---|
| Tipo | **Scorecard** |
| Metric | `retention_rate` |
| Filter | `retention_day = 7` + `cohort_date >= DATE_SUB(TODAY, 37)` |
| Comparison | Target: `0.10` (kill-criteria D7 ≥ 10%) |
| Format | Percent |

#### Chart 4: Line chart — D1/D7 por fecha de cohort

| Configuración | Valor |
|---|---|
| Tipo | **Time series** |
| Dimension | `cohort_date` |
| Metric | `retention_rate` (una serie por `retention_day`) |
| Breakdown | `retention_day` |
| Filter | `retention_day` IN (1, 7) |

#### Filtros globales del dashboard
- Date range control → campo `cohort_date` (por default: últimos 30 días)
- Dropdown control → campo `country`
- Dropdown control → campo `platform`

---

### Paso 3 — Dashboard 2: Revenue

**Crear → Report** → título: `MotaMaze — Revenue`
Data source inicial: `BQ_Revenue`

#### Chart 1: Time series — Revenue diario total

| Configuración | Valor |
|---|---|
| Tipo | **Time series** |
| Dimension | `report_date` |
| Metric | `revenue_usd` (stacked por `revenue_source`: IAP vs AdMob) |
| Breakdown | `revenue_source` |

#### Chart 2: Bar chart — Revenue por país

| Configuración | Valor |
|---|---|
| Tipo | **Bar chart** |
| Dimension | `country` |
| Metric | `revenue_usd` |
| Sort | `revenue_usd` DESC |

#### Chart 3: Scorecard — Total revenue

| Configuración | Valor |
|---|---|
| Tipo | **Scorecard** |
| Metric | `revenue_usd` (SUM) |
| Label | `Total Revenue (USD)` |

#### Chart 4: Scorecard — Paying users

| Configuración | Valor |
|---|---|
| Tipo | **Scorecard** |
| Metric | `paying_users` (SUM, source='iap' filter) |
| Label | `Paying Users` |

#### Chart 5: Tabla — Detalle por país y fuente

| Configuración | Valor |
|---|---|
| Tipo | **Table** |
| Dimension | `report_date`, `country`, `revenue_source` |
| Metric | `revenue_usd`, `paying_users`, `transactions` |
| Sort | `report_date` DESC |

#### Filtros globales
- Date range control → `report_date`
- Dropdown → `revenue_source`
- Dropdown → `country`

---

### Paso 4 — Dashboard 3: KPI Gates

**Crear → Report** → título: `MotaMaze — KPI Gates (Go/No-Go)`
Data source inicial: `BQ_KPI_Gates`

> Este dashboard tiene UNA fila de datos (la vista es un agregado global). Los scorecards muestran el estado actual acumulado de todos los usuarios.

#### Chart 1: Scorecard — D1 Retention

| Configuración | Valor |
|---|---|
| Tipo | **Scorecard** |
| Metric | `d1_rate` |
| Comparison metric | Valor fijo: `0.25` |
| Conditional formatting | ≥ 0.25 → verde, < 0.25 → rojo |
| Label | `D1 Retention (gate: ≥ 25%)` |
| Format | Percent |

#### Chart 2: Scorecard — D7 Retention

| Configuración | Valor |
|---|---|
| Tipo | **Scorecard** |
| Metric | `d7_rate` |
| Comparison | `0.10` |
| Conditional formatting | ≥ 0.10 → verde, < 0.10 → rojo |
| Label | `D7 Retention (gate: ≥ 10%)` |
| Format | Percent |

#### Chart 3: Scorecard — No-Ads Conversion

| Configuración | Valor |
|---|---|
| Tipo | **Scorecard** |
| Metric | `no_ads_conversion_rate` |
| Comparison | `0.02` |
| Conditional formatting | 0.02–0.05 → verde, fuera rango → rojo |
| Label | `No-Ads Conversion (gate: 2–5%)` |
| Format | Percent |

#### Chart 4: Scorecard — Total Users

| Configuración | Valor |
|---|---|
| Tipo | **Scorecard** |
| Metric | `total_users` |
| Label | `Total Users` |

#### Chart 5: Scorecard — Total Revenue USD

| Configuración | Valor |
|---|---|
| Tipo | **Scorecard** |
| Metric | `total_revenue_usd` |
| Label | `Total Revenue (IAP + AdMob)` |
| Format | Currency USD |

#### Chart 6: Table — Resumen de gates

| Configuración | Valor |
|---|---|
| Tipo | **Table** |
| Columns | `d1_rate`, `d7_rate`, `no_ads_conversion_rate`, `gate_d1_ok`, `gate_d7_ok`, `gate_no_ads_ok` |
| Conditional formatting | `gate_*_ok = TRUE` → fondo verde, `FALSE` → fondo rojo |

---

### Paso 5 — Compartir dashboards

1. Clic en **Share** (top-right) en cada dashboard
2. Agregar `juan@ingeniouscruciblestudios.com` como **Viewer**
3. Activar **"Link sharing"** → Anyone with the link (para junta de go/no-go)

---

## ST-03 — Uso en decisión go/no-go ⬜ Pendiente (2026-09-14)

Los dashboards estarán vacíos hasta que el soft launch arranque (~9/14). El flujo de datos es:
```
Usuarios → App → POST /auth/login → login_events (BQ streaming) → v_retention_cohorts
Usuarios → Compra → POST /payments/android/verify → purchase_events → v_revenue_daily
AdMob → admob_daily_report (DATA-003, 7/10)
```

En la junta go/no-go: revisar Dashboard 3 (KPI Gates) — si los 3 gates están en verde ≥ 2 semanas post soft-launch → decisión de escalar a commercial launch (10/27).

---

## Notas técnicas

- **Per-age revenue:** Pendiente EXT-002 ST-07 (Firebase Analytics demographics → BQ). Cuando esté disponible, agregar `age_bracket` como dimensión en `v_revenue_daily` y un Chart 6 en el dashboard Revenue.
- **LTV > UA cost gate:** LTV se calcula como `total_revenue_usd / paying_users`. UA cost viene de Tenjin (T-440). Por ahora se agrega manualmente en el dashboard KPI Gates como campo calculado cuando tengamos el gasto de UA.
- **Data freshness:** Las views BQ leen datos en tiempo real (no hay cache en BigQuery Standard). Looker Studio cachea por 12h por default — reducir a 1h en producción via **Resource → Manage added data sources → Edit → Freshness**.
- **Costo BQ:** Las views no tienen costo fijo. Looker Studio hace queries a demanda. Con volumen MVP (miles de usuarios) el costo será < $1/mes.
