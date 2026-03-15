from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import MetricSnapshot
from src.db.repositories import TimeWindow, get_comparison_snapshot, get_previous_snapshot
from src.rules.thresholds import classify_severity


@dataclass
class AlertCandidate:
    scope: str
    entity: str
    metric_name: str
    current_value: Decimal
    previous_value: Decimal | None
    formatted_value: str | None
    time_window: str
    change_pct: Decimal | None
    severity: str
    trigger_reason: str
    is_ath: bool = False
    is_milestone: bool = False
    milestone_label: str | None = None
    source_platform: str | None = None
    source_ref: str | None = None
    cooldown_until: datetime | None = None


class RuleEngine:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def evaluate(
        self, current_snapshots: list[MetricSnapshot]
    ) -> list[AlertCandidate]:
        from src.rules.ath import check_ath
        from src.rules.cooldown import apply_cooldown
        from src.rules.decline import check_decline
        from src.rules.milestones import check_milestones
        from src.rules.multi_signal import check_multi_signal

        candidates: list[AlertCandidate] = []

        for snapshot in current_snapshots:
            if self._skip_alerts_for_snapshot(snapshot):
                continue

            candidates.extend(await self._check_thresholds(snapshot))

            historic_max = await get_comparison_snapshot(
                self.session, snapshot.entity, snapshot.metric_name, TimeWindow.ATH
            )
            candidates.extend(check_ath(snapshot, historic_max))

            previous = await get_previous_snapshot(
                self.session, snapshot.entity, snapshot.metric_name
            )
            candidates.extend(check_milestones(snapshot, previous))

            for window in [TimeWindow.D7, TimeWindow.MTD]:
                anchor = await get_comparison_snapshot(
                    self.session, snapshot.entity, snapshot.metric_name, window
                )
                candidates.extend(check_decline(snapshot, anchor, window.value))

        candidates.extend(check_multi_signal(candidates))
        return await apply_cooldown(candidates, self.session)

    def _skip_alerts_for_snapshot(self, snapshot: MetricSnapshot) -> bool:
        return (
            snapshot.entity.startswith("mantle:")
            and snapshot.metric_name in {
                "stablecoin_transfer_volume",
                "stablecoin_transfer_tx_count",
            }
        )

    async def _check_thresholds(
        self, snapshot: MetricSnapshot
    ) -> list[AlertCandidate]:
        results: list[AlertCandidate] = []
        for window in [TimeWindow.D7, TimeWindow.MTD]:
            anchor = await get_comparison_snapshot(
                self.session, snapshot.entity, snapshot.metric_name, window
            )
            if anchor is None or anchor.value == 0:
                continue
            change_pct = (snapshot.value - anchor.value) / anchor.value
            severity = classify_severity(change_pct, snapshot.metric_name)
            if severity is None:
                continue

            results.append(
                AlertCandidate(
                    scope=snapshot.scope,
                    entity=snapshot.entity,
                    metric_name=snapshot.metric_name,
                    current_value=snapshot.value,
                    previous_value=anchor.value,
                    formatted_value=None,
                    time_window=window.value,
                    change_pct=change_pct,
                    severity=severity,
                    trigger_reason=f"threshold_{int(abs(change_pct) * 100)}pct_{window.value}",
                    source_platform=snapshot.source_platform,
                    source_ref=snapshot.source_ref,
                )
            )
        return results
