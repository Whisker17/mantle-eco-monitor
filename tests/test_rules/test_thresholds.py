from decimal import Decimal

from src.rules.thresholds import classify_severity


def test_threshold_rule_emits_moderate_alert_for_15pct_growth():
    result = classify_severity(Decimal("0.15"), "tvl")
    assert result == "moderate"


def test_threshold_rule_emits_high_for_25pct():
    result = classify_severity(Decimal("0.25"), "tvl")
    assert result == "high"


def test_threshold_rule_emits_critical_for_35pct():
    result = classify_severity(Decimal("0.35"), "tvl")
    assert result == "critical"


def test_threshold_rule_emits_minor_for_12pct():
    result = classify_severity(Decimal("0.12"), "tvl")
    assert result == "minor"


def test_threshold_rule_returns_none_below_threshold():
    result = classify_severity(Decimal("0.05"), "tvl")
    assert result is None


def test_threshold_utilization_uses_tighter_thresholds():
    result = classify_severity(Decimal("0.06"), "utilization")
    assert result == "minor"  # >= 0.05 minor threshold

    result = classify_severity(Decimal("0.11"), "utilization")
    assert result == "moderate"  # >= 0.10 moderate threshold

    result = classify_severity(Decimal("0.04"), "utilization")
    assert result is None


def test_threshold_works_for_negative_changes():
    result = classify_severity(Decimal("-0.22"), "tvl")
    assert result == "high"
