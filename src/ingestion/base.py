from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class MetricRecord:
    scope: str
    entity: str
    metric_name: str
    value: Decimal
    unit: str
    source_platform: str
    source_ref: str | None
    collected_at: datetime


class BaseCollector(ABC):
    @abstractmethod
    async def collect(self) -> list[MetricRecord]:
        """Fetch and normalize metrics from the source."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the source is reachable."""
        ...

    @property
    @abstractmethod
    def source_platform(self) -> str:
        """Identifier: 'dune', 'defillama', 'growthepie', etc."""
        ...
