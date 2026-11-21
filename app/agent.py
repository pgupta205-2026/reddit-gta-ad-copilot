"""Multi-agent ADK orchestration, strategic model routing, compaction, and HITL app.

Architecture:
- `AccountCopilotCoordinator` (LlmAgent · Pro): Entry coordinator with persistent
  benchmark recall (`retrieve_historical_campaign_benchmarks`) and delegation to
  `StrategyAndVerificationPipeline`.
- `StrategyAndVerificationPipeline` (SequentialAgent):
    1. `ParallelMarketResearchSquad` (ParallelAgent):
        - `AdvertiserOpportunityScout` (LlmAgent · Flash)
        - `BrandSafetyAuditor` (LlmAgent · Flash)
    2. `StrategyRefinementLoop` (LoopAgent, max_iterations=2):
        - `CampaignStrategistAgent` (LlmAgent · Pro, with HITL-gated tools)
        - `SelfEvalGuardrailAgent` (LlmAgent · Flash, `output_schema=SelfEvalVerdict`)
        - `SelfEvalEscalationChecker` (BaseAgent — stops loop immediately once `passed=True`)
- `App(name="app", ...)`:
    - `EventsCompactionConfig` (`LlmEventSummarizer` sliding-window + token compaction)
    - `ContextCacheConfig` (Google Cloud context caching)
    - Global `PolicyGuardrailPlugin` & `ObservabilityIntentOutcomePlugin`
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from google.adk.agents import Agent, BaseAgent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.agents.invocation_context import InvocationContext
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.events import Event, EventActions
from google.adk.models import Gemini
from google.adk.tools import FunctionTool
from google.genai import types as genai_types

from app.config import CopilotConfig, TaskTier
from app.memory.async_consolidator import AsyncMemoryConsolidator
from app.observability.logging import configure_logging, get_logger
from app.observability.tracing import configure_tracing
from app.plugins.observability_plugin import ObservabilityIntentOutcomePlugin
from app.plugins.policy_guardrail_plugin import PolicyGuardrailPlugin
from app.prompts import (
    BRAND_SAFETY_AUDITOR_INSTRUCTION,
    CAMPAIGN_STRATEGIST_INSTRUCTION,
    COORDINATOR_CONSTITUTION,
    OPPORTUNITY_SCOUT_INSTRUCTION,
    SELF_EVAL_JUDGE_INSTRUCTION,
)
from app.schemas import SelfEvalVerdict
from app.tools.copilot_tools import CopilotToolkit

_LOGGER = get_logger(__name__)


class SelfEvalEscalationChecker(BaseAgent):
    """Custom BaseAgent that stops `StrategyRefinementLoop` once self-eval passes."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        raw_verdict = ctx.session.state.get("self_eval_verdict")
        passed = False
        feedback = "Ensure all recommendations include verifiable thread_id citations and zero PII."

        if isinstance(raw_verdict, dict):
            passed = bool(raw_verdict.get("passed", False))
            feedback = str(raw_verdict.get("revision_feedback", feedback))
        elif raw_verdict is not None and hasattr(raw_verdict, "passed"):
            passed = bool(getattr(raw_verdict, "passed", False))
            feedback = str(getattr(raw_verdict, "revision_feedback", feedback))

        ctx.session.state["self_eval_feedback"] = feedback
        _LOGGER.info(
            "self_eval_verdict",
            passed=passed,
            revision_feedback=feedback,
            session_id=ctx.session.id,
        )
        if passed:
            yield Event(author=self.name, actions=EventActions(escalate=True))
        else:
            yield Event(author=self.name)


async def initialize_session_defaults(callback_context: CallbackContext) -> None:
    """Seed required state placeholders so prompt template interpolation never fails."""
    state = callback_context.state
    state.setdefault("opportunity_findings", "No opportunity scan run yet.")
    state.setdefault("brand_safety_findings", "No brand-safety audit run yet.")
    state.setdefault("strategy_draft", "")
    state.setdefault("self_eval_feedback", "Initial draft — no prior feedback.")


def create_opportunity_scout(
    config: CopilotConfig, toolkit: CopilotToolkit
) -> Agent:
    """Factory creating the fast-tier parallel Advertiser Opportunity Scout."""
    return Agent(
        name="advertiser_opportunity_scout",
        model=config.model_router.select_model(TaskTier.FAST_EXTRACTION),
        description=(
            "Scans GTA VI subreddits in parallel to quantify advertiser purchase "
            "intent across OLED displays, NVMe SSDs, consoles, peripherals, and CPG."
        ),
        instruction=OPPORTUNITY_SCOUT_INSTRUCTION,
        generate_content_config=genai_types.GenerateContentConfig(temperature=0.2),
        tools=[
            FunctionTool(func=toolkit.fetch_gta6_subreddit_discussions),
            FunctionTool(func=toolkit.score_advertiser_category_opportunity),
        ],
        output_key="opportunity_findings",
    )


def create_brand_safety_auditor(
    config: CopilotConfig, toolkit: CopilotToolkit
) -> Agent:
    """Factory creating the fast-tier parallel GARM Brand-Safety Auditor."""
    return Agent(
        name="brand_safety_auditor",
        model=config.model_router.select_model(TaskTier.FAST_EXTRACTION),
        description=(
            "Audits GTA VI discussions against GARM brand-safety categories "
            "(refund waves, toxicity, crash outrage) and flags pause triggers."
        ),
        instruction=BRAND_SAFETY_AUDITOR_INSTRUCTION,
        generate_content_config=genai_types.GenerateContentConfig(temperature=0.1),
        tools=[
            FunctionTool(func=toolkit.fetch_gta6_subreddit_discussions),
            FunctionTool(func=toolkit.audit_subreddit_brand_safety_risks),
        ],
        output_key="brand_safety_findings",
    )


def create_campaign_strategist(
    config: CopilotConfig, toolkit: CopilotToolkit
) -> Agent:
    """Factory creating the reasoning-tier Campaign Strategist with HITL action tools."""
    pause_tool = FunctionTool(
        func=toolkit.issue_campaign_pause_recommendation,
        require_confirmation=True,
    )
    pitch_brief_tool = FunctionTool(
        func=toolkit.dispatch_advertiser_pitch_brief,
        require_confirmation=True,
    )
    return Agent(
        name="campaign_strategist",
        model=config.model_router.select_model(TaskTier.STRATEGIC_PLANNING),
        description=(
            "Synthesizes commercial opportunity vs. GARM risk into executive account "
            "recommendations and prepares HITL-confirmed pause alerts or pitch briefs."
        ),
        instruction=CAMPAIGN_STRATEGIST_INSTRUCTION,
        generate_content_config=genai_types.GenerateContentConfig(temperature=0.3),
        tools=[pause_tool, pitch_brief_tool],
        output_key="strategy_draft",
    )


def create_self_eval_guardrail_agent(config: CopilotConfig) -> Agent:
    """Factory creating the fast-tier Self-Eval Judge using strict `output_schema`."""
    return Agent(
        name="self_eval_guardrail_agent",
        model=config.model_router.select_model(TaskTier.SAFETY_EVALUATION),
        description=(
            "Evaluates drafted campaign recommendations for verifiable thread citations, "
            "zero PII leakage, and HITL policy adherence using strict SelfEvalVerdict JSON."
        ),
        instruction=SELF_EVAL_JUDGE_INSTRUCTION,
        generate_content_config=genai_types.GenerateContentConfig(temperature=0.0),
        output_schema=SelfEvalVerdict,
        output_key="self_eval_verdict",
    )


def build_copilot_app(
    config: CopilotConfig | None = None,
    *,
    toolkit: CopilotToolkit | None = None,
) -> tuple[App, Agent, AsyncMemoryConsolidator]:
    """Assemble the complete multi-agent ADK App with plugins, compaction, and telemetry."""
    cfg = config or CopilotConfig.from_env()
    tk = toolkit or CopilotToolkit.from_config(cfg)

    configure_logging(level=cfg.log_level, redactor=tk.redactor)
    configure_tracing(
        service_name=cfg.service_name,
        gcp_project_id=cfg.gcp_project_id,
        exporter_mode=cfg.otel_traces_exporter,
        disabled=cfg.otel_sdk_disabled,
    )

    consolidator = AsyncMemoryConsolidator(store=tk.memory_store)

    research_squad = ParallelAgent(
        name="parallel_market_research_squad",
        description="Runs Opportunity Scout and Brand-Safety Auditor concurrently.",
        sub_agents=[
            create_opportunity_scout(cfg, tk),
            create_brand_safety_auditor(cfg, tk),
        ],
    )

    refinement_loop = LoopAgent(
        name="strategy_refinement_and_self_eval_loop",
        description="Synthesizes campaign recommendations and verifies policy/citations via self-eval.",
        sub_agents=[
            create_campaign_strategist(cfg, tk),
            create_self_eval_guardrail_agent(cfg),
            SelfEvalEscalationChecker(name="self_eval_escalation_checker"),
        ],
        max_iterations=2,
    )

    pipeline = SequentialAgent(
        name="strategy_and_verification_pipeline",
        description="Executes parallel market research followed by strategic synthesis and self-eval.",
        sub_agents=[research_squad, refinement_loop],
    )

    coordinator_tools: list[Any] = [
        FunctionTool(func=tk.retrieve_historical_campaign_benchmarks),
    ]
    if cfg.vertex_ai_search_datastore_id:
        from google.adk.tools import VertexAiSearchTool

        coordinator_tools.append(
            VertexAiSearchTool(data_store_id=cfg.vertex_ai_search_datastore_id)
        )

    coordinator = Agent(
        name="account_copilot_coordinator",
        model=cfg.model_router.select_model(TaskTier.COORDINATOR_ROUTING),
        description=(
            "Top-level Reddit Gaming Advertiser & Brand-Safety Copilot orchestrator "
            "managing GTA VI launch intelligence, memory recall, and safe escalations."
        ),
        instruction=COORDINATOR_CONSTITUTION,
        generate_content_config=genai_types.GenerateContentConfig(temperature=0.2),
        tools=coordinator_tools,
        sub_agents=[pipeline],
        before_agent_callback=initialize_session_defaults,
    )

    compaction_model = cfg.model_router.select_model(TaskTier.HISTORY_COMPACTION)
    compaction_config = EventsCompactionConfig(  # type: ignore[operator]
        compaction_interval=cfg.compaction_interval,
        overlap_size=cfg.compaction_overlap_size,
        token_threshold=cfg.compaction_token_threshold,
        event_retention_size=cfg.compaction_event_retention_size,
        summarizer=LlmEventSummarizer(llm=Gemini(model=compaction_model)),
    )

    cache_config = ContextCacheConfig(
        min_tokens=cfg.context_cache_min_tokens,
        ttl_seconds=cfg.context_cache_ttl_seconds,
        cache_intervals=10,
    )

    policy_plugin = PolicyGuardrailPlugin(
        redactor=tk.redactor,
        model_armor_template=cfg.model_armor_template,
    )
    observability_plugin = ObservabilityIntentOutcomePlugin(
        redactor=tk.redactor,
        consolidator=consolidator,
    )

    adk_app = App(
        name=cfg.app_name,
        root_agent=coordinator,
        events_compaction_config=compaction_config,
        context_cache_config=cache_config,
        plugins=[policy_plugin, observability_plugin],
    )

    _LOGGER.info(
        "copilot_app_initialized",
        app_name=cfg.app_name,
        model_routing=cfg.model_router.routing_table(),
        reddit_data_mode=cfg.reddit_data_mode,
        cloud_dlp_enabled=cfg.enable_cloud_dlp,
    )
    return adk_app, coordinator, consolidator


app, root_agent, memory_consolidator = build_copilot_app()
