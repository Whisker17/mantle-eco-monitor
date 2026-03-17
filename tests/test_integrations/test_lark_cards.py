from __future__ import annotations

from datetime import UTC, datetime

from src.integrations.lark.cards import (
    build_alert_card,
    build_bot_reply_card,
    build_consolidated_alert_card,
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


def test_build_consolidated_alert_card_single_alert_delegates_to_build_alert_card():
    alert = {
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
    single = build_consolidated_alert_card([alert])
    direct = build_alert_card(alert)
    assert single == direct


def test_build_consolidated_alert_card_same_metric_multiple_triggers():
    alerts = [
        {
            "entity": "scenario-decline-7d-dau",
            "metric_name": "daily_active_users",
            "formatted_value": None,
            "current_value": "750",
            "time_window": "7d",
            "change_pct": "-0.25",
            "severity": "high",
            "trigger_reason": "threshold_25pct_7d",
            "source_platform": "admin_seed",
            "source_ref": "admin://seed/scenario",
            "detected_at": datetime(2026, 3, 15, 10, 0, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        },
        {
            "entity": "scenario-decline-7d-dau",
            "metric_name": "daily_active_users",
            "formatted_value": None,
            "current_value": "750",
            "time_window": "7d",
            "change_pct": "-0.25",
            "severity": "critical",
            "trigger_reason": "decline_25pct_7d",
            "source_platform": "admin_seed",
            "source_ref": "admin://seed/scenario",
            "detected_at": datetime(2026, 3, 15, 10, 0, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        },
        {
            "entity": "scenario-decline-7d-dau",
            "metric_name": "multi_signal",
            "formatted_value": None,
            "current_value": "750",
            "time_window": "combined",
            "change_pct": None,
            "severity": "critical",
            "trigger_reason": "multi_signal:daily_active_users",
            "source_platform": None,
            "source_ref": None,
            "detected_at": datetime(2026, 3, 15, 10, 0, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        },
    ]
    card = build_consolidated_alert_card(alerts)
    blocks = _markdown_text_blocks(card)

    assert card["header"]["template"] == "red"
    assert any("Metric:" in b and "Daily Active Users" in b for b in blocks)
    assert any("Triggers:" in b for b in blocks)
    trigger_block = next(b for b in blocks if "Triggers:" in b)
    assert "decline_25pct_7d" in trigger_block
    assert "threshold_25pct_7d" in trigger_block


def test_build_consolidated_alert_card_same_metric_multi_window_shows_all_movements():
    alerts = [
        {
            "entity": "scenario-threshold-mtd",
            "metric_name": "active_addresses",
            "formatted_value": None,
            "current_value": "120",
            "time_window": "7d",
            "change_pct": "0.15",
            "severity": "moderate",
            "trigger_reason": "threshold_15pct_7d",
            "source_platform": "admin_seed",
            "source_ref": "admin://seed/scenario",
            "detected_at": datetime(2026, 3, 15, 10, 0, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        },
        {
            "entity": "scenario-threshold-mtd",
            "metric_name": "active_addresses",
            "formatted_value": None,
            "current_value": "120",
            "time_window": "mtd",
            "change_pct": "0.20",
            "severity": "high",
            "trigger_reason": "threshold_20pct_mtd",
            "source_platform": "admin_seed",
            "source_ref": "admin://seed/scenario",
            "detected_at": datetime(2026, 3, 15, 10, 0, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        },
    ]
    card = build_consolidated_alert_card(alerts)
    blocks = _markdown_text_blocks(card)

    metric_block = next(b for b in blocks if "Metric:" in b)
    assert "Active Addresses" in metric_block

    movement_block = next(b for b in blocks if "Movement:" in b)
    assert "+15.00% (7D)" in movement_block
    assert "+20.00% (MTD)" in movement_block

    trigger_block = next(b for b in blocks if "Triggers:" in b)
    assert "threshold_15pct_7d" in trigger_block
    assert "threshold_20pct_mtd" in trigger_block


def test_build_consolidated_alert_card_multi_metric_shows_signals_detected():
    alerts = [
        {
            "entity": "scenario-multi-signal-core",
            "metric_name": "tvl",
            "formatted_value": None,
            "current_value": "125000000",
            "time_window": "7d",
            "change_pct": "0.25",
            "severity": "high",
            "trigger_reason": "threshold_25pct_7d",
            "source_platform": "admin_seed",
            "source_ref": "admin://seed/scenario",
            "detected_at": datetime(2026, 3, 15, 10, 0, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        },
        {
            "entity": "scenario-multi-signal-core",
            "metric_name": "dex_volume",
            "formatted_value": None,
            "current_value": "135000000",
            "time_window": "7d",
            "change_pct": "0.35",
            "severity": "critical",
            "trigger_reason": "threshold_35pct_7d",
            "source_platform": "admin_seed",
            "source_ref": "admin://seed/scenario",
            "detected_at": datetime(2026, 3, 15, 10, 0, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        },
        {
            "entity": "scenario-multi-signal-core",
            "metric_name": "multi_signal",
            "formatted_value": None,
            "current_value": "125000000",
            "time_window": "combined",
            "change_pct": None,
            "severity": "critical",
            "trigger_reason": "multi_signal:dex_volume, tvl",
            "source_platform": None,
            "source_ref": None,
            "detected_at": datetime(2026, 3, 15, 10, 0, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        },
    ]
    card = build_consolidated_alert_card(alerts)
    blocks = _markdown_text_blocks(card)

    assert card["header"]["template"] == "green"
    signals_block = next(b for b in blocks if "Signals Detected" in b)
    assert "TVL" in signals_block
    assert "DEX Volume" in signals_block
    status_block = next(b for b in blocks if "Status:" in b)
    assert "MULTI-SIGNAL" in status_block


def test_build_daily_summary_card_categorises_metrics_and_formats_alerts():
    card = build_daily_summary_card(
        {
            "title": "Mantle Daily Summary",
            "summary_text": "TVL and DEX volume both moved higher.",
            "metrics": [
                {
                    "scope": "core",
                    "entity": "mantle",
                    "metric_name": "tvl",
                    "value": "731191559",
                    "formatted_value": "$731.2M",
                    "source_platform": "defillama",
                    "source_ref": "https://defillama.com/chain/Mantle",
                },
                {
                    "scope": "core",
                    "entity": "mantle",
                    "metric_name": "dex_volume",
                    "value": "2429889",
                    "formatted_value": "$2.43M",
                    "source_platform": "defillama",
                    "source_ref": "https://defillama.com/chain/Mantle?dexs=true",
                },
                {
                    "scope": "core",
                    "entity": "mantle",
                    "metric_name": "stablecoin_mcap",
                    "value": "770978332",
                    "formatted_value": "$771M",
                    "source_platform": "defillama",
                    "source_ref": "https://defillama.com/chain/Mantle",
                },
                {
                    "scope": "ecosystem",
                    "entity": "aave-v3",
                    "metric_name": "tvl",
                    "value": "490856620",
                    "formatted_value": "$490.9M",
                    "source_platform": "defillama",
                    "source_ref": "https://defillama.com/protocol/aave-v3",
                },
                {
                    "scope": "ecosystem",
                    "entity": "cian-yield-layer",
                    "metric_name": "tvl",
                    "value": "179013806",
                    "formatted_value": "$179.0M",
                    "source_platform": "defillama",
                    "source_ref": "https://defillama.com/protocol/cian-yield-layer",
                },
            ],
            "alerts": [
                {
                    "entity": "mantle",
                    "metric_name": "tvl",
                    "trigger_reason": "milestone_$1.00B",
                    "severity": "high",
                    "change_pct": None,
                    "time_window": "7d",
                    "is_ath": False,
                    "is_milestone": True,
                    "milestone_label": "$1.00B",
                },
                {
                    "entity": "mantle",
                    "metric_name": "dex_volume",
                    "trigger_reason": "decline_27pct_7d",
                    "severity": "critical",
                    "change_pct": "-0.275",
                    "time_window": "7d",
                    "is_ath": False,
                    "is_milestone": False,
                    "milestone_label": None,
                },
            ],
        }
    )

    text_blocks = _markdown_text_blocks(card)

    assert card["header"]["title"]["content"] == "Mantle Daily Summary"
    assert text_blocks[0] == "TVL and DEX volume both moved higher."

    core_block = next(b for b in text_blocks if b.startswith("**Core Metrics**"))
    assert "TVL (Total Value Locked): $731.2M" in core_block
    assert "DEX Volume: $2.43M" in core_block
    assert "(DefiLlama)" in core_block

    stablecoin_block = next(b for b in text_blocks if b.startswith("**Stablecoin**"))
    assert "Stablecoin Market Cap: $771M" in stablecoin_block

    ecosystem_block = next(b for b in text_blocks if b.startswith("**Ecosystem Protocols**"))
    assert "Aave V3" in ecosystem_block
    assert "Cian Yield Layer" in ecosystem_block
    aave_pos = ecosystem_block.index("Aave V3")
    cian_pos = ecosystem_block.index("Cian Yield Layer")
    assert aave_pos < cian_pos, "Ecosystem protocols should be sorted by TVL descending"

    alert_block = next(b for b in text_blocks if b.startswith("**Alerts**"))
    assert "Mantle / TVL" in alert_block
    assert "milestone_$1.00B" in alert_block
    assert "Mantle / DEX Volume" in alert_block
    assert "-27.50%" in alert_block
    assert "critical" in alert_block

    assert not any("**Sources**" in b for b in text_blocks)


def test_build_alert_card_ecosystem_protocol_shows_entity_in_title_and_body():
    card = build_alert_card(
        {
            "scope": "ecosystem",
            "entity": "fluxion-network",
            "display_name": "Fluxion Network",
            "category": "dex",
            "metric_name": "volume",
            "formatted_value": None,
            "current_value": "1500000",
            "time_window": "7d",
            "change_pct": "0.3032",
            "severity": "high",
            "trigger_reason": "threshold_30pct_7d",
            "source_platform": "defillama",
            "source_ref": "https://defillama.com/protocol/fluxion-network",
            "detected_at": datetime(2026, 3, 17, 9, 27, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        }
    )

    text_blocks = _markdown_text_blocks(card)

    assert card["header"]["title"]["content"] == "\U0001f7e2 FLUXION NETWORK \u2014 MANTLE ECO ALERT"
    assert card["header"]["template"] == "green"
    assert text_blocks[0] == "**\U0001f3e2 Protocol:** Fluxion Network (DEX)"
    assert text_blocks[1] == "**\U0001f4ca Metric:** Volume"
    assert text_blocks[2] == "**\U0001f4c8 Movement:** +30.32% (7D)"
    assert text_blocks[3] == "**\U0001f4b0 Current Value:** $~1.5M"
    assert text_blocks[4] == "**\U0001f3c6 Status:** SIGNIFICANT UPWARD MOVE"
    assert text_blocks[5] == "**\U0001f4e1 Source:** DefiLlama (https://defillama.com/protocol/fluxion-network)"


def test_build_consolidated_alert_card_ecosystem_multi_signal_shows_entity():
    alerts = [
        {
            "scope": "ecosystem",
            "entity": "fluxion-network",
            "display_name": "Fluxion Network",
            "category": "dex",
            "metric_name": "tvl",
            "formatted_value": None,
            "current_value": "575600",
            "time_window": "7d",
            "change_pct": "0.2842",
            "severity": "high",
            "trigger_reason": "threshold_28pct_7d",
            "source_platform": "defillama",
            "source_ref": "https://defillama.com/protocol/fluxion-network",
            "detected_at": datetime(2026, 3, 17, 9, 27, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        },
        {
            "scope": "ecosystem",
            "entity": "fluxion-network",
            "display_name": "Fluxion Network",
            "category": "dex",
            "metric_name": "volume",
            "formatted_value": None,
            "current_value": "165700",
            "time_window": "7d",
            "change_pct": "6.4276",
            "severity": "critical",
            "trigger_reason": "threshold_642pct_7d",
            "source_platform": "defillama",
            "source_ref": "https://defillama.com/protocol/fluxion-network",
            "detected_at": datetime(2026, 3, 17, 9, 27, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        },
        {
            "scope": "ecosystem",
            "entity": "fluxion-network",
            "display_name": "Fluxion Network",
            "category": "dex",
            "metric_name": "multi_signal",
            "formatted_value": None,
            "current_value": "575600",
            "time_window": "combined",
            "change_pct": None,
            "severity": "critical",
            "trigger_reason": "multi_signal:tvl, volume",
            "source_platform": None,
            "source_ref": None,
            "detected_at": datetime(2026, 3, 17, 9, 27, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        },
    ]
    card = build_consolidated_alert_card(alerts)
    blocks = _markdown_text_blocks(card)

    assert card["header"]["title"]["content"] == "\U0001f7e2 FLUXION NETWORK \u2014 MANTLE ECO ALERT"
    assert blocks[0] == "**\U0001f3e2 Protocol:** Fluxion Network (DEX)"
    signals_block = next(b for b in blocks if "Signals Detected" in b)
    assert "TVL" in signals_block
    assert "Volume" in signals_block
    status_block = next(b for b in blocks if "Status:" in b)
    assert "MULTI-SIGNAL" in status_block


def test_build_alert_card_ecosystem_without_display_name_falls_back():
    card = build_alert_card(
        {
            "scope": "ecosystem",
            "entity": "merchant-moe",
            "metric_name": "volume",
            "formatted_value": "$2.1M",
            "time_window": "7d",
            "change_pct": "0.40",
            "severity": "high",
            "trigger_reason": "threshold_40pct_7d",
            "source_platform": "defillama",
            "source_ref": "https://defillama.com/protocol/merchant-moe",
            "detected_at": datetime(2026, 3, 17, 9, 0, tzinfo=UTC).isoformat(),
            "is_ath": False,
            "is_milestone": False,
            "milestone_label": None,
        }
    )

    text_blocks = _markdown_text_blocks(card)

    assert card["header"]["title"]["content"] == "\U0001f7e2 MERCHANT MOE \u2014 MANTLE ECO ALERT"
    assert text_blocks[0] == "**\U0001f3e2 Protocol:** Merchant Moe"
    assert text_blocks[1] == "**\U0001f4ca Metric:** Volume"


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
