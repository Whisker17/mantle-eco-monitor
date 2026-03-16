from __future__ import annotations

from src.admin.inspect import inspect_alerts, inspect_overview, inspect_runs, inspect_snapshots


async def test_inspect_overview_returns_table_counts_and_recent_rows(seeded_session):
    result = await inspect_overview(seeded_session)

    assert result["counts"] == {
        "metric_snapshots": 2,
        "alert_events": 1,
        "source_runs": 1,
        "watchlist_protocols": 1,
    }
    assert result["snapshots"][0]["entity"] == "mantle"
    assert result["snapshots"][0]["metric_name"] == "tvl"
    assert result["alerts"][0]["severity"] == "high"
    assert result["runs"][0]["job_name"] == "core_defillama"


async def test_inspect_snapshots_filters_by_entity_metric_and_limit(seeded_session):
    result = await inspect_snapshots(seeded_session, entity="mantle", metric="tvl", limit=1)

    assert len(result["snapshots"]) == 1
    assert result["snapshots"][0]["entity"] == "mantle"
    assert result["snapshots"][0]["metric_name"] == "tvl"
    assert result["snapshots"][0]["value"] == "1500"


async def test_inspect_alerts_filters_by_entity_metric_and_limit(seeded_session):
    result = await inspect_alerts(seeded_session, entity="mantle", metric="tvl", limit=1)

    assert len(result["alerts"]) == 1
    assert result["alerts"][0]["entity"] == "mantle"
    assert result["alerts"][0]["metric_name"] == "tvl"
    assert result["alerts"][0]["severity"] == "high"


async def test_inspect_runs_filters_by_source_and_limit(seeded_session):
    result = await inspect_runs(seeded_session, source="defillama", limit=1)

    assert len(result["runs"]) == 1
    assert result["runs"][0]["source_platform"] == "defillama"
    assert result["runs"][0]["job_name"] == "core_defillama"
