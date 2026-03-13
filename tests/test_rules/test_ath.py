from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.rules.ath import check_ath


def _make_snapshot(value, metric_name="tvl", entity="mantle"):
    s = MagicMock()
    s.scope = "core"
    s.entity = entity
    s.metric_name = metric_name
    s.value = Decimal(str(value))
    s.source_platform = "defillama"
    s.source_ref = None
    return s


def test_new_ath_rule_emits_priority_override_alert():
    current = _make_snapshot(1_600_000_000)
    historic_max = _make_snapshot(1_500_000_000)

    alerts = check_ath(current, historic_max)

    assert len(alerts) == 1
    assert alerts[0].severity == "critical"
    assert alerts[0].trigger_reason == "new_ath"
    assert alerts[0].is_ath is True


def test_no_ath_alert_when_below_max():
    current = _make_snapshot(1_400_000_000)
    historic_max = _make_snapshot(1_500_000_000)

    alerts = check_ath(current, historic_max)
    assert len(alerts) == 0


def test_ath_alert_when_no_history():
    current = _make_snapshot(100)
    alerts = check_ath(current, None)

    assert len(alerts) == 1
    assert alerts[0].is_ath is True
