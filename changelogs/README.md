# Changelogs

| Ticket | Slug | Workstream | Status | Date |
|---|---|---|---|---|
| [INFRA-001](INFRA-001-gcp-base-infra.md) | gcp-base-infra | Infra/DevOps | ✅ Done | 2026-06-16 |
| [EXT-001](EXT-001-google-play-developer-api.md) | google-play-developer-api | External Services | In Progress — ST-01–05 ✅, ST-06 🔴 Stuck — permisos SA perdidos post-publish; Juan re-aplica en Play Console → retry 2026-07-02 | 2026-07-01 |
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
| [INFRA-006](INFRA-006-dev-staging-prod-terraform.md) | dev-staging-prod-terraform | Infra/DevOps | In Progress — ST-01 ✅ proyectos GCP creados (billing dev pendiente Juan), ST-02 ✅ módulo Terraform, ST-03 ✅ remote state bucket, ST-04 ✅ apply prod completo (2026-06-22) — apply dev pendiente billing Juan. Staging diferido. | 2026-06-22 |
| [CI-001](CI-001-cicd-github-actions.md) | cicd-github-actions | Infra/DevOps | ✅ Done — pipeline verde end-to-end run #19, dev + prod (2026-06-24) | 2026-06-24 |
