from __future__ import annotations

from src.scheduler.runtime import JobResult


def test_bootstrap_initial_history_job_order_covers_core_dune_and_ecosystem():
    from src.admin.bootstrap import INITIAL_HISTORY_JOB_ORDER

    assert INITIAL_HISTORY_JOB_ORDER == [
        "watchlist_refresh",
        "core_defillama_history",
        "core_growthepie_history",
        "core_l2beat_history",
        "core_dune_history",
        "core_coingecko_history",
        "eco_aave_history",
        "eco_protocols_history",
    ]


async def test_bootstrap_initial_history_dry_run_reports_job_plan(session_factory):
    from src.admin.bootstrap import bootstrap_initial_history

    result = await bootstrap_initial_history(
        session_factory,
        settings=object(),
        apply=False,
    )

    assert result["apply"] is False
    assert result["jobs"] == [
        "watchlist_refresh",
        "core_defillama_history",
        "core_growthepie_history",
        "core_l2beat_history",
        "core_dune_history",
        "core_coingecko_history",
        "eco_aave_history",
        "eco_protocols_history",
    ]


async def test_bootstrap_initial_history_apply_runs_jobs_in_order(session_factory, monkeypatch):
    from src.admin.bootstrap import bootstrap_initial_history

    calls: list[str] = []

    async def fake_run_bootstrap_job(job_id, *, settings, session_factory):
        calls.append(job_id)
        return JobResult(status="success", records_collected=1, alerts_created=0)

    monkeypatch.setattr("src.admin.bootstrap._run_bootstrap_job", fake_run_bootstrap_job)

    result = await bootstrap_initial_history(
        session_factory,
        settings=object(),
        apply=True,
    )

    assert result["apply"] is True
    assert list(result["job_results"]) == calls
    assert calls == result["jobs"]
