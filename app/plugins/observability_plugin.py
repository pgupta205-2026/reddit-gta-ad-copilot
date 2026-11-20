"""ADK BasePlugin for structured intent-vs-outcome logging, OTel tracing & async memory.

Explicitly captures:
1. `agent_intent` / `tool_intent` BEFORE execution (intended target, model/agent,
   PII-redacted arguments, correlation `action_id`).
2. `agent_outcome` / `tool_outcome` AFTER execution (status, latency_ms,
   PII-redacted result summary or error details, matching `action_id`).
3. Non-blocking async background memory consolidation in `after_run_callback`.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from google.adk.plugins.base_plugin import BasePlugin

from app.memory.async_consolidator import AsyncMemoryConsolidator, MemoryConsolidationJob
from app.observability.logging import get_logger
from app.observability.tracing import get_tracer
from app.security.pii_redactor import PiiRedactor

_LOGGER = get_logger(__name__)


class ObservabilityIntentOutcomePlugin(BasePlugin):
    """Captures intent-vs-outcome structured JSON logs, OTel spans, and async memory."""

    def __init__(
        self,
        *,
        redactor: PiiRedactor | None = None,
        consolidator: AsyncMemoryConsolidator | None = None,
    ) -> None:
        super().__init__(name="observability_intent_outcome_plugin")
        self.redactor = redactor or PiiRedactor()
        self.consolidator = consolidator
        self._inflight_tools: dict[str, tuple[str, float]] = {}
        self._inflight_agents: dict[str, tuple[str, float]] = {}

    def _tool_tracking_key(self, tool_name: str, tool_context: Any) -> str:
        invocation_id = getattr(tool_context, "invocation_id", "local")
        return f"{invocation_id}:{tool_name}"

    async def before_agent_callback(
        self, *, agent: Any, callback_context: Any
    ) -> None:
        """Record agent execution intent before an agent begins reasoning."""
        agent_name = getattr(agent, "name", "unknown_agent")
        model_name = str(getattr(agent, "model", "workflow_orchestrator"))
        action_id = f"ag_{uuid.uuid4().hex[:10]}"
        self._inflight_agents[agent_name] = (action_id, time.perf_counter())

        _LOGGER.info(
            "agent_intent",
            action_id=action_id,
            agent_name=agent_name,
            model=model_name,
            session_id=getattr(callback_context, "session_id", None),
            intended_action=f"invoke_agent:{agent_name}",
        )
        return None

    async def after_agent_callback(
        self, *, agent: Any, callback_context: Any
    ) -> None:
        """Record agent execution outcome and latency after an agent finishes."""
        agent_name = getattr(agent, "name", "unknown_agent")
        action_id, start_ts = self._inflight_agents.pop(
            agent_name, (f"ag_{uuid.uuid4().hex[:10]}", time.perf_counter())
        )
        latency_ms = round((time.perf_counter() - start_ts) * 1000.0, 2)

        _LOGGER.info(
            "agent_outcome",
            action_id=action_id,
            agent_name=agent_name,
            status="completed",
            latency_ms=latency_ms,
            session_id=getattr(callback_context, "session_id", None),
        )
        return None

    async def before_tool_callback(
        self, *, tool: Any, tool_args: dict[str, Any], tool_context: Any
    ) -> None:
        """Record explicit tool execution intent BEFORE calling the tool."""
        tool_name = getattr(tool, "name", str(tool))
        action_id = f"tl_{uuid.uuid4().hex[:10]}"
        key = self._tool_tracking_key(tool_name, tool_context)
        self._inflight_tools[key] = (action_id, time.perf_counter())

        redacted_args = self.redactor.redact_value(tool_args)
        _LOGGER.info(
            "tool_intent",
            action_id=action_id,
            tool_name=tool_name,
            intended_args=redacted_args,
            agent_name=getattr(tool_context, "agent_name", "unknown"),
        )
        return None

    async def after_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],  # noqa: ARG002
        tool_context: Any,
        result: Any,
    ) -> None:
        """Record actual tool outcome, status, and duration AFTER tool completes."""
        tool_name = getattr(tool, "name", str(tool))
        key = self._tool_tracking_key(tool_name, tool_context)
        action_id, start_ts = self._inflight_tools.pop(
            key, (f"tl_{uuid.uuid4().hex[:10]}", time.perf_counter())
        )
        latency_ms = round((time.perf_counter() - start_ts) * 1000.0, 2)

        outcome_status = (
            str(result.get("status", "success"))
            if isinstance(result, dict)
            else "success"
        )
        error_code = (
            result.get("error_code") if isinstance(result, dict) else None
        )
        tracer = get_tracer()
        with tracer.start_as_current_span(f"copilot.audit.{tool_name}") as span:
            span.set_attribute("copilot.action_id", action_id)
            span.set_attribute("copilot.outcome_status", outcome_status)
            span.set_attribute("copilot.latency_ms", latency_ms)

        _LOGGER.info(
            "tool_outcome",
            action_id=action_id,
            tool_name=tool_name,
            status=outcome_status,
            error_code=error_code,
            latency_ms=latency_ms,
            agent_name=getattr(tool_context, "agent_name", "unknown"),
            redacted_outcome_preview=self.redactor.redact_text(str(result)[:300]),
        )
        return None

    async def on_tool_error_callback(  # type: ignore[override]
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],  # noqa: ARG002
        tool_context: Any,
        error: Exception,
    ) -> dict[str, Any] | None:
        """Record structured failure outcome if an unexpected tool exception occurs."""
        tool_name = getattr(tool, "name", str(tool))
        key = self._tool_tracking_key(tool_name, tool_context)
        action_id, start_ts = self._inflight_tools.pop(
            key, (f"tl_{uuid.uuid4().hex[:10]}", time.perf_counter())
        )
        latency_ms = round((time.perf_counter() - start_ts) * 1000.0, 2)
        _LOGGER.error(
            "tool_outcome",
            action_id=action_id,
            tool_name=tool_name,
            status="exception",
            latency_ms=latency_ms,
            error_type=type(error).__name__ if error is not None else "UnknownError",
            error_message=self.redactor.redact_text(str(error or "")),
        )
        return None

    async def after_run_callback(self, *, invocation_context: Any) -> None:
        """Trigger non-blocking async memory consolidation after an agent turn finishes."""
        if self.consolidator is None:
            return None

        session = getattr(invocation_context, "session", None)
        state = getattr(session, "state", {}) if session is not None else {}
        strategy_draft = state.get("strategy_draft")
        if not strategy_draft:
            return None

        session_id = str(getattr(session, "id", "unknown_session"))
        vertical = str(state.get("last_vertical", "multi_vertical"))
        opportunity_score = float(state.get("last_opportunity_score", 75.0))
        risk_tier = str(state.get("last_risk_tier", "medium"))

        self.consolidator.enqueue_non_blocking(
            MemoryConsolidationJob(
                session_id=session_id,
                vertical=vertical,
                raw_summary=str(strategy_draft),
                opportunity_score=opportunity_score,
                risk_tier=risk_tier,
            )
        )
        return None
