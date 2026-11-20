resource "google_service_account" "app_sa" {
  account_id   = "${var.project_name}-sa"
  display_name = "Runtime Service Account for ${var.project_name}"
  project      = var.project_id

  depends_on = [google_project_service.required]
}

locals {
  app_sa_roles = toset([
    "roles/aiplatform.user",
    "roles/bigquery.dataEditor",
    "roles/cloudsql.client",
    "roles/cloudtrace.agent",
    "roles/dlp.user",
    "roles/logging.logWriter",
    "roles/modelarmor.user",
    "roles/pubsub.publisher",
    "roles/secretmanager.secretAccessor",
    "roles/storage.objectCreator",
  ])
}

resource "google_project_iam_member" "app_sa_bindings" {
  for_each = local.app_sa_roles
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.app_sa.email}"
}
