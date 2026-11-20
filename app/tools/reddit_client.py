"""Reddit Data API client with Secret Manager auth and fixture fallback.

All fetched thread titles and excerpts pass through `PiiRedactor` before being
returned to any agent or logged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import CopilotConfig
from app.data.gta6_reddit_fixtures import GTA6_LAUNCH_FIXTURES
from app.observability.logging import get_logger
from app.observability.tracing import traced_span
from app.schemas import SUPPORTED_SUBREDDITS, RedditThreadRecord
from app.security.pii_redactor import PiiRedactor
from app.security.secrets import SecretManagerProvider

_LOGGER = get_logger(__name__)


class RedditRateLimitError(RuntimeError):
    """Raised when Reddit Data API returns HTTP 429 Too Many Requests."""


class RedditAuthConfigError(RuntimeError):
    """Raised when live Reddit mode is requested without valid Secret Manager credentials."""


@dataclass
class RedditDiscussionClient:
    """Retrieves PII-redacted GTA VI discussions from Reddit API or launch fixtures."""

    config: CopilotConfig
    secrets: SecretManagerProvider
    redactor: PiiRedactor

    def fetch_discussions(
        self,
        *,
        subreddit: str,
        topic_filter: str,
        limit: int,
    ) -> tuple[str, list[RedditThreadRecord]]:
        """Fetch PII-redacted discussion threads from live Reddit API or fixtures."""
        normalized = subreddit.removeprefix("r/").removeprefix("/r/").strip()
        canonical_map = {name.lower(): name for name in SUPPORTED_SUBREDDITS}
        canonical_sub = canonical_map.get(normalized.lower())
        if canonical_sub is None:
            raise ValueError(f"Unsupported subreddit: {normalized}")

        with traced_span(
            "copilot.reddit_fetch",
            {
                "reddit.subreddit": canonical_sub,
                "reddit.mode": self.config.reddit_data_mode,
                "reddit.topic_filter": topic_filter,
            },
        ):
            if self.config.reddit_data_mode == "live":
                raw_records = self._fetch_from_live_reddit_api(
                    subreddit=canonical_sub, topic_filter=topic_filter, limit=limit
                )
                source = "reddit_live_api"
            else:
                raw_records = self._fetch_from_fixtures(
                    subreddit=canonical_sub, topic_filter=topic_filter, limit=limit
                )
                source = "gta6_launch_fixture"

            redacted_threads = [
                RedditThreadRecord(
                    thread_id=item["thread_id"],
                    subreddit=item["subreddit"],
                    title=self.redactor.redact_text(item["title"]),
                    permalink=item["permalink"],
                    upvotes=int(item["upvotes"]),
                    comment_count=int(item["comment_count"]),
                    comments_per_hour=float(item["comments_per_hour"]),
                    sentiment_score=float(item["sentiment_score"]),
                    top_excerpts=[
                        self.redactor.redact_text(excerpt)
                        for excerpt in item["top_excerpts"]
                    ],
                    tags=list(item["tags"]),
                )
                for item in raw_records
            ]
            return source, redacted_threads

    def _fetch_from_fixtures(
        self, *, subreddit: str, topic_filter: str, limit: int
    ) -> list[dict[str, Any]]:
        rows = list(GTA6_LAUNCH_FIXTURES.get(subreddit, []))
        needle = topic_filter.strip().lower()
        if needle and needle != "all":
            filtered = [
                row
                for row in rows
                if needle in row["title"].lower()
                or any(needle in excerpt.lower() for excerpt in row["top_excerpts"])
                or any(needle in tag.lower() for tag in row["tags"])
            ]
            rows = filtered
        return rows[:limit]

    def _fetch_from_live_reddit_api(
        self, *, subreddit: str, topic_filter: str, limit: int
    ) -> list[dict[str, Any]]:
        import httpx

        client_id = self.secrets.get_secret(
            self.config.secret_name_reddit_client_id,
            env_fallback="REDDIT_CLIENT_ID",
        )
        client_secret = self.secrets.get_secret(
            self.config.secret_name_reddit_client_secret,
            env_fallback="REDDIT_CLIENT_SECRET",
        )
        if not client_id or not client_secret:
            raise RedditAuthConfigError(
                "Reddit OAuth credentials not found in Secret Manager or environment."
            )

        headers = {"User-Agent": self.config.reddit_user_agent}
        with httpx.Client(timeout=10.0) as client:
            token_resp = client.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(client_id, client_secret),
                data={"grant_type": "client_credentials"},
                headers=headers,
            )
            if token_resp.status_code == 429:
                raise RedditRateLimitError("Reddit OAuth token endpoint rate limited (429).")
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            api_headers = {
                "Authorization": f"bearer {access_token}",
                "User-Agent": self.config.reddit_user_agent,
            }
            query = "GTA 6 OR GTA VI" if topic_filter.lower() == "all" else f"(GTA 6 OR GTA VI) {topic_filter}"
            resp = client.get(
                f"https://oauth.reddit.com/r/{subreddit}/search",
                params={"q": query, "restrict_sr": "on", "sort": "hot", "limit": limit},
                headers=api_headers,
            )
            if resp.status_code == 429:
                raise RedditRateLimitError(f"Reddit search endpoint rate limited for r/{subreddit}.")
            resp.raise_for_status()
            children = resp.json().get("data", {}).get("children", [])

        parsed: list[dict[str, Any]] = []
        for child in children:
            data = child.get("data", {})
            parsed.append(
                {
                    "thread_id": str(data.get("name") or f"t3_{data.get('id', 'unknown')}"),
                    "subreddit": subreddit,
                    "title": str(data.get("title", "")),
                    "permalink": str(data.get("permalink", f"/r/{subreddit}/")),
                    "upvotes": max(0, int(data.get("ups", 0))),
                    "comment_count": max(0, int(data.get("num_comments", 0))),
                    "comments_per_hour": round(max(1.0, float(data.get("num_comments", 1)) / 4.0), 1),
                    "sentiment_score": 0.0,
                    "top_excerpts": [str(data.get("selftext", ""))[:300]] if data.get("selftext") else [],
                    "tags": [topic_filter.lower()],
                }
            )
        _LOGGER.info(
            "reddit_live_api_fetch_completed",
            subreddit=subreddit,
            thread_count=len(parsed),
        )
        return parsed
