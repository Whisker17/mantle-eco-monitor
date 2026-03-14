# Mantle Ecosystem Monitor - Technical Design

> Phase 1 implementation blueprint for the Mantle Onchain Metrics Monitor and Alerting System.
> Source PRD: [specs/prd-simple.md](specs/prd-simple.md)

---

## 1. Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python 3.12+ | Strong ecosystem for data pipelines; first-class async; SDKs and HTTP tooling for Dune and DefiLlama |
| Web Framework | FastAPI | Async-native, auto OpenAPI docs, Pydantic validation |
| Database | PostgreSQL 16 | PRD-recommended; robust time-range queries, JSONB for flexible source metadata |
| ORM | SQLAlchemy 2.0 (async) | Mature, typed, supports both Core and ORM styles |
| Migrations | Alembic | Standard companion to SQLAlchemy |
| HTTP Client | httpx | Async HTTP with retry/timeout support |
| Scheduler | APScheduler 4 | In-process cron-style scheduling, async job support |
| Config | pydantic-settings | Typed env-var loading with validation and `.env` support |
| Testing | pytest + pytest-asyncio | Async test support, fixtures for DB |
| Containerization | Docker Compose | PostgreSQL + app in one command |

### Key Python Dependencies

```
fastapi>=0.115
uvicorn[standard]>=0.32
sqlalchemy[asyncio]>=2.0
asyncpg>=0.30
alembic>=1.14
httpx>=0.28
apscheduler>=4.0
pydantic-settings>=2.6
python-dotenv>=1.0
```

---

## 2. Architecture

### 2.1 Six-Layer Overview

```mermaid
flowchart TB
    subgraph scheduler [1. Scheduler]
        CRON[APScheduler Jobs]
    end

    subgraph ingestion [2. Ingestion Layer]
        DFL[DefiLlama Collector]
        L2B[L2Beat Collector]
        GTP[Growthepie Fallback Collector]
        DUNE[Dune Collector]
        CGK[CoinGecko Collector]
    end

    subgraph storage [3. Snapshot Storage]
        PG[(PostgreSQL)]
    end

    subgraph rules [4. Rule Evaluation]
        THR[Threshold Check]
        ATH[ATH Detection]
        MIL[Milestone Detection]
        DEC[Decline Detection]
        CLD[Cooldown / Suppression]
    end

    subgraph ai [5. AI Enrichment]
        AIS[AI Service Stub]
    end

    subgraph delivery [6. Delivery Layer]
        API[FastAPI Alert Feed]
        LARK[Lark Webhook Stub]
    end

    CRON --> DFL & GTP & L2B & DUNE & CGK
    DFL & GTP & L2B & DUNE & CGK --> PG
    PG --> THR & ATH & MIL & DEC
    THR & ATH & MIL & DEC --> CLD
    CLD --> PG
    PG --> AIS
    AIS -.->|Phase 2| PG
    PG --> API
    PG -.->|Phase 2| LARK
```

### 2.2 Request-Time Data Flow (Alert Feed)

```mermaid
sequenceDiagram
    participant U as BD/Social User
    participant API as FastAPI
    participant DB as PostgreSQL

    U->>API: GET /api/alerts?severity=high
    API->>DB: SELECT from alert_events
    DB-->>API: rows
    API-->>U: JSON alert list
```

### 2.3 Scheduled Pipeline Flow

```mermaid
sequenceDiagram
    participant S as Scheduler
    participant C as Collector
    participant SRC as External API
    participant DB as PostgreSQL
    participant R as Rule Engine

    S->>C: trigger collect(metric, entity)
    C->>SRC: HTTP GET
    SRC-->>C: raw JSON
    C->>DB: INSERT metric_snapshot
    C->>DB: INSERT source_run (success)
    S->>R: trigger evaluate(entity, metric)
    R->>DB: SELECT historical snapshots
    DB-->>R: rows
    R->>R: compute changes, check rules
    R->>DB: INSERT alert_event (if triggered)
```

---

## 3. Data Source Mapping

### 3.0 Source Priority Policy

This project uses a public-source-first strategy.

Approved source set for Phase 1:

- Dune
- DefiLlama
- L2Beat
- CoinGecko
- Growthepie

Source selection rule:

- Prefer public, unauthenticated endpoints first when the metric semantics remain acceptable.
- Use the most appropriate specialized public source:
  - DefiLlama for TVL, stablecoins, chain DEX volume, and ecosystem protocol data
  - L2Beat for Total Value Secured
  - Growthepie for Mantle activity metrics
  - CoinGecko for MNT volume, and as a reference source for MNT market cap
- Keep Dune only for metrics that the public source set does not cover cleanly, especially stablecoin transfer volume.
- Phase 1 product assumption: treat Growthepie `daa` as acceptable for both `daily_active_users` and `active_addresses`.

Artemis and Nansen are out of scope for this implementation plan and should not be included in Phase 1.

### 3.1 Core Monitor Metrics (11 metrics)

| # | Metric | Primary Source | API Endpoint | Fallback Source | Notes |
|---|--------|---------------|-------------|-----------------|-------|
| 1 | TVL | DefiLlama | `GET https://api.llama.fi/v2/historicalChainTvl/Mantle` | -- | Keep separate from L2Beat TVS and Growthepie TVL because the semantics diverge materially |
| 2 | Total Value Secured | L2Beat | `GET https://l2beat.com/api/scaling/tvs/mantle` | -- | Sum of native + canonical + external value |
| 3 | Daily Active Users | Growthepie | `GET https://api.growthepie.com/v1/export/daa.json` | -- | Phase 1 assumes `DAU == DAA` |
| 4 | Active Addresses | Growthepie | `GET https://api.growthepie.com/v1/export/daa.json` | -- | Same public source as `daily_active_users` in this phase |
| 5 | Stablecoin Supply | DefiLlama | `GET https://stablecoins.llama.fi/stablecoincharts/Mantle` | -- | Use latest `totalCirculatingUSD.peggedUSD` |
| 6 | Stablecoin Market Cap | DefiLlama | `GET https://stablecoins.llama.fi/stablecoinchains` | Growthepie `stables_mcap` | Growthepie is comparison-only until methodology reconciliation is needed |
| 7 | Mantle Chain Transactions | Growthepie | `GET https://api.growthepie.com/v1/export/txcount.json` | L2Beat `GET /api/scaling/activity/mantle` | Public source preferred over Dune |
| 8 | Stablecoin Transfer Volume | Dune | Execute saved query on `mantle.transactions` filtering known stablecoin contracts | -- | No clean public source confirmed in Phase 1 |
| 9 | DEX Volume | DefiLlama | `GET https://api.llama.fi/overview/dexs/Mantle` | -- | Public chain-level DEX volume is available |
| 10 | MNT Volume | CoinGecko | `GET /api/v3/coins/mantle` field `market_data.total_volume.usd` | -- | Not covered by the validated public trio |
| 11 | MNT Market Cap | Growthepie | `GET https://api.growthepie.com/v1/fundamentals.json` metric `market_cap_usd` | CoinGecko | CoinGecko remains a comparison/fallback source |

### 3.2 Ecosystem Protocol Metrics

| Protocol Type | Source | TVL Endpoint | Volume Endpoint | Borrow/Supply |
|---------------|--------|-------------|-----------------|---------------|
| Aave V3 | DefiLlama | `GET https://api.llama.fi/protocol/aave-v3` | -- | Use Mantle chain entries for supply, borrowed, utilization, and TVL |
| DEX (e.g. Merchant Moe) | DefiLlama | `GET https://api.llama.fi/protocol/{slug}` | `GET https://api.llama.fi/summary/dexs/{slug}` | Public endpoints are sufficient for Phase 1 |
| Non-DEX (e.g. Ondo) | DefiLlama | `GET https://api.llama.fi/protocol/{slug}` | -- | TVL only unless a special adapter is justified |
| Secondary Lending | DefiLlama | `GET https://api.llama.fi/protocol/{slug}` | -- | Phase 1 stays TVL-first unless the product requires more fields |

### 3.3 Source Authentication

| Source | Auth Method | Key Env Var |
|--------|------------|-------------|
| DefiLlama | None (public endpoints) | -- |
| Growthepie | None | -- |
| L2Beat | None (public, rate-limited in practice) | -- |
| CoinGecko | Optional API key header | `COINGECKO_API_KEY` |
| Dune | `X-Dune-API-Key` header | `DUNE_API_KEY` |

---

## 4. Database Schema

Four tables as specified in the PRD. All timestamps are `TIMESTAMPTZ` (UTC).

### 4.1 `metric_snapshots`

Stores every collected data point. This is the source of truth for historical comparisons.

```sql
CREATE TABLE metric_snapshots (
    id            BIGSERIAL PRIMARY KEY,
    scope         TEXT        NOT NULL,  -- 'core' | 'ecosystem'
    entity        TEXT        NOT NULL,  -- 'mantle' | 'aave-v3' | 'merchant-moe' ...
    metric_name   TEXT        NOT NULL,  -- 'tvl' | 'dex_volume' | 'borrowed' ...
    value         NUMERIC     NOT NULL,
    formatted_value TEXT,                -- '$1.23B', '142K', etc.
    unit          TEXT,                  -- 'usd' | 'count' | 'percent'
    source_platform TEXT      NOT NULL,  -- 'defillama' | 'growthepie' ...
    source_ref    TEXT,                  -- URL or query ID
    collected_at  TIMESTAMPTZ NOT NULL,  -- logical timestamp of the data point
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_snapshots_lookup
    ON metric_snapshots (entity, metric_name, collected_at DESC);

CREATE INDEX idx_snapshots_scope_time
    ON metric_snapshots (scope, collected_at DESC);
```

### 4.2 `alert_events`

Each row is one fired alert. The alert feed API reads from this table.

```sql
CREATE TABLE alert_events (
    id              BIGSERIAL PRIMARY KEY,
    scope           TEXT        NOT NULL,
    entity          TEXT        NOT NULL,
    metric_name     TEXT        NOT NULL,
    current_value   NUMERIC     NOT NULL,
    previous_value  NUMERIC,
    formatted_value TEXT,
    time_window     TEXT        NOT NULL,  -- '7d' | 'mtd' | '1m' | '3m' ...
    change_pct      NUMERIC,
    severity        TEXT        NOT NULL,  -- 'minor' | 'moderate' | 'high' | 'critical'
    trigger_reason  TEXT        NOT NULL,  -- 'threshold_15pct_7d' | 'new_ath' | 'milestone_1b' ...
    source_platform TEXT,
    source_ref      TEXT,
    detected_at     TIMESTAMPTZ NOT NULL,
    is_ath          BOOLEAN     NOT NULL DEFAULT FALSE,
    is_milestone    BOOLEAN     NOT NULL DEFAULT FALSE,
    milestone_label TEXT,                  -- '$1B' | '100K users' ...
    cooldown_until  TIMESTAMPTZ,
    reviewed        BOOLEAN     NOT NULL DEFAULT FALSE,
    review_note     TEXT,
    ai_eligible     BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alerts_feed
    ON alert_events (detected_at DESC, severity);

CREATE INDEX idx_alerts_entity
    ON alert_events (entity, metric_name, detected_at DESC);

CREATE INDEX idx_alerts_cooldown
    ON alert_events (entity, metric_name, cooldown_until);
```

### 4.3 `watchlist_protocols`

Tracks which ecosystem protocols are actively monitored.

```sql
CREATE TABLE watchlist_protocols (
    id             SERIAL  PRIMARY KEY,
    slug           TEXT    UNIQUE NOT NULL,  -- DefiLlama slug: 'aave-v3', 'merchant-moe' ...
    display_name   TEXT    NOT NULL,
    category       TEXT    NOT NULL,         -- 'lending' | 'dex' | 'yield' | 'rwa' | 'index'
    monitoring_tier TEXT   NOT NULL,         -- 'special' (Aave) | 'dex' | 'generic'
    is_pinned      BOOLEAN NOT NULL DEFAULT FALSE,
    metrics        TEXT[]  NOT NULL,         -- {'tvl'} | {'tvl','volume'} | {'supply','borrowed','utilization'}
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    added_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 4.4 `source_runs`

Observability log for every collection attempt. Enables freshness checks and source-by-source debugging.

```sql
CREATE TABLE source_runs (
    id               BIGSERIAL PRIMARY KEY,
    source_platform  TEXT        NOT NULL,
    job_name         TEXT        NOT NULL,  -- 'core_tvl' | 'ecosystem_aave' ...
    status           TEXT        NOT NULL,  -- 'success' | 'failed' | 'timeout' | 'partial'
    records_collected INT        NOT NULL DEFAULT 0,
    error_message    TEXT,
    http_status      INT,
    latency_ms       INT,
    started_at       TIMESTAMPTZ NOT NULL,
    completed_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_source_runs_recent
    ON source_runs (source_platform, started_at DESC);
```

### 4.5 Entity-Relationship Diagram

```mermaid
erDiagram
    metric_snapshots {
        bigint id PK
        text scope
        text entity
        text metric_name
        numeric value
        text source_platform
        timestamptz collected_at
    }

    alert_events {
        bigint id PK
        text scope
        text entity
        text metric_name
        numeric current_value
        text time_window
        text severity
        text trigger_reason
        boolean is_ath
        boolean is_milestone
        boolean reviewed
        timestamptz detected_at
    }

    watchlist_protocols {
        int id PK
        text slug UK
        text category
        text monitoring_tier
        boolean is_pinned
        boolean active
    }

    source_runs {
        bigint id PK
        text source_platform
        text job_name
        text status
        timestamptz started_at
    }

    metric_snapshots ||--o{ alert_events : "triggers"
    watchlist_protocols ||--o{ metric_snapshots : "defines entities"
    source_runs ||--o{ metric_snapshots : "produces"
```

---

## 5. Project Structure

```
mantle-eco-monitor/
├── DESIGN.md
├── README.md
├── specs/
│   └── prd-simple.md
├── pyproject.toml                      # Dependencies, project metadata
├── .env.example                        # Template for required env vars
├── alembic.ini
├── alembic/
│   └── versions/                       # Auto-generated migration files
├── config/
│   ├── __init__.py
│   ├── settings.py                     # Pydantic-settings: DB URL, API keys, feature flags
│   ├── thresholds.py                   # Alert threshold definitions per metric
│   ├── milestones.py                   # Milestone values per metric
│   └── watchlist_seed.py               # Initial watchlist entries
├── src/
│   ├── __init__.py
│   ├── main.py                         # FastAPI app factory + lifespan (scheduler start)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── engine.py                   # async engine + sessionmaker
│   │   └── models.py                   # SQLAlchemy ORM models for all 4 tables
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── base.py                     # BaseCollector ABC
│   │   ├── defillama.py                # DefiLlama: TVL, stablecoins, ecosystem protocol data
│   │   ├── growthepie.py               # Growthepie: fallback DAU / active addresses / tx count
│   │   ├── l2beat.py                   # L2Beat: Total Value Secured
│   │   ├── dune.py                     # Dune: DAU, active addresses, tx count, stablecoin transfer volume, DEX volume
│   │   ├── coingecko.py                # CoinGecko: MNT volume, MNT market cap
│   │   └── normalize.py                # Value formatting helpers ($1.2B, 142K, etc.)
│   ├── protocols/
│   │   ├── __init__.py
│   │   ├── registry.py                 # Protocol registry: resolves slug -> adapter
│   │   ├── base.py                     # GenericProtocolAdapter
│   │   ├── aave.py                     # AaveAdapter: supply, borrowed, utilization
│   │   ├── dex.py                      # DexAdapter: TVL + volume
│   │   └── watchlist.py                # WatchlistManager: dynamic refresh from DefiLlama
│   ├── rules/
│   │   ├── __init__.py
│   │   ├── engine.py                   # RuleEngine orchestrator
│   │   ├── thresholds.py               # Percentage-change threshold checks
│   │   ├── ath.py                      # All-time-high detection
│   │   ├── milestones.py               # Round-number milestone crossing
│   │   ├── decline.py                  # Significant decline detection
│   │   ├── multi_signal.py             # Multi-metric coincidence detection
│   │   └── cooldown.py                 # Suppression and cooldown logic
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── jobs.py                     # Job definitions + cadence config
│   └── api/
│       ├── __init__.py
│       ├── deps.py                     # Shared dependencies (DB session)
│       ├── schemas.py                  # Pydantic response/request models
│       └── routes/
│           ├── __init__.py
│           ├── alerts.py               # GET /api/alerts, PATCH /api/alerts/:id/review
│           ├── metrics.py              # GET /api/metrics/latest, GET /api/metrics/history
│           ├── watchlist.py            # GET /api/watchlist, POST /api/watchlist/refresh
│           └── health.py              # GET /api/health
├── tests/
│   ├── conftest.py                     # Shared fixtures: test DB, mock HTTP
│   ├── test_ingestion/
│   │   ├── test_defillama.py
│   │   ├── test_dune.py
│   │   ├── test_growthepie.py
│   │   └── ...
│   ├── test_rules/
│   │   ├── test_thresholds.py
│   │   ├── test_ath.py
│   │   ├── test_milestones.py
│   │   └── test_cooldown.py
│   └── test_api/
│       ├── test_alerts.py
│       └── test_metrics.py
└── docker-compose.yml                  # PostgreSQL 16 + app service
```

---

## 6. Ingestion Layer

### 6.1 BaseCollector Interface

Every data source implements this abstract contract:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

@dataclass
class MetricRecord:
    scope: str              # 'core' | 'ecosystem'
    entity: str             # 'mantle' | 'aave-v3' | ...
    metric_name: str        # 'tvl' | 'dex_volume' | ...
    value: Decimal
    unit: str               # 'usd' | 'count' | 'percent'
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
```

### 6.2 Collector Implementations

**DefiLlamaCollector** (handles specialized chain metrics + ecosystem protocol data):

```python
class DefiLlamaCollector(BaseCollector):
    BASE = "https://api.llama.fi"
    STABLES_BASE = "https://stablecoins.llama.fi"

    async def collect(self) -> list[MetricRecord]:
        records = []
        records += await self._collect_chain_tvl()          # metric: tvl
        records += await self._collect_stablecoin_supply()   # metric: stablecoin_supply
        records += await self._collect_stablecoin_mcap()     # metric: stablecoin_mcap
        records += await self._collect_protocol_tvls()       # ecosystem TVLs
        records += await self._collect_aave_details()        # supply, borrowed
        records += await self._collect_dex_protocol_volumes() # per-protocol DEX volume for eco watchlist
        return records
```

**DuneCollector** (primary source for queryable activity metrics):

```python
class DuneCollector(BaseCollector):
    async def collect(self) -> list[MetricRecord]:
        records = []
        records += await self._collect_daily_active_users()      # metric: daily_active_users
        records += await self._collect_active_addresses()        # metric: active_addresses
        records += await self._collect_chain_transactions()      # metric: chain_transactions
        records += await self._collect_stablecoin_volume()       # metric: stablecoin_transfer_volume
        records += await self._collect_dex_volume()              # metric: dex_volume
        return records
```

**GrowthepieCollector** (fallback source for selected activity metrics only):

```python
class GrowthepieCollector(BaseCollector):
    BASE = "https://api.growthepie.xyz"

    async def collect(self) -> list[MetricRecord]:
        data = await self._fetch("/v1/fundamentals/full.json")
        mantle = [r for r in data if r["origin_key"] == "mantle"]
        return [
            # used only when the corresponding Dune activity query is unavailable
            # filter for metric_key in ("daa", "txcount")
            # map daa -> "daily_active_users" and "active_addresses"
            # map txcount -> "chain_transactions"
        ]
```

**Other collectors** follow the same pattern: L2BeatCollector (TVS), CoinGeckoCollector (MNT volume + mcap), and source-specific fallback handling where needed.

### 6.3 Normalization

The `normalize.py` module provides formatting helpers:

```python
def format_usd(value: Decimal) -> str:
    """1_234_567_890 -> '$1.23B'"""

def format_count(value: Decimal) -> str:
    """142_000 -> '142K'"""

def format_pct(value: Decimal) -> str:
    """0.1534 -> '15.3%'"""
```

### 6.4 Retry and Error Handling

Each collector wraps HTTP calls with:
- **3 retries** with exponential backoff (1s, 2s, 4s)
- **30-second timeout** per request
- On failure: log a `source_runs` row with `status='failed'` and `error_message`
- On success: log a `source_runs` row with `status='success'`, `records_collected`, and `latency_ms`

---

## 7. Snapshot Storage

### 7.1 Write Pattern

After each successful collection run, the ingestion layer inserts one `metric_snapshots` row per metric record. The `collected_at` timestamp represents the logical data point time (typically the beginning of the day for daily metrics, or the collection moment for real-time metrics).

Deduplication rule: if a snapshot with the same `(entity, metric_name, collected_at::date)` already exists, **skip the insert**. This prevents double-writes when the scheduler fires more than once per logical period.

### 7.2 Historical Query Patterns

The rule engine needs to compare the current value against historical values across multiple time windows. All queries operate on the `metric_snapshots` table.

| Time Window | SQL Logic |
|-------------|-----------|
| 7D | `collected_at >= NOW() - INTERVAL '7 days'` ORDER BY `collected_at ASC` LIMIT 1 |
| MTD | `collected_at >= date_trunc('month', NOW())` ORDER BY `collected_at ASC` LIMIT 1 |
| 1M | `collected_at >= NOW() - INTERVAL '30 days'` ORDER BY `collected_at ASC` LIMIT 1 |
| 3M | `collected_at >= NOW() - INTERVAL '90 days'` ORDER BY `collected_at ASC` LIMIT 1 |
| 6M | `collected_at >= NOW() - INTERVAL '180 days'` ORDER BY `collected_at ASC` LIMIT 1 |
| YTD | `collected_at >= date_trunc('year', NOW())` ORDER BY `collected_at ASC` LIMIT 1 |
| 1Y | `collected_at >= NOW() - INTERVAL '365 days'` ORDER BY `collected_at ASC` LIMIT 1 |
| All Time | `ORDER BY collected_at ASC LIMIT 1` (earliest snapshot) |
| ATH | `ORDER BY value DESC LIMIT 1` (highest value ever) |

These are consolidated into a single helper:

```python
async def get_comparison_snapshot(
    session: AsyncSession,
    entity: str,
    metric_name: str,
    window: TimeWindow,
) -> MetricSnapshot | None:
    """Return the anchor snapshot for a given time window."""
```

### 7.3 Retention

Phase 1 retains all snapshots indefinitely. Retention pruning can be added in Phase 3 if storage grows beyond reasonable limits (unlikely with daily data points for ~20 entities x ~5 metrics).

---

## 8. Rule Evaluation Engine

### 8.1 Orchestrator

The `RuleEngine` is invoked after each ingestion run. It receives the freshly-written snapshots and evaluates them against all rule types.

```python
class RuleEngine:
    def __init__(self, session: AsyncSession, config: ThresholdConfig):
        self.session = session
        self.config = config

    async def evaluate(
        self, current_snapshots: list[MetricSnapshot]
    ) -> list[AlertCandidate]:
        candidates: list[AlertCandidate] = []

        for snapshot in current_snapshots:
            candidates += await self._check_thresholds(snapshot)
            candidates += await self._check_ath(snapshot)
            candidates += await self._check_milestones(snapshot)
            candidates += await self._check_decline(snapshot)

        candidates += await self._check_multi_signal(candidates)
        return await self._apply_cooldown(candidates)
```

### 8.2 AlertCandidate Structure

```python
@dataclass
class AlertCandidate:
    scope: str
    entity: str
    metric_name: str
    current_value: Decimal
    previous_value: Decimal | None
    formatted_value: str
    time_window: str
    change_pct: Decimal | None
    severity: str             # 'minor' | 'moderate' | 'high' | 'critical'
    trigger_reason: str       # machine-readable: 'threshold_15pct_7d', 'new_ath', ...
    is_ath: bool
    is_milestone: bool
    milestone_label: str | None
    source_platform: str
    source_ref: str | None
```

### 8.3 Threshold Detection

For each `(entity, metric_name)` pair, compute percentage change across the primary windows (7D, MTD) and map to severity:

```python
async def _check_thresholds(self, snapshot: MetricSnapshot) -> list[AlertCandidate]:
    results = []
    for window in [TimeWindow.D7, TimeWindow.MTD]:
        anchor = await get_comparison_snapshot(
            self.session, snapshot.entity, snapshot.metric_name, window
        )
        if anchor is None:
            continue
        change_pct = (snapshot.value - anchor.value) / anchor.value

        severity = self._classify_severity(abs(change_pct))
        if severity is None:
            continue  # below 10% threshold, no alert

        results.append(AlertCandidate(
            severity=severity,
            trigger_reason=f"threshold_{int(abs(change_pct)*100)}pct_{window.value}",
            change_pct=change_pct,
            time_window=window.value,
            ...
        ))
    return results
```

### 8.4 ATH Detection

Compare the current value against the historical maximum:

```python
async def _check_ath(self, snapshot: MetricSnapshot) -> list[AlertCandidate]:
    historic_max = await get_comparison_snapshot(
        self.session, snapshot.entity, snapshot.metric_name, TimeWindow.ATH
    )
    if historic_max is None or snapshot.value > historic_max.value:
        return [AlertCandidate(
            severity="critical",  # ATH always overrides to highest priority
            trigger_reason="new_ath",
            is_ath=True,
            time_window="all_time",
            ...
        )]
    return []
```

### 8.5 Milestone Detection

Check if the current value crossed a configured milestone boundary since the last snapshot:

```python
MILESTONES = {
    "tvl":                [500_000_000, 1_000_000_000, 1_500_000_000, 2_000_000_000, 5_000_000_000],
    "daily_active_users": [50_000, 100_000, 200_000, 500_000, 1_000_000],
    "stablecoin_supply":  [100_000_000, 500_000_000, 1_000_000_000],
    "dex_volume":         [50_000_000, 100_000_000, 500_000_000, 1_000_000_000],
    "chain_transactions": [100_000, 500_000, 1_000_000, 5_000_000],
    "borrowed":           [50_000_000, 100_000_000, 250_000_000, 500_000_000],
    "supply":             [100_000_000, 250_000_000, 500_000_000, 1_000_000_000],
    "mnt_market_cap":     [1_000_000_000, 2_000_000_000, 5_000_000_000],
}

async def _check_milestones(self, snapshot: MetricSnapshot) -> list[AlertCandidate]:
    thresholds = MILESTONES.get(snapshot.metric_name, [])
    prev = await get_previous_snapshot(self.session, snapshot.entity, snapshot.metric_name)
    if prev is None:
        return []

    crossed = [
        m for m in thresholds
        if prev.value < m <= snapshot.value
    ]
    return [
        AlertCandidate(
            severity="high",
            trigger_reason=f"milestone_{format_usd_short(m)}",
            is_milestone=True,
            milestone_label=format_usd_short(m),
            ...
        )
        for m in crossed
    ]
```

### 8.6 Decline Detection

A decline of >20% in any primary window triggers a dedicated alert regardless of normal threshold logic:

```python
async def _check_decline(self, snapshot: MetricSnapshot) -> list[AlertCandidate]:
    results = []
    for window in [TimeWindow.D7, TimeWindow.MTD]:
        anchor = await get_comparison_snapshot(...)
        if anchor is None:
            continue
        change_pct = (snapshot.value - anchor.value) / anchor.value
        if change_pct <= Decimal("-0.20"):
            results.append(AlertCandidate(
                severity="critical",
                trigger_reason=f"decline_{int(abs(change_pct)*100)}pct_{window.value}",
                ...
            ))
    return results
```

### 8.7 Multi-Signal Coincidence

After individual checks, scan for patterns where 2+ important metrics for the same entity cross significant thresholds simultaneously:

```python
async def _check_multi_signal(self, candidates: list[AlertCandidate]) -> list[AlertCandidate]:
    by_entity: dict[str, list[AlertCandidate]] = defaultdict(list)
    for c in candidates:
        if c.severity in ("high", "critical"):
            by_entity[c.entity].append(c)

    combined = []
    for entity, group in by_entity.items():
        if len(group) >= 2:
            metrics = ", ".join(c.metric_name for c in group)
            combined.append(AlertCandidate(
                severity="critical",
                trigger_reason=f"multi_signal:{metrics}",
                ...
            ))
    return combined
```

### 8.8 Cooldown and Suppression

Prevents the same alert from firing repeatedly:

```python
COOLDOWN_HOURS = {
    "minor": 72,      # 3 days
    "moderate": 48,    # 2 days
    "high": 24,        # 1 day
    "critical": 12,    # 12 hours (ATH, major milestones still surface quickly)
}

async def _apply_cooldown(self, candidates: list[AlertCandidate]) -> list[AlertCandidate]:
    filtered = []
    for c in candidates:
        last_alert = await self._get_last_alert(c.entity, c.metric_name, c.trigger_reason)
        if last_alert and last_alert.cooldown_until and last_alert.cooldown_until > utc_now():
            continue  # still in cooldown
        c.cooldown_until = utc_now() + timedelta(hours=COOLDOWN_HOURS[c.severity])
        filtered.append(c)
    return filtered
```

Suppression rule: if a `multi_signal` combined alert fires, individual `threshold_*` alerts for the same entity at severity < `high` are dropped from the batch.

---

## 9. Alert Severity and Threshold Config

### 9.1 Severity Tiers

| Severity | Change Range | Behavior | Priority |
|----------|-------------|----------|----------|
| `minor` | ~10-14% | Stored internally only; not shown in default feed view | 4 (lowest) |
| `moderate` | ~15-19% | Included in internal alert feed | 3 |
| `high` | ~20-29% | High-priority internal alert; candidate for AI enrichment | 2 |
| `critical` | >=30%, ATH, >20% decline, multi-signal | Highest internal priority | 1 |

### 9.2 Threshold Configuration Object

Thresholds are defined per-metric and can be overridden. Default values:

```python
DEFAULT_THRESHOLDS = {
    "tvl":                {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "total_value_secured":{"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "daily_active_users": {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "active_addresses":   {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "stablecoin_supply":  {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "stablecoin_mcap":    {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "chain_transactions": {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "stablecoin_transfer_volume": {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "dex_volume":         {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "mnt_volume":         {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "mnt_market_cap":     {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "supply":             {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "borrowed":           {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
    "utilization":        {"minor": 0.05, "moderate": 0.10, "high": 0.15, "critical": 0.20},
    "volume":             {"minor": 0.10, "moderate": 0.15, "high": 0.20, "critical": 0.30},
}
```

Note: `utilization` uses tighter thresholds since it is a ratio (typically 0-100%) where a 10% absolute change is significant.

### 9.3 Severity Classification Function

```python
def classify_severity(change_pct: Decimal, metric_name: str) -> str | None:
    thresholds = DEFAULT_THRESHOLDS.get(metric_name, DEFAULT_THRESHOLDS["tvl"])
    abs_change = abs(change_pct)

    if abs_change >= thresholds["critical"]:
        return "critical"
    if abs_change >= thresholds["high"]:
        return "high"
    if abs_change >= thresholds["moderate"]:
        return "moderate"
    if abs_change >= thresholds["minor"]:
        return "minor"
    return None  # below threshold, no alert
```

---

## 10. Ecosystem Watchlist

### 10.1 Hybrid Model

The watchlist is split into two segments:

| Segment | Behavior | Example |
|---------|----------|---------|
| **Pinned** | Always present, never removed automatically | Aave V3 |
| **Dynamic** | Refreshed periodically from DefiLlama Mantle protocol list | Merchant Moe, Ondo, CIAN, ... |

### 10.2 WatchlistManager

```python
class WatchlistManager:
    MAX_DYNAMIC_SLOTS = 15

    async def refresh(self, session: AsyncSession) -> None:
        """
        1. Fetch DefiLlama /api/protocols
        2. Filter to chain == 'Mantle'
        3. Score and rank by category priority + TVL
        4. Exclude: CEX entities, pure bridges, low-signal protocols
        5. Upsert top N into watchlist_protocols (preserving pinned entries)
        """
```

### 10.3 Category Priority Scoring

When ranking candidates for dynamic slots, apply a category weight:

| Category | Weight | Rationale |
|----------|--------|-----------|
| Lending | 1.0 | Direct capital depth signal |
| DEX | 0.9 | Trading activity signal |
| RWA | 0.85 | High narrative value |
| Yield / Index | 0.8 | Ecosystem depth signal |
| Other DeFi | 0.6 | Generic |
| Bridge | 0.2 | Low storytelling value |
| CEX | 0.0 | Excluded |

Final score: `category_weight * log10(tvl_usd + 1)`. This ensures a high-TVL bridge still ranks below a moderate-TVL DEX.

### 10.4 Monitoring Tier Assignment

When a protocol enters the watchlist, it is assigned a `monitoring_tier` that determines which metrics are collected:

| Tier | Applies To | Metrics Collected |
|------|-----------|-------------------|
| `special` | Aave V3 | `tvl`, `supply`, `borrowed`, `utilization` |
| `dex` | DEX protocols | `tvl`, `volume` |
| `generic` | Everything else | `tvl` |

### 10.5 Refresh Cadence

The watchlist refreshes **once daily** at a low-traffic hour (e.g., 04:00 UTC). Protocol additions and removals are logged. Removed protocols' historical snapshots are retained.

### 10.6 Seed Data

Initial watchlist for Phase 1 launch:

```python
WATCHLIST_SEED = [
    {"slug": "aave-v3",           "display_name": "Aave V3",               "category": "lending", "tier": "special", "pinned": True},
    {"slug": "merchant-moe-liquidity-book", "display_name": "Merchant Moe LB", "category": "dex",     "tier": "dex",     "pinned": False},
    {"slug": "merchant-moe-dex",  "display_name": "Merchant Moe DEX",      "category": "dex",     "tier": "dex",     "pinned": False},
    {"slug": "agni-finance",      "display_name": "Agni Finance",          "category": "dex",     "tier": "dex",     "pinned": False},
    {"slug": "ondo-finance",      "display_name": "Ondo Yield Assets",     "category": "rwa",     "tier": "generic",  "pinned": False},
    {"slug": "treehouse-protocol","display_name": "Treehouse Protocol",    "category": "yield",   "tier": "generic",  "pinned": False},
    {"slug": "mantle-index-four", "display_name": "Mantle Index Four Fund","category": "index",   "tier": "generic",  "pinned": False},
    {"slug": "cian-protocol",     "display_name": "CIAN Yield Layer",      "category": "yield",   "tier": "generic",  "pinned": False},
    {"slug": "compound-v3",       "display_name": "Compound V3",           "category": "lending", "tier": "generic",  "pinned": False},
    {"slug": "init-capital",      "display_name": "INIT Capital",          "category": "lending", "tier": "generic",  "pinned": False},
    {"slug": "lendle",            "display_name": "Lendle",                "category": "lending", "tier": "generic",  "pinned": False},
    {"slug": "fluxion-network",   "display_name": "Fluxion Network",       "category": "dex",     "tier": "dex",     "pinned": False},
]
```

---

## 11. Aave Special Adapter

### 11.1 Why Special

Aave provides deeper capital-usage signal than TVL alone. The PRD requires tracking supply, borrowed, and utilization separately with their own ATH/milestone/threshold rules.

### 11.2 Data Extraction from DefiLlama

DefiLlama's `/api/protocol/aave-v3` response includes a `chainTvls` object with per-chain breakdowns:

```json
{
  "chainTvls": {
    "Mantle": {
      "tvl": [{"date": 1710000000, "totalLiquidityUSD": 245000000}],
      "tokensInUsd": [...]
    },
    "Mantle-borrowed": {
      "tvl": [{"date": 1710000000, "totalLiquidityUSD": 89000000}]
    }
  }
}
```

Mapping:

| Metric | DefiLlama Field | Derivation |
|--------|----------------|------------|
| `supply` | `chainTvls["Mantle"].tvl[-1].totalLiquidityUSD` | Direct |
| `borrowed` | `chainTvls["Mantle-borrowed"].tvl[-1].totalLiquidityUSD` | Direct |
| `utilization` | -- | `borrowed / supply` |
| `tvl` | -- | `supply - borrowed` (net TVL) |

### 11.3 AaveAdapter

```python
class AaveAdapter:
    SLUG = "aave-v3"

    async def collect(self, http: httpx.AsyncClient) -> list[MetricRecord]:
        data = await http.get(f"https://api.llama.fi/api/protocol/{self.SLUG}")
        chain_tvls = data.json()["chainTvls"]

        supply_entries = chain_tvls.get("Mantle", {}).get("tvl", [])
        borrow_entries = chain_tvls.get("Mantle-borrowed", {}).get("tvl", [])

        supply = Decimal(str(supply_entries[-1]["totalLiquidityUSD"]))
        borrowed = Decimal(str(borrow_entries[-1]["totalLiquidityUSD"]))
        utilization = borrowed / supply if supply > 0 else Decimal(0)

        return [
            MetricRecord(scope="ecosystem", entity="aave-v3", metric_name="supply",
                         value=supply, unit="usd", ...),
            MetricRecord(scope="ecosystem", entity="aave-v3", metric_name="borrowed",
                         value=borrowed, unit="usd", ...),
            MetricRecord(scope="ecosystem", entity="aave-v3", metric_name="utilization",
                         value=utilization, unit="percent", ...),
            MetricRecord(scope="ecosystem", entity="aave-v3", metric_name="tvl",
                         value=supply - borrowed, unit="usd", ...),
        ]
```

### 11.4 Aave-Specific Alert Rules

In addition to the standard threshold/ATH/milestone rules applied to all metrics, the following Aave-specific conditions are evaluated:

| Condition | Logic | Severity |
|-----------|-------|----------|
| Supply ATH | `supply > max(historical supply)` | `critical` |
| Borrowed ATH | `borrowed > max(historical borrowed)` | `critical` |
| Supply + Borrowed dual milestone | Both cross milestones in same evaluation | `critical` |
| Utilization crosses 50%, 70%, 80% | Threshold crossing from below | `high` |
| Utilization drops below 30% | May signal capital flight | `moderate` |

### 11.5 Utilization Thresholds

```python
UTILIZATION_THRESHOLDS = [
    {"boundary": Decimal("0.80"), "direction": "above", "severity": "critical", "label": "80% utilization"},
    {"boundary": Decimal("0.70"), "direction": "above", "severity": "high",     "label": "70% utilization"},
    {"boundary": Decimal("0.50"), "direction": "above", "severity": "moderate", "label": "50% utilization"},
    {"boundary": Decimal("0.30"), "direction": "below", "severity": "moderate", "label": "sub-30% utilization"},
]
```

---

## 12. API Endpoints

### 12.1 Overview

All endpoints are prefixed with `/api`. Responses use JSON. Authentication is deferred to Phase 2 (internal tool).

### 12.2 Alert Feed

**`GET /api/alerts`** - List alerts with filtering

Query parameters:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `scope` | string | -- | Filter by `core` or `ecosystem` |
| `entity` | string | -- | Filter by entity slug |
| `severity` | string | -- | Filter by severity level |
| `is_ath` | bool | -- | Filter ATH alerts only |
| `is_milestone` | bool | -- | Filter milestone alerts only |
| `reviewed` | bool | -- | Filter by review status |
| `since` | datetime | 7 days ago | Start of time range |
| `until` | datetime | now | End of time range |
| `limit` | int | 50 | Max results |
| `offset` | int | 0 | Pagination offset |

Response:

```json
{
  "total": 142,
  "alerts": [
    {
      "id": 1023,
      "scope": "core",
      "entity": "mantle",
      "metric_name": "tvl",
      "current_value": "1523000000",
      "formatted_value": "$1.52B",
      "time_window": "7d",
      "change_pct": "0.187",
      "severity": "moderate",
      "trigger_reason": "threshold_18pct_7d",
      "source_platform": "defillama",
      "source_ref": "https://defillama.com/chain/Mantle",
      "detected_at": "2026-03-13T06:00:00Z",
      "is_ath": false,
      "is_milestone": false,
      "milestone_label": null,
      "reviewed": false,
      "ai_eligible": false
    }
  ]
}
```

**`PATCH /api/alerts/{id}/review`** - Mark an alert as reviewed

Request body:

```json
{
  "reviewed": true,
  "review_note": "Shared in weekly report"
}
```

### 12.3 Metrics

**`GET /api/metrics/latest`** - Latest snapshot per entity/metric

Query parameters: `scope`, `entity`, `metric_name`

Response:

```json
{
  "snapshots": [
    {
      "entity": "mantle",
      "metric_name": "tvl",
      "value": "1523000000",
      "formatted_value": "$1.52B",
      "source_platform": "defillama",
      "collected_at": "2026-03-13T04:00:00Z"
    }
  ]
}
```

**`GET /api/metrics/history`** - Historical snapshots for a single metric

Query parameters: `entity` (required), `metric_name` (required), `since`, `until`, `limit`

### 12.4 Watchlist

**`GET /api/watchlist`** - Current active watchlist

**`POST /api/watchlist/refresh`** - Trigger an immediate watchlist refresh from DefiLlama

### 12.5 Health and Observability

**`GET /api/health`** - System health

Response:

```json
{
  "status": "healthy",
  "db": "connected",
  "last_source_runs": {
    "defillama": {"status": "success", "at": "2026-03-13T04:01:23Z"},
    "growthepie": {"status": "not_run", "at": null},
    "l2beat": {"status": "failed", "at": "2026-03-13T04:02:01Z", "error": "timeout"},
    "dune": {"status": "success", "at": "2026-03-13T04:03:12Z"},
    "coingecko": {"status": "success", "at": "2026-03-13T04:01:30Z"}
  },
  "next_scheduled_run": "2026-03-13T08:00:00Z"
}
```

**`GET /api/health/sources`** - Detailed source run history

Query parameters: `source_platform`, `limit` (default 20)

---

## 13. Scheduler Design

### 13.1 Job Definitions

The scheduler uses APScheduler 4 with an async scheduler running inside the FastAPI lifespan. All times are UTC.

| Job ID | Description | Cadence | Targets |
|--------|-------------|---------|---------|
| `core_defillama` | Collect TVL, stablecoin supply/mcap | Every 4 hours | DefiLlama |
| `core_dune` | Collect DAU, active addresses, tx count, stablecoin transfer volume, DEX volume | Every 6 hours | Dune |
| `core_l2beat` | Collect Total Value Secured | Every 6 hours | L2Beat |
| `core_coingecko` | Collect MNT volume, MNT market cap | Every 4 hours | CoinGecko |
| `core_growthepie_fallback` | Collect fallback DAU, active addresses, tx count only when needed | On-demand | Growthepie |
| `eco_protocols` | Collect all watchlist protocol metrics | Every 6 hours | DefiLlama |
| `eco_aave` | Collect Aave supply/borrowed/utilization | Every 4 hours | DefiLlama |
| `watchlist_refresh` | Refresh dynamic watchlist from DefiLlama | Daily at 04:00 UTC | DefiLlama |
| `rule_evaluation` | Run rule engine on latest snapshots | After each collection job | Internal |
| `source_health` | Check source reachability | Every 1 hour | All sources |

### 13.2 Job Orchestration

Each collection job follows this sequence:

```mermaid
flowchart LR
    A[Scheduler Fires] --> B[Collector.collect]
    B --> C{Success?}
    C -->|Yes| D[Store Snapshots]
    C -->|No| E[Log source_run failure]
    E --> F[Try Fallback?]
    F -->|Yes| G[Fallback Collector]
    F -->|No| H[Done]
    G --> C
    D --> I[Log source_run success]
    I --> J[Rule Engine.evaluate]
    J --> K[Store Alerts]
    K --> H
```

### 13.3 Staggering

Jobs are staggered by a few minutes to avoid hitting rate limits on shared sources (especially Dune, DefiLlama, and CoinGecko):

```python
scheduler.add_job(core_defillama_job, CronTrigger(hour="*/4", minute=0))
scheduler.add_job(core_coingecko_job, CronTrigger(hour="*/4", minute=5))
scheduler.add_job(eco_aave_job,       CronTrigger(hour="*/4", minute=10))
scheduler.add_job(core_l2beat_job,     CronTrigger(hour="*/6", minute=15))
scheduler.add_job(core_dune_job,       CronTrigger(hour="*/6", minute=20))
scheduler.add_job(eco_protocols_job,   CronTrigger(hour="*/6", minute=30))
scheduler.add_job(watchlist_refresh,   CronTrigger(hour=4,     minute=0))
scheduler.add_job(source_health_check, CronTrigger(hour="*",   minute=45))
```

### 13.4 Failure Handling

- If a collector fails after retries, the `source_runs` row records the failure.
- The rule engine skips evaluation for metrics with no new snapshot (stale data is not re-evaluated).
- The `/api/health` endpoint surfaces stale sources so operators can investigate.
- Growthepie is retained only as a manual or targeted fallback for selected activity metrics.
- No automatic fallback switching in Phase 1. Fallback sources are manual override only. Automatic failover is a Phase 3 enhancement.

---

## 14. Configuration

### 14.1 Environment Variables

All sensitive configuration is loaded from environment variables (or a `.env` file in development).

```ini
# --- Database ---
DATABASE_URL=postgresql+asyncpg://monitor:password@localhost:5432/mantle_monitor

# --- API Keys ---
DUNE_API_KEY=
COINGECKO_API_KEY=

# --- Dune Queries ---
DUNE_DAILY_ACTIVE_USERS_QUERY_ID=1234501
DUNE_ACTIVE_ADDRESSES_QUERY_ID=1234502
DUNE_CHAIN_TRANSACTIONS_QUERY_ID=1234503
DUNE_STABLECOIN_VOLUME_QUERY_ID=1234567
DUNE_DEX_VOLUME_QUERY_ID=1234504

# --- Feature Flags ---
AI_ENRICHMENT_ENABLED=false
LARK_DELIVERY_ENABLED=false

# --- Scheduler ---
SCHEDULER_ENABLED=true

# --- Server ---
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=info
```

### 14.2 Pydantic Settings Class

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    dune_api_key: str = ""
    coingecko_api_key: str = ""
    dune_daily_active_users_query_id: int = 0
    dune_active_addresses_query_id: int = 0
    dune_chain_transactions_query_id: int = 0
    dune_stablecoin_volume_query_id: int = 0
    dune_dex_volume_query_id: int = 0
    ai_enrichment_enabled: bool = False
    lark_delivery_enabled: bool = False
    scheduler_enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```

### 14.3 Threshold and Milestone Config

Stored in Python config files (`config/thresholds.py`, `config/milestones.py`) rather than in the database. This keeps alert tuning in version control and makes it auditable. See sections 8.5 and 9.2 for the data structures.

### 14.4 Docker Compose

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: mantle_monitor
      POSTGRES_USER: monitor
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  app:
    build: .
    depends_on:
      - db
    env_file:
      - .env
    ports:
      - "8000:8000"

volumes:
  pgdata:
```

---

## 15. Phase 2/3 Extension Points

The Phase 1 architecture is designed with clear seams for future features. No Phase 2/3 code is written in Phase 1, but the following extension points are preserved.

### 15.1 AI Enrichment (Phase 2)

**Hook location**: after `RuleEngine.evaluate()` returns alert candidates, before they are written to `alert_events`.

```mermaid
flowchart LR
    RE[RuleEngine] --> AC[AlertCandidates]
    AC --> AI{AI Enabled?}
    AI -->|No| DB[(Write to DB)]
    AI -->|Yes| AIS[AI Service]
    AIS --> ENR[Enriched Alerts]
    ENR --> DB
```

**New columns on `alert_events`** (added via Alembic migration in Phase 2):

```sql
ALTER TABLE alert_events ADD COLUMN ai_reason TEXT;
ALTER TABLE alert_events ADD COLUMN ai_signal_strength TEXT;
ALTER TABLE alert_events ADD COLUMN ai_draft_copy TEXT;
ALTER TABLE alert_events ADD COLUMN ai_visual_suggestion TEXT;
ALTER TABLE alert_events ADD COLUMN ai_combine_recommendation TEXT;
```

**AI Service interface** (stubbed in Phase 1):

```python
class AIEnrichmentService(ABC):
    @abstractmethod
    async def enrich(self, candidate: AlertCandidate) -> AIEnrichment:
        ...

@dataclass
class AIEnrichment:
    reason: str
    signal_strength: str       # 'weak' | 'moderate' | 'strong' | 'very_strong'
    draft_copy: str
    visual_suggestion: str
    combine_recommendation: str | None
```

### 15.2 Lark Delivery (Phase 2)

**Hook location**: after alerts are persisted, a delivery step fans out to configured channels.

**New module**: `src/delivery/lark.py`

```python
class LarkDelivery:
    async def send_alert_card(self, alert: AlertEvent) -> bool:
        """POST structured card to Lark webhook."""
```

The `LARK_DELIVERY_ENABLED` feature flag controls whether this step runs. The webhook URL is stored in an environment variable `LARK_WEBHOOK_URL`.

### 15.3 Weekly/Monthly Digests (Phase 3)

**Hook location**: a new scheduled job that aggregates alerts and snapshots over a period.

**New module**: `src/delivery/digest.py`

The digest job queries `alert_events` and `metric_snapshots` for the past week/month, groups by entity, and generates a summary payload. This summary can be delivered to Lark or rendered in the API as a dedicated `/api/digests` endpoint.

### 15.4 Automatic Failover (Phase 3)

**Hook location**: inside the collector layer, a `SourceRouter` sits in front of collectors and automatically switches to fallback sources when the primary fails N times in a row.

```python
class SourceRouter:
    async def collect(self, metric: str) -> list[MetricRecord]:
        for source in self._get_sources_by_priority(metric):
            try:
                return await source.collect()
            except CollectorError:
                continue
        raise AllSourcesFailedError(metric)
```

### 15.5 Extension Summary

| Feature | Phase | Extension Point | New Files |
|---------|-------|----------------|-----------|
| AI enrichment | 2 | Post-rule-engine hook | `src/ai/service.py`, `src/ai/prompts.py` |
| Lark delivery | 2 | Post-persist hook | `src/delivery/lark.py` |
| Weekly digest | 3 | New scheduler job | `src/delivery/digest.py` |
| Auto failover | 3 | Collector wrapper | `src/ingestion/router.py` |
| Watchlist tuning | 3 | Enhanced scoring | Update `src/protocols/watchlist.py` |

---

## Appendix A: Metric Name Registry

Canonical `metric_name` values used across snapshots and alerts:

| metric_name | Scope | Entity | Unit |
|-------------|-------|--------|------|
| `tvl` | core | `mantle` | usd |
| `total_value_secured` | core | `mantle` | usd |
| `daily_active_users` | core | `mantle` | count |
| `active_addresses` | core | `mantle` | count |
| `stablecoin_supply` | core | `mantle` | usd |
| `stablecoin_mcap` | core | `mantle` | usd |
| `chain_transactions` | core | `mantle` | count |
| `stablecoin_transfer_volume` | core | `mantle` | usd |
| `dex_volume` | core | `mantle` | usd |
| `mnt_volume` | core | `mantle` | usd |
| `mnt_market_cap` | core | `mantle` | usd |
| `tvl` | ecosystem | `{protocol_slug}` | usd |
| `volume` | ecosystem | `{protocol_slug}` | usd |
| `supply` | ecosystem | `aave-v3` | usd |
| `borrowed` | ecosystem | `aave-v3` | usd |
| `utilization` | ecosystem | `aave-v3` | percent |

---

## Appendix B: Time Window Enum

```python
from enum import Enum

class TimeWindow(str, Enum):
    D7 = "7d"
    MTD = "mtd"
    M1 = "1m"
    M3 = "3m"
    M6 = "6m"
    YTD = "ytd"
    Y1 = "1y"
    ALL_TIME = "all_time"
    ATH = "ath"  # special: query max value, not time-bounded
```
