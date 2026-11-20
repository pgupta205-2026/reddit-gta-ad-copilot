"""Architecture & AgentOps rubric contract tests (multi-agent, routing, compaction, no print)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.config import CopilotConfig, TaskTier
from app.tools.copilot_tools import CopilotToolkit

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_zero_bare_print_statements_in_app_package() -> None:
    app_dir = REPO_ROOT / "app"
    violations: list[str] = []
    for py_file in app_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                violations.append(f"{py_file.relative_to(REPO_ROOT)}:{node.lineno}")
    assert not violations, f"Bare print() calls found in app/: {violations}"


def test_strategic_model_routing_separates_fast_and_reasoning_tiers() -> None:
    cfg = CopilotConfig.from_env()
    fast = cfg.model_router.select_model(TaskTier.FAST_EXTRACTION)
    eval_model = cfg.model_router.select_model(TaskTier.SAFETY_EVALUATION)
    compaction_model = cfg.model_router.select_model(TaskTier.HISTORY_COMPACTION)
    pro = cfg.model_router.select_model(TaskTier.STRATEGIC_PLANNING)
    coord = cfg.model_router.select_model(TaskTier.COORDINATOR_ROUTING)

    assert "flash" in fast.lower()
    assert eval_model == fast
    assert compaction_model == fast
    assert "pro" in pro.lower()
    assert coord == pro
    assert fast != pro


def test_all_six_tools_have_comprehensive_docstrings_without_tool_context_mention() -> None:
    tool_names = (
        "fetch_gta6_subreddit_discussions",
        "score_advertiser_category_opportunity",
        "audit_subreddit_brand_safety_risks",
        "retrieve_historical_campaign_benchmarks",
        "issue_campaign_pause_recommendation",
        "dispatch_advertiser_pitch_brief",
    )
    for name in tool_names:
        fn = getattr(CopilotToolkit, name)
        doc = inspect.getdoc(fn) or ""
        assert len(doc) >= 120, f"Tool '{name}' docstring is too short."
        assert "Args:" in doc and "Returns:" in doc, f"Tool '{name}' missing Args/Returns sections."
        assert "tool_context" not in doc, f"Tool '{name}' docstring should not mention tool_context."


def test_multi_agent_app_topology_compaction_and_plugins(tmp_path) -> None:
    from google.adk.agents import LoopAgent, ParallelAgent, SequentialAgent

    from app.agent import build_copilot_app

    cfg = CopilotConfig(
        campaign_memory_db_path=str(tmp_path / "topo.db"),
        otel_sdk_disabled=True,
    )
    adk_app, coordinator, _ = build_copilot_app(cfg)

    assert adk_app.name == "app"
    assert adk_app.events_compaction_config is not None
    assert adk_app.context_cache_config is not None
    assert len(adk_app.plugins) == 2

    assert coordinator.name == "account_copilot_coordinator"
    assert len(coordinator.sub_agents) == 1
    pipeline = coordinator.sub_agents[0]
    assert isinstance(pipeline, SequentialAgent)
    assert isinstance(pipeline.sub_agents[0], ParallelAgent)
    assert isinstance(pipeline.sub_agents[1], LoopAgent)

    parallel_names = {a.name for a in pipeline.sub_agents[0].sub_agents}
    assert parallel_names == {"advertiser_opportunity_scout", "brand_safety_auditor"}
