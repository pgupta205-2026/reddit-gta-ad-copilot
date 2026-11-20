output "cloud_run_service_url" {
  description = "Deployed Cloud Run service URL."
  value       = google_cloud_run_v2_service.app.uri
}

output "runtime_service_account" {
  description = "Least-privilege runtime service account email."
  value       = google_service_account.app_sa.email
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL Postgres 15 instance connection name for ADK DatabaseSessionService."
  value       = google_sql_database_instance.sessions.connection_name
}

output "telemetry_bigquery_dataset" {
  description = "BigQuery dataset receiving structured intent/outcome telemetry."
  value       = google_bigquery_dataset.telemetry.dataset_id
}

output "telemetry_logs_bucket" {
  description = "GCS bucket storing GenAI telemetry logs."
  value       = google_storage_bucket.telemetry_logs.name
}

output "managed_secret_ids" {
  description = "Secret Manager secret IDs managed by Terraform."
  value       = [for s in google_secret_manager_secret.copilot_secrets : s.secret_id]
}
