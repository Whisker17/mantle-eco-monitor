from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse


UTC_PLUS_8 = timezone(timedelta(hours=8))

METRIC_LABELS = {
    "tvl": "TVL (Total Value Locked)",
    "daily_active_users": "Daily Active Users (7D Rolling Average)",
    "active_addresses": "Active Addresses",
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

SOURCE_FALLBACK_URLS = {
    "defillama": "https://defillama.com/chain/Mantle",
    "l2beat": "https://l2beat.com/scaling/projects/mantle",
    "growthepie": "https://www.growthepie.xyz/chains/mantle",
    "coingecko": "https://www.coingecko.com/en/coins/mantle",
    "dune": "https://dune.com",
}

CATEGORY_LABELS = {
    "dex": "DEX",
    "lending": "Lending",
    "yield": "Yield",
    "bridge": "Bridge",
    "derivatives": "Derivatives",
    "index": "Index",
    "rwa": "RWA",
    "stablecoin": "Stablecoin",
    "liquid_staking": "Liquid Staking",
    "cdp": "CDP",
    "perps": "Perps",
}

ACTION_REQUIRED_PLACEHOLDER = (
    "**⚡ Action Required:**\n"
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


def _title_prefix(alert: dict) -> str:
    return "🔴" if _is_downward(alert) else "🟢"


def _format_movement(alert: dict) -> str:
    change_pct = _parse_decimal(alert.get("change_pct"))
    window = _format_window(alert.get("time_window"))
    if change_pct is None:
        return f"N/A ({window})"

    percent = change_pct * Decimal("100")
    sign = "+" if percent > 0 else ""
    return f"{sign}{percent.quantize(Decimal('0.01'))}% ({window})"


def _format_detected(value: str | None) -> str:
    if not value:
        return "Unknown"

    detected_at = datetime.fromisoformat(value)
    if detected_at.tzinfo is None:
        detected_at = detected_at.replace(tzinfo=UTC)
    localized = detected_at.astimezone(UTC_PLUS_8)
    return f"{localized.strftime('%B')} {localized.day}, {localized.year} - {localized.strftime('%H:%M')} SGT"


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

    if not source_ref and source_platform:
        source_ref = SOURCE_FALLBACK_URLS.get(source_platform)

    if source_label and source_ref:
        return f"{source_label} ({source_ref})"
    if source_label:
        return source_label
    if source_ref:
        return source_ref
    return "Unknown"


def _compact_number(value: Decimal, *, currency: bool) -> str:
    abs_value = abs(value)
    suffix = ""
    divisor = Decimal("1")
    if abs_value >= Decimal("1000000000000"):
        suffix = "T"
        divisor = Decimal("1000000000000")
    elif abs_value >= Decimal("1000000000"):
        suffix = "B"
        divisor = Decimal("1000000000")
    elif abs_value >= Decimal("1000000"):
        suffix = "M"
        divisor = Decimal("1000000")
    elif abs_value >= Decimal("1000"):
        suffix = "K"
        divisor = Decimal("1000")

    scaled = value / divisor
    prefix = "$" if currency else ""
    if suffix:
        return f"{prefix}~{scaled.quantize(Decimal('0.1'))}{suffix}"
    return f"{prefix}{_format_decimal(value)}"


def _looks_like_currency(text: str) -> bool:
    return "$" in text or text.lower().endswith(("m", "b", "k", "t")) and "$" in text


def _is_currency_metric(metric_name: str) -> bool:
    return metric_name in {
        "tvl",
        "dex_volume",
        "stablecoin_supply",
        "stablecoin_mcap",
        "stablecoin_transfer_volume",
        "mnt_market_cap",
        "mnt_volume",
        "tvs",
        "supply",
        "borrowed",
        "volume",
    }


def _format_current_value(alert: dict) -> str:
    formatted_value = alert.get("formatted_value")
    if formatted_value:
        return str(formatted_value)

    raw = _parse_decimal(alert.get("current_value"))
    if raw is None:
        return ""
    return _compact_number(raw, currency=_is_currency_metric(alert["metric_name"]))


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


def _is_ecosystem_alert(alert: dict) -> bool:
    scope = alert.get("scope", "")
    if scope:
        return scope == "ecosystem"
    return alert.get("entity", "mantle") != "mantle"


def _format_entity_title(alert: dict) -> str:
    if not _is_ecosystem_alert(alert):
        return "MANTLE METRICS ALERT"
    display_name = alert.get("display_name") or _humanize_entity(alert.get("entity", ""))
    return f"{display_name.upper()} \u2014 MANTLE ECO ALERT"


def _format_protocol_line(alert: dict) -> str | None:
    if not _is_ecosystem_alert(alert):
        return None
    display_name = alert.get("display_name") or _humanize_entity(alert.get("entity", ""))
    category = alert.get("category", "")
    category_label = CATEGORY_LABELS.get(category, category.capitalize()) if category else ""
    if category_label:
        return f"**\U0001f3e2 Protocol:** {display_name} ({category_label})"
    return f"**\U0001f3e2 Protocol:** {display_name}"


def build_alert_card(alert: dict) -> dict:
    movement_icon = "📉" if _is_downward(alert) else "📈"
    blocks: list[str] = []
    protocol_line = _format_protocol_line(alert)
    if protocol_line:
        blocks.append(protocol_line)
    blocks.extend([
        f"**📊 Metric:** {_humanize_metric_name(alert['metric_name'])}",
        f"**{movement_icon} Movement:** {_format_movement(alert)}",
        f"**💰 Current Value:** {_format_current_value(alert)}",
        f"**🏆 Status:** {_derive_status(alert)}",
        f"**📡 Source:** {_format_source(alert)}",
        f"**⏰ Detected:** {_format_detected(alert.get('detected_at'))}",
        "**✍️ Suggested Draft Copy:** Placeholder - draft copy not generated yet.",
        ACTION_REQUIRED_PLACEHOLDER,
    ])
    return _base_card(
        f"{_title_prefix(alert)} {_format_entity_title(alert)}",
        blocks,
        template=_header_template(alert),
    )


def build_consolidated_alert_card(alerts: list[dict]) -> dict:
    metric_alerts = [a for a in alerts if a.get("metric_name") != "multi_signal"]
    if not metric_alerts:
        metric_alerts = alerts

    if len(metric_alerts) == 1:
        return build_alert_card(metric_alerts[0])

    by_metric: dict[str, dict] = {}
    for alert in metric_alerts:
        key = alert["metric_name"]
        if key not in by_metric:
            by_metric[key] = alert

    primary = metric_alerts[0]
    has_downward = any(_is_downward(a) for a in metric_alerts)
    primary_for_header = next((a for a in metric_alerts if _is_downward(a)), primary) if has_downward else primary

    blocks: list[str] = []

    protocol_line = _format_protocol_line(primary)
    if protocol_line:
        blocks.append(protocol_line)

    if len(by_metric) == 1:
        rep = list(by_metric.values())[0]
        movement_icon = "📉" if _is_downward(rep) else "📈"
        blocks.append(f"**📊 Metric:** {_humanize_metric_name(rep['metric_name'])}")

        unique_windows = {a.get("time_window") for a in metric_alerts}
        if len(unique_windows) > 1:
            movements = [_format_movement(a) for a in metric_alerts]
            blocks.append(f"**{movement_icon} Movement:** " + " / ".join(movements))
        else:
            blocks.append(f"**{movement_icon} Movement:** {_format_movement(rep)}")

        blocks.append(f"**💰 Current Value:** {_format_current_value(rep)}")
        blocks.append(f"**🏆 Status:** {_derive_status(rep)}")
    else:
        signal_lines = []
        for alert in by_metric.values():
            name = _humanize_metric_name(alert["metric_name"])
            movement = _format_movement(alert)
            value = _format_current_value(alert)
            signal_lines.append(f"▸ **{name}:** {movement} → {value}")
        blocks.append("**📊 Signals Detected:**\n" + "\n".join(signal_lines))
        blocks.append(f"**🏆 Status:** {_derive_consolidated_status(alerts)}")

    reasons = sorted({a.get("trigger_reason", "") for a in alerts if a.get("trigger_reason")})
    blocks.append("**🔔 Triggers:** " + ", ".join(reasons))

    blocks.append(f"**📡 Source:** {_format_source(primary)}")
    blocks.append(f"**⏰ Detected:** {_format_detected(primary.get('detected_at'))}")
    blocks.append("**✍️ Suggested Draft Copy:** Placeholder - draft copy not generated yet.")
    blocks.append(ACTION_REQUIRED_PLACEHOLDER)

    return _base_card(
        f"{_title_prefix(primary_for_header)} {_format_entity_title(primary_for_header)}",
        blocks,
        template=_header_template(primary_for_header),
    )


def _derive_consolidated_status(alerts: list[dict]) -> str:
    has_multi = any(
        (a.get("trigger_reason") or "").startswith("multi_signal") for a in alerts
    )
    if has_multi:
        return "MULTI-SIGNAL ALERT"
    if any(a.get("is_ath") for a in alerts):
        return "NEW ALL-TIME HIGH"
    if any(a.get("is_milestone") for a in alerts):
        labels = [a.get("milestone_label") for a in alerts if a.get("milestone_label")]
        if labels:
            return f"MILESTONE REACHED: {labels[0]}"
        return "MILESTONE REACHED"
    if any(_is_downward(a) for a in alerts):
        return "SHARP DECLINE"
    if any(_is_upward(a) for a in alerts):
        return "SIGNIFICANT UPWARD MOVE"
    return "MONITORED ALERT"


def _categorize_summary_metrics(
    metrics: list[dict],
) -> dict[str, list[dict]]:
    core: list[dict] = []
    stablecoin: list[dict] = []
    ecosystem: list[dict] = []
    for metric in metrics:
        scope = metric.get("scope", "")
        name = metric.get("metric_name", "")
        if scope == "ecosystem":
            ecosystem.append(metric)
        elif name.startswith("stablecoin_"):
            stablecoin.append(metric)
        else:
            core.append(metric)
    return {"core": core, "stablecoin": stablecoin, "ecosystem": ecosystem}


def _summary_metric_value(metric: dict) -> str:
    if metric.get("formatted_value"):
        return str(metric["formatted_value"])
    raw = _parse_decimal(metric.get("value"))
    if raw is None:
        return str(metric.get("value", ""))
    return _compact_number(raw, currency=_is_currency_metric(metric.get("metric_name", "")))


def _summary_source_label(metric: dict) -> str:
    platform = (metric.get("source_platform") or "").lower()
    return SOURCE_LABELS.get(platform) or _guess_source_label(metric.get("source_ref")) or ""


def _humanize_entity(entity: str) -> str:
    return " ".join(
        word.upper() if word.lower() in {"tvl", "tvs", "dex", "mnt", "v3", "v2"} else word.capitalize()
        for word in entity.replace("-", " ").replace("_", " ").split()
    )


def _render_core_or_stablecoin_block(title: str, metrics: list[dict]) -> str:
    lines = [f"**{title}**"]
    for metric in metrics:
        label = _humanize_metric_name(metric["metric_name"])
        value = _summary_metric_value(metric)
        source = _summary_source_label(metric)
        source_part = f"  ({source})" if source else ""
        lines.append(f"- {label}: {value}{source_part}")
    return "\n".join(lines)


def _render_ecosystem_block(metrics: list[dict]) -> str:
    by_entity: dict[str, list[dict]] = {}
    for metric in metrics:
        by_entity.setdefault(metric.get("entity", "unknown"), []).append(metric)

    entity_entries: list[tuple[Decimal, str, str]] = []
    for entity, group in by_entity.items():
        tvl_metric = next((m for m in group if m.get("metric_name") == "tvl"), None)
        sort_value = _parse_decimal((tvl_metric or group[0]).get("value")) or Decimal("0")

        parts: list[str] = []
        tvl_first = sorted(group, key=lambda m: (0 if m.get("metric_name") == "tvl" else 1, m.get("metric_name", "")))
        for m in tvl_first:
            parts.append(f"{_humanize_metric_name(m['metric_name'])}: {_summary_metric_value(m)}")

        source = _summary_source_label(group[0])
        source_part = f"  ({source})" if source else ""
        line = f"- {_humanize_entity(entity)}: {', '.join(parts)}{source_part}"
        entity_entries.append((sort_value, entity, line))

    entity_entries.sort(key=lambda e: e[0], reverse=True)

    lines = ["**Ecosystem Protocols**"]
    lines.extend(line for _, _, line in entity_entries)
    return "\n".join(lines)


def _format_summary_alerts(alerts: list[dict]) -> str:
    real_alerts = [a for a in alerts if not (a.get("trigger_reason") or "").startswith("multi_signal")]
    multi_signals = [a for a in alerts if (a.get("trigger_reason") or "").startswith("multi_signal")]

    by_key: dict[tuple[str, str], list[dict]] = {}
    for alert in real_alerts:
        key = (alert.get("entity", ""), alert.get("metric_name", ""))
        by_key.setdefault(key, []).append(alert)

    lines = ["**Alerts**"]
    for (entity, metric_name), group in by_key.items():
        entity_label = _humanize_entity(entity) if entity else "Unknown"
        metric_label = _humanize_metric_name(metric_name)
        parts: list[str] = []
        for a in group:
            change_pct = _parse_decimal(a.get("change_pct"))
            window = _format_window(a.get("time_window"))
            severity = a.get("severity", "")
            reason = a.get("trigger_reason", "")

            if a.get("is_milestone"):
                parts.append(f"{reason} ({severity})")
            elif a.get("is_ath"):
                parts.append(f"new ATH ({severity})")
            elif change_pct is not None:
                pct = change_pct * Decimal("100")
                sign = "+" if pct > 0 else ""
                parts.append(f"{sign}{pct.quantize(Decimal('0.01'))}% ({window}), {severity}")
            else:
                parts.append(f"{reason} ({severity})")

        lines.append(f"- {entity_label} / {metric_label}: {' | '.join(parts)}")

    if multi_signals:
        reasons = sorted({a.get("trigger_reason", "") for a in multi_signals})
        lines.append(f"- Multi-signal: {', '.join(reasons)}")

    return "\n".join(lines)


def build_daily_summary_card(summary: dict) -> dict:
    blocks = [summary["summary_text"]]

    metrics = summary.get("metrics") or []
    if metrics:
        categories = _categorize_summary_metrics(metrics)
        if categories["core"]:
            blocks.append(_render_core_or_stablecoin_block("Core Metrics", categories["core"]))
        if categories["stablecoin"]:
            blocks.append(_render_core_or_stablecoin_block("Stablecoin", categories["stablecoin"]))
        if categories["ecosystem"]:
            blocks.append(_render_ecosystem_block(categories["ecosystem"]))

    alerts = summary.get("alerts") or []
    if alerts:
        blocks.append(_format_summary_alerts(alerts))

    return _base_card(summary["title"], blocks)


def build_bot_reply_card(*, answer: str, source_urls: list[str]) -> dict:
    blocks = [answer]
    if source_urls:
        blocks.append("**Sources**\n" + "\n".join(f"- {url}" for url in source_urls))
    return _base_card("Query Result", blocks)
