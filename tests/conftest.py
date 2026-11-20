"""Shared pytest fixtures for isolated offline unit and integration tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.config import CopilotConfig
from app.memory.store import CampaignMemoryStore
from app.security.pii_redactor import PiiRedactor
from app.tools.copilot_tools import CopilotToolkit


@dataclass
class FakeToolConfirmation:
    """Minimal stand-in for ADK ToolConfirmation in deterministic tests."""

    confirmed: bool
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeToolContext:
    """Minimal stand-in for ADK ToolContext tracking HITL confirmation requests."""

    agent_name: str = "campaign_strategist"
    invocation_id: str = "inv_test_001"
    tool_confirmation: FakeToolConfirmation | None = None
    requested_confirmations: list[dict[str, Any]] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)

    def request_confirmation(
        self, *, hint: str, payload: dict[str, Any] | None = None
    ) -> None:
        self.requested_confirmations.append({"hint": hint, "payload": payload or {}})


@pytest.fixture()
def isolated_toolkit(tmp_path) -> CopilotToolkit:
    """Return a CopilotToolkit backed by a temp SQLite DB and offline GTA VI fixtures."""
    cfg = CopilotConfig(
        campaign_memory_db_path=str(tmp_path / "campaign_memory.db"),
        session_db_url=f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}",
        reddit_data_mode="fixture",
        enable_cloud_dlp=False,
        otel_sdk_disabled=True,
    )
    redactor = PiiRedactor(enable_cloud_dlp=False)
    store = CampaignMemoryStore(db_path=cfg.campaign_memory_db_path, redactor=redactor)
    toolkit = CopilotToolkit.from_config(cfg, memory_store=store)
    yield toolkit
    store.close()
