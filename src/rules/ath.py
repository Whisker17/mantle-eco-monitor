from __future__ import annotations

from decimal import Decimal

from src.db.models import MetricSnapshot
from src.rules.engine import AlertCandidate


def check_ath(
    snapshot: MetricSnapshot,
    historic_max: MetricSnapshot | None,
) -> list[AlertCandidate]:
    if historic_max is None or snapshot.value > historic_max.value:
        return [
            AlertCandidate(
                scope=snapshot.scope,
                entity=snapshot.entity,
                metric_name=snapshot.metric_name,
                current_value=snapshot.value,
                previous_value=historic_max.value if historic_max else None,
                formatted_value=None,
                time_window="all_time",
                change_pct=None,
                severity="critical",
                trigger_reason="new_ath",
                is_ath=True,
                is_milestone=False,
                milestone_label=None,
                source_platform=snapshot.source_platform,
                source_ref=snapshot.source_ref,
            )
        ]
    return []
