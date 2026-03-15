import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import src.scheduler.__main__ as scheduler_cli
import src.scheduler.jobs as scheduler_jobs
from src.ingestion.dune import DuneCollector
from src.scheduler.jobs import build_scheduler, core_dune_job, load_scheduler_profile, run_job_now


def test_build_scheduler_registers_prod_cron_jobs():
    class FakeSettings:
        scheduler_profile = "prod"
        scheduler_config_path = "config/scheduler.toml"

    scheduler = build_scheduler(FakeSettings())
    schedules = scheduler.get_schedules()
    schedule_ids = {s.id for s in schedules}

    assert schedule_ids == {
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

    schedule_by_id = {schedule.id: schedule for schedule in schedules}
    assert isinstance(schedule_by_id["core_defillama"].trigger, CronTrigger)
    assert isinstance(schedule_by_id["source_health"].trigger, CronTrigger)


def test_build_scheduler_registers_interval_jobs_and_skips_manual_jobs():
    class FakeSettings:
        scheduler_profile = "dev_live"
        scheduler_config_path = "config/scheduler.toml"

    scheduler = build_scheduler(FakeSettings())
    schedules = scheduler.get_schedules()
    schedule_ids = {s.id for s in schedules}

    assert schedule_ids == {
        "core_l2beat",
        "core_coingecko",
        "source_health",
    }

    schedule_by_id = {schedule.id: schedule for schedule in schedules}
    assert isinstance(schedule_by_id["core_l2beat"].trigger, IntervalTrigger)
    assert isinstance(schedule_by_id["core_coingecko"].trigger, IntervalTrigger)
    assert isinstance(schedule_by_id["source_health"].trigger, IntervalTrigger)


def test_build_scheduler_skips_disabled_jobs(tmp_path):
    config_path = tmp_path / "scheduler.toml"
    config_path.write_text(
        """
active_profile = "ci"

[profiles.ci]
scheduler_enabled = false

[profiles.ci.jobs.core_defillama]
mode = "disabled"

[profiles.ci.jobs.source_health]
mode = "disabled"
""".strip(),
        encoding="utf-8",
    )

    class FakeSettings:
        scheduler_profile = "ci"
        scheduler_config_path = str(config_path)

    scheduler = build_scheduler(FakeSettings())

    assert scheduler.get_schedules() == []


def test_load_scheduler_profile_uses_toml_active_profile(tmp_path):
    config_path = tmp_path / "scheduler.toml"
    config_path.write_text(
        """
active_profile = "dev_live"

[profiles.prod.jobs.core_defillama]
mode = "cron"
hour = 10
minute = 0

[profiles.dev_live.jobs.core_defillama]
mode = "manual"
""".strip(),
        encoding="utf-8",
    )

    class FakeSettings:
        scheduler_profile = "prod"
        scheduler_config_path = str(config_path)

    profile_name, profile = load_scheduler_profile(FakeSettings(), use_default_profile=True)

    assert profile_name == "dev_live"
    assert profile["jobs"]["core_defillama"]["mode"] == "manual"


def test_load_scheduler_profile_allows_settings_override(tmp_path):
    config_path = tmp_path / "scheduler.toml"
    config_path.write_text(
        """
active_profile = "prod"

[profiles.prod.jobs.core_defillama]
mode = "cron"
hour = 10
minute = 0

[profiles.dev_live.jobs.core_defillama]
mode = "manual"
""".strip(),
        encoding="utf-8",
    )

    class FakeSettings:
        scheduler_profile = "dev_live"
        scheduler_config_path = str(config_path)

    profile_name, profile = load_scheduler_profile(FakeSettings())

    assert profile_name == "dev_live"
    assert profile["jobs"]["core_defillama"]["mode"] == "manual"


def test_load_scheduler_profile_rejects_unknown_profile(tmp_path):
    config_path = tmp_path / "scheduler.toml"
    config_path.write_text(
        """
active_profile = "prod"

[profiles.prod.jobs.core_defillama]
mode = "cron"
hour = 10
minute = 0
""".strip(),
        encoding="utf-8",
    )

    class FakeSettings:
        scheduler_profile = "missing"
        scheduler_config_path = str(config_path)

    with pytest.raises(ValueError, match="Unknown scheduler profile"):
        load_scheduler_profile(FakeSettings())


def test_load_scheduler_profile_rejects_unknown_job_ids(tmp_path):
    config_path = tmp_path / "scheduler.toml"
    config_path.write_text(
        """
active_profile = "prod"

[profiles.prod.jobs.not_a_real_job]
mode = "cron"
hour = 10
minute = 0
""".strip(),
        encoding="utf-8",
    )

    class FakeSettings:
        scheduler_profile = "prod"
        scheduler_config_path = str(config_path)

    with pytest.raises(ValueError, match="Unknown scheduler job id"):
        load_scheduler_profile(FakeSettings())


@pytest.mark.asyncio
async def test_run_job_now_dispatches_known_job(monkeypatch):
    captured = {}

    async def fake_job():
        captured["ran"] = True
        return {"status": "ok"}

    monkeypatch.setitem(scheduler_jobs.JOB_REGISTRY, "core_defillama", fake_job)

    class FakeSettings:
        scheduler_profile = "prod"
        scheduler_config_path = "config/scheduler.toml"

    result = await run_job_now("core_defillama", FakeSettings())

    assert result == {"status": "ok"}
    assert captured["ran"] is True


@pytest.mark.asyncio
async def test_run_job_now_rejects_unknown_job_id():
    class FakeSettings:
        scheduler_profile = "prod"
        scheduler_config_path = "config/scheduler.toml"

    with pytest.raises(ValueError, match="Unknown scheduler job id"):
        await run_job_now("not_a_real_job", FakeSettings())


@pytest.mark.asyncio
async def test_run_job_now_rejects_disabled_jobs(tmp_path):
    config_path = tmp_path / "scheduler.toml"
    config_path.write_text(
        """
active_profile = "ci"

[profiles.ci.jobs.core_defillama]
mode = "disabled"
""".strip(),
        encoding="utf-8",
    )

    class FakeSettings:
        scheduler_profile = "ci"
        scheduler_config_path = str(config_path)

    with pytest.raises(ValueError, match="disabled"):
        await run_job_now("core_defillama", FakeSettings())


def test_scheduler_cli_list_prints_job_modes(monkeypatch, capsys):
    class FakeSettings:
        scheduler_profile = "dev_live"
        scheduler_config_path = "config/scheduler.toml"

    monkeypatch.setattr(scheduler_cli, "Settings", lambda: FakeSettings())

    result = scheduler_cli.main(["list"])

    captured = capsys.readouterr()
    assert result == 0
    assert "Active profile: dev_live" in captured.out
    assert "core_defillama: manual" in captured.out
    assert "core_coingecko: interval" in captured.out


def test_scheduler_cli_run_dispatches_job(monkeypatch, capsys):
    class FakeSettings:
        scheduler_profile = "dev_live"
        scheduler_config_path = "config/scheduler.toml"

    monkeypatch.setattr(scheduler_cli, "Settings", lambda: FakeSettings())

    async def fake_run_job_now(job_id, settings):
        assert job_id == "core_defillama"
        assert settings.scheduler_profile == "dev_live"
        return {"status": "ok"}

    monkeypatch.setattr(scheduler_cli, "run_job_now", fake_run_job_now)

    result = scheduler_cli.main(["run", "core_defillama"])

    captured = capsys.readouterr()
    assert result == 0
    assert "{'status': 'ok'}" in captured.out


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
