# Ambient hourly GTA VI launch-week brand-safety monitoring via Pub/Sub + Cloud Scheduler.

resource "google_pubsub_topic" "gta6_monitor_ticks" {
  name    = "${var.project_name}-monitor-ticks"
  project = var.project_id

  depends_on = [google_project_service.required]
}

resource "google_pubsub_subscription" "gta6_monitor_push" {
  name    = "${var.project_name}-monitor-push"
  topic   = google_pubsub_topic.gta6_monitor_ticks.id
  project = var.project_id

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.app.uri}/apps/app/trigger/pubsub"

    oidc_token {
      service_account_email = google_service_account.app_sa.email
    }
  }

  ack_deadline_seconds = 60
}

resource "google_cloud_run_v2_service_iam_member" "pubsub_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.app_sa.email}"
}

resource "google_cloud_scheduler_job" "hourly_gta6_pulse" {
  name        = "${var.project_name}-hourly-pulse"
  description = "Triggers hourly GTA VI advertiser opportunity and brand-safety pulse scan."
  schedule    = var.monitoring_schedule
  time_zone   = "UTC"
  region      = var.region
  project     = var.project_id

  pubsub_target {
    topic_name = google_pubsub_topic.gta6_monitor_ticks.id
    data = base64encode(jsonencode({
      prompt = "Run hourly GTA VI advertiser opportunity and GARM brand-safety scan across r/GTA6, r/PS5, r/xbox, and r/OLED_Gaming."
    }))
  }

  depends_on = [google_project_service.required]
}
