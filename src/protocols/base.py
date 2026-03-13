from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from src.ingestion.base import MetricRecord


class ProtocolAdapter(ABC):
    @abstractmethod
    async def collect(self, http: httpx.AsyncClient) -> list[MetricRecord]:
        ...

    @property
    @abstractmethod
    def slug(self) -> str:
        ...

    @property
    @abstractmethod
    def monitoring_tier(self) -> str:
        ...
