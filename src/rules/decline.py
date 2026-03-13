from __future__ import annotations

from decimal import Decimal

from src.db.models import MetricSnapshot
from src.rules.engine import AlertCandidate


def check_decline(
    snapshot: MetricSnapshot,
    anchor: MetricSnapshot | None,
    window: str,
) -> list[AlertCandidate]:
    if anchor is None or anchor.value == 0:
        return []

    change_pct = (snapshot.value - anchor.value) / anchor.value
    if change_pct <= Decimal("-0.20"):
        return [
            AlertCandidate(
                scope=snapshot.scope,
                entity=snapshot.entity,
                metric_name=snapshot.metric_name,
                current_value=snapshot.value,
                previous_value=anchor.value,
                formatted_value=None,
                time_window=window,
                change_pct=change_pct,
                severity="critical",
                trigger_reason=f"decline_{int(abs(change_pct) * 100)}pct_{window}",
                is_ath=False,
                is_milestone=False,
                milestone_label=None,
                source_platform=snapshot.source_platform,
                source_ref=snapshot.source_ref,
            )
        ]
    return []
