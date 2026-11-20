"""Cloud Run FastAPI server entrypoint with Cloud Trace, persistent sessions & Pub/Sub triggers.

Uses ADK's `get_fast_api_app` to expose interactive `/run` & `/run_sse` endpoints
plus `/apps/app/trigger/pubsub` for hourly Cloud Scheduler brand-safety scans.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

from app.config import CopilotConfig
from app.observability.logging import configure_logging, get_logger

_CONFIG = CopilotConfig.from_env()
configure_logging(level=_CONFIG.log_level)
_LOGGER = get_logger(__name__)

_AGENTS_DIR = str(Path(__file__).resolve().parent.parent)

app: FastAPI = get_fast_api_app(
    agents_dir=_AGENTS_DIR,
    session_service_uri=_CONFIG.session_db_url,
    web=False,
    otel_to_cloud=True,
    trigger_sources=["pubsub", "eventarc"],
)


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    """Liveness/startup probe endpoint for Cloud Run."""
    return {
        "status": "ok",
        "service": _CONFIG.service_name,
        "model_routing": _CONFIG.model_router.routing_table(),
        "reddit_data_mode": _CONFIG.reddit_data_mode,
    }


_LOGGER.info(
    "fastapi_server_configured",
    agents_dir=_AGENTS_DIR,
    otel_to_cloud=True,
    trigger_sources=["pubsub", "eventarc"],
)
