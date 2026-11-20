# Keyless Workload Identity Federation (WIF) for GitHub Actions CI/CD.

resource "google_service_account" "cicd_runner_sa" {
  account_id   = "${var.project_name}-cicd"
  display_name = "GitHub Actions CI/CD Runner SA for ${var.project_name}"
  project      = var.cicd_project_id
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.cicd_project_id
  workload_identity_pool_id = "${var.project_name}-gh-pool"
  display_name              = "GitHub Actions Pool (${var.project_name})"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.cicd_project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub Actions OIDC Provider"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }

  attribute_condition = "assertion.repository == '${var.github_repository}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_wif_binding" {
  service_account_id = google_service_account.cicd_runner_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

resource "google_project_iam_member" "cicd_run_deployer" {
  for_each = var.deploy_project_ids
  project  = each.value
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.cicd_runner_sa.email}"
}

resource "google_project_iam_member" "cicd_artifact_writer" {
  project = var.cicd_project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cicd_runner_sa.email}"
}

resource "google_project_iam_member" "cicd_sa_user" {
  for_each = var.deploy_project_ids
  project  = each.value
  role     = "roles/iam.serviceAccountUser"
  member   = "serviceAccount:${google_service_account.cicd_runner_sa.email}"
}
