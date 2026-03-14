import pytest

from src.ingestion.dune import DuneCollector
from src.scheduler.jobs import build_scheduler, core_dune_job


def test_scheduler_registers_phase1_jobs():
    scheduler = build_scheduler()
    schedules = scheduler.get_schedules()
    schedule_ids = {s.id for s in schedules}

    expected_ids = {
        "core_defillama",
        "core_growthepie",
        "core_dune",
        "core_l2beat",
        "core_coingecko",
        "eco_protocols",
        "eco_aave",
        "watchlist_refresh",
        "source_health",
    }
    assert schedule_ids >= expected_ids


def test_scheduler_has_correct_count():
    scheduler = build_scheduler()
    schedules = scheduler.get_schedules()
    assert len(schedules) >= 9


@pytest.mark.asyncio
async def test_core_dune_job_uses_configured_dune_collector(monkeypatch):
    class FakeSettings:
        dune_api_key = "token"
        dune_stablecoin_volume_query_id = 123

    fake_session_factory = object()
    monkeypatch.setattr(
        "src.scheduler.jobs._get_runtime_dependencies",
        lambda: (FakeSettings(), fake_session_factory),
    )

    captured = {}

    async def fake_run_collection_job(job_name, collector, session_factory):
        captured["job_name"] = job_name
        captured["collector"] = collector
        captured["session_factory"] = session_factory
        return "ok"

    monkeypatch.setattr("src.scheduler.jobs.run_collection_job", fake_run_collection_job)

    result = await core_dune_job()

    assert result == "ok"
    assert captured["job_name"] == "core_dune"
    assert captured["session_factory"] is fake_session_factory
    assert isinstance(captured["collector"], DuneCollector)
    assert captured["collector"]._settings.dune_stablecoin_volume_query_id == 123
