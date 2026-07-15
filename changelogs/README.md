# Changelogs

| Ticket | Slug | Workstream | Status | Date |
|---|---|---|---|---|
| [INFRA-001](INFRA-001-gcp-base-infra.md) | gcp-base-infra | Infra/DevOps | ✅ Done | 2026-06-16 |
| [EXT-001](EXT-001-google-play-developer-api.md) | google-play-developer-api | External Services | ✅ Done — ST-01–06 ✅ (SA autenticado vs. Play Developer API, reviews.list 200 ✅, 2026-07-01) | 2026-07-01 |
| [EXT-002](EXT-002-admob-account-ad-units.md) | admob-account-ad-units | External Services | ✅ Done | 2026-06-17 |
| [DATA-001](DATA-001-bigquery-analytics-tables.md) | bigquery-analytics-tables | Dataflow & Outputs | ✅ Done | 2026-06-16 |
| [INFRA-002](INFRA-002-env-secrets-design.md) | env-secrets-design | Infra/DevOps | ✅ Done | 2026-06-17 |
| [REST-001](REST-001-rest-api-contract.md) | rest-api-contract | Planning | ✅ Done — ST-01–08 ✅ (sign-off Juan commit 9216611, 2026-06-22) | 2026-06-22 |
| [INFRA-003](INFRA-003-fastapi-scaffold-cloud-run.md) | fastapi-scaffold-cloud-run | Infra/DevOps | ✅ Done — ST-01–06 ✅ (Cloud Run dev+prod live 2026-06-24), T-440 ✅ (2026-06-30) | 2026-06-30 |
| [T-440](T-440-share-score-backend.md) | share-score-backend | Social | In Progress — ST-01 ✅ POST /share/create + GET /s/{token} + GET /ogimg/{token} (2026-06-30); ST-02 ⬜ integration tests pending deploy (Cloudinary / WhatsApp / Telegram) | 2026-06-30 |
| [T-210](T-210-progress-backend.md) | progress-backend | Game Services | ✅ Done — GET /progress + POST /progress/level-complete Firestore completo; ST-02 integration tests 7/7 ✅ (2026-06-30) | 2026-06-30 |
| [T-220](T-220-lives-backend.md) | lives-backend | Game Services | ✅ Done — GET /lives + POST /lives/spend (Firestore txn) + POST /lives/grant; ST-02 integration tests 9/9 ✅ (2026-06-30) | 2026-06-30 |
| [T-115](T-115-cloud-monitoring.md) | cloud-monitoring | Infra/DevOps | Done — dashboard ✅, uptime check /health ✅, 3 alert policies ✅ (5xx/latency/uptime), Pub/Sub kill switch ✅, email notifs → Saul ✅ (2026-06-30) | 2026-06-30 |
| [DATA-002](DATA-002-firestore-bigquery-streaming.md) | firestore-bigquery-streaming | Dataflow & Outputs | Done — ST-01–12 ✅ (BQ streaming verificado end-to-end 2026-06-26) | 2026-06-26 |
| [INFRA-004](INFRA-004-rs256-keypair-secret-manager.md) | rs256-keypair-secret-manager | Infra/DevOps | ✅ Done — ST-01–05 ✅, JWKS endpoint live, jwt-private-key en dev+prod SM (2026-06-24) | 2026-06-24 |
| [INFRA-005](INFRA-005-firestore-schema-security-rules.md) | firestore-schema-security-rules | Infra/DevOps | ✅ Done — ST-01–04 ✅, ST-03 8/8 tests passed vía Firebase Rules API (2026-06-30) | 2026-06-30 |
| [INFRA-006](INFRA-006-dev-staging-prod-terraform.md) | dev-staging-prod-terraform | Infra/DevOps | ✅ Done — ST-01–04 ✅ terraform apply dev completo (9 imported, 24 added, 9 changed, 0 destroyed, 2026-07-13). Staging diferido a post-lanzamiento. | 2026-07-13 |
| [CI-001](CI-001-cicd-github-actions.md) | cicd-github-actions | Infra/DevOps | ✅ Done — pipeline verde end-to-end run #19, dev + prod (2026-06-24) | 2026-06-24 |
| [PAY-001](PAY-001-android-purchase-verification.md) | android-purchase-verification | Payments | ✅ Done — ST-01 ✅ implementación completa (commit `cd9ad1e`); ST-02 ✅ error-path tests PASS (2026-07-09); ST-03 ✅ movida a T-607 (2026-07-13); Fix T-405 purchaseToken → SHA-256 hash | 2026-07-13 |
| [T-303](T-303-looker-studio-dashboards.md) | looker-studio-dashboards | Dataflow & Outputs | ✅ Done — ST-01 ✅ 3 BQ views; ST-02 ✅ 3 dashboards Looker Studio live; ST-03 ✅ movida a T-600 (2026-07-13) | 2026-07-13 |
| [DATA-003](DATA-003-admob-reporting-api.md) | admob-reporting-api | Dataflow & Outputs | In Progress — ST-01 ✅ OAuth credentials SM; ST-02 ✅ Cloud Run job + Scheduler live (2026-07-09); ST-03 ⬜ verificar datos reales post soft-launch | 2026-07-09 |
| [PAY-002](PAY-002-daily-reconciliation-job.md) | daily-reconciliation-job | Payments | ✅ Done — ST-01 ✅ implementación completa (2026-07-09); ST-02 ✅ Cloud Scheduler live (2026-07-09); ST-03 ⬜ test e2e pending T-252/T-607 | 2026-07-09 |
| [T-400](T-400-region-aware-age-logic.md) | region-aware-age-logic | Compliance | ✅ Done — ST-01 ✅ ST-02 ✅ ST-03 ✅ 18/18 PASS (2026-07-14); tests 1-2 store_country_code movidos a T-607 | 2026-07-14 |
| [T-406](T-406-iarc-content-rating.md) | iarc-content-rating | Compliance | In Progress — ST-01 ✅ IARC questionnaire completo, ratings guardados en Play Console (ESRB:E / PEGI:3 / ClassInd:14+ / USK:0, 2026-07-13); ST-02 ⬜ coppa_compliant flag activation pending T-400 ST-03 | 2026-07-13 |
| [T-414](T-414-upgrade-firebase-blaze.md) | upgrade-firebase-blaze | Infra/DevOps | ✅ Done — Firebase Blaze confirmado + google-oauth-client-id/secret poblados en prod SM (2026-07-13); admob-ssv-hmac-key diferido (SSV no implementado, ticket futuro) | 2026-07-13 |
| [T-443](T-443-leaderboard-backend.md) | leaderboard-backend | Game Services | ✅ Done — POST /leaderboard/score (App Check + BQ anomaly) + GET /leaderboard (CDN 5-min) + Firestore leaderboards/{season}/scores/{uid} (2026-07-14) | 2026-07-14 |
| [T-254](T-254-refund-notifications.md) | refund-notifications | Payments | ✅ Done — ST-01 ✅ código completo; ST-02 ✅ GCP infra completa (topic + IAM + push subscription); ST-03 → T-607 (Play Console RTDN config, pending publicación) | 2026-07-14 |
| [T-407](T-407-latam-age-thresholds.md) | latam-age-thresholds | Compliance | ✅ Done — MX=18 / AR=16 / PE=14 / UY=18 agregados a consent_age_threshold(); 16/16 tests PASS (2026-07-14) | 2026-07-14 |
| [T-401](T-401-verifiable-parental-consent.md) | verifiable-parental-consent | Compliance | In Progress — ST-01 ✅ ST-02 ✅ ST-03 ✅ backend completo (SendGrid, 2026-07-15); ST-04–05 ⬜ client (Juan); ST-06 ⬜ E2E | 2026-07-15 |
