output "cicd_service_account_email" {
  description = "Service account impersonated by GitHub Actions via WIF."
  value       = google_service_account.cicd_runner_sa.email
}

output "workload_identity_provider" {
  description = "Full resource name of the GitHub OIDC Workload Identity Provider."
  value       = google_iam_workload_identity_pool_provider.github.name
}
