variable "cicd_project_id" {
  description = "GCP project hosting CI/CD Workload Identity Federation and Artifact Registry."
  type        = string
}

variable "deploy_project_ids" {
  description = "Map of environment name (staging/prod) to target GCP project ID."
  type        = map(string)
}

variable "region" {
  description = "Primary GCP deployment region."
  type        = string
  default     = "us-central1"
}

variable "project_name" {
  description = "Short application name."
  type        = string
  default     = "reddit-gta-ad-copilot"
}

variable "github_repository" {
  description = "GitHub repository in 'owner/repo' format allowed to impersonate the CI/CD service account."
  type        = string
}
