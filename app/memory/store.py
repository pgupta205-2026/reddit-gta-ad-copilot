"""Persistent session state & cross-session campaign benchmark memory store.

Provides:
1. `CampaignMemoryStore`: SQLite-backed persistent benchmark repository with
   lexical TF-cosine similarity retrieval (zero external vector DB setup
   required locally, automatic PII scrubbing before every write, seeded with
   Launch-Eve Day-0 baselines).
2. ADK service factories (`create_session_service`, `create_memory_service`)
   supporting local SQLite (`DatabaseSessionService`), Cloud SQL Postgres,
   `VertexAiSessionService`, and `VertexAiMemoryBankService`.
"""

from __future__ import annotations

import math
import re
import sqlite3
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import CopilotConfig
from app.observability.logging import get_logger
from app.security.pii_redactor import PiiRedactor

_LOGGER = get_logger(__name__)
_TOKEN_RE = re.compile(r"[a-z0-9_]+")

_SEED_BENCHMARKS: tuple[dict[str, Any], ...] = (
    {
        "snapshot_id": "snap_launch_eve_oled_01",
        "recorded_at": "2026-11-19T05:00:00+00:00",
        "vertical": "oled_displays",
        "summary": (
            "Launch-Eve baseline: OLED TV and QD-OLED monitor purchase intent surged "
            "across r/OLED_Gaming and r/4kTV following HDR preview impressions. "
            "Brand-safety risk remained low across hardware communities."
        ),
        "opportunity_score": 78.5,
        "risk_tier": "low",
    },
    {
        "snapshot_id": "snap_launch_eve_ssd_02",
        "recorded_at": "2026-11-19T05:00:00+00:00",
        "vertical": "ssd_storage",
        "summary": (
            "Launch-Eve baseline: Pre-load reveal of ~212 GB GTA VI install size "
            "triggered strong 2TB NVMe SSD upgrade questions in r/PS5 and r/buildapc."
        ),
        "opportunity_score": 82.0,
        "risk_tier": "low",
    },
    {
        "snapshot_id": "snap_launch_eve_xbox_03",
        "recorded_at": "2026-11-19T05:00:00+00:00",
        "vertical": "console_hardware",
        "summary": (
            "Launch-Eve baseline: Xbox Series S stability concerns began surfacing "
            "during staggered midnight regional unlock; moderate refund chatter in r/xbox."
        ),
        "opportunity_score": 61.0,
        "risk_tier": "medium",
    },
    {
        "snapshot_id": "snap_launch_eve_cpg_04",
        "recorded_at": "2026-11-19T05:00:00+00:00",
        "vertical": "cpg_beverages",
        "summary": (
            "Launch-Eve baseline: High celebratory launch-weekend snack and energy drink "
            "mentions in r/GTA6 and r/gaming, offset by sporadic subreddit lag reports."
        ),
        "opportunity_score": 74.0,
        "risk_tier": "medium",
    },
)


def _tokenize(text: str) -> Counter[str]:
    return Counter(_TOKEN_RE.findall(text.lower()))


def _cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left).intersection(right)
    dot = sum(left[tok] * right[tok] for tok in shared)
    norm_l = math.sqrt(sum(v * v for v in left.values()))
    norm_r = math.sqrt(sum(v * v for v in right.values()))
    if norm_l == 0.0 or norm_r == 0.0:
        return 0.0
    return round(min(1.0, max(0.0, dot / (norm_l * norm_r))), 4)


@dataclass
class CampaignMemoryStore:
    """SQLite persistent store for cross-session advertiser & brand-safety memory."""

    db_path: str = "./data/campaign_memory.db"
    redactor: PiiRedactor | None = None

    def __post_init__(self) -> None:
        if self.redactor is None:
            self.redactor = PiiRedactor()
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._seed_if_empty()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS campaign_benchmarks (
                    snapshot_id TEXT PRIMARY KEY,
                    recorded_at TEXT NOT NULL,
                    vertical TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    opportunity_score REAL NOT NULL,
                    risk_tier TEXT NOT NULL,
                    session_id TEXT
                )
                """
            )

    def _seed_if_empty(self) -> None:
        cur = self._conn.execute("SELECT COUNT(*) AS cnt FROM campaign_benchmarks")
        row = cur.fetchone()
        if row is not None and int(row["cnt"]) > 0:
            return
        with self._conn:
            for item in _SEED_BENCHMARKS:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO campaign_benchmarks
                        (snapshot_id, recorded_at, vertical, summary, opportunity_score, risk_tier, session_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["snapshot_id"],
                        item["recorded_at"],
                        item["vertical"],
                        item["summary"],
                        item["opportunity_score"],
                        item["risk_tier"],
                        "seed_launch_eve",
                    ),
                )

    def save_snapshot(
        self,
        *,
        vertical: str,
        summary: str,
        opportunity_score: float,
        risk_tier: str,
        session_id: str | None = None,
    ) -> str:
        """PII-redact and persist a new campaign memory snapshot."""
        assert self.redactor is not None
        redaction = self.redactor.redact_with_report(summary)
        snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
        recorded_at = datetime.now(timezone.utc).isoformat()

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO campaign_benchmarks
                    (snapshot_id, recorded_at, vertical, summary, opportunity_score, risk_tier, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    recorded_at,
                    vertical,
                    redaction.redacted_text,
                    float(opportunity_score),
                    risk_tier,
                    session_id,
                ),
            )

        _LOGGER.info(
            "campaign_memory_snapshot_persisted",
            snapshot_id=snapshot_id,
            vertical=vertical,
            risk_tier=risk_tier,
            pii_redactions=redaction.findings_count,
            pii_backend=redaction.backend,
        )
        return snapshot_id

    def search_benchmarks(
        self,
        *,
        query: str,
        vertical: str = "all",
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Retrieve top-K semantically relevant historical campaign benchmarks."""
        if vertical and vertical.lower() != "all":
            rows = self._conn.execute(
                "SELECT * FROM campaign_benchmarks WHERE vertical = ? ORDER BY recorded_at DESC",
                (vertical,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM campaign_benchmarks ORDER BY recorded_at DESC"
            ).fetchall()

        query_vec = _tokenize(query)
        scored: list[dict[str, Any]] = []
        for row in rows:
            doc_text = f"{row['vertical']} {row['risk_tier']} {row['summary']}"
            sim = _cosine_similarity(query_vec, _tokenize(doc_text))
            scored.append(
                {
                    "snapshot_id": str(row["snapshot_id"]),
                    "recorded_at": str(row["recorded_at"]),
                    "vertical": str(row["vertical"]),
                    "summary": str(row["summary"]),
                    "opportunity_score": float(row["opportunity_score"]),
                    "risk_tier": str(row["risk_tier"]),
                    "similarity_score": sim,
                }
            )

        scored.sort(key=lambda r: (r["similarity_score"], r["recorded_at"]), reverse=True)
        return scored[:top_k]

    def close(self) -> None:
        """Close the underlying SQLite connection cleanly."""
        self._conn.close()


def create_session_service(config: CopilotConfig) -> Any:
    """Create the configured ADK persistent session service.

    Uses `DatabaseSessionService` (SQLite locally or Cloud SQL Postgres in GCP)
    so conversational history and state survive restarts across turns.
    """
    from google.adk.sessions import DatabaseSessionService, InMemorySessionService

    if config.session_db_url:
        if config.session_db_url.startswith("sqlite"):
            db_file = config.session_db_url.split("///", 1)[-1]
            if db_file and db_file != ":memory:":
                Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        return DatabaseSessionService(db_url=config.session_db_url)
    return InMemorySessionService()


def create_memory_service(config: CopilotConfig) -> Any:
    """Create the configured ADK long-term memory service.

    Uses `VertexAiMemoryBankService` when deployed with an Agent Engine Memory
    Bank ID, falling back to `InMemoryMemoryService` for local development.
    """
    if config.vertex_memory_bank_engine_id and config.gcp_project_id:
        from google.adk.memory import VertexAiMemoryBankService

        return VertexAiMemoryBankService(
            project=config.gcp_project_id,
            location=config.gcp_location,
            agent_engine_id=config.vertex_memory_bank_engine_id,
        )

    from google.adk.memory import InMemoryMemoryService

    return InMemoryMemoryService()
