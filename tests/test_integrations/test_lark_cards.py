from __future__ import annotations

from datetime import UTC, datetime

from src.integrations.lark.cards import (
    build_alert_card,
    build_bot_reply_card,
    build_daily_summary_card,
)


def _markdown_text_blocks(card: dict) -> list[str]:
    return [element["content"] for element in card["elements"] if element["tag"] == "markdown"]


def test_build_alert_card_formats_upward_alert_in_prd_layout():
    card = build_alert_card(
        {
            "entity": "mantle",
            "metric_name": "tvl",
            "formatted_value": "$1.5B",
            "time_window": "7d",
            "change_pct": "0.25",
            "severity": "high",
            "trigger_reason": "threshold_25pct_7d",
            "source_platform": "defillama",
            "source_ref": "https://defillama.com/chain/Mantle",
            "detected_at": datetime(2026, 3, 15, 10, 0, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        }
    )

    text_blocks = _markdown_text_blocks(card)

    assert card["header"]["title"]["content"] == "🟢 MANTLE METRICS ALERT"
    assert card["header"]["template"] == "green"
    assert all("text" not in element for element in card["elements"] if element["tag"] == "markdown")
    assert text_blocks == [
        "**📊 Metric:** TVL (Total Value Locked)",
        "**📈 Movement:** +25.00% (7D)",
        "**💰 Current Value:** $1.5B",
        "**🏆 Status:** SIGNIFICANT UPWARD MOVE",
        "**📡 Source:** DefiLlama (https://defillama.com/chain/Mantle)",
        "**⏰ Detected:** March 15, 2026 - 18:00 SGT",
        '**✍️ Suggested Draft Copy:** Placeholder - draft copy not generated yet.',
        "**⚡ Action Required:**\n- Social: Review alert context and refine for posting\n- Design: Prepare metric card or lightweight visual\n- Target post window: Within 6 hours of alert",
    ]


def test_build_alert_card_uses_red_header_for_declines():
    card = build_alert_card(
        {
            "entity": "mantle",
            "metric_name": "daily_active_users",
            "formatted_value": "120K",
            "time_window": "1d",
            "change_pct": "-0.20",
            "severity": "high",
            "trigger_reason": "decline_20pct_1d",
            "source_platform": "growthepie",
            "source_ref": "https://api.growthepie.com",
            "detected_at": datetime(2026, 3, 15, 3, 30, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        }
    )

    text_blocks = _markdown_text_blocks(card)

    assert card["header"]["title"]["content"] == "🔴 MANTLE METRICS ALERT"
    assert card["header"]["template"] == "red"
    assert text_blocks[0] == "**📊 Metric:** Daily Active Users (7D Rolling Average)"
    assert text_blocks[1] == "**📉 Movement:** -20.00% (1D)"
    assert text_blocks[3] == "**🏆 Status:** SHARP DECLINE"


def test_build_alert_card_formats_ath_status_with_neutral_header():
    card = build_alert_card(
        {
            "entity": "mantle",
            "metric_name": "tvl",
            "formatted_value": "$755M+",
            "time_window": "7d",
            "change_pct": "0.66",
            "severity": "critical",
            "trigger_reason": "new_ath",
            "source_platform": "defillama",
            "source_ref": "https://defillama.com/chain/Mantle",
            "detected_at": datetime(2026, 3, 4, 1, 42, tzinfo=UTC).isoformat(),
            "is_ath": True,
            "is_milestone": False,
            "milestone_label": None,
        }
    )

    text_blocks = _markdown_text_blocks(card)

    assert card["header"]["title"]["content"] == "🟢 MANTLE METRICS ALERT"
    assert card["header"]["template"] == "wathet"
    assert text_blocks[1] == "**📈 Movement:** +66.00% (7D)"
    assert text_blocks[3] == "**🏆 Status:** NEW ALL-TIME HIGH"


def test_build_alert_card_compacts_raw_value_for_readability():
    card = build_alert_card(
        {
            "entity": "mantle",
            "metric_name": "active_addresses",
            "formatted_value": None,
            "current_value": "45207521",
            "time_window": "7d",
            "change_pct": "-0.2684",
            "severity": "high",
            "trigger_reason": "decline_26pct_7d",
            "source_platform": "dune",
            "source_ref": "https://dune.com/queries/42",
            "detected_at": datetime(2026, 3, 15, 1, 42, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        }
    )

    text_blocks = _markdown_text_blocks(card)

    assert text_blocks[0] == "**📊 Metric:** Active Addresses"
    assert text_blocks[1] == "**📉 Movement:** -26.84% (7D)"
    assert text_blocks[2] == "**💰 Current Value:** ~45.2M"
    assert text_blocks[4] == "**📡 Source:** Dune (https://dune.com/queries/42)"
    assert text_blocks[5] == "**⏰ Detected:** March 15, 2026 - 09:42 SGT"


def test_build_daily_summary_card_includes_metrics_alerts_and_sources():
    card = build_daily_summary_card(
        {
            "title": "Mantle Daily Summary",
            "summary_text": "TVL and DEX volume both moved higher.",
            "metrics": [
                {
                    "metric_name": "tvl",
                    "formatted_value": "$1.5B",
                    "source_ref": "https://defillama.com/chain/Mantle",
                }
            ],
            "alerts": [
                {
                    "trigger_reason": "TVL up 25% in 7d",
                    "source_ref": "https://defillama.com/chain/Mantle",
                }
            ],
        }
    )

    text_blocks = _markdown_text_blocks(card)

    assert card["header"]["title"]["content"] == "Mantle Daily Summary"
    assert all("text" not in element for element in card["elements"] if element["tag"] == "markdown")
    assert any("TVL and DEX volume both moved higher." in block for block in text_blocks)
    assert any("tvl" in block and "$1.5B" in block for block in text_blocks)
    assert any("https://defillama.com/chain/Mantle" in block for block in text_blocks)


def test_build_bot_reply_card_includes_answer_and_source_urls():
    card = build_bot_reply_card(
        answer="Mantle TVL is $1.5B.",
        source_urls=[
            "https://defillama.com/chain/Mantle",
            "https://example.com/secondary",
        ],
    )

    text_blocks = _markdown_text_blocks(card)

    assert card["header"]["title"]["content"] == "Query Result"
    assert all("text" not in element for element in card["elements"] if element["tag"] == "markdown")
    assert any("Mantle TVL is $1.5B." in block for block in text_blocks)
    assert any("https://defillama.com/chain/Mantle" in block for block in text_blocks)
    assert any("https://example.com/secondary" in block for block in text_blocks)
