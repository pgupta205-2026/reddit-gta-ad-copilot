"""Unit tests for strict Pydantic schemas, guided errors, and domain scoring tools."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import FetchDiscussionsInput, SelfEvalVerdict


def test_strict_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        FetchDiscussionsInput(
            subreddit="GTA6",
            topic_filter="all",
            limit=5,
            unexpected_extra_field="blocked",  # type: ignore[call-arg]
        )


def test_self_eval_verdict_schema_enforces_bounds() -> None:
    verdict = SelfEvalVerdict(
        passed=True,
        groundedness_score=0.95,
        pii_leak_detected=False,
        policy_violations=[],
        revision_feedback="Approved",
    )
    assert verdict.passed is True
    with pytest.raises(ValidationError):
        SelfEvalVerdict(
            passed=True,
            groundedness_score=1.5,
            pii_leak_detected=False,
            policy_violations=[],
            revision_feedback="Invalid score",
        )


def test_fetch_discussions_redacts_pii_from_fixtures(isolated_toolkit) -> None:
    result = isolated_toolkit.fetch_gta6_subreddit_discussions(
        subreddit="r/xbox", topic_filter="all", limit=5
    )
    assert result["status"] == "success"
    assert result["data_source"] == "gta6_launch_fixture"
    joined = " ".join(
        excerpt
        for thread in result["threads"]
        for excerpt in thread["top_excerpts"]
    )
    assert "555-019-2834" not in joined
    assert "198.51.100.42" not in joined
    assert "u/series_s_owner" not in joined
    assert "[REDACTED_PHONE]" in joined
    assert "[REDACTED_IP]" in joined
    assert "[REDACTED_REDDIT_USER]" in joined


def test_guided_error_on_unsupported_subreddit(isolated_toolkit) -> None:
    err = isolated_toolkit.fetch_gta6_subreddit_discussions(
        subreddit="fake_unmonitored_sub", topic_filter="all", limit=5
    )
    assert err["status"] == "error"
    assert err["error_code"] == "UNSUPPORTED_SUBREDDIT"
    assert "GTA6" in err["recovery_instructions"]
    assert err["suggested_next_call"]["subreddit"] == "GTA6"


def test_guided_error_on_invalid_vertical(isolated_toolkit) -> None:
    err = isolated_toolkit.score_advertiser_category_opportunity(
        vertical="crypto_gambling", subreddits=["GTA6"]
    )
    assert err["status"] == "error"
    assert err["error_code"] == "INVALID_VERTICAL_OR_SUBREDDITS"
    assert "oled_displays" in err["recovery_instructions"]


def test_opportunity_scoring_identifies_tier1_oled_and_ssd(isolated_toolkit) -> None:
    oled = isolated_toolkit.score_advertiser_category_opportunity(
        vertical="oled_displays", subreddits=["OLED_Gaming", "4kTV"]
    )
    assert oled["status"] == "success"
    assert oled["priority_tier"] == "tier_1_immediate"
    assert "t3_oled_gta6_001" in oled["cited_thread_ids"]

    ssd = isolated_toolkit.score_advertiser_category_opportunity(
        vertical="ssd_storage", subreddits=["PS5", "buildapc"]
    )
    assert ssd["status"] == "success"
    assert "t3_ps5_gta6_001" in ssd["cited_thread_ids"]


def test_brand_safety_audit_flags_critical_and_safe_communities(isolated_toolkit) -> None:
    audit = isolated_toolkit.audit_subreddit_brand_safety_risks(
        subreddits=["GTA6", "xbox", "OLED_Gaming"],
        advertiser_sensitivity="strict",
    )
    assert audit["status"] == "success"
    assert audit["overall_risk_tier"] == "critical"
    assert audit["pause_recommended"] is True
    assert "OLED_Gaming" in audit["safe_subreddits"]
    cited = {f["thread_id"] for f in audit["findings"]}
    assert {"t3_gta6_002", "t3_xbox_gta6_001"}.issubset(cited)
