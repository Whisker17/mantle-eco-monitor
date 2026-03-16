from __future__ import annotations

import logging
import math
from decimal import Decimal

import httpx

from config.watchlist_seed import WATCHLIST_SEED

logger = logging.getLogger(__name__)

CATEGORY_WEIGHTS: dict[str, float] = {
    "lending": 1.0,
    "dex": 0.9,
    "rwa": 0.85,
    "yield": 0.8,
    "index": 0.8,
    "other": 0.6,
    "bridge": 0.2,
    "cex": 0.0,
}

MAX_DYNAMIC_SLOTS = 15


def _normalize_category(category: str) -> str:
    cat = category.lower().strip()
    if cat in CATEGORY_WEIGHTS:
        return cat
    if "dex" in cat:
        return "dex"
    if "lend" in cat:
        return "lending"
    if "yield" in cat or "farm" in cat:
        return "yield"
    if "bridge" in cat:
        return "bridge"
    if "cex" in cat:
        return "cex"
    return "other"


def _score_protocol(tvl: float, category: str) -> float:
    weight = CATEGORY_WEIGHTS.get(_normalize_category(category), 0.6)
    return weight * math.log10(tvl + 1)


class WatchlistManager:
    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    def get_seed(self) -> list[dict]:
        return list(WATCHLIST_SEED)

    async def fetch_mantle_protocols(self) -> list[dict]:
        resp = await self._http.get("https://api.llama.fi/protocols")
        resp.raise_for_status()
        protocols = resp.json()
        mantle_protocols = []
        for p in protocols:
            chains = p.get("chains", [])
            if "Mantle" in chains:
                mantle_protocols.append(p)
        return mantle_protocols

    def score_and_rank(self, protocols: list[dict]) -> list[dict]:
        scored = []
        for p in protocols:
            category = _normalize_category(p.get("category", "other"))
            if category == "cex":
                continue
            tvl = float(p.get("tvl", 0) or 0)
            score = _score_protocol(tvl, category)
            scored.append({**p, "_score": score, "_category": category})
        scored.sort(key=lambda x: x["_score"], reverse=True)
        return scored

    def build_watchlist(
        self,
        ranked_protocols: list[dict],
        pinned_slugs: set[str] | None = None,
    ) -> list[dict]:
        return self.get_seed()
