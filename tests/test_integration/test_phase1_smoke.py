"""
End-to-end Phase 1 smoke test:
1. Seed historical snapshots
2. Insert a new snapshot representing a significant jump
3. Run the rule engine
4. Assert alerts appear via the API
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.db.models import MetricSnapshot
from src.db.repositories import insert_alert, insert_snapshots
from src.ingestion.base import MetricRecord
from src.rules.engine import RuleEngine


@pytest.mark.asyncio
async def test_phase1_pipeline_writes_snapshot_and_alert(
    test_app, test_session_factory
):
    now = datetime.now(tz=timezone.utc)

    async with test_session_factory() as session:
        old_record = MetricRecord(
            scope="core",
            entity="mantle",
            metric_name="tvl",
            value=Decimal("1_000_000_000"),
            unit="usd",
            source_platform="defillama",
            source_ref=None,
            collected_at=now - timedelta(days=8),
        )
        await insert_snapshots(session, [old_record])
        await session.commit()

    async with test_session_factory() as session:
        new_record = MetricRecord(
            scope="core",
            entity="mantle",
            metric_name="tvl",
            value=Decimal("1_250_000_000"),
            unit="usd",
            source_platform="defillama",
            source_ref=None,
            collected_at=now,
        )
        new_snapshots = await insert_snapshots(session, [new_record])
        await session.commit()

    async with test_session_factory() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(MetricSnapshot)
            .where(MetricSnapshot.collected_at == now)
        )
        current_snapshots = list(result.scalars().all())
        assert len(current_snapshots) == 1

        engine = RuleEngine(session)
        candidates = await engine.evaluate(current_snapshots)

        for c in candidates:
            await insert_alert(
                session,
                scope=c.scope,
                entity=c.entity,
                metric_name=c.metric_name,
                current_value=c.current_value,
                previous_value=c.previous_value,
                time_window=c.time_window,
                change_pct=c.change_pct,
                severity=c.severity,
                trigger_reason=c.trigger_reason,
                detected_at=now,
                is_ath=c.is_ath,
                is_milestone=c.is_milestone,
                milestone_label=c.milestone_label,
                cooldown_until=c.cooldown_until,
                reviewed=False,
                ai_eligible=False,
                created_at=now,
            )
        await session.commit()

    response = test_app.get("/api/alerts")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0

    alert_reasons = [a["trigger_reason"] for a in data["alerts"]]
    has_threshold = any("threshold" in r for r in alert_reasons)
    has_ath = any(r == "new_ath" for r in alert_reasons)
    has_milestone = any("milestone" in r for r in alert_reasons)
    assert has_threshold or has_ath or has_milestone, (
        f"Expected at least one alert type, got: {alert_reasons}"
    )


@pytest.mark.asyncio
async def test_health_endpoint_works(test_app):
    response = test_app.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_metrics_endpoint_works_empty(test_app):
    response = test_app.get("/api/metrics/latest")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_rule_engine_skips_token_level_stablecoin_breakdown_alerts(
    test_session_factory,
):
    now = datetime.now(tz=timezone.utc)

    async with test_session_factory() as session:
        old_records = [
            MetricRecord(
                scope="core",
                entity="mantle:USDT",
                metric_name="stablecoin_transfer_volume",
                value=Decimal("1000000"),
                unit="usd",
                source_platform="dune",
                source_ref=None,
                collected_at=now - timedelta(days=8),
            ),
            MetricRecord(
                scope="core",
                entity="mantle:USDT",
                metric_name="stablecoin_transfer_tx_count",
                value=Decimal("100"),
                unit="count",
                source_platform="dune",
                source_ref=None,
                collected_at=now - timedelta(days=8),
            ),
        ]
        await insert_snapshots(session, old_records)
        await session.commit()

    async with test_session_factory() as session:
        current_records = [
            MetricRecord(
                scope="core",
                entity="mantle:USDT",
                metric_name="stablecoin_transfer_volume",
                value=Decimal("1500000"),
                unit="usd",
                source_platform="dune",
                source_ref=None,
                collected_at=now,
            ),
            MetricRecord(
                scope="core",
                entity="mantle:USDT",
                metric_name="stablecoin_transfer_tx_count",
                value=Decimal("150"),
                unit="count",
                source_platform="dune",
                source_ref=None,
                collected_at=now,
            ),
        ]
        await insert_snapshots(session, current_records)
        await session.commit()

    async with test_session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(MetricSnapshot).where(MetricSnapshot.collected_at == now)
        )
        current_snapshots = list(result.scalars().all())

        candidates = await RuleEngine(session).evaluate(current_snapshots)

        assert candidates == []


@pytest.mark.asyncio
async def test_watchlist_refresh_seeds_data(test_app):
    response = test_app.post("/api/watchlist/refresh")
    assert response.status_code == 200

    response = test_app.get("/api/watchlist")
    data = response.json()
    assert len(data["protocols"]) > 0
    slugs = [p["slug"] for p in data["protocols"]]
    assert "aave-v3" in slugs
