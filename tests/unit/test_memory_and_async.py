"""Unit tests for persistent SQLite campaign memory and async background consolidation."""

from __future__ import annotations

import asyncio

import pytest

from app.memory.async_consolidator import AsyncMemoryConsolidator, MemoryConsolidationJob
from app.memory.store import CampaignMemoryStore
from app.security.pii_redactor import PiiRedactor


def test_persistent_campaign_memory_survives_reopen_and_redacts_pii(tmp_path) -> None:
    db_file = str(tmp_path / "benchmarks.db")
    redactor = PiiRedactor(enable_cloud_dlp=False)

    store1 = CampaignMemoryStore(db_path=db_file, redactor=redactor)
    snap_id = store1.save_snapshot(
        vertical="ssd_storage",
        summary="2TB NVMe SSD surge on r/PS5; contact u/buyer_42 or buyer@example.com.",
        opportunity_score=91.5,
        risk_tier="low",
        session_id="sess_persist_01",
    )
    store1.close()

    # Reopen a brand new connection to verify true cross-session disk persistence
    store2 = CampaignMemoryStore(db_path=db_file, redactor=redactor)
    results = store2.search_benchmarks(
        query="2TB NVMe SSD surge PS5", vertical="ssd_storage", top_k=2
    )
    store2.close()

    assert any(r["snapshot_id"] == snap_id for r in results)
    top = next(r for r in results if r["snapshot_id"] == snap_id)
    assert "buyer@example.com" not in top["summary"]
    assert "u/buyer_42" not in top["summary"]
    assert "[REDACTED_EMAIL]" in top["summary"]


@pytest.mark.asyncio
async def test_async_memory_consolidator_runs_non_blocking_in_background(tmp_path) -> None:
    db_file = str(tmp_path / "async_memory.db")
    store = CampaignMemoryStore(db_path=db_file, redactor=PiiRedactor())
    consolidator = AsyncMemoryConsolidator(store=store)

    task = consolidator.enqueue_non_blocking(
        MemoryConsolidationJob(
            session_id="sess_async_01",
            vertical="oled_displays",
            raw_summary="OLED TV upgrade surge reported by u/hdr_lover in r/OLED_Gaming.",
            opportunity_score=89.0,
            risk_tier="low",
        )
    )
    assert isinstance(task, asyncio.Task)
    await consolidator.flush(timeout_seconds=5.0)
    assert consolidator.processed_count == 1

    matches = store.search_benchmarks(
        query="OLED TV upgrade surge", vertical="oled_displays", top_k=3
    )
    assert any("OLED TV upgrade surge" in m["summary"] for m in matches)
    assert all("u/hdr_lover" not in m["summary"] for m in matches)
    store.close()
