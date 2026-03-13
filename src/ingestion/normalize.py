from decimal import Decimal


def format_usd(value: Decimal) -> str:
    abs_val = abs(value)
    if abs_val >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs_val >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if abs_val >= 1_000:
        return f"${value / 1_000:.2f}K"
    return f"${value:.2f}"


def format_count(value: Decimal) -> str:
    abs_val = abs(value)
    if abs_val >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs_val >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs_val >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(int(value))


def format_pct(value: Decimal) -> str:
    return f"{value * 100:.1f}%"
