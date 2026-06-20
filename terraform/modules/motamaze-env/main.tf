# ────────────────────────────────────────────────────────────────────────────
# APIs
# ────────────────────────────────────────────────────────────────────────────

resource "google_project_service" "apis" {
  for_each = toset([
    "firestore.googleapis.com",
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "secretmanager.googleapis.com",
    "run.googleapis.com",
    "firebaserules.googleapis.com",
    "cloudtrace.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "pubsub.googleapis.com",
    "firebase.googleapis.com",
    "iamcredentials.googleapis.com",
  ])

  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

# ────────────────────────────────────────────────────────────────────────────
# Service Account
# ────────────────────────────────────────────────────────────────────────────

resource "google_service_account" "game_api_backend" {
  project      = var.project_id
  account_id   = "game-api-backend"
  display_name = "MotaMaze Game API Backend"
  description  = "Used by FastAPI on Cloud Run to access Firestore, BigQuery, and Secret Manager"

  depends_on = [google_project_service.apis]
}

# ────────────────────────────────────────────────────────────────────────────
# IAM role bindings for game-api-backend
# ────────────────────────────────────────────────────────────────────────────

locals {
  backend_roles = toset([
    "roles/datastore.user",
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/secretmanager.secretAccessor",
    "roles/storage.objectAdmin",
    "roles/cloudtrace.agent",
  ])
}

resource "google_project_iam_member" "game_api_backend_roles" {
  for_each = local.backend_roles

  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.game_api_backend.email}"
}

# ────────────────────────────────────────────────────────────────────────────
# Firestore (Native mode, nam5)
# ────────────────────────────────────────────────────────────────────────────

resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.firestore_location
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.apis]
}

# ────────────────────────────────────────────────────────────────────────────
# BigQuery — Dataset
# ────────────────────────────────────────────────────────────────────────────

resource "google_bigquery_dataset" "analytics" {
  project    = var.project_id
  dataset_id = "motamaze_analytics"
  location   = var.bq_location

  labels = {
    environment = var.environment
  }

  depends_on = [google_project_service.apis]
}

# ────────────────────────────────────────────────────────────────────────────
# BigQuery — Tables (DATA-001)
# ────────────────────────────────────────────────────────────────────────────

resource "google_bigquery_table" "login_events" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = "login_events"

  time_partitioning { type = "DAY"; field = "event_date" }
  clustering      = ["user_id"]
  deletion_protection = false

  schema = jsonencode([
    { name = "event_timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "event_date",      type = "DATE",      mode = "REQUIRED" },
    { name = "user_id",         type = "STRING",    mode = "REQUIRED" },
    { name = "session_id",      type = "STRING",    mode = "REQUIRED" },
    { name = "platform",        type = "STRING",    mode = "NULLABLE" },
    { name = "app_version",     type = "STRING",    mode = "NULLABLE" },
    { name = "country",         type = "STRING",    mode = "NULLABLE" },
    { name = "login_method",    type = "STRING",    mode = "NULLABLE" },
    { name = "is_new_user",     type = "BOOL",      mode = "NULLABLE" },
    { name = "age_verified",    type = "BOOL",      mode = "NULLABLE" },
    { name = "device_model",    type = "STRING",    mode = "NULLABLE" },
    { name = "os_version",      type = "STRING",    mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "session_durations" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = "session_durations"

  time_partitioning { type = "DAY"; field = "event_date" }
  clustering      = ["user_id"]
  deletion_protection = false

  schema = jsonencode([
    { name = "event_timestamp",       type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "event_date",            type = "DATE",      mode = "REQUIRED" },
    { name = "user_id",               type = "STRING",    mode = "REQUIRED" },
    { name = "session_id",            type = "STRING",    mode = "REQUIRED" },
    { name = "event_type",            type = "STRING",    mode = "REQUIRED" },
    { name = "platform",              type = "STRING",    mode = "NULLABLE" },
    { name = "app_version",           type = "STRING",    mode = "NULLABLE" },
    { name = "country",               type = "STRING",    mode = "NULLABLE" },
    { name = "session_duration_secs", type = "INT64",     mode = "NULLABLE" },
    { name = "levels_played",         type = "INT64",     mode = "NULLABLE" },
    { name = "ads_shown",             type = "INT64",     mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "player_behavior" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = "player_behavior"

  time_partitioning { type = "DAY"; field = "event_date" }
  clustering      = ["user_id", "event_name"]
  deletion_protection = false

  schema = jsonencode([
    { name = "event_timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "event_date",      type = "DATE",      mode = "REQUIRED" },
    { name = "user_id",         type = "STRING",    mode = "REQUIRED" },
    { name = "session_id",      type = "STRING",    mode = "NULLABLE" },
    { name = "event_name",      type = "STRING",    mode = "REQUIRED" },
    { name = "platform",        type = "STRING",    mode = "NULLABLE" },
    { name = "app_version",     type = "STRING",    mode = "NULLABLE" },
    { name = "country",         type = "STRING",    mode = "NULLABLE" },
    { name = "level_id",        type = "INT64",     mode = "NULLABLE" },
    { name = "score",           type = "INT64",     mode = "NULLABLE" },
    { name = "stars_earned",    type = "INT64",     mode = "NULLABLE" },
    { name = "duration_secs",   type = "INT64",     mode = "NULLABLE" },
    { name = "npc_type",        type = "STRING",    mode = "NULLABLE" },
    { name = "extra_json",      type = "STRING",    mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "purchase_events" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = "purchase_events"

  time_partitioning { type = "DAY"; field = "event_date" }
  clustering      = ["user_id"]
  deletion_protection = false

  schema = jsonencode([
    { name = "event_timestamp",     type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "event_date",          type = "DATE",      mode = "REQUIRED" },
    { name = "user_id",             type = "STRING",    mode = "REQUIRED" },
    { name = "session_id",          type = "STRING",    mode = "NULLABLE" },
    { name = "platform",            type = "STRING",    mode = "NULLABLE" },
    { name = "app_version",         type = "STRING",    mode = "NULLABLE" },
    { name = "country",             type = "STRING",    mode = "NULLABLE" },
    { name = "product_id",          type = "STRING",    mode = "REQUIRED" },
    { name = "product_type",        type = "STRING",    mode = "NULLABLE" },
    { name = "purchase_token",      type = "STRING",    mode = "NULLABLE" },
    { name = "order_id",            type = "STRING",    mode = "NULLABLE" },
    { name = "price_usd",           type = "FLOAT64",   mode = "NULLABLE" },
    { name = "currency_code",       type = "STRING",    mode = "NULLABLE" },
    { name = "verification_status", type = "STRING",    mode = "NULLABLE" },
    { name = "grant_status",        type = "STRING",    mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "ad_impressions" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = "ad_impressions"

  time_partitioning { type = "DAY"; field = "event_date" }
  clustering      = ["user_id"]
  deletion_protection = false

  schema = jsonencode([
    { name = "event_timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "event_date",      type = "DATE",      mode = "REQUIRED" },
    { name = "user_id",         type = "STRING",    mode = "REQUIRED" },
    { name = "session_id",      type = "STRING",    mode = "NULLABLE" },
    { name = "platform",        type = "STRING",    mode = "NULLABLE" },
    { name = "app_version",     type = "STRING",    mode = "NULLABLE" },
    { name = "country",         type = "STRING",    mode = "NULLABLE" },
    { name = "ad_unit_id",      type = "STRING",    mode = "NULLABLE" },
    { name = "ad_type",         type = "STRING",    mode = "NULLABLE" },
    { name = "event_type",      type = "STRING",    mode = "NULLABLE" },
    { name = "revenue_usd",     type = "FLOAT64",   mode = "NULLABLE" },
    { name = "ad_network",      type = "STRING",    mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "entitlement_grants" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = "entitlement_grants"

  time_partitioning { type = "DAY"; field = "event_date" }
  clustering      = ["user_id"]
  deletion_protection = false

  schema = jsonencode([
    { name = "event_timestamp",  type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "event_date",       type = "DATE",      mode = "REQUIRED" },
    { name = "user_id",          type = "STRING",    mode = "REQUIRED" },
    { name = "session_id",       type = "STRING",    mode = "NULLABLE" },
    { name = "platform",         type = "STRING",    mode = "NULLABLE" },
    { name = "app_version",      type = "STRING",    mode = "NULLABLE" },
    { name = "country",          type = "STRING",    mode = "NULLABLE" },
    { name = "entitlement_type", type = "STRING",    mode = "REQUIRED" },
    { name = "entitlement_id",   type = "STRING",    mode = "NULLABLE" },
    { name = "source",           type = "STRING",    mode = "NULLABLE" },
    { name = "granted_by",       type = "STRING",    mode = "NULLABLE" },
    { name = "quantity",         type = "INT64",     mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "account_deletions" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = "account_deletions"

  time_partitioning { type = "DAY"; field = "request_date" }
  clustering      = ["user_id"]
  deletion_protection = false

  schema = jsonencode([
    { name = "requested_at",   type = "TIMESTAMP",     mode = "REQUIRED" },
    { name = "request_date",   type = "DATE",          mode = "REQUIRED" },
    { name = "user_id",        type = "STRING",        mode = "REQUIRED" },
    { name = "platform",       type = "STRING",        mode = "NULLABLE" },
    { name = "request_source", type = "STRING",        mode = "NULLABLE" },
    { name = "status",         type = "STRING",        mode = "NULLABLE" },
    { name = "completed_at",   type = "TIMESTAMP",     mode = "NULLABLE" },
    { name = "tables_purged",  type = "STRING",        mode = "REPEATED" },
    { name = "notes",          type = "STRING",        mode = "NULLABLE" },
  ])
}

resource "google_bigquery_table" "admob_daily_report" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = "admob_daily_report"

  time_partitioning { type = "DAY"; field = "report_date" }
  clustering      = ["ad_unit_id", "country"]
  deletion_protection = false

  schema = jsonencode([
    { name = "report_date",               type = "DATE",    mode = "REQUIRED" },
    { name = "ad_unit_id",                type = "STRING",  mode = "REQUIRED" },
    { name = "ad_format",                 type = "STRING",  mode = "NULLABLE" },
    { name = "country",                   type = "STRING",  mode = "REQUIRED" },
    { name = "estimated_earnings_micros", type = "INTEGER", mode = "NULLABLE" },
    { name = "impressions",               type = "INTEGER", mode = "NULLABLE" },
    { name = "clicks",                    type = "INTEGER", mode = "NULLABLE" },
    { name = "impression_rpm",            type = "FLOAT",   mode = "NULLABLE" },
    { name = "fill_rate",                 type = "FLOAT",   mode = "NULLABLE" },
  ])
}

# ────────────────────────────────────────────────────────────────────────────
# Cloud Storage
# ────────────────────────────────────────────────────────────────────────────

resource "google_storage_bucket" "main" {
  project                     = var.project_id
  name                        = "motamaze-${var.environment}-storage"
  location                    = "US"
  uniform_bucket_level_access = true

  versioning { enabled = true }

  depends_on = [google_project_service.apis]
}

# ────────────────────────────────────────────────────────────────────────────
# Secret Manager — secret placeholders (values filled manually per env)
# ────────────────────────────────────────────────────────────────────────────

locals {
  secrets = toset([
    "jwt-private-key",
    "google-oauth-client-id",
    "google-oauth-client-secret",
    "play-package-name",
    "admob-ssv-hmac-key",
  ])
}

resource "google_secret_manager_secret" "secrets" {
  for_each = local.secrets

  project   = var.project_id
  secret_id = each.key

  replication { auto {} }

  depends_on = [google_project_service.apis]
}

# ────────────────────────────────────────────────────────────────────────────
# Cloud Run — skipped if cloud_run_image is empty (pre-INFRA-003)
# ────────────────────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "api" {
  count = var.cloud_run_image != "" ? 1 : 0

  project  = var.project_id
  name     = "motamaze-backend"
  location = var.region

  template {
    service_account = google_service_account.game_api_backend.email

    scaling { max_instance_count = var.environment == "prod" ? 10 : 3 }

    containers {
      image = var.cloud_run_image

      resources { limits = { cpu = "1", memory = "512Mi" } }

      dynamic "env" {
        for_each = {
          GCP_PROJECT_ID = var.project_id
          ENVIRONMENT    = var.environment
          BQ_DATASET     = "motamaze_analytics"
          LOG_LEVEL      = var.environment == "prod" ? "info" : "debug"
          JWT_ISSUER     = "https://api.motamaze.com"
          JWKS_URL       = "https://api.motamaze.com/.well-known/jwks.json"
        }
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = toset(["jwt-private-key", "google-oauth-client-id", "google-oauth-client-secret"])
        content {
          name = upper(replace(env.value, "-", "_"))
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [
    google_project_iam_member.game_api_backend_roles,
    google_secret_manager_secret.secrets,
  ]
}
