DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    "tvl":                          {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "total_value_secured":          {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "daily_active_users":           {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "active_addresses":             {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "stablecoin_supply":            {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "stablecoin_mcap":              {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "chain_transactions":           {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "stablecoin_transfer_volume":   {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "dex_volume":                   {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "mnt_volume":                   {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "mnt_market_cap":               {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "supply":                       {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "borrowed":                     {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "utilization":                  {"minor": 0.05, "moderate": 0.10, "high": 0.15, "critical": 0.20},
    "volume":                       {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
}

COOLDOWN_HOURS: dict[str, int] = {
    "minor": 72,
    "moderate": 48,
    "high": 24,
    "critical": 12,
}
