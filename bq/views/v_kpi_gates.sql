-- v_kpi_gates
-- KPI scorecard para el go/no-go del soft launch (9/14).
-- Kill-criteria: D1>=25%, D7>=10%, No-Ads conversion 2-5%, total revenue positivo.
-- Usado por: Looker Studio dashboard "KPI Gates".
-- Nota: LTV>UA cost se agrega manualmente en Looker Studio como métrica calculada
--       cuando tengamos datos de Tenjin (T-440 share_url tracking).

CREATE OR REPLACE VIEW `motamaze.motamaze_analytics.v_kpi_gates` AS
WITH new_users AS (
  SELECT
    user_id,
    MIN(event_date) AS cohort_date
  FROM `motamaze.motamaze_analytics.login_events`
  GROUP BY user_id
),
total_users AS (
  SELECT COUNT(DISTINCT user_id) AS total
  FROM `motamaze.motamaze_analytics.login_events`
),
d1_cohorts AS (
  -- Cohorts con al menos 1 día de historia (para poder medir D1)
  SELECT nu.user_id, nu.cohort_date
  FROM new_users nu
  WHERE nu.cohort_date <= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
),
d7_cohorts AS (
  -- Cohorts con al menos 7 días de historia (para poder medir D7)
  SELECT nu.user_id, nu.cohort_date
  FROM new_users nu
  WHERE nu.cohort_date <= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
),
d1_retained AS (
  SELECT COUNT(DISTINCT d1.user_id) AS retained
  FROM d1_cohorts d1
  JOIN `motamaze.motamaze_analytics.login_events` l
    ON  d1.user_id = l.user_id
    AND l.event_date = DATE_ADD(d1.cohort_date, INTERVAL 1 DAY)
),
d7_retained AS (
  SELECT COUNT(DISTINCT d7.user_id) AS retained
  FROM d7_cohorts d7
  JOIN `motamaze.motamaze_analytics.login_events` l
    ON  d7.user_id = l.user_id
    AND l.event_date = DATE_ADD(d7.cohort_date, INTERVAL 7 DAY)
),
no_ads_buyers AS (
  SELECT COUNT(DISTINCT user_id) AS buyers
  FROM `motamaze.motamaze_analytics.entitlement_grants`
  WHERE entitlement_type = 'no_ads'
    AND source = 'iap'
),
revenue_totals AS (
  SELECT
    SUM(CASE WHEN verification_status = 'verified' THEN COALESCE(price_usd, 0) ELSE 0 END) AS iap_revenue_usd
  FROM `motamaze.motamaze_analytics.purchase_events`
),
ad_revenue_totals AS (
  SELECT SUM(COALESCE(estimated_earnings_micros, 0)) / 1000000.0 AS ad_revenue_usd
  FROM `motamaze.motamaze_analytics.admob_daily_report`
)
SELECT
  -- Totales
  tu.total                                                           AS total_users,
  (SELECT COUNT(*) FROM d1_cohorts)                                  AS d1_eligible_cohort,
  (SELECT COUNT(*) FROM d7_cohorts)                                  AS d7_eligible_cohort,

  -- Retention
  d1r.retained                                                       AS d1_retained_users,
  d7r.retained                                                       AS d7_retained_users,
  SAFE_DIVIDE(d1r.retained, (SELECT COUNT(*) FROM d1_cohorts))       AS d1_rate,
  SAFE_DIVIDE(d7r.retained, (SELECT COUNT(*) FROM d7_cohorts))       AS d7_rate,

  -- Conversion No-Ads
  nab.buyers                                                         AS no_ads_buyers,
  SAFE_DIVIDE(nab.buyers, tu.total)                                  AS no_ads_conversion_rate,

  -- Revenue
  rt.iap_revenue_usd,
  art.ad_revenue_usd,
  rt.iap_revenue_usd + art.ad_revenue_usd                           AS total_revenue_usd,

  -- Kill-criteria flags (TRUE = passing gate)
  SAFE_DIVIDE(d1r.retained, (SELECT COUNT(*) FROM d1_cohorts)) >= 0.25  AS gate_d1_ok,
  SAFE_DIVIDE(d7r.retained, (SELECT COUNT(*) FROM d7_cohorts)) >= 0.10  AS gate_d7_ok,
  SAFE_DIVIDE(nab.buyers, tu.total) BETWEEN 0.02 AND 0.05               AS gate_no_ads_ok

FROM total_users tu
CROSS JOIN d1_retained d1r
CROSS JOIN d7_retained d7r
CROSS JOIN no_ads_buyers nab
CROSS JOIN revenue_totals rt
CROSS JOIN ad_revenue_totals art;
