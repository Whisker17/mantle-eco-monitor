from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import json

import pytest

from src.admin.collect import collect_job
from src.ingestion.base import MetricRecord
from src.scheduler.runtime import JobResult


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


@pytest.mark.asyncio
async def test_collect_job_run_result_is_json_serializable(monkeypatch):
    async def fake_run_job_now(job_id, settings):
        assert job_id == "core_defillama"
        return JobResult(status="success", records_collected=3, alerts_created=1)

    monkeypatch.setattr("src.admin.collect.run_job_now", fake_run_job_now)

    result = await collect_job("core_defillama", dry_run=False, settings=object())
    payload = json.dumps(result)

    assert '"mode": "run"' in payload
    assert '"status": "success"' in payload
