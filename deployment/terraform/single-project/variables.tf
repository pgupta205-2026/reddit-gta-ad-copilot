variable "project_id" {
  description = "Target Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "Primary GCP region for Cloud Run, Cloud SQL, and telemetry resources."
  type        = string
  default     = "us-central1"
}

variable "project_name" {
  description = "Short application name matching [tool.agents-cli] name (<= 26 chars)."
  type        = string
  default     = "reddit-gta-ad-copilot"
}

variable "container_image" {
  description = "Container image URI in Artifact Registry deployed to Cloud Run."
  type        = string
  default     = "us-central1-docker.pkg.dev/example-project/reddit-gta-ad-copilot/app:latest"
}

variable "cloud_sql_tier" {
  description = "Machine tier for Cloud SQL Postgres 15 session store."
  type        = string
  default     = "db-f1-micro"
}

variable "enable_cloud_dlp" {
  description = "Enable Google Cloud Sensitive Data Protection (DLP) API for PII redaction."
  type        = bool
  default     = true
}

variable "model_armor_template" {
  description = "Optional Google Cloud Model Armor template resource path."
  type        = string
  default     = ""
}

variable "monitoring_schedule" {
  description = "Cloud Scheduler cron schedule for ambient GTA VI launch monitoring."
  type        = string
  default     = "0 * * * *"
}
