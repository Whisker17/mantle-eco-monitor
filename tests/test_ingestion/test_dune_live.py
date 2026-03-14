import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

from src.ingestion.dune import DuneClient, DuneCollector


def _load_live_dune_config() -> tuple[str, int]:
    repo_root = Path(__file__).resolve().parents[2]
    candidate_env_files = [repo_root / ".env"]
    if repo_root.parent.name == ".worktrees":
        candidate_env_files.append(repo_root.parent.parent / ".env")

    env_data = {}
    for env_file in candidate_env_files:
        if env_file.exists():
            env_data.update({k: v for k, v in dotenv_values(env_file).items() if v is not None})

    api_key = os.getenv("DUNE_API_KEY") or env_data.get("DUNE_API_KEY", "")
    query_id_raw = os.getenv("DUNE_STABLECOIN_VOLUME_QUERY_ID") or env_data.get(
        "DUNE_STABLECOIN_VOLUME_QUERY_ID", "0"
    )
    try:
        query_id = int(query_id_raw)
    except (TypeError, ValueError):
        query_id = 0

    return api_key, query_id


@pytest.mark.asyncio
@pytest.mark.live_dune
async def test_live_dune_stablecoin_transfer_volume():
    if os.getenv("RUN_LIVE_DUNE_TESTS") != "1":
        pytest.skip("set RUN_LIVE_DUNE_TESTS=1 to run live Dune verification")

    api_key, query_id = _load_live_dune_config()
    if not api_key:
        pytest.skip("missing DUNE_API_KEY for live Dune verification")
    if not query_id:
        pytest.skip("missing DUNE_STABLECOIN_VOLUME_QUERY_ID for live Dune verification")

    class LiveSettings:
        dune_stablecoin_volume_query_id = query_id

    collector = DuneCollector(DuneClient(api_key), LiveSettings())

    records = await collector.collect()

    assert records, "expected Dune stablecoin transfer volume query to return at least one row"
    assert all(record.metric_name == "stablecoin_transfer_volume" for record in records)
    assert all(record.entity == "mantle" for record in records)
    assert all(record.unit == "usd" for record in records)
