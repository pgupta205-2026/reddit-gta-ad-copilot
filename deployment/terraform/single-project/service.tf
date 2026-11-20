resource "google_sql_database_instance" "sessions" {
  name                = "${var.project_name}-sessions-pg"
  project             = var.project_id
  region              = var.region
  database_version    = "POSTGRES_15"
  deletion_protection = false

  settings {
    tier = var.cloud_sql_tier

    backup_configuration {
      enabled = true
    }

    ip_configuration {
      ipv4_enabled = true
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_sql_database" "adk_sessions" {
  name     = "adk_sessions"
  instance = google_sql_database_instance.sessions.name
  project  = var.project_id
}

resource "google_cloud_run_v2_service" "app" {
  name     = var.project_name
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account                  = google_service_account.app_sa.email
    max_instance_request_concurrency = 40
    session_affinity                 = true

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.sessions.connection_name]
      }
    }

    containers {
      image = var.container_image

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        cpu_idle = true
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "True"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "COPILOT_FAST_MODEL"
        value = "gemini-2.5-flash"
      }
      env {
        name  = "COPILOT_REASONING_MODEL"
        value = "gemini-2.5-pro"
      }
      env {
        name  = "ENABLE_CLOUD_DLP"
        value = tostring(var.enable_cloud_dlp)
      }
      env {
        name  = "MODEL_ARMOR_TEMPLATE"
        value = var.model_armor_template
      }
      env {
        name  = "OTEL_SDK_DISABLED"
        value = "false"
      }
      env {
        name  = "OTEL_TRACES_EXPORTER"
        value = "google_cloud_trace"
      }
      env {
        name  = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
        value = "NO_CONTENT"
      }
      env {
        name  = "LOGS_BUCKET_NAME"
        value = google_storage_bucket.telemetry_logs.name
      }
      env {
        name  = "BQ_ANALYTICS_DATASET_ID"
        value = google_bigquery_dataset.telemetry.dataset_id
      }
      env {
        name  = "CLOUD_SQL_CONNECTION_NAME"
        value = google_sql_database_instance.sessions.connection_name
      }
      env {
        name = "REDDIT_CLIENT_ID"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.copilot_secrets["reddit-client-id"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "REDDIT_CLIENT_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.copilot_secrets["reddit-client-secret"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "ALERT_WEBHOOK_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.copilot_secrets["alert-webhook-url"].secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/healthz"
        }
        initial_delay_seconds = 5
        period_seconds        = 10
        failure_threshold     = 6
      }
    }
  }

  depends_on = [
    google_project_iam_member.app_sa_bindings,
    google_secret_manager_secret_iam_member.app_sa_accessor,
  ]
}
