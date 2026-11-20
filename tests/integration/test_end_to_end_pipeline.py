"""End-to-end deterministic integration test of the copilot workflow."""

from __future__ import annotations

import pytest

from app.memory.async_consolidator import AsyncMemoryConsolidator, MemoryConsolidationJob
from tests.conftest import FakeToolConfirmation, FakeToolContext


@pytest.mark.asyncio
async def test_full_advertiser_opportunity_safety_hitl_and_memory_lifecycle(
    isolated_toolkit,
) -> None:
    # 1. Parallel research equivalent: Opportunity Scout + Brand-Safety Auditor
    oled_report = isolated_toolkit.score_advertiser_category_opportunity(
        vertical="oled_displays", subreddits=["OLED_Gaming", "4kTV"]
    )
    safety_audit = isolated_toolkit.audit_subreddit_brand_safety_risks(
        subreddits=["GTA6", "xbox", "OLED_Gaming"], advertiser_sensitivity="strict"
    )
    assert oled_report["priority_tier"] == "tier_1_immediate"
    assert safety_audit["pause_recommended"] is True

    # 2. HITL pause gate -> human confirmation -> approved dispatch
    pause_ctx = FakeToolContext(tool_confirmation=None)
    pending = isolated_toolkit.issue_campaign_pause_recommendation(
        advertiser_name="VoltFizz Energy",
        vertical="cpg_beverages",
        affected_subreddits=["GTA6", "xbox"],
        severity="critical",
        rationale="Toxicity and refund spikes identified during strict GARM audit.",
        cited_thread_ids=[f["thread_id"] for f in safety_audit["findings"][:2]],
        tool_context=pause_ctx,
    )
    assert pending["status"] == "awaiting_human_confirmation"

    approved_ctx = FakeToolContext(tool_confirmation=FakeToolConfirmation(confirmed=True))
    dispatched = isolated_toolkit.issue_campaign_pause_recommendation(
        advertiser_name="VoltFizz Energy",
        vertical="cpg_beverages",
        affected_subreddits=["GTA6", "xbox"],
        severity="critical",
        rationale="Toxicity and refund spikes identified during strict GARM audit.",
        cited_thread_ids=[f["thread_id"] for f in safety_audit["findings"][:2]],
        tool_context=approved_ctx,
    )
    assert dispatched["status"] == "dispatched"

    # 3. Non-blocking async memory consolidation -> cross-session recall
    consolidator = AsyncMemoryConsolidator(store=isolated_toolkit.memory_store)
    consolidator.enqueue_non_blocking(
        MemoryConsolidationJob(
            session_id="sess_e2e_01",
            vertical="oled_displays",
            raw_summary=(
                "Day-1 launch confirmed Tier-1 OLED intent on r/OLED_Gaming "
                "while r/xbox Series S crash threads triggered critical pause."
            ),
            opportunity_score=oled_report["overall_opportunity_score"],
            risk_tier=safety_audit["overall_risk_tier"],
        )
    )
    await consolidator.flush(timeout_seconds=5.0)

    recalled = isolated_toolkit.retrieve_historical_campaign_benchmarks(
        query="Day-1 launch OLED intent r/OLED_Gaming",
        vertical="oled_displays",
        top_k=3,
    )
    assert recalled["status"] == "success"
    assert any("Day-1 launch confirmed Tier-1 OLED" in m["summary"] for m in recalled["matches"])
