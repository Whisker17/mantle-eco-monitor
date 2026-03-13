from __future__ import annotations

from collections import defaultdict

from src.rules.engine import AlertCandidate


def check_multi_signal(candidates: list[AlertCandidate]) -> list[AlertCandidate]:
    by_entity: dict[str, list[AlertCandidate]] = defaultdict(list)
    for c in candidates:
        if c.severity in ("high", "critical"):
            by_entity[c.entity].append(c)

    combined: list[AlertCandidate] = []
    for entity, group in by_entity.items():
        if len(group) >= 2:
            metrics = ", ".join(sorted({c.metric_name for c in group}))
            combined.append(
                AlertCandidate(
                    scope=group[0].scope,
                    entity=entity,
                    metric_name="multi_signal",
                    current_value=group[0].current_value,
                    previous_value=None,
                    formatted_value=None,
                    time_window="combined",
                    change_pct=None,
                    severity="critical",
                    trigger_reason=f"multi_signal:{metrics}",
                    is_ath=False,
                    is_milestone=False,
                    milestone_label=None,
                    source_platform=None,
                    source_ref=None,
                )
            )
    return combined
