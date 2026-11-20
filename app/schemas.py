"""Strict Pydantic v2 JSON input/output schemas for tools and structured agents.

Using `extra="forbid"` and explicit field constraints ensures tool arguments and
structured LLM outputs are validated against deterministic JSON schemas before
execution or downstream consumption.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SUPPORTED_SUBREDDITS: tuple[str, ...] = (
    "GTA6",
    "gaming",
    "PS5",
    "xbox",
    "rockstar",
    "OLED_Gaming",
    "4kTV",
    "buildapc",
)

AdvertiserVertical = Literal[
    "oled_displays",
    "ssd_storage",
    "console_hardware",
    "gaming_peripherals",
    "cpg_beverages",
]

RiskTier = Literal["low", "medium", "high", "critical"]


class StrictSchema(BaseModel):
    """Base schema rejecting unknown fields for strict contract validation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# Guided Error Recovery Schema
# ---------------------------------------------------------------------------


class ToolErrorResponse(StrictSchema):
    """Structured error returned to the LLM with explicit recovery instructions."""

    status: Literal["error"] = "error"
    error_code: str = Field(
        description="Machine-readable error identifier (e.g., INVALID_SUBREDDIT, RATE_LIMITED)."
    )
    message: str = Field(description="Clear explanation of what went wrong.")
    recovery_instructions: str = Field(
        description="Concrete step-by-step instructions telling the LLM how to recover."
    )
    suggested_next_call: dict[str, Any] | None = Field(
        default=None,
        description="Optional example tool arguments that will succeed on retry.",
    )


# ---------------------------------------------------------------------------
# Tool 1: fetch_gta6_subreddit_discussions
# ---------------------------------------------------------------------------


class FetchDiscussionsInput(StrictSchema):
    """Validated input arguments for `fetch_gta6_subreddit_discussions`."""

    subreddit: str = Field(
        min_length=2,
        max_length=32,
        description="Target subreddit name without 'r/' prefix (e.g., 'GTA6', 'OLED_Gaming').",
    )
    topic_filter: str = Field(
        min_length=1,
        max_length=80,
        description="Keyword or theme filter (e.g., 'OLED', '212GB', 'refund', or 'all').",
    )
    limit: int = Field(
        ge=1,
        le=25,
        description="Maximum number of discussion threads to return (1-25).",
    )

    @field_validator("subreddit")
    @classmethod
    def normalize_subreddit(cls, value: str) -> str:
        cleaned = value.removeprefix("r/").removeprefix("/r/").strip()
        return cleaned


class RedditThreadRecord(StrictSchema):
    """Single PII-redacted Reddit discussion thread with engagement metadata."""

    thread_id: str = Field(description="Unique Reddit submission ID (e.g., t3_gta6_001).")
    subreddit: str = Field(description="Subreddit where the thread was posted.")
    title: str = Field(description="PII-redacted thread title.")
    permalink: str = Field(description="Canonical Reddit permalink path.")
    upvotes: int = Field(ge=0, description="Net upvote score.")
    comment_count: int = Field(ge=0, description="Total comments in thread.")
    comments_per_hour: float = Field(ge=0.0, description="Comment velocity per hour.")
    sentiment_score: float = Field(
        ge=-1.0, le=1.0, description="Normalized sentiment (-1.0 negative to +1.0 positive)."
    )
    top_excerpts: list[str] = Field(
        description="PII-redacted representative comment excerpts from the thread."
    )
    tags: list[str] = Field(description="Topic/signal tags extracted from discussion.")


class SubredditDiscussionBatch(StrictSchema):
    """Structured output of `fetch_gta6_subreddit_discussions`."""

    status: Literal["success"] = "success"
    data_source: Literal["reddit_live_api", "gta6_launch_fixture"] = Field(
        description="Whether data came from live Reddit OAuth API or local launch fixtures."
    )
    subreddit: str = Field(description="Normalized subreddit queried.")
    topic_filter: str = Field(description="Filter applied to discussions.")
    thread_count: int = Field(ge=0, description="Number of matching threads returned.")
    threads: list[RedditThreadRecord] = Field(description="Matching PII-redacted threads.")


# ---------------------------------------------------------------------------
# Tool 2: score_advertiser_category_opportunity
# ---------------------------------------------------------------------------


class ScoreOpportunityInput(StrictSchema):
    """Validated input arguments for `score_advertiser_category_opportunity`."""

    vertical: AdvertiserVertical = Field(
        description="Advertiser vertical to evaluate for GTA VI spillover demand."
    )
    subreddits: list[str] = Field(
        min_length=1,
        max_length=8,
        description="Subreddits to scan for purchase-intent signals.",
    )


class SubredditOpportunitySignal(StrictSchema):
    """Quantified advertiser opportunity for one subreddit."""

    subreddit: str = Field(description="Evaluated subreddit.")
    intent_score: float = Field(
        ge=0.0, le=100.0, description="Commercial purchase-intent score (0-100)."
    )
    velocity_comments_per_hour: float = Field(ge=0.0)
    matched_thread_ids: list[str] = Field(
        description="Verifiable thread IDs supporting the score."
    )
    recommended_ad_angle: str = Field(
        description="Suggested creative/targeting hook aligned to community chatter."
    )


class AdvertiserOpportunityReport(StrictSchema):
    """Structured output of `score_advertiser_category_opportunity`."""

    status: Literal["success"] = "success"
    vertical: AdvertiserVertical = Field(description="Evaluated advertiser vertical.")
    overall_opportunity_score: float = Field(ge=0.0, le=100.0)
    priority_tier: Literal["tier_1_immediate", "tier_2_test", "tier_3_monitor"]
    subreddit_breakdown: list[SubredditOpportunitySignal]
    cited_thread_ids: list[str]


# ---------------------------------------------------------------------------
# Tool 3: audit_subreddit_brand_safety_risks
# ---------------------------------------------------------------------------


class BrandSafetyAuditInput(StrictSchema):
    """Validated input arguments for `audit_subreddit_brand_safety_risks`."""

    subreddits: list[str] = Field(
        min_length=1,
        max_length=8,
        description="Subreddits to audit against GARM brand-safety categories.",
    )
    advertiser_sensitivity: Literal["standard", "strict"] = Field(
        description="Risk sensitivity threshold ('strict' flags lower-severity controversy)."
    )


class BrandSafetyFinding(StrictSchema):
    """Single GARM-aligned brand-safety risk finding backed by a thread ID."""

    thread_id: str = Field(description="Verifiable Reddit thread ID.")
    subreddit: str = Field(description="Subreddit containing the risk.")
    garm_category: str = Field(
        description="GARM risk category (e.g., Profanity/Toxicity, Consumer Outrage/Refund Wave, Sensitive Social Issue)."
    )
    severity: RiskTier = Field(description="Severity rating for this thread.")
    evidence_summary: str = Field(description="PII-redacted explanation of the risk trigger.")
    recommended_mitigation: str = Field(
        description="Actionable placement control (e.g., thread exclusion, keyword blocklist, pause)."
    )


class BrandSafetyAuditResult(StrictSchema):
    """Structured output of `audit_subreddit_brand_safety_risks`."""

    status: Literal["success"] = "success"
    overall_risk_tier: RiskTier
    pause_recommended: bool = Field(
        description="True when risk warrants invoking the HITL campaign-pause workflow."
    )
    audited_subreddits: list[str]
    findings: list[BrandSafetyFinding]
    safe_subreddits: list[str]


# ---------------------------------------------------------------------------
# Tool 4: retrieve_historical_campaign_benchmarks
# ---------------------------------------------------------------------------


class HistoricalBenchmarkInput(StrictSchema):
    """Validated input arguments for `retrieve_historical_campaign_benchmarks`."""

    query: str = Field(
        min_length=2,
        max_length=200,
        description="Natural-language query for prior launch-week campaign snapshots.",
    )
    vertical: str = Field(
        min_length=2,
        max_length=64,
        description="Advertiser vertical filter or 'all'.",
    )
    top_k: int = Field(ge=1, le=10, description="Number of historical snapshots to return.")


class HistoricalBenchmarkEntry(StrictSchema):
    """Single persisted benchmark entry retrieved from cross-session memory."""

    snapshot_id: str
    recorded_at: str
    vertical: str
    summary: str
    opportunity_score: float
    risk_tier: RiskTier
    similarity_score: float = Field(ge=0.0, le=1.0)


class HistoricalBenchmarkResponse(StrictSchema):
    """Structured output of `retrieve_historical_campaign_benchmarks`."""

    status: Literal["success"] = "success"
    storage_backend: str
    matches: list[HistoricalBenchmarkEntry]


# ---------------------------------------------------------------------------
# Tools 5 & 6: Human-in-the-Loop High-Stakes Actions
# ---------------------------------------------------------------------------


class CampaignPauseInput(StrictSchema):
    """Validated input arguments for HITL-gated `issue_campaign_pause_recommendation`."""

    advertiser_name: str = Field(min_length=2, max_length=100)
    vertical: AdvertiserVertical
    affected_subreddits: list[str] = Field(min_length=1, max_length=8)
    severity: Literal["high", "critical"]
    rationale: str = Field(min_length=15, max_length=600)
    cited_thread_ids: list[str] = Field(min_length=1, max_length=20)


class PitchBriefInput(StrictSchema):
    """Validated input arguments for HITL-gated `dispatch_advertiser_pitch_brief`."""

    advertiser_name: str = Field(min_length=2, max_length=100)
    vertical: AdvertiserVertical
    target_subreddits: list[str] = Field(min_length=1, max_length=8)
    executive_summary: str = Field(min_length=20, max_length=1200)
    recommended_budget_shift_pct: int = Field(ge=0, le=100)
    cited_thread_ids: list[str] = Field(min_length=1, max_length=20)


class HitlActionResult(StrictSchema):
    """Structured output for HITL-gated external actions."""

    status: Literal["awaiting_human_confirmation", "dispatched", "rejected_by_human"]
    action_type: Literal["campaign_pause_recommendation", "advertiser_pitch_brief"]
    action_id: str
    confirmation_prompt: str | None = None
    delivery_channel: str | None = None
    summary: str


# ---------------------------------------------------------------------------
# Structured Self-Evaluation Verdict (Used with ADK output_schema)
# ---------------------------------------------------------------------------


class SelfEvalVerdict(StrictSchema):
    """Strict output_schema produced by `SelfEvalGuardrailAgent`."""

    passed: bool = Field(
        description="True only if citations, brand-safety logic, HITL boundaries, and PII hygiene all pass."
    )
    groundedness_score: float = Field(
        ge=0.0, le=1.0, description="Fraction of claims backed by cited Reddit thread IDs."
    )
    pii_leak_detected: bool = Field(
        description="True if any unredacted email, phone, IP, token, or u/username appears."
    )
    policy_violations: list[str] = Field(
        description="List of any constitutional or brand-safety policy issues found."
    )
    revision_feedback: str = Field(
        description="Concise guidance for CampaignStrategistAgent if passed is False; otherwise 'Approved'."
    )
