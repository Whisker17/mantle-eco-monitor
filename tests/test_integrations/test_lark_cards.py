from __future__ import annotations

from src.integrations.lark.cards import (
    build_alert_card,
    build_bot_reply_card,
    build_daily_summary_card,
)


def test_build_alert_card_includes_source_url():
    card = build_alert_card(
        {
            "entity": "mantle",
            "metric_name": "tvl",
            "formatted_value": "$1.5B",
            "time_window": "7d",
            "severity": "high",
            "trigger_reason": "TVL up 25% in 7d",
            "source_ref": "https://defillama.com/chain/Mantle",
        }
    )

    text_blocks = [element["content"] for element in card["elements"] if element["tag"] == "markdown"]

    assert card["header"]["title"]["content"] == "Alert: mantle tvl"
    assert all("text" not in element for element in card["elements"] if element["tag"] == "markdown")
    assert any("TVL up 25% in 7d" in block for block in text_blocks)
    assert any("https://defillama.com/chain/Mantle" in block for block in text_blocks)


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

    text_blocks = [element["content"] for element in card["elements"] if element["tag"] == "markdown"]

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

    text_blocks = [element["content"] for element in card["elements"] if element["tag"] == "markdown"]

    assert card["header"]["title"]["content"] == "Query Result"
    assert all("text" not in element for element in card["elements"] if element["tag"] == "markdown")
    assert any("Mantle TVL is $1.5B." in block for block in text_blocks)
    assert any("https://defillama.com/chain/Mantle" in block for block in text_blocks)
    assert any("https://example.com/secondary" in block for block in text_blocks)
