locals {
  telemetry_dataset_id = "${replace(var.project_name, "-", "_")}_telemetry"
}

resource "google_storage_bucket" "telemetry_logs" {
  name                        = "${var.project_id}-${var.project_name}-logs"
  location                    = var.region
  project                     = var.project_id
  uniform_bucket_level_access = true
  force_destroy               = false

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_bigquery_dataset" "telemetry" {
  dataset_id  = local.telemetry_dataset_id
  project     = var.project_id
  location    = var.region
  description = "Structured AgentOps observability, intent/outcome logs, and GenAI telemetry for ${var.project_name}."

  depends_on = [google_project_service.required]
}

resource "google_logging_project_sink" "agent_telemetry_sink" {
  name                   = "${var.project_name}-bq-telemetry-sink"
  project                = var.project_id
  destination            = "bigquery.googleapis.com/projects/${var.project_id}/datasets/${google_bigquery_dataset.telemetry.dataset_id}"
  unique_writer_identity = true

  filter = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="${var.project_name}"
    (jsonPayload.event="tool_intent" OR jsonPayload.event="tool_outcome" OR jsonPayload.event="agent_intent" OR jsonPayload.event="agent_outcome" OR jsonPayload.event="self_eval_verdict")
  EOT

  bigquery_options {
    use_partitioned_tables = true
  }
}

resource "google_bigquery_dataset_iam_member" "log_sink_writer" {
  dataset_id = google_bigquery_dataset.telemetry.dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = google_logging_project_sink.agent_telemetry_sink.writer_identity
}
