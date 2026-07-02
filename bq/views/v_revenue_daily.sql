-- v_revenue_daily
-- Revenue diario combinado: IAP (purchase_events) + AdMob (admob_daily_report).
-- Per-age queda pendiente hasta que EXT-002 ST-07 lleve Firebase demo data a BQ.
-- Usado por: Looker Studio dashboard "Revenue".

CREATE OR REPLACE VIEW `motamaze.motamaze_analytics.v_revenue_daily` AS
SELECT
  event_date                              AS report_date,
  country,
  platform,
  'iap'                                   AS revenue_source,
  SUM(COALESCE(price_usd, 0))             AS revenue_usd,
  COUNT(DISTINCT user_id)                 AS paying_users,
  COUNT(*)                                AS transactions
FROM `motamaze.motamaze_analytics.purchase_events`
WHERE verification_status = 'verified'
GROUP BY 1, 2, 3, 4

UNION ALL

SELECT
  report_date,
  country,
  'android'                               AS platform,
  'admob'                                 AS revenue_source,
  SUM(COALESCE(estimated_revenue, 0))     AS revenue_usd,
  0                                       AS paying_users,
  SUM(impressions)                        AS transactions
FROM `motamaze.motamaze_analytics.admob_daily_report`
GROUP BY 1, 2, 3, 4;
