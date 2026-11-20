"""Non-blocking asynchronous memory consolidation worker.

Expensive memory extraction, PII scrubbing, and persistence execute on a
background `asyncio.Task` queue triggered after an agent turn completes so
user-facing responses return immediately with zero UI blocking.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.memory.store import CampaignMemoryStore
from app.observability.logging import get_logger
from app.observability.tracing import traced_span

_LOGGER = get_logger(__name__)


@dataclass(frozen=True)
class MemoryConsolidationJob:
    """Payload describing one background memory consolidation unit of work."""

    session_id: str
    vertical: str
    raw_summary: str
    opportunity_score: float
    risk_tier: str


@dataclass
class AsyncMemoryConsolidator:
    """Background asyncio queue draining memory consolidation jobs off the hot path."""

    store: CampaignMemoryStore
    _pending_tasks: set[asyncio.Task[Any]] = field(default_factory=set, init=False, repr=False)
    _processed_count: int = field(default=0, init=False)

    @property
    def processed_count(self) -> int:
        """Total number of background consolidation jobs completed."""
        return self._processed_count

    def enqueue_non_blocking(self, job: MemoryConsolidationJob) -> asyncio.Task[str]:
        """Schedule memory consolidation as a non-blocking background asyncio task.

        Returns immediately to the caller so agent turn latency is unaffected.
        """
        task = asyncio.create_task(
            self._consolidate(job),
            name=f"memory-consolidate-{job.session_id}",
        )
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)
        _LOGGER.info(
            "async_memory_job_enqueued",
            session_id=job.session_id,
            vertical=job.vertical,
            pending_jobs=len(self._pending_tasks),
        )
        return task

    async def _consolidate(self, job: MemoryConsolidationJob) -> str:
        """Run PII scrubbing and SQLite write off the event loop via asyncio.to_thread."""
        with traced_span(
            "copilot.memory_consolidate",
            {
                "copilot.session_id": job.session_id,
                "copilot.vertical": job.vertical,
                "copilot.risk_tier": job.risk_tier,
            },
        ):
            compact_summary = " ".join(job.raw_summary.split())[:600]
            snapshot_id = await asyncio.to_thread(
                self.store.save_snapshot,
                vertical=job.vertical,
                summary=compact_summary,
                opportunity_score=job.opportunity_score,
                risk_tier=job.risk_tier,
                session_id=job.session_id,
            )
            self._processed_count += 1
            _LOGGER.info(
                "async_memory_job_completed",
                session_id=job.session_id,
                snapshot_id=snapshot_id,
                vertical=job.vertical,
            )
            return snapshot_id

    async def flush(self, timeout_seconds: float = 5.0) -> None:
        """Await all in-flight background memory tasks (for graceful shutdown/tests)."""
        if not self._pending_tasks:
            return
        tasks = list(self._pending_tasks)
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=timeout_seconds,
        )
