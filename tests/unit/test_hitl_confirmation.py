"""Unit tests verifying Human-in-the-Loop (HITL) ToolConfirmation gates."""

from __future__ import annotations

from tests.conftest import FakeToolConfirmation, FakeToolContext


def test_campaign_pause_requires_human_confirmation_before_dispatch(
    isolated_toolkit,
) -> None:
    ctx_unconfirmed = FakeToolContext(tool_confirmation=None)
    paused = isolated_toolkit.issue_campaign_pause_recommendation(
        advertiser_name="VoltFizz Energy",
        vertical="cpg_beverages",
        affected_subreddits=["GTA6", "xbox"],
        severity="critical",
        rationale="Critical toxicity flamewar and Xbox Series S refund wave detected.",
        cited_thread_ids=["t3_gta6_002", "t3_xbox_gta6_001"],
        tool_context=ctx_unconfirmed,
    )
    assert paused["status"] == "awaiting_human_confirmation"
    assert len(ctx_unconfirmed.requested_confirmations) == 1
    assert "HUMAN APPROVAL REQUIRED" in paused["confirmation_prompt"]

    # Human explicitly rejects
    ctx_rejected = FakeToolContext(tool_confirmation=FakeToolConfirmation(confirmed=False))
    rejected = isolated_toolkit.issue_campaign_pause_recommendation(
        advertiser_name="VoltFizz Energy",
        vertical="cpg_beverages",
        affected_subreddits=["GTA6", "xbox"],
        severity="critical",
        rationale="Critical toxicity flamewar and Xbox Series S refund wave detected.",
        cited_thread_ids=["t3_gta6_002", "t3_xbox_gta6_001"],
        tool_context=ctx_rejected,
    )
    assert rejected["status"] == "rejected_by_human"

    # Human explicitly approves
    ctx_approved = FakeToolContext(tool_confirmation=FakeToolConfirmation(confirmed=True))
    dispatched = isolated_toolkit.issue_campaign_pause_recommendation(
        advertiser_name="VoltFizz Energy",
        vertical="cpg_beverages",
        affected_subreddits=["GTA6", "xbox"],
        severity="critical",
        rationale="Critical toxicity flamewar and Xbox Series S refund wave detected.",
        cited_thread_ids=["t3_gta6_002", "t3_xbox_gta6_001"],
        tool_context=ctx_approved,
    )
    assert dispatched["status"] == "dispatched"
    assert dispatched["delivery_channel"] == "local_audit_sink"


def test_pitch_brief_dispatch_requires_human_confirmation(isolated_toolkit) -> None:
    ctx = FakeToolContext(tool_confirmation=None)
    pending = isolated_toolkit.dispatch_advertiser_pitch_brief(
        advertiser_name="Lumina OLED Displays",
        vertical="oled_displays",
        target_subreddits=["OLED_Gaming", "4kTV"],
        executive_summary="Vice City HDR night-lighting praise is driving Tier-1 OLED upgrade intent.",
        recommended_budget_shift_pct=25,
        cited_thread_ids=["t3_oled_gta6_001", "t3_4ktv_gta6_001"],
        tool_context=ctx,
    )
    assert pending["status"] == "awaiting_human_confirmation"
    assert len(ctx.requested_confirmations) == 1

    ctx_approved = FakeToolContext(tool_confirmation=FakeToolConfirmation(confirmed=True))
    sent = isolated_toolkit.dispatch_advertiser_pitch_brief(
        advertiser_name="Lumina OLED Displays",
        vertical="oled_displays",
        target_subreddits=["OLED_Gaming", "4kTV"],
        executive_summary="Vice City HDR night-lighting praise is driving Tier-1 OLED upgrade intent.",
        recommended_budget_shift_pct=25,
        cited_thread_ids=["t3_oled_gta6_001", "t3_4ktv_gta6_001"],
        tool_context=ctx_approved,
    )
    assert sent["status"] == "dispatched"
