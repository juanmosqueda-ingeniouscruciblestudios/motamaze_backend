-- v_retention_cohorts
-- Cohort retention para D1 / D7 / D14 / D30.
-- Fuente: login_events (motamaze prod).
-- Usado por: Looker Studio dashboard "Retention".

CREATE OR REPLACE VIEW `motamaze.motamaze_analytics.v_retention_cohorts` AS
WITH first_seen AS (
  SELECT
    user_id,
    MIN(event_date)  AS cohort_date,
    MAX(country)     AS country,
    MAX(platform)    AS platform
  FROM `motamaze.motamaze_analytics.login_events`
  GROUP BY user_id
),
cohort_sizes AS (
  SELECT cohort_date, country, platform, COUNT(*) AS cohort_size
  FROM first_seen
  GROUP BY 1, 2, 3
),
daily_active AS (
  SELECT DISTINCT user_id, event_date
  FROM `motamaze.motamaze_analytics.login_events`
),
retained AS (
  SELECT
    f.cohort_date,
    f.country,
    f.platform,
    DATE_DIFF(da.event_date, f.cohort_date, DAY) AS retention_day,
    COUNT(DISTINCT f.user_id)                     AS retained_users
  FROM first_seen f
  JOIN daily_active da ON f.user_id = da.user_id
  WHERE DATE_DIFF(da.event_date, f.cohort_date, DAY) IN (0, 1, 7, 14, 30)
  GROUP BY 1, 2, 3, 4
)
SELECT
  r.cohort_date,
  r.country,
  r.platform,
  r.retention_day,
  cs.cohort_size,
  r.retained_users,
  SAFE_DIVIDE(r.retained_users, cs.cohort_size) AS retention_rate
FROM retained r
JOIN cohort_sizes cs
  ON  r.cohort_date = cs.cohort_date
  AND r.country     = cs.country
  AND r.platform    = cs.platform
ORDER BY r.cohort_date, r.retention_day;
