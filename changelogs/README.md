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
| [T-440](T-440-share-score-backend.md) | share-score-backend | Social | Done — ST-01 ✅ POST /share/create + GET /s/{token} + GET /ogimg/{token} (2026-06-30); ST-02 integration tests ⬜ pending deploy | 2026-06-30 |
| [T-210](T-210-progress-backend.md) | progress-backend | Game Services | ✅ Done — GET /progress + POST /progress/level-complete Firestore completo; ST-02 integration tests 7/7 ✅ (2026-06-30) | 2026-06-30 |
| [T-220](T-220-lives-backend.md) | lives-backend | Game Services | ✅ Done — GET /lives + POST /lives/spend (Firestore txn) + POST /lives/grant; ST-02 integration tests 9/9 ✅ (2026-06-30) | 2026-06-30 |
| [T-115](T-115-cloud-monitoring.md) | cloud-monitoring | Infra/DevOps | Done — dashboard ✅, uptime check /health ✅, 3 alert policies ✅ (5xx/latency/uptime), Pub/Sub kill switch ✅, email notifs → Saul ✅ (2026-06-30) | 2026-06-30 |
| [DATA-002](DATA-002-firestore-bigquery-streaming.md) | firestore-bigquery-streaming | Dataflow & Outputs | Done — ST-01–12 ✅ (BQ streaming verificado end-to-end 2026-06-26) | 2026-06-26 |
| [INFRA-004](INFRA-004-rs256-keypair-secret-manager.md) | rs256-keypair-secret-manager | Infra/DevOps | ✅ Done — ST-01–05 ✅, JWKS endpoint live, jwt-private-key en dev+prod SM (2026-06-24) | 2026-06-24 |
| [INFRA-005](INFRA-005-firestore-schema-security-rules.md) | firestore-schema-security-rules | Infra/DevOps | ✅ Done — ST-01–04 ✅, ST-03 8/8 tests passed vía Firebase Rules API (2026-06-30) | 2026-06-30 |
| [INFRA-006](INFRA-006-dev-staging-prod-terraform.md) | dev-staging-prod-terraform | Infra/DevOps | ✅ Done — ST-01–04 ✅ terraform apply dev completo (9 imported, 24 added, 9 changed, 0 destroyed, 2026-07-13). Staging diferido a post-lanzamiento. | 2026-07-13 |
| [CI-001](CI-001-cicd-github-actions.md) | cicd-github-actions | Infra/DevOps | ✅ Done — pipeline verde end-to-end run #19, dev + prod (2026-06-24) | 2026-06-24 |
| [PAY-001](PAY-001-android-purchase-verification.md) | android-purchase-verification | Payments | In Progress — ST-01 ✅ implementación completa (commit `cd9ad1e`); ST-02 ✅ error-path tests PASS (2026-07-09); ST-03 ⬜ real grant test pending T-252 | 2026-07-09 |
| [T-303](T-303-looker-studio-dashboards.md) | looker-studio-dashboards | Dataflow & Outputs | In Progress — ST-01 ✅ 3 BQ views; ST-02 ✅ 3 dashboards Looker Studio live (Retention/Revenue/KPI Gates, 2026-07-07); ST-03 ⬜ go/no-go 2026-09-14 | 2026-07-07 |
| [DATA-003](DATA-003-admob-reporting-api.md) | admob-reporting-api | Dataflow & Outputs | In Progress — ST-01 ✅ OAuth credentials SM; ST-02 ✅ Cloud Run job + Scheduler live (2026-07-09); ST-03 ⬜ verificar datos reales post soft-launch | 2026-07-09 |
| [PAY-002](PAY-002-daily-reconciliation-job.md) | daily-reconciliation-job | Payments | In Progress — ST-01 ✅ implementación completa (2026-07-09); ST-02 ✅ Cloud Scheduler live (2026-07-09); ST-03 ⬜ test e2e pending T-252 | 2026-07-09 |
| [T-400](T-400-region-aware-age-logic.md) | region-aware-age-logic | Compliance | In Progress — ST-01 ✅ backend code completo (2026-07-12); ST-02 ✅ GCS + MaxMind refresh pipeline live (2026-07-13); ST-03 ⬜ test e2e pending T-252 | 2026-07-13 |
| [T-406](T-406-iarc-content-rating.md) | iarc-content-rating | Compliance | In Progress — ST-01 ✅ IARC questionnaire completo, ratings guardados en Play Console (ESRB:E / PEGI:3 / ClassInd:14+ / USK:0, 2026-07-13); ST-02 ⬜ coppa_compliant flag activation pending T-400 ST-03 | 2026-07-13 |
