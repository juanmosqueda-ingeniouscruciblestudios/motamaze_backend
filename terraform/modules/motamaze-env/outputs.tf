output "backend_sa_email" {
  description = "Email of the game-api-backend service account"
  value       = google_service_account.game_api_backend.email
}

output "bq_dataset_id" {
  description = "BigQuery analytics dataset ID"
  value       = google_bigquery_dataset.analytics.dataset_id
}

output "storage_bucket_name" {
  description = "Cloud Storage bucket name"
  value       = google_storage_bucket.main.name
}

output "cloud_run_url" {
  description = "Cloud Run service URL (empty if not deployed yet)"
  value       = length(google_cloud_run_v2_service.api) > 0 ? google_cloud_run_v2_service.api[0].uri : ""
}
