"""Hyper-specific ADK tools with strict Pydantic I/O, guided errors, and HITL gates.

Design principles enforced across every tool:
1. Descriptive, action-oriented names (e.g., `audit_subreddit_brand_safety_risks`).
2. Comprehensive Google-style docstrings covering purpose, parameters, and outputs.
3. Strict Pydantic v2 input and output JSON schemas (`extra="forbid"`).
4. Guided error recovery (`ToolErrorResponse`) instructing the LLM how to recover.
5. Explicit Human-in-the-Loop (HITL) confirmation hooks via ADK `ToolConfirmation`
   (`require_confirmation=True` + `tool_context.request_confirmation`) for all
   high-stakes external actions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.config import CopilotConfig
from app.memory.store import CampaignMemoryStore
from app.observability.logging import get_logger
from app.observability.tracing import traced_span
from app.schemas import (
    SUPPORTED_SUBREDDITS,
    AdvertiserOpportunityReport,
    BrandSafetyAuditInput,
    BrandSafetyAuditResult,
    BrandSafetyFinding,
    CampaignPauseInput,
    FetchDiscussionsInput,
    HistoricalBenchmarkEntry,
    HistoricalBenchmarkInput,
    HistoricalBenchmarkResponse,
    HitlActionResult,
    PitchBriefInput,
    ScoreOpportunityInput,
    SubredditDiscussionBatch,
    SubredditOpportunitySignal,
    ToolErrorResponse,
)
from app.security.pii_redactor import PiiRedactor
from app.security.secrets import SecretManagerProvider
from app.tools.reddit_client import (
    RedditAuthConfigError,
    RedditDiscussionClient,
    RedditRateLimitError,
)

_LOGGER = get_logger(__name__)

_VERTICAL_HOOKS: dict[str, str] = {
    "oled_displays": "Highlight infinite contrast & HDR reflection clarity for Vice City night driving.",
    "ssd_storage": "Lead with instant 2TB Gen4 NVMe expansion messaging tailored to GTA VI's 212 GB install.",
    "console_hardware": "Target PC-waiters and Series S upgraders with launch-weekend console trade-in bundles.",
    "gaming_peripherals": "Spotlight low-latency spatial audio headsets & pro controllers for marathon Leonida play.",
    "cpg_beverages": "Sponsor celebratory launch-weekend battlestation & zero-sugar marathon gaming moments.",
}

_GARM_TAG_MAP: dict[str, tuple[str, str, str]] = {
    "brand_safety_refund_wave": (
        "Consumer Outrage / Refund Wave",
        "high",
        "Pause performance creatives targeting affected console threads; apply 'refund'/'crash' negative keywords.",
    ),
    "brand_safety_crash_outrage": (
        "Product Failure / Technical Outrage",
        "medium",
        "Exclude launch-bug megathreads from automated feed placements until hotfix stabilizes sentiment.",
    ),
    "brand_safety_toxicity": (
        "Harassment / Severe Community Toxicity",
        "critical",
        "Immediately exclude thread and recommend pausing brand-sensitive placements in this subreddit.",
    ),
    "brand_safety_profanity": (
        "Excessive Profanity / Aggressive Debate",
        "high",
        "Apply strict GARM floor filters and avoid adjacent comment-thread sponsorships.",
    ),
}

_RISK_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass
class CopilotToolkit:
    """Dependency-injected container binding runtime config, memory, and redactor to tools."""

    config: CopilotConfig
    secrets: SecretManagerProvider
    redactor: PiiRedactor
    memory_store: CampaignMemoryStore
    reddit_client: RedditDiscussionClient

    @classmethod
    def from_config(
        cls,
        config: CopilotConfig | None = None,
        *,
        memory_store: CampaignMemoryStore | None = None,
    ) -> CopilotToolkit:
        cfg = config or CopilotConfig.from_env()
        secrets = cfg.build_secret_provider()
        redactor = PiiRedactor(
            gcp_project_id=cfg.gcp_project_id,
            enable_cloud_dlp=cfg.enable_cloud_dlp,
        )
        store = memory_store or CampaignMemoryStore(
            db_path=cfg.campaign_memory_db_path,
            redactor=redactor,
        )
        reddit_client = RedditDiscussionClient(
            config=cfg, secrets=secrets, redactor=redactor
        )
        return cls(
            config=cfg,
            secrets=secrets,
            redactor=redactor,
            memory_store=store,
            reddit_client=reddit_client,
        )

    # ------------------------------------------------------------------
    # Tool 1: fetch_gta6_subreddit_discussions
    # ------------------------------------------------------------------

    def fetch_gta6_subreddit_discussions(
        self,
        subreddit: str,
        topic_filter: str,
        limit: int,
    ) -> dict[str, Any]:
        """Fetch PII-redacted GTA VI launch discussions from a supported Reddit community.

        Retrieves recent posts, comment velocity, sentiment scores, and redacted
        comment excerpts from either the live Reddit OAuth API or deterministic
        GTA VI launch fixtures.

        Args:
            subreddit: Target subreddit name without leading 'r/' (supported:
                GTA6, gaming, PS5, xbox, rockstar, OLED_Gaming, 4kTV, buildapc).
            topic_filter: Keyword filter such as 'OLED', '212GB', 'refund', or
                'all' to return all tracked discussions in that subreddit.
            limit: Maximum number of threads to return (integer between 1 and 25).

        Returns:
            JSON-serializable dict matching `SubredditDiscussionBatch` on success,
            or `ToolErrorResponse` with explicit recovery instructions on error.
        """
        with traced_span(
            "copilot.tool.fetch_gta6_subreddit_discussions",
            {"reddit.subreddit": subreddit, "reddit.topic_filter": topic_filter},
        ):
            try:
                parsed = FetchDiscussionsInput(
                    subreddit=subreddit, topic_filter=topic_filter, limit=limit
                )
            except ValidationError as exc:
                return ToolErrorResponse(
                    error_code="INVALID_ARGUMENTS",
                    message=f"Input schema validation failed: {exc.errors()[0]['msg']}",
                    recovery_instructions=(
                        "Retry `fetch_gta6_subreddit_discussions` with a valid subreddit "
                        f"from {list(SUPPORTED_SUBREDDITS)}, a non-empty `topic_filter` "
                        "(e.g., 'all'), and `limit` between 1 and 25."
                    ),
                    suggested_next_call={
                        "subreddit": "GTA6",
                        "topic_filter": "all",
                        "limit": 5,
                    },
                ).model_dump(mode="json")

            try:
                source, threads = self.reddit_client.fetch_discussions(
                    subreddit=parsed.subreddit,
                    topic_filter=parsed.topic_filter,
                    limit=parsed.limit,
                )
            except ValueError:
                return ToolErrorResponse(
                    error_code="UNSUPPORTED_SUBREDDIT",
                    message=f"Subreddit 'r/{parsed.subreddit}' is not in the tracked gaming/tech allowlist.",
                    recovery_instructions=(
                        f"Choose one of the monitored subreddits: {', '.join(SUPPORTED_SUBREDDITS)}. "
                        "Retry with `subreddit='GTA6'` or an adjacent hardware subreddit like 'OLED_Gaming' or 'PS5'."
                    ),
                    suggested_next_call={
                        "subreddit": "GTA6",
                        "topic_filter": parsed.topic_filter,
                        "limit": parsed.limit,
                    },
                ).model_dump(mode="json")
            except RedditRateLimitError as exc:
                return ToolErrorResponse(
                    error_code="REDDIT_RATE_LIMITED",
                    message=str(exc),
                    recovery_instructions=(
                        "Reddit API rate limit reached. Reduce `limit` to 3, query a single "
                        "priority subreddit, or inform the user that live polling is throttled."
                    ),
                    suggested_next_call={
                        "subreddit": parsed.subreddit,
                        "topic_filter": "all",
                        "limit": 3,
                    },
                ).model_dump(mode="json")
            except RedditAuthConfigError as exc:
                return ToolErrorResponse(
                    error_code="REDDIT_AUTH_UNAVAILABLE",
                    message=str(exc),
                    recovery_instructions=(
                        "Live Reddit OAuth secrets are not configured in Secret Manager. "
                        "Inform the account lead to populate `reddit-client-id` and "
                        "`reddit-client-secret` in GCP Secret Manager or switch REDDIT_DATA_MODE=fixture."
                    ),
                ).model_dump(mode="json")

            if not threads:
                return ToolErrorResponse(
                    error_code="NO_MATCHING_THREADS",
                    message=(
                        f"No GTA VI threads in r/{parsed.subreddit} matched topic_filter='{parsed.topic_filter}'."
                    ),
                    recovery_instructions=(
                        "Broaden the search by retrying with `topic_filter='all'` on the same "
                        "subreddit so you can inspect all active discussions."
                    ),
                    suggested_next_call={
                        "subreddit": parsed.subreddit,
                        "topic_filter": "all",
                        "limit": parsed.limit,
                    },
                ).model_dump(mode="json")

            batch = SubredditDiscussionBatch(
                data_source=source,  # type: ignore[arg-type]
                subreddit=threads[0].subreddit,
                topic_filter=parsed.topic_filter,
                thread_count=len(threads),
                threads=threads,
            )
            return batch.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Tool 2: score_advertiser_category_opportunity
    # ------------------------------------------------------------------

    def score_advertiser_category_opportunity(
        self,
        vertical: str,
        subreddits: list[str],
    ) -> dict[str, Any]:
        """Quantify commercial ad-placement opportunity for an advertiser vertical.

        Scans GTA VI discussions across the supplied subreddits, calculates
        purchase-intent density and comment velocity for the requested vertical,
        and returns verifiable thread ID citations and creative angle hooks.

        Args:
            vertical: Advertiser vertical to evaluate. Must be one of:
                'oled_displays', 'ssd_storage', 'console_hardware',
                'gaming_peripherals', or 'cpg_beverages'.
            subreddits: Non-empty list of up to 8 subreddit names to analyze
                (e.g., ['OLED_Gaming', '4kTV', 'PS5']).

        Returns:
            JSON-serializable dict matching `AdvertiserOpportunityReport` on
            success, or `ToolErrorResponse` with recovery instructions on error.
        """
        with traced_span(
            "copilot.tool.score_advertiser_category_opportunity",
            {"copilot.vertical": vertical, "copilot.subreddit_count": len(subreddits)},
        ):
            try:
                parsed = ScoreOpportunityInput(
                    vertical=vertical,  # type: ignore[arg-type]
                    subreddits=subreddits,
                )
            except ValidationError as exc:
                return ToolErrorResponse(
                    error_code="INVALID_VERTICAL_OR_SUBREDDITS",
                    message=f"Invalid opportunity scoring request: {exc.errors()[0]['msg']}",
                    recovery_instructions=(
                        "Retry `score_advertiser_category_opportunity` with `vertical` set to one of "
                        "['oled_displays', 'ssd_storage', 'console_hardware', 'gaming_peripherals', "
                        "'cpg_beverages'] and a list of 1-8 supported subreddits."
                    ),
                    suggested_next_call={
                        "vertical": "oled_displays",
                        "subreddits": ["OLED_Gaming", "4kTV", "GTA6"],
                    },
                ).model_dump(mode="json")

            signals: list[SubredditOpportunitySignal] = []
            all_cited: list[str] = []
            invalid_subs: list[str] = []

            for sub in parsed.subreddits:
                try:
                    _, threads = self.reddit_client.fetch_discussions(
                        subreddit=sub, topic_filter="all", limit=10
                    )
                except ValueError:
                    invalid_subs.append(sub)
                    continue

                matched = [t for t in threads if parsed.vertical in t.tags]
                if not matched:
                    continue

                total_velocity = round(sum(t.comments_per_hour for t in matched), 1)
                avg_sentiment = sum(t.sentiment_score for t in matched) / len(matched)
                intent_bonus = 20.0 if any("purchase_intent" in t.tags for t in matched) else 5.0
                raw_score = (
                    45.0
                    + intent_bonus
                    + min(25.0, total_velocity / 12.0)
                    + (avg_sentiment * 12.0)
                )
                intent_score = round(max(0.0, min(100.0, raw_score)), 1)
                thread_ids = [t.thread_id for t in matched]
                all_cited.extend(thread_ids)

                signals.append(
                    SubredditOpportunitySignal(
                        subreddit=matched[0].subreddit,
                        intent_score=intent_score,
                        velocity_comments_per_hour=total_velocity,
                        matched_thread_ids=thread_ids,
                        recommended_ad_angle=_VERTICAL_HOOKS[parsed.vertical],
                    )
                )

            if not signals:
                return ToolErrorResponse(
                    error_code="NO_VERTICAL_SIGNALS_FOUND",
                    message=(
                        f"No commercial signals found for vertical '{parsed.vertical}' "
                        f"in subreddits {parsed.subreddits} (ignored unsupported: {invalid_subs})."
                    ),
                    recovery_instructions=(
                        "Expand your scan to include relevant spillover subreddits: "
                        "OLED_Gaming & 4kTV for oled_displays; PS5, xbox & buildapc for ssd_storage; "
                        "GTA6 & gaming for cpg_beverages and gaming_peripherals."
                    ),
                    suggested_next_call={
                        "vertical": parsed.vertical,
                        "subreddits": ["GTA6", "PS5", "OLED_Gaming", "gaming"],
                    },
                ).model_dump(mode="json")

            signals.sort(key=lambda s: s.intent_score, reverse=True)
            overall = round(sum(s.intent_score for s in signals) / len(signals), 1)
            if overall >= 80.0:
                tier = "tier_1_immediate"
            elif overall >= 60.0:
                tier = "tier_2_test"
            else:
                tier = "tier_3_monitor"

            report = AdvertiserOpportunityReport(
                vertical=parsed.vertical,
                overall_opportunity_score=overall,
                priority_tier=tier,  # type: ignore[arg-type]
                subreddit_breakdown=signals,
                cited_thread_ids=list(dict.fromkeys(all_cited)),
            )
            return report.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Tool 3: audit_subreddit_brand_safety_risks
    # ------------------------------------------------------------------

    def audit_subreddit_brand_safety_risks(
        self,
        subreddits: list[str],
        advertiser_sensitivity: str,
    ) -> dict[str, Any]:
        """Audit GTA VI Reddit communities for GARM-aligned brand-safety risks.

        Inspects active discussions for refund waves, game-breaking crash outrage,
        severe toxicity, and excessive profanity, returning structured risk
        findings with thread citations and whether a campaign pause is advised.

        Args:
            subreddits: Non-empty list of up to 8 subreddit names to audit
                (e.g., ['GTA6', 'xbox', 'PS5', 'OLED_Gaming']).
            advertiser_sensitivity: Brand tolerance threshold — must be either
                'standard' or 'strict' (strict escalates medium technical outrage).

        Returns:
            JSON-serializable dict matching `BrandSafetyAuditResult` on success,
            or `ToolErrorResponse` with recovery instructions on error.
        """
        with traced_span(
            "copilot.tool.audit_subreddit_brand_safety_risks",
            {
                "copilot.sensitivity": advertiser_sensitivity,
                "copilot.subreddit_count": len(subreddits),
            },
        ):
            try:
                parsed = BrandSafetyAuditInput(
                    subreddits=subreddits,
                    advertiser_sensitivity=advertiser_sensitivity,  # type: ignore[arg-type]
                )
            except ValidationError as exc:
                return ToolErrorResponse(
                    error_code="INVALID_AUDIT_REQUEST",
                    message=f"Brand-safety audit validation failed: {exc.errors()[0]['msg']}",
                    recovery_instructions=(
                        "Retry `audit_subreddit_brand_safety_risks` with `advertiser_sensitivity` "
                        "set to 'standard' or 'strict' and 1-8 supported subreddit names."
                    ),
                    suggested_next_call={
                        "subreddits": ["GTA6", "xbox", "PS5", "OLED_Gaming"],
                        "advertiser_sensitivity": "standard",
                    },
                ).model_dump(mode="json")

            findings: list[BrandSafetyFinding] = []
            audited: list[str] = []
            risky_subs: set[str] = set()

            for sub in parsed.subreddits:
                try:
                    _, threads = self.reddit_client.fetch_discussions(
                        subreddit=sub, topic_filter="all", limit=10
                    )
                except ValueError:
                    continue
                if not threads:
                    continue
                canonical_sub = threads[0].subreddit
                audited.append(canonical_sub)

                for thread in threads:
                    for tag in thread.tags:
                        if tag not in _GARM_TAG_MAP:
                            continue
                        garm_category, base_severity, mitigation = _GARM_TAG_MAP[tag]
                        severity = base_severity
                        if (
                            parsed.advertiser_sensitivity == "strict"
                            and base_severity == "medium"
                        ):
                            severity = "high"

                        risky_subs.add(canonical_sub)
                        findings.append(
                            BrandSafetyFinding(
                                thread_id=thread.thread_id,
                                subreddit=canonical_sub,
                                garm_category=garm_category,
                                severity=severity,  # type: ignore[arg-type]
                                evidence_summary=(
                                    f"Thread '{thread.title}' ({thread.comments_per_hour} comments/hr, "
                                    f"sentiment {thread.sentiment_score:+.2f}) triggered {garm_category}."
                                ),
                                recommended_mitigation=mitigation,
                            )
                        )

            if not audited:
                return ToolErrorResponse(
                    error_code="NO_VALID_SUBREDDITS_AUDITED",
                    message=f"None of {parsed.subreddits} matched monitored subreddits.",
                    recovery_instructions=(
                        f"Retry with valid subreddits from {list(SUPPORTED_SUBREDDITS)}."
                    ),
                    suggested_next_call={
                        "subreddits": ["GTA6", "xbox", "PS5"],
                        "advertiser_sensitivity": parsed.advertiser_sensitivity,
                    },
                ).model_dump(mode="json")

            overall_risk = "low"
            for finding in findings:
                if _RISK_RANK[finding.severity] > _RISK_RANK[overall_risk]:
                    overall_risk = finding.severity

            safe_subreddits = [sub for sub in audited if sub not in risky_subs]
            result = BrandSafetyAuditResult(
                overall_risk_tier=overall_risk,  # type: ignore[arg-type]
                pause_recommended=overall_risk in {"high", "critical"},
                audited_subreddits=audited,
                findings=findings,
                safe_subreddits=safe_subreddits,
            )
            return result.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Tool 4: retrieve_historical_campaign_benchmarks
    # ------------------------------------------------------------------

    def retrieve_historical_campaign_benchmarks(
        self,
        query: str,
        vertical: str,
        top_k: int,
    ) -> dict[str, Any]:
        """Retrieve persisted cross-session campaign and brand-safety benchmarks.

        Queries the persistent SQLite / Vertex AI Memory Bank repository for
        earlier launch-week snapshots so the copilot can compute trend deltas
        across sessions.

        Args:
            query: Natural-language search query describing the trend or risk
                to compare (e.g., 'Xbox Series S crash risk baseline').
            vertical: Advertiser vertical filter (e.g., 'oled_displays',
                'ssd_storage', 'console_hardware') or 'all'.
            top_k: Number of top matching historical snapshots to return (1-10).

        Returns:
            JSON-serializable dict matching `HistoricalBenchmarkResponse`, or
            `ToolErrorResponse` if arguments fail schema validation.
        """
        with traced_span(
            "copilot.tool.retrieve_historical_campaign_benchmarks",
            {"copilot.vertical": vertical, "copilot.top_k": top_k},
        ):
            try:
                parsed = HistoricalBenchmarkInput(
                    query=query, vertical=vertical, top_k=top_k
                )
            except ValidationError as exc:
                return ToolErrorResponse(
                    error_code="INVALID_BENCHMARK_QUERY",
                    message=f"Benchmark query failed validation: {exc.errors()[0]['msg']}",
                    recovery_instructions=(
                        "Provide a non-empty `query` (2-200 chars), a `vertical` string "
                        "(or 'all'), and `top_k` between 1 and 10."
                    ),
                    suggested_next_call={
                        "query": "GTA VI launch OLED SSD baseline",
                        "vertical": "all",
                        "top_k": 3,
                    },
                ).model_dump(mode="json")

            raw_matches = self.memory_store.search_benchmarks(
                query=parsed.query, vertical=parsed.vertical, top_k=parsed.top_k
            )
            entries = [HistoricalBenchmarkEntry(**item) for item in raw_matches]
            backend = (
                "vertex_ai_memory_bank+sqlite"
                if self.config.vertex_memory_bank_engine_id
                else "sqlite_persistent_store"
            )
            return HistoricalBenchmarkResponse(
                storage_backend=backend,
                matches=entries,
            ).model_dump(mode="json")

    # ------------------------------------------------------------------
    # Tool 5 (HITL-Gated): issue_campaign_pause_recommendation
    # ------------------------------------------------------------------

    def issue_campaign_pause_recommendation(
        self,
        advertiser_name: str,
        vertical: str,
        affected_subreddits: list[str],
        severity: str,
        rationale: str,
        cited_thread_ids: list[str],
        tool_context: Any,
    ) -> dict[str, Any]:
        """Issue a high-stakes brand-safety campaign pause recommendation (HITL-gated).

        Pauses execution via ADK `ToolConfirmation` (`request_confirmation`) so
        a human account lead MUST review and explicitly approve the advertiser,
        subreddits, severity, and cited threads before any alert is dispatched.

        Args:
            advertiser_name: Client or advertiser brand name (e.g., 'BrandX Audio').
            vertical: Advertiser vertical ('oled_displays', 'ssd_storage',
                'console_hardware', 'gaming_peripherals', or 'cpg_beverages').
            affected_subreddits: Subreddits where placements should be paused.
            severity: Risk severity justifying the pause ('high' or 'critical').
            rationale: Evidence-backed explanation of the brand-safety risk.
            cited_thread_ids: Non-empty list of verifiable Reddit thread IDs.

        Returns:
            JSON-serializable dict matching `HitlActionResult` indicating whether
            the pause alert is awaiting human confirmation, dispatched, or rejected.
        """
        with traced_span(
            "copilot.tool.issue_campaign_pause_recommendation",
            {"copilot.vertical": vertical, "copilot.severity": severity},
        ):
            try:
                parsed = CampaignPauseInput(
                    advertiser_name=advertiser_name,
                    vertical=vertical,  # type: ignore[arg-type]
                    affected_subreddits=affected_subreddits,
                    severity=severity,  # type: ignore[arg-type]
                    rationale=self.redactor.redact_text(rationale),
                    cited_thread_ids=cited_thread_ids,
                )
            except ValidationError as exc:
                return ToolErrorResponse(
                    error_code="INVALID_PAUSE_PAYLOAD",
                    message=f"Campaign pause request failed schema validation: {exc.errors()[0]['msg']}",
                    recovery_instructions=(
                        "Supply a valid `advertiser_name`, supported `vertical`, at least one "
                        "affected subreddit, `severity` ('high' or 'critical'), a rationale of "
                        "at least 15 characters, and verifiable `cited_thread_ids`."
                    ),
                ).model_dump(mode="json")

            action_id = f"pause_{uuid.uuid4().hex[:10]}"
            confirmation = getattr(tool_context, "tool_confirmation", None)

            if confirmation is None:
                prompt = (
                    f"HUMAN APPROVAL REQUIRED: Issue {parsed.severity.upper()} brand-safety "
                    f"campaign pause recommendation for '{parsed.advertiser_name}' "
                    f"({parsed.vertical}) across {', '.join(parsed.affected_subreddits)}? "
                    f"Cited evidence: {', '.join(parsed.cited_thread_ids)}."
                )
                request_fn = getattr(tool_context, "request_confirmation", None)
                if callable(request_fn):
                    request_fn(
                        hint=prompt,
                        payload={
                            "action_id": action_id,
                            "advertiser_name": parsed.advertiser_name,
                            "vertical": parsed.vertical,
                            "affected_subreddits": parsed.affected_subreddits,
                            "severity": parsed.severity,
                            "cited_thread_ids": parsed.cited_thread_ids,
                        },
                    )
                _LOGGER.info(
                    "hitl_confirmation_requested",
                    action_id=action_id,
                    action_type="campaign_pause_recommendation",
                    advertiser_name=parsed.advertiser_name,
                    severity=parsed.severity,
                )
                return HitlActionResult(
                    status="awaiting_human_confirmation",
                    action_type="campaign_pause_recommendation",
                    action_id=action_id,
                    confirmation_prompt=prompt,
                    summary="Execution paused pending explicit human account-lead approval.",
                ).model_dump(mode="json")

            if not getattr(confirmation, "confirmed", False):
                _LOGGER.info(
                    "hitl_action_rejected",
                    action_id=action_id,
                    action_type="campaign_pause_recommendation",
                    advertiser_name=parsed.advertiser_name,
                )
                return HitlActionResult(
                    status="rejected_by_human",
                    action_type="campaign_pause_recommendation",
                    action_id=action_id,
                    summary=(
                        f"Human reviewer declined campaign pause recommendation for "
                        f"'{parsed.advertiser_name}'. No external alert was sent."
                    ),
                ).model_dump(mode="json")

            webhook_url = self.secrets.get_secret(
                self.config.secret_name_alert_webhook_url,
                env_fallback="ALERT_WEBHOOK_URL",
            )
            channel = "secret_manager_webhook" if webhook_url else "local_audit_sink"
            _LOGGER.info(
                "campaign_pause_recommendation_dispatched",
                action_id=action_id,
                advertiser_name=parsed.advertiser_name,
                vertical=parsed.vertical,
                affected_subreddits=parsed.affected_subreddits,
                severity=parsed.severity,
                delivery_channel=channel,
            )
            return HitlActionResult(
                status="dispatched",
                action_type="campaign_pause_recommendation",
                action_id=action_id,
                delivery_channel=channel,
                summary=(
                    f"Approved & dispatched {parsed.severity.upper()} pause alert for "
                    f"'{parsed.advertiser_name}' on {', '.join(parsed.affected_subreddits)} "
                    f"citing {', '.join(parsed.cited_thread_ids)}."
                ),
            ).model_dump(mode="json")

    # ------------------------------------------------------------------
    # Tool 6 (HITL-Gated): dispatch_advertiser_pitch_brief
    # ------------------------------------------------------------------

    def dispatch_advertiser_pitch_brief(
        self,
        advertiser_name: str,
        vertical: str,
        target_subreddits: list[str],
        executive_summary: str,
        recommended_budget_shift_pct: int,
        cited_thread_ids: list[str],
        tool_context: Any,
    ) -> dict[str, Any]:
        """Publish an executive advertiser opportunity pitch brief (HITL-gated).

        Pauses execution via ADK `ToolConfirmation` (`request_confirmation`) so
        a human account lead MUST review and approve the budget-shift proposal
        and citations before the brief is published externally.

        Args:
            advertiser_name: Client brand name receiving the pitch brief.
            vertical: Advertiser vertical ('oled_displays', 'ssd_storage',
                'console_hardware', 'gaming_peripherals', or 'cpg_beverages').
            target_subreddits: Subreddits recommended for incremental ad spend.
            executive_summary: Grounded executive narrative summarizing insights.
            recommended_budget_shift_pct: Recommended budget reallocation (0-100).
            cited_thread_ids: Non-empty list of verifiable Reddit thread IDs.

        Returns:
            JSON-serializable dict matching `HitlActionResult` showing pending
            confirmation, dispatched status, or human rejection.
        """
        with traced_span(
            "copilot.tool.dispatch_advertiser_pitch_brief",
            {
                "copilot.vertical": vertical,
                "copilot.budget_shift_pct": recommended_budget_shift_pct,
            },
        ):
            try:
                parsed = PitchBriefInput(
                    advertiser_name=advertiser_name,
                    vertical=vertical,  # type: ignore[arg-type]
                    target_subreddits=target_subreddits,
                    executive_summary=self.redactor.redact_text(executive_summary),
                    recommended_budget_shift_pct=recommended_budget_shift_pct,
                    cited_thread_ids=cited_thread_ids,
                )
            except ValidationError as exc:
                return ToolErrorResponse(
                    error_code="INVALID_PITCH_BRIEF",
                    message=f"Pitch brief payload failed validation: {exc.errors()[0]['msg']}",
                    recovery_instructions=(
                        "Provide a valid `advertiser_name`, supported `vertical`, 1-8 target "
                        "subreddits, an `executive_summary` (20-1200 chars), "
                        "`recommended_budget_shift_pct` (0-100), and verifiable `cited_thread_ids`."
                    ),
                ).model_dump(mode="json")

            action_id = f"brief_{uuid.uuid4().hex[:10]}"
            confirmation = getattr(tool_context, "tool_confirmation", None)

            if confirmation is None:
                prompt = (
                    f"HUMAN APPROVAL REQUIRED: Dispatch advertiser pitch brief to "
                    f"'{parsed.advertiser_name}' ({parsed.vertical}, +{parsed.recommended_budget_shift_pct}% "
                    f"budget shift into {', '.join(parsed.target_subreddits)})?"
                )
                request_fn = getattr(tool_context, "request_confirmation", None)
                if callable(request_fn):
                    request_fn(
                        hint=prompt,
                        payload={
                            "action_id": action_id,
                            "advertiser_name": parsed.advertiser_name,
                            "vertical": parsed.vertical,
                            "target_subreddits": parsed.target_subreddits,
                            "recommended_budget_shift_pct": parsed.recommended_budget_shift_pct,
                            "cited_thread_ids": parsed.cited_thread_ids,
                        },
                    )
                _LOGGER.info(
                    "hitl_confirmation_requested",
                    action_id=action_id,
                    action_type="advertiser_pitch_brief",
                    advertiser_name=parsed.advertiser_name,
                )
                return HitlActionResult(
                    status="awaiting_human_confirmation",
                    action_type="advertiser_pitch_brief",
                    action_id=action_id,
                    confirmation_prompt=prompt,
                    summary="Pitch brief paused pending explicit human account-lead sign-off.",
                ).model_dump(mode="json")

            if not getattr(confirmation, "confirmed", False):
                _LOGGER.info(
                    "hitl_action_rejected",
                    action_id=action_id,
                    action_type="advertiser_pitch_brief",
                    advertiser_name=parsed.advertiser_name,
                )
                return HitlActionResult(
                    status="rejected_by_human",
                    action_type="advertiser_pitch_brief",
                    action_id=action_id,
                    summary=(
                        f"Human reviewer cancelled pitch brief dispatch for "
                        f"'{parsed.advertiser_name}'."
                    ),
                ).model_dump(mode="json")

            webhook_url = self.secrets.get_secret(
                self.config.secret_name_alert_webhook_url,
                env_fallback="ALERT_WEBHOOK_URL",
            )
            channel = "secret_manager_webhook" if webhook_url else "local_audit_sink"
            _LOGGER.info(
                "advertiser_pitch_brief_dispatched",
                action_id=action_id,
                advertiser_name=parsed.advertiser_name,
                vertical=parsed.vertical,
                target_subreddits=parsed.target_subreddits,
                budget_shift_pct=parsed.recommended_budget_shift_pct,
                delivery_channel=channel,
            )
            return HitlActionResult(
                status="dispatched",
                action_type="advertiser_pitch_brief",
                action_id=action_id,
                delivery_channel=channel,
                summary=(
                    f"Approved & dispatched pitch brief for '{parsed.advertiser_name}' "
                    f"(+{parsed.recommended_budget_shift_pct}% shift into "
                    f"{', '.join(parsed.target_subreddits)})."
                ),
            ).model_dump(mode="json")
