from __future__ import annotations

from decimal import Decimal

from config.milestones import MILESTONES
from src.db.models import MetricSnapshot
from src.ingestion.normalize import format_usd
from src.rules.engine import AlertCandidate


def check_milestones(
    snapshot: MetricSnapshot,
    previous: MetricSnapshot | None,
) -> list[AlertCandidate]:
    thresholds = MILESTONES.get(snapshot.metric_name, [])
    if not thresholds or previous is None:
        return []

    crossed = [
        m for m in thresholds
        if previous.value < m <= snapshot.value
    ]

    return [
        AlertCandidate(
            scope=snapshot.scope,
            entity=snapshot.entity,
            metric_name=snapshot.metric_name,
            current_value=snapshot.value,
            previous_value=previous.value,
            formatted_value=None,
            time_window="milestone",
            change_pct=None,
            severity="high",
            trigger_reason=f"milestone_{format_usd(Decimal(str(m)))}",
            is_ath=False,
            is_milestone=True,
            milestone_label=format_usd(Decimal(str(m))),
            source_platform=snapshot.source_platform,
            source_ref=snapshot.source_ref,
        )
        for m in crossed
    ]
