from __future__ import annotations


def _markdown_block(content: str) -> dict:
    return {
        "tag": "markdown",
        "content": content,
    }


def _base_card(title: str, blocks: list[str]) -> dict:
    return {
        "header": {
            "title": {
                "tag": "plain_text",
                "content": title,
            }
        },
        "elements": [_markdown_block(block) for block in blocks],
    }


def build_alert_card(alert: dict) -> dict:
    blocks = [
        f"**Metric:** {alert['metric_name']}",
        f"**Value:** {alert.get('formatted_value') or alert.get('current_value', '')}",
        f"**Window:** {alert['time_window']}",
        f"**Severity:** {alert['severity']}",
        f"**Reason:** {alert['trigger_reason']}",
    ]
    if alert.get("source_ref"):
        blocks.append(f"**Source:** {alert['source_ref']}")
    return _base_card(f"Alert: {alert['entity']} {alert['metric_name']}", blocks)


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
