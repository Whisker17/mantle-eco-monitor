from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse


UTC_PLUS_8 = timezone(timedelta(hours=8))

METRIC_LABELS = {
    "tvl": "TVL (Total Value Locked)",
    "daily_active_users": "Daily Active Users",
    "chain_transactions": "Chain Transactions",
    "dex_volume": "DEX Volume",
    "stablecoin_supply": "Stablecoin Supply",
    "stablecoin_mcap": "Stablecoin Market Cap",
    "stablecoin_transfer_volume": "Stablecoin Transfer Volume",
    "stablecoin_transfer_tx_count": "Stablecoin Transfer Transaction Count",
    "mnt_market_cap": "MNT Market Cap",
    "mnt_volume": "MNT Volume",
    "tvs": "TVS (Total Value Secured)",
    "supply": "Supply",
    "borrowed": "Borrowed",
    "utilization": "Utilization",
    "volume": "Volume",
    "users": "Users",
}

SOURCE_LABELS = {
    "defillama": "DefiLlama",
    "l2beat": "L2BEAT",
    "growthepie": "growthepie",
    "coingecko": "CoinGecko",
    "dune": "Dune",
}

ACTION_REQUIRED_PLACEHOLDER = (
    "**Action Required:**\n"
    "- Social: Review alert context and refine for posting\n"
    "- Design: Prepare metric card or lightweight visual\n"
    "- Target post window: Within 6 hours of alert"
)


def _markdown_block(content: str) -> dict:
    return {
        "tag": "markdown",
        "content": content,
    }


def _base_card(title: str, blocks: list[str], *, template: str | None = None) -> dict:
    header = {
        "title": {
            "tag": "plain_text",
            "content": title,
        }
    }
    if template:
        header["template"] = template

    return {"header": header, "elements": [_markdown_block(block) for block in blocks]}


def _parse_decimal(value: str | int | float | Decimal | None) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _format_decimal(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _humanize_metric_name(metric_name: str) -> str:
    if metric_name in METRIC_LABELS:
        return METRIC_LABELS[metric_name]

    words = []
    for word in metric_name.split("_"):
        if word in {"dex", "tvl", "tvs", "mnt"}:
            words.append(word.upper())
        else:
            words.append(word.capitalize())
    return " ".join(words)


def _format_window(window: str | None) -> str:
    if not window:
        return "N/A"
    return window.upper()


def _is_downward(alert: dict) -> bool:
    change_pct = _parse_decimal(alert.get("change_pct"))
    if change_pct is not None:
        return change_pct < 0

    reason = (alert.get("trigger_reason") or "").lower()
    return reason.startswith("decline_") or " down " in f" {reason} " or "decline" in reason


def _is_upward(alert: dict) -> bool:
    change_pct = _parse_decimal(alert.get("change_pct"))
    if change_pct is not None:
        return change_pct > 0

    reason = (alert.get("trigger_reason") or "").lower()
    return reason.startswith("threshold_") or " up " in f" {reason} " or "surge" in reason


def _header_template(alert: dict) -> str:
    if alert.get("is_ath") or alert.get("is_milestone"):
        return "wathet"
    if _is_downward(alert):
        return "red"
    return "green"


def _format_movement(alert: dict) -> str:
    change_pct = _parse_decimal(alert.get("change_pct"))
    window = _format_window(alert.get("time_window"))
    if change_pct is None:
        return f"N/A ({window})"

    percent = change_pct * Decimal("100")
    sign = "+" if percent > 0 else ""
    return f"{sign}{_format_decimal(percent)}% ({window})"


def _format_detected(value: str | None) -> str:
    if not value:
        return "Unknown"

    detected_at = datetime.fromisoformat(value)
    if detected_at.tzinfo is None:
        detected_at = detected_at.replace(tzinfo=UTC)
    localized = detected_at.astimezone(UTC_PLUS_8)
    return f"{localized.strftime('%B')} {localized.day}, {localized.year} - {localized.strftime('%H:%M')} UTC+8"


def _guess_source_label(source_ref: str | None) -> str | None:
    if not source_ref:
        return None

    host = urlparse(source_ref).netloc.lower()
    if "defillama" in host or "llama.fi" in host:
        return "DefiLlama"
    if "l2beat" in host:
        return "L2BEAT"
    if "growthepie" in host:
        return "growthepie"
    if "coingecko" in host:
        return "CoinGecko"
    if "dune" in host:
        return "Dune"
    return None


def _format_source(alert: dict) -> str:
    source_platform = (alert.get("source_platform") or "").lower()
    source_label = SOURCE_LABELS.get(source_platform) or _guess_source_label(alert.get("source_ref"))
    source_ref = alert.get("source_ref")

    if source_label and source_ref:
        return f"{source_label} ({source_ref})"
    if source_label:
        return source_label
    if source_ref:
        return source_ref
    return "Unknown"


def _humanize_reason(reason: str | None) -> str:
    if not reason:
        return "MONITORED ALERT"
    return reason.replace("_", " ").upper()


def _derive_status(alert: dict) -> str:
    if alert.get("is_ath") or (alert.get("trigger_reason") or "").lower() == "new_ath":
        return "NEW ALL-TIME HIGH"
    if alert.get("is_milestone"):
        label = alert.get("milestone_label")
        if label:
            return f"MILESTONE REACHED: {label}"
        return "MILESTONE REACHED"
    if _is_downward(alert):
        return "SHARP DECLINE"
    if _is_upward(alert):
        return "SIGNIFICANT UPWARD MOVE"
    return _humanize_reason(alert.get("trigger_reason"))


def build_alert_card(alert: dict) -> dict:
    blocks = [
        f"**Metric:** {_humanize_metric_name(alert['metric_name'])}",
        f"**Movement:** {_format_movement(alert)}",
        f"**Current Value:** {alert.get('formatted_value') or alert.get('current_value', '')}",
        f"**Status:** {_derive_status(alert)}",
        f"**Source:** {_format_source(alert)}",
        f"**Detected:** {_format_detected(alert.get('detected_at'))}",
        "**Suggested Draft Copy:** Placeholder - draft copy not generated yet.",
        ACTION_REQUIRED_PLACEHOLDER,
    ]
    return _base_card("MANTLE METRICS ALERT", blocks, template=_header_template(alert))


def build_daily_summary_card(summary: dict) -> dict:
    blocks = [summary["summary_text"]]
    if summary.get("metrics"):
        metric_lines = [
            f"- {metric['metric_name']}: {metric.get('formatted_value') or metric.get('value', '')}"
            for metric in summary["metrics"]
        ]
        blocks.append("**Metrics**\n" + "\n".join(metric_lines))
    if summary.get("alerts"):
        alert_lines = [f"- {alert['trigger_reason']}" for alert in summary["alerts"]]
        blocks.append("**Alerts**\n" + "\n".join(alert_lines))

    source_urls = [
        entry["source_ref"]
        for entry in [*(summary.get("metrics") or []), *(summary.get("alerts") or [])]
        if entry.get("source_ref")
    ]
    if source_urls:
        blocks.append("**Sources**\n" + "\n".join(f"- {url}" for url in source_urls))

    return _base_card(summary["title"], blocks)


def build_bot_reply_card(*, answer: str, source_urls: list[str]) -> dict:
    blocks = [answer]
    if source_urls:
        blocks.append("**Sources**\n" + "\n".join(f"- {url}" for url in source_urls))
    return _base_card("Query Result", blocks)
