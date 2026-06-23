# Changelogs

| Ticket | Slug | Workstream | Status | Date |
|---|---|---|---|---|
| [INFRA-001](INFRA-001-gcp-base-infra.md) | gcp-base-infra | Infra/DevOps | ✅ Done | 2026-06-16 |
| [EXT-001](EXT-001-google-play-developer-api.md) | google-play-developer-api | External Services | In Progress — ST-01 ✅, ST-02 ✅, ST-03–06 🔴 bloqueados por verificación de cuenta Google (puede tardar días) | 2026-06-17 |
| [EXT-002](EXT-002-admob-account-ad-units.md) | admob-account-ad-units | External Services | ✅ Done | 2026-06-17 |
| [DATA-001](DATA-001-bigquery-analytics-tables.md) | bigquery-analytics-tables | Dataflow & Outputs | ✅ Done | 2026-06-16 |
| [INFRA-002](INFRA-002-env-secrets-design.md) | env-secrets-design | Infra/DevOps | ✅ Done | 2026-06-17 |
| [REST-001](REST-001-rest-api-contract.md) | rest-api-contract | Planning | ✅ Done — ST-01–08 ✅ (sign-off Juan commit 9216611, 2026-06-22) | 2026-06-22 |
| [INFRA-003](INFRA-003-fastapi-scaffold-cloud-run.md) | fastapi-scaffold-cloud-run | Infra/DevOps | In Progress — ST-01 ✅, ST-02 ✅ scaffold (2026-06-22), ST-03 ✅ /health+/ready, ST-04–06 ⬜ bloqueados billing motamaze-dev (Juan) | 2026-06-22 |
| [DATA-002](DATA-002-firestore-bigquery-streaming.md) | firestore-bigquery-streaming | Dataflow & Outputs | In Progress — ST-01 ✅ diseño, ST-02 ✅ endpoint mapping reconciliado (POST /events/behavior agregado a REST-001), ST-03–12 pendientes INFRA-003 | 2026-06-18 |
| [INFRA-004](INFRA-004-rs256-keypair-secret-manager.md) | rs256-keypair-secret-manager | Infra/DevOps | In Progress — ST-01 ✅ keypair generado, ST-02 ✅ `jwt-private-key` en Secret Manager prod, ST-03–05 pendientes INFRA-003 | 2026-06-19 |
| [INFRA-005](INFRA-005-firestore-schema-security-rules.md) | firestore-schema-security-rules | Infra/DevOps | In Progress — ST-01 ✅ schema 6 colecciones, ST-02 ✅ deny-all rules en prod, ST-03 ⬜ tests pendientes INFRA-003, ST-04 ✅ DATA_MODEL.md | 2026-06-19 |
| [INFRA-006](INFRA-006-dev-staging-prod-terraform.md) | dev-staging-prod-terraform | Infra/DevOps | In Progress — ST-01 ✅ proyectos GCP creados (billing dev pendiente Juan), ST-02 ✅ módulo Terraform, ST-03 ✅ remote state bucket, ST-04 ✅ apply prod completo (2026-06-22) — apply dev pendiente billing Juan. Staging diferido. | 2026-06-22 |
| [CI-001](CI-001-cicd-github-actions.md) | cicd-github-actions | Infra/DevOps | In Progress — ST-01 ✅, ST-02 ✅ AR+WIF+SA+Environments (Juan 2026-06-23), ST-03 ✅ Build+push AR (5 runs), ST-04 ⬜ bloqueado billing motamaze-dev (Juan), ST-05 ⬜ | 2026-06-23 |
