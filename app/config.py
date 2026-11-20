"""Runtime configuration and strategic Gemini model routing.

Centralizes environment settings, Secret Manager identifiers, persistence URIs,
and explicit task-complexity model routing (Flash for high-volume extraction,
safety auditing, self-evaluation, and compaction; Pro for executive planning
and multi-agent synthesis).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

from app.security.secrets import SecretManagerProvider


class TaskTier(str, Enum):
    """Cognitive complexity tiers governing strategic model routing."""

    FAST_EXTRACTION = "fast_extraction"
    SAFETY_EVALUATION = "safety_evaluation"
    HISTORY_COMPACTION = "history_compaction"
    STRATEGIC_PLANNING = "strategic_planning"
    COORDINATOR_ROUTING = "coordinator_routing"


@dataclass(frozen=True)
class ModelRouter:
    """Routes agent workloads to the optimal Gemini model tier.

    Fast/cost-efficient models handle parallel subreddit scanning, brand-safety
    classification, self-evaluation, and compaction summarization. Reasoning
    models handle executive account synthesis, cross-vertical tradeoffs, and
    high-stakes campaign pause planning.
    """

    fast_model: str = "gemini-2.5-flash"
    reasoning_model: str = "gemini-2.5-pro"

    def select_model(self, tier: TaskTier) -> str:
        """Return the Gemini model name assigned to a cognitive task tier."""
        if tier in {
            TaskTier.FAST_EXTRACTION,
            TaskTier.SAFETY_EVALUATION,
            TaskTier.HISTORY_COMPACTION,
        }:
            return self.fast_model
        return self.reasoning_model

    def routing_table(self) -> dict[str, str]:
        """Expose the complete tier-to-model mapping for observability & audits."""
        return {tier.value: self.select_model(tier) for tier in TaskTier}


@dataclass
class CopilotConfig:
    """Typed runtime configuration loaded from environment and Secret Manager."""

    app_name: str = "app"
    service_name: str = "reddit-gta-ad-copilot"
    gcp_project_id: str | None = None
    gcp_location: str = "us-central1"
    use_vertex_ai: bool = False

    model_router: ModelRouter = field(default_factory=ModelRouter)

    # Context compaction & caching
    compaction_interval: int = 6
    compaction_overlap_size: int = 2
    compaction_token_threshold: int = 4000
    context_cache_min_tokens: int = 2048
    context_cache_ttl_seconds: int = 1800

    # Persistence & memory
    session_db_url: str = "sqlite+aiosqlite:///./data/adk_sessions.db"
    campaign_memory_db_path: str = "./data/campaign_memory.db"
    vertex_memory_bank_engine_id: str | None = None
    vertex_ai_search_datastore_id: str | None = None

    # Reddit data ingestion
    reddit_data_mode: str = "fixture"
    reddit_user_agent: str = "reddit-gta-ad-copilot/0.1.0"
    secret_name_reddit_client_id: str = "reddit-client-id"
    secret_name_reddit_client_secret: str = "reddit-client-secret"
    secret_name_alert_webhook_url: str = "alert-webhook-url"

    # Security & observability
    enable_cloud_dlp: bool = False
    model_armor_template: str | None = None
    log_level: str = "INFO"
    otel_traces_exporter: str = "console"
    otel_sdk_disabled: bool = False
    logs_bucket_name: str | None = None

    @classmethod
    def from_env(cls) -> CopilotConfig:
        """Build configuration from environment variables with safe defaults."""
        fast_model = os.environ.get("COPILOT_FAST_MODEL", "gemini-2.5-flash")
        reasoning_model = os.environ.get("COPILOT_REASONING_MODEL", "gemini-2.5-pro")
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or None
        if project_id == "your-gcp-project-id":
            project_id = None

        cloud_sql_conn = os.environ.get("CLOUD_SQL_CONNECTION_NAME") or ""
        default_session_url = (
            f"postgresql+psycopg://postgres@/adk_sessions?host=/cloudsql/{cloud_sql_conn}"
            if cloud_sql_conn
            else "sqlite+aiosqlite:///./data/adk_sessions.db"
        )

        return cls(
            gcp_project_id=project_id,
            gcp_location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
            use_vertex_ai=os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "False").lower()
            in {"1", "true", "yes"},
            model_router=ModelRouter(
                fast_model=fast_model,
                reasoning_model=reasoning_model,
            ),
            session_db_url=os.environ.get("SESSION_DB_URL", default_session_url),
            campaign_memory_db_path=os.environ.get(
                "CAMPAIGN_MEMORY_DB_PATH", "./data/campaign_memory.db"
            ),
            vertex_memory_bank_engine_id=os.environ.get(
                "VERTEX_AI_MEMORY_BANK_AGENT_ENGINE_ID"
            )
            or None,
            vertex_ai_search_datastore_id=os.environ.get(
                "VERTEX_AI_SEARCH_DATASTORE_ID"
            )
            or None,
            reddit_data_mode=os.environ.get("REDDIT_DATA_MODE", "fixture").lower(),
            reddit_user_agent=os.environ.get(
                "REDDIT_USER_AGENT", "reddit-gta-ad-copilot/0.1.0"
            ),
            secret_name_reddit_client_id=os.environ.get(
                "SECRET_NAME_REDDIT_CLIENT_ID", "reddit-client-id"
            ),
            secret_name_reddit_client_secret=os.environ.get(
                "SECRET_NAME_REDDIT_CLIENT_SECRET", "reddit-client-secret"
            ),
            secret_name_alert_webhook_url=os.environ.get(
                "SECRET_NAME_ALERT_WEBHOOK_URL", "alert-webhook-url"
            ),
            enable_cloud_dlp=os.environ.get("ENABLE_CLOUD_DLP", "false").lower()
            in {"1", "true", "yes"},
            model_armor_template=os.environ.get("MODEL_ARMOR_TEMPLATE") or None,
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            otel_traces_exporter=os.environ.get("OTEL_TRACES_EXPORTER", "console"),
            otel_sdk_disabled=os.environ.get("OTEL_SDK_DISABLED", "false").lower()
            in {"1", "true", "yes"},
            logs_bucket_name=os.environ.get("LOGS_BUCKET_NAME") or None,
        )

    def build_secret_provider(self) -> SecretManagerProvider:
        """Instantiate a SecretManagerProvider bound to this config."""
        return SecretManagerProvider(
            project_id=self.gcp_project_id,
            prefer_secret_manager=bool(self.gcp_project_id),
        )
