from decimal import Decimal

from config.thresholds import DEFAULT_THRESHOLDS


def classify_severity(change_pct: Decimal, metric_name: str) -> str | None:
    thresholds = DEFAULT_THRESHOLDS.get(metric_name, DEFAULT_THRESHOLDS["tvl"])
    abs_change = abs(change_pct)

    if abs_change >= Decimal(str(thresholds["critical"])):
        return "critical"
    if abs_change >= Decimal(str(thresholds["high"])):
        return "high"
    if abs_change >= Decimal(str(thresholds["moderate"])):
        return "moderate"
    if abs_change >= Decimal(str(thresholds["minor"])):
        return "minor"
    return None
