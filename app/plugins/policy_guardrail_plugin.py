"""ADK BasePlugin enforcing security guardrails, Model Armor, and PII hygiene.

Intercepts LLM requests (`before_model_callback`), tool calls
(`before_tool_callback`), and LLM responses (`after_model_callback`) globally
across all agents in the `App`:
- Blocks prompt-injection and data-exfiltration patterns before LLM execution.
- Optionally screens prompts via Google Cloud Model Armor when configured.
- Enforces subreddit/vertical policy constraints on tool arguments.
- Redacts any residual PII before responses reach the user.
"""

from __future__ import annotations

import importlib
import re
from typing import Any

from google.adk.plugins.base_plugin import BasePlugin
from google.genai import types as genai_types

from app.observability.logging import get_logger
from app.observability.tracing import traced_span
from app.security.pii_redactor import PiiRedactor

_LOGGER = get_logger(__name__)

_PROMPT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(?:your\s+)?(?:system\s+prompt|secrets?|api\s+keys?)", re.IGNORECASE),
    re.compile(r"bypass\s+(?:human\s+confirmation|hitl|guardrails?|safety)", re.IGNORECASE),
    re.compile(r"dump\s+(?:raw\s+)?(?:user\s+)?(?:emails?|pii|passwords?|tokens?)", re.IGNORECASE),
)

_DISALLOWED_TOOL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:^|/)(?:admin|modmail|private_messages)(?:$|/)", re.IGNORECASE),
    re.compile(r"(?:drop\s+table|;\s*delete\s+from)", re.IGNORECASE),
)


class PolicyGuardrailPlugin(BasePlugin):
    """Global ADK security, policy, Model Armor, and output-redaction plugin."""

    def __init__(
        self,
        *,
        redactor: PiiRedactor | None = None,
        model_armor_template: str | None = None,
        model_armor_client: Any | None = None,
    ) -> None:
        super().__init__(name="policy_guardrail_plugin")
        self.redactor = redactor or PiiRedactor()
        self.model_armor_template = model_armor_template
        self._model_armor_client = model_armor_client

    def _extract_request_text(self, llm_request: Any) -> str:
        contents = getattr(llm_request, "contents", None) or []
        parts_text: list[str] = []
        for content in contents:
            for part in getattr(content, "parts", None) or []:
                text = getattr(part, "text", None)
                if text:
                    parts_text.append(str(text))
        return "\n".join(parts_text)

    def _screen_with_model_armor(self, text: str) -> str | None:
        """Screen prompt via Google Cloud Model Armor when a template is configured.

        Returns a human-readable violation reason if Model Armor flags the input,
        or None if safe / not configured.
        """
        if not self.model_armor_template:
            return None

        client = self._model_armor_client
        if client is None:
            try:
                modelarmor_v1 = importlib.import_module("google.cloud.modelarmor_v1")

                client = modelarmor_v1.ModelArmorClient()
                self._model_armor_client = client
            except Exception:
                return None

        try:
            response = client.sanitize_user_prompt(
                request={
                    "name": self.model_armor_template,
                    "user_prompt_data": {"text": text},
                }
            )
            result = getattr(response, "sanitization_result", None)
            match_state = str(getattr(result, "filter_match_state", ""))
            if "MATCH_FOUND" in match_state.upper():
                return f"Blocked by Google Cloud Model Armor ({match_state})."
        except Exception as exc:
            _LOGGER.warning("model_armor_screening_error", error=str(exc))
        return None

    def check_prompt_policy(self, text: str) -> str | None:
        """Return a violation reason if prompt violates safety/injection policy."""
        for pattern in _PROMPT_INJECTION_PATTERNS:
            if pattern.search(text):
                return (
                    "Request blocked by PolicyGuardrailPlugin: detected prompt-injection "
                    "or unauthorized PII/secret extraction attempt."
                )
        return self._screen_with_model_armor(text)

    async def before_model_callback(
        self, *, callback_context: Any, llm_request: Any
    ) -> Any:
        """Block prompt injection and Model Armor violations prior to LLM call."""
        from google.adk.models.llm_response import LlmResponse

        with traced_span("copilot.guardrail.before_model"):
            request_text = self._extract_request_text(llm_request)
            violation = self.check_prompt_policy(request_text)
            if violation is not None:
                _LOGGER.warning(
                    "policy_guardrail_blocked_prompt",
                    agent_name=getattr(callback_context, "agent_name", "unknown"),
                    reason=violation,
                )
                return LlmResponse(
                    content=genai_types.Content(
                        role="model",
                        parts=[genai_types.Part.from_text(text=violation)],
                    )
                )
        return None

    async def before_tool_callback(
        self, *, tool: Any, tool_args: dict[str, Any], tool_context: Any
    ) -> dict[str, Any] | None:
        """Enforce argument hygiene and block unsafe/disallowed tool targets."""
        tool_name = getattr(tool, "name", str(tool))
        serialized_args = str(tool_args)
        for pattern in _DISALLOWED_TOOL_PATTERNS:
            if pattern.search(serialized_args):
                _LOGGER.warning(
                    "policy_guardrail_blocked_tool_args",
                    tool_name=tool_name,
                    reason="disallowed_target_pattern",
                )
                return {
                    "status": "error",
                    "error_code": "POLICY_BLOCKED_TOOL_CALL",
                    "message": f"Tool '{tool_name}' call rejected by security policy.",
                    "recovery_instructions": (
                        "Remove disallowed SQL/private-channel targets and retry using "
                        "public gaming subreddits from the allowlist."
                    ),
                }
        return None

    async def after_model_callback(
        self, *, callback_context: Any, llm_response: Any
    ) -> Any:
        """Scrub any residual PII from model responses before returning to user."""
        content = getattr(llm_response, "content", None)
        parts = getattr(content, "parts", None) if content is not None else None
        if not parts:
            return None

        modified = False
        new_parts: list[Any] = []
        for part in parts:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text:
                report = self.redactor.redact_with_report(text)
                if report.findings_count > 0:
                    modified = True
                    _LOGGER.warning(
                        "policy_guardrail_redacted_model_output",
                        agent_name=getattr(callback_context, "agent_name", "unknown"),
                        findings_count=report.findings_count,
                        info_types=list(report.info_types_found),
                    )
                    new_parts.append(genai_types.Part.from_text(text=report.redacted_text))
                    continue
            new_parts.append(part)

        if modified and content is not None:
            content.parts = new_parts
            return llm_response
        return None
