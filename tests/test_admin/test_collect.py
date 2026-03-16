from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.admin.collect import collect_job
from src.ingestion.base import MetricRecord


@pytest.mark.asyncio
async def test_collect_job_rejects_unknown_job():
    with pytest.raises(ValueError, match="Unknown scheduler job id"):
        await collect_job("missing_job")


@pytest.mark.asyncio
async def test_collect_job_dry_run_collects_without_writing(monkeypatch):
    @dataclass
    class FakeCollector:
        async def collect(self):
            return [
                MetricRecord(
                    scope="core",
                    entity="mantle",
                    metric_name="tvl",
                    value=Decimal("1500"),
                    unit="usd",
                    source_platform="defillama",
                    source_ref="https://defillama.com/chain/Mantle",
                    collected_at=datetime(2026, 3, 16, tzinfo=UTC),
                )
            ]

    monkeypatch.setattr(
        "src.admin.collect._build_dry_run_collector",
        lambda job_id, settings=None, session_factory=None: FakeCollector(),
    )

    result = await collect_job("core_defillama", dry_run=True)

    assert result["mode"] == "dry_run"
    assert result["job_id"] == "core_defillama"
    assert result["records_collected"] == 1
    assert result["records"][0]["entity"] == "mantle"
    assert result["records"][0]["metric_name"] == "tvl"
