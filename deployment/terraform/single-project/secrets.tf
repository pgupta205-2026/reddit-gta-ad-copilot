# Secret Manager shells only. Populate secret versions out-of-band via:
#   echo -n "<VALUE>" | gcloud secrets versions add <SECRET_ID> --data-file=-
# Never commit secret payloads or API keys into Terraform state or Git.

locals {
  managed_secrets = toset([
    "reddit-client-id",
    "reddit-client-secret",
    "alert-webhook-url",
    "session-db-password",
  ])
}

resource "google_secret_manager_secret" "copilot_secrets" {
  for_each  = local.managed_secrets
  project   = var.project_id
  secret_id = each.value

  replication {
    auto {}
  }

  labels = {
    app        = var.project_name
    managed_by = "terraform"
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "app_sa_accessor" {
  for_each  = google_secret_manager_secret.copilot_secrets
  project   = var.project_id
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app_sa.email}"
}
