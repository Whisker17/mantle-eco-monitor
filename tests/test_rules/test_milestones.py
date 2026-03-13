from decimal import Decimal
from unittest.mock import MagicMock

from src.rules.milestones import check_milestones


def _make_snapshot(value, metric_name="tvl", entity="mantle"):
    s = MagicMock()
    s.scope = "core"
    s.entity = entity
    s.metric_name = metric_name
    s.value = Decimal(str(value))
    s.source_platform = "defillama"
    s.source_ref = None
    return s


def test_milestone_crossing_emits_alert():
    current = _make_snapshot(1_100_000_000)
    previous = _make_snapshot(900_000_000)

    alerts = check_milestones(current, previous)

    assert len(alerts) == 1
    assert alerts[0].is_milestone is True
    assert "$1.00B" in alerts[0].milestone_label


def test_no_milestone_when_not_crossed():
    current = _make_snapshot(800_000_000)
    previous = _make_snapshot(700_000_000)

    alerts = check_milestones(current, previous)
    assert len(alerts) == 0


def test_multiple_milestones_crossed():
    current = _make_snapshot(2_100_000_000, metric_name="tvl")
    previous = _make_snapshot(1_400_000_000, metric_name="tvl")

    alerts = check_milestones(current, previous)
    assert len(alerts) == 2  # 1.5B and 2B


def test_no_milestone_without_previous():
    current = _make_snapshot(1_100_000_000)
    alerts = check_milestones(current, None)
    assert len(alerts) == 0
