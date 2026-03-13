# Mantle Phase 1 Monitor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Phase 1 backend-only Mantle monitor that ingests Dune-first core metrics and DefiLlama-based ecosystem metrics, stores snapshots and alert events in PostgreSQL, and exposes an internal alert feed API.

**Architecture:** Use a single FastAPI service with APScheduler for collection jobs, SQLAlchemy/Alembic for PostgreSQL persistence, Dune as the primary source for queryable chain activity metrics, and DefiLlama/L2Beat/CoinGecko/Growthepie only where Dune is not appropriate or as explicit fallback. Keep alert generation deterministic in Phase 1: collectors write `metric_snapshots`, the rule engine writes `alert_events`, and the backend exposes read/review APIs without Lark delivery.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL 16, APScheduler 4, httpx, pytest, Dune API, DefiLlama, L2Beat, CoinGecko, Growthepie fallback

---

## Reference Docs

- Read first: `specs/DESIGN.md`
- Product summary: `specs/prd-simple.md`
- Execution skills to use during implementation:
  - `@superpowers/test-driven-development`
  - `@superpowers/systematic-debugging`
  - `@superpowers/verification-before-completion`

## Milestones

| Milestone | Outcome |
|-----------|---------|
| M1 | App boots, config loads, database schema exists |
| M2 | Core Dune-first metrics ingest into `metric_snapshots` |
| M3 | Ecosystem watchlist and Aave special adapter ingest successfully |
| M4 | Rule engine writes `alert_events` and scheduler runs jobs |
| M5 | Internal alert feed API is usable by BD/Social reviewers |

## Dune Query Inventory

Create and version these SQL files locally, then save them as Dune queries and store the resulting IDs in `.env`.

| Metric | Local SQL File | Env Var |
|--------|----------------|---------|
| Daily Active Users | `queries/dune/daily_active_users.sql` | `DUNE_DAILY_ACTIVE_USERS_QUERY_ID` |
| Active Addresses | `queries/dune/active_addresses.sql` | `DUNE_ACTIVE_ADDRESSES_QUERY_ID` |
| Mantle Chain Transactions | `queries/dune/chain_transactions.sql` | `DUNE_CHAIN_TRANSACTIONS_QUERY_ID` |
| Stablecoin Transfer Volume | `queries/dune/stablecoin_transfer_volume.sql` | `DUNE_STABLECOIN_VOLUME_QUERY_ID` |
| DEX Volume | `queries/dune/dex_volume.sql` | `DUNE_DEX_VOLUME_QUERY_ID` |

## Phase 1 Scope Guardrails

- Do not implement Lark delivery.
- Do not implement AI enrichment beyond a stub interface.
- Do not add Artemis or Nansen integration.
- Do not add automatic fallback switching.
- Do not implement user auth beyond internal access assumptions.

### Task 1: Bootstrap the Service Shell

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `src/main.py`
- Create: `src/api/__init__.py`
- Create: `src/api/routes/__init__.py`
- Create: `src/api/routes/health.py`
- Create: `tests/test_api/test_health.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient

from src.main import create_app


def test_health_endpoint_returns_ok():
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api/test_health.py::test_health_endpoint_returns_ok -v`
Expected: FAIL with `ModuleNotFoundError` or missing route error.

**Step 3: Write minimal implementation**

```python
from fastapi import APIRouter, FastAPI


health_router = APIRouter()


@health_router.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


def create_app() -> FastAPI:
    app = FastAPI(title="Mantle Monitor")
    app.include_router(health_router)
    return app
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_api/test_health.py::test_health_endpoint_returns_ok -v`
Expected: PASS

**Step 5: Commit**

```bash
git add pyproject.toml .env.example src/__init__.py src/main.py src/api/__init__.py src/api/routes/__init__.py src/api/routes/health.py tests/test_api/test_health.py
git commit -m "feat: bootstrap fastapi service shell"
```

### Task 2: Add Settings and Environment Loading

**Files:**
- Create: `config/__init__.py`
- Create: `config/settings.py`
- Modify: `.env.example`
- Modify: `src/main.py`
- Create: `tests/test_config/test_settings.py`

**Step 1: Write the failing test**

```python
from config.settings import Settings


def test_settings_load_dune_query_ids():
    settings = Settings(
        database_url="postgresql+asyncpg://x:y@localhost:5432/mantle_monitor",
        dune_api_key="token",
        dune_daily_active_users_query_id=1,
        dune_active_addresses_query_id=2,
        dune_chain_transactions_query_id=3,
        dune_stablecoin_volume_query_id=4,
        dune_dex_volume_query_id=5,
    )

    assert settings.dune_api_key == "token"
    assert settings.dune_dex_volume_query_id == 5
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config/test_settings.py::test_settings_load_dune_query_ids -v`
Expected: FAIL because `config/settings.py` does not exist.

**Step 3: Write minimal implementation**

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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config/test_settings.py::test_settings_load_dune_query_ids -v`
Expected: PASS

**Step 5: Commit**

```bash
git add config/__init__.py config/settings.py .env.example src/main.py tests/test_config/test_settings.py
git commit -m "feat: add typed settings for phase1 monitor"
```

### Task 3: Add Database Engine and ORM Models

**Files:**
- Create: `src/db/__init__.py`
- Create: `src/db/engine.py`
- Create: `src/db/models.py`
- Create: `tests/test_db/test_models.py`

**Step 1: Write the failing test**

```python
from src.db.models import AlertEvent, MetricSnapshot, SourceRun, WatchlistProtocol


def test_expected_tables_exist():
    assert MetricSnapshot.__tablename__ == "metric_snapshots"
    assert AlertEvent.__tablename__ == "alert_events"
    assert WatchlistProtocol.__tablename__ == "watchlist_protocols"
    assert SourceRun.__tablename__ == "source_runs"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_db/test_models.py::test_expected_tables_exist -v`
Expected: FAIL because ORM models do not exist.

**Step 3: Write minimal implementation**

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)


class AlertEvent(Base):
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(primary_key=True)
```

Add the rest of the columns from `specs/DESIGN.md` section 4 before moving on.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_db/test_models.py::test_expected_tables_exist -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/db/__init__.py src/db/engine.py src/db/models.py tests/test_db/test_models.py
git commit -m "feat: add database engine and orm models"
```

### Task 4: Create Alembic Migration for the Initial Schema

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/0001_initial_schema.py`
- Create: `tests/test_db/test_migration_smoke.py`

**Step 1: Write the failing test**

```python
def test_initial_migration_creates_all_phase1_tables(db_inspector):
    assert "metric_snapshots" in db_inspector.get_table_names()
    assert "alert_events" in db_inspector.get_table_names()
    assert "watchlist_protocols" in db_inspector.get_table_names()
    assert "source_runs" in db_inspector.get_table_names()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_db/test_migration_smoke.py::test_initial_migration_creates_all_phase1_tables -v`
Expected: FAIL because migrations have not been created or applied.

**Step 3: Write minimal implementation**

Create Alembic wiring and a single migration that creates:

- `metric_snapshots`
- `alert_events`
- `watchlist_protocols`
- `source_runs`

Use the exact columns and indexes from `specs/DESIGN.md`.

**Step 4: Run test to verify it passes**

Run:
- `alembic upgrade head`
- `pytest tests/test_db/test_migration_smoke.py::test_initial_migration_creates_all_phase1_tables -v`

Expected: migration succeeds; test PASS

**Step 5: Commit**

```bash
git add alembic.ini alembic/env.py alembic/versions/0001_initial_schema.py tests/test_db/test_migration_smoke.py
git commit -m "feat: add initial alembic schema migration"
```

### Task 5: Add Versioned Dune SQL Assets and Dune Client

**Files:**
- Create: `queries/dune/daily_active_users.sql`
- Create: `queries/dune/active_addresses.sql`
- Create: `queries/dune/chain_transactions.sql`
- Create: `queries/dune/stablecoin_transfer_volume.sql`
- Create: `queries/dune/dex_volume.sql`
- Create: `src/ingestion/__init__.py`
- Create: `src/ingestion/base.py`
- Create: `src/ingestion/dune.py`
- Create: `tests/test_ingestion/test_dune_client.py`

**Step 1: Write the failing test**

```python
from decimal import Decimal

from src.ingestion.dune import DuneCollector


def test_dune_collector_maps_query_rows_to_metric_records(fake_dune_client):
    collector = DuneCollector(fake_dune_client)

    records = collector._map_rows(
        metric_name="daily_active_users",
        rows=[{"day": "2026-03-13", "value": 12345}],
    )

    assert records[0].metric_name == "daily_active_users"
    assert records[0].value == Decimal("12345")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingestion/test_dune_client.py::test_dune_collector_maps_query_rows_to_metric_records -v`
Expected: FAIL because `DuneCollector` does not exist.

**Step 3: Write minimal implementation**

Implement:

- a lightweight Dune API client that runs saved queries by ID
- `DuneCollector` methods for:
  - daily active users
  - active addresses
  - chain transactions
  - stablecoin transfer volume
  - DEX volume
- SQL files stored in `queries/dune/` as the local source of truth

Example SQL shape:

```sql
select
  date_trunc('day', block_time) as day,
  count(distinct "from") as value
from mantle.transactions
group by 1
order by 1 desc;
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingestion/test_dune_client.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add queries/dune/*.sql src/ingestion/__init__.py src/ingestion/base.py src/ingestion/dune.py tests/test_ingestion/test_dune_client.py
git commit -m "feat: add dune query assets and collector"
```

### Task 6: Implement DefiLlama, L2Beat, CoinGecko, and Growthepie Fallback Collectors

**Files:**
- Create: `src/ingestion/defillama.py`
- Create: `src/ingestion/l2beat.py`
- Create: `src/ingestion/coingecko.py`
- Create: `src/ingestion/growthepie.py`
- Create: `src/ingestion/normalize.py`
- Create: `tests/test_ingestion/test_defillama.py`
- Create: `tests/test_ingestion/test_l2beat.py`
- Create: `tests/test_ingestion/test_coingecko.py`
- Create: `tests/test_ingestion/test_growthepie.py`

**Step 1: Write the failing tests**

```python
def test_defillama_collector_maps_chain_tvl(sample_defillama_tvl_payload):
    ...


def test_l2beat_collector_maps_total_value_secured(sample_l2beat_payload):
    ...


def test_coingecko_collector_maps_mnt_metrics(sample_coingecko_payload):
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingestion/test_defillama.py tests/test_ingestion/test_l2beat.py tests/test_ingestion/test_coingecko.py -v`
Expected: FAIL because the collectors do not exist.

**Step 3: Write minimal implementation**

Implement:

- `DefiLlamaCollector` for:
  - chain TVL
  - stablecoin supply
  - stablecoin market cap
  - protocol TVL data
  - DEX protocol volume for ecosystem watchlist entries
- `L2BeatCollector` for Total Value Secured
- `CoinGeckoCollector` for MNT volume and market cap
- `GrowthepieCollector` only as a manual/targeted fallback for DAU, active addresses, and tx count
- formatting helpers in `normalize.py`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingestion/test_defillama.py tests/test_ingestion/test_l2beat.py tests/test_ingestion/test_coingecko.py tests/test_ingestion/test_growthepie.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ingestion/defillama.py src/ingestion/l2beat.py src/ingestion/coingecko.py src/ingestion/growthepie.py src/ingestion/normalize.py tests/test_ingestion/test_defillama.py tests/test_ingestion/test_l2beat.py tests/test_ingestion/test_coingecko.py tests/test_ingestion/test_growthepie.py
git commit -m "feat: add non-dune collectors for core and fallback sources"
```

### Task 7: Implement Protocol Adapters and the Hybrid Watchlist

**Files:**
- Create: `config/watchlist_seed.py`
- Create: `src/protocols/__init__.py`
- Create: `src/protocols/base.py`
- Create: `src/protocols/registry.py`
- Create: `src/protocols/aave.py`
- Create: `src/protocols/dex.py`
- Create: `src/protocols/watchlist.py`
- Create: `tests/test_protocols/test_aave_adapter.py`
- Create: `tests/test_protocols/test_watchlist.py`

**Step 1: Write the failing tests**

```python
def test_aave_adapter_returns_supply_borrowed_utilization(sample_aave_payload):
    ...


def test_watchlist_manager_preserves_pinned_aave_and_refreshes_dynamic_slots(sample_protocol_list):
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_protocols/test_aave_adapter.py tests/test_protocols/test_watchlist.py -v`
Expected: FAIL because the adapters and manager do not exist.

**Step 3: Write minimal implementation**

Implement:

- `AaveAdapter` extracting:
  - `supply`
  - `borrowed`
  - `utilization`
  - `tvl`
- `DexAdapter` for ecosystem `tvl` + `volume`
- generic handling in `base.py`
- `WatchlistManager` that:
  - seeds pinned Aave
  - fetches DefiLlama protocol list
  - filters Mantle protocols
  - scores candidates
  - preserves pinned entries
  - upserts the top dynamic protocols

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_protocols/test_aave_adapter.py tests/test_protocols/test_watchlist.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add config/watchlist_seed.py src/protocols/__init__.py src/protocols/base.py src/protocols/registry.py src/protocols/aave.py src/protocols/dex.py src/protocols/watchlist.py tests/test_protocols/test_aave_adapter.py tests/test_protocols/test_watchlist.py
git commit -m "feat: add ecosystem protocol adapters and hybrid watchlist"
```

### Task 8: Add Snapshot, Alert, and Source Run Persistence Helpers

**Files:**
- Create: `src/db/repositories.py`
- Create: `tests/test_db/test_repositories.py`

**Step 1: Write the failing test**

```python
def test_snapshot_repository_skips_duplicate_daily_snapshot(db_session):
    ...


def test_source_run_repository_records_success_and_failure(db_session):
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_db/test_repositories.py -v`
Expected: FAIL because the repository helpers do not exist.

**Step 3: Write minimal implementation**

Implement repository helpers for:

- inserting `metric_snapshots`
- deduplicating by `(entity, metric_name, collected_at logical period)`
- inserting `source_runs`
- inserting `alert_events`
- updating `watchlist_protocols`

Keep the repository layer thin. Avoid premature abstractions.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_db/test_repositories.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/db/repositories.py tests/test_db/test_repositories.py
git commit -m "feat: add persistence helpers for snapshots alerts and source runs"
```

### Task 9: Implement the Rule Engine

**Files:**
- Create: `config/thresholds.py`
- Create: `config/milestones.py`
- Create: `src/rules/__init__.py`
- Create: `src/rules/engine.py`
- Create: `src/rules/thresholds.py`
- Create: `src/rules/ath.py`
- Create: `src/rules/milestones.py`
- Create: `src/rules/decline.py`
- Create: `src/rules/multi_signal.py`
- Create: `src/rules/cooldown.py`
- Create: `tests/test_rules/test_thresholds.py`
- Create: `tests/test_rules/test_ath.py`
- Create: `tests/test_rules/test_milestones.py`
- Create: `tests/test_rules/test_cooldown.py`

**Step 1: Write the failing tests**

```python
def test_threshold_rule_emits_moderate_alert_for_15pct_7d_growth():
    ...


def test_new_ath_rule_emits_priority_override_alert():
    ...


def test_cooldown_rule_suppresses_duplicate_alert():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_rules/test_thresholds.py tests/test_rules/test_ath.py tests/test_rules/test_milestones.py tests/test_rules/test_cooldown.py -v`
Expected: FAIL because the rule modules do not exist.

**Step 3: Write minimal implementation**

Implement deterministic rules for:

- percentage thresholds
- ATH detection
- milestone crossings
- major declines
- multi-signal coincidence
- cooldown suppression

The engine should read from `metric_snapshots` and write plain alert candidate objects that are later persisted into `alert_events`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_rules/test_thresholds.py tests/test_rules/test_ath.py tests/test_rules/test_milestones.py tests/test_rules/test_cooldown.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add config/thresholds.py config/milestones.py src/rules/__init__.py src/rules/engine.py src/rules/thresholds.py src/rules/ath.py src/rules/milestones.py src/rules/decline.py src/rules/multi_signal.py src/rules/cooldown.py tests/test_rules/test_thresholds.py tests/test_rules/test_ath.py tests/test_rules/test_milestones.py tests/test_rules/test_cooldown.py
git commit -m "feat: add deterministic alert rule engine"
```

### Task 10: Wire the Scheduler and Collection Orchestration

**Files:**
- Create: `src/scheduler/__init__.py`
- Create: `src/scheduler/jobs.py`
- Modify: `src/main.py`
- Create: `tests/test_scheduler/test_jobs.py`

**Step 1: Write the failing test**

```python
def test_scheduler_registers_phase1_jobs():
    job_ids = build_scheduler().get_jobs()
    assert {job.id for job in job_ids} >= {
        "core_defillama",
        "core_dune",
        "core_l2beat",
        "core_coingecko",
        "eco_protocols",
        "eco_aave",
        "watchlist_refresh",
    }
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scheduler/test_jobs.py::test_scheduler_registers_phase1_jobs -v`
Expected: FAIL because the scheduler module does not exist.

**Step 3: Write minimal implementation**

Implement:

- APScheduler setup
- job registration for:
  - `core_defillama`
  - `core_dune`
  - `core_l2beat`
  - `core_coingecko`
  - `core_growthepie_fallback`
  - `eco_protocols`
  - `eco_aave`
  - `watchlist_refresh`
  - `source_health`
- post-collection rule evaluation hook
- app lifespan startup/shutdown wiring in `src/main.py`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_scheduler/test_jobs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/scheduler/__init__.py src/scheduler/jobs.py src/main.py tests/test_scheduler/test_jobs.py
git commit -m "feat: wire scheduler and collection orchestration"
```

### Task 11: Add API Schemas and Routes for Internal Review

**Files:**
- Create: `src/api/deps.py`
- Create: `src/api/schemas.py`
- Create: `src/api/routes/alerts.py`
- Create: `src/api/routes/metrics.py`
- Create: `src/api/routes/watchlist.py`
- Modify: `src/api/routes/health.py`
- Modify: `src/main.py`
- Create: `tests/test_api/test_alerts.py`
- Create: `tests/test_api/test_metrics.py`
- Create: `tests/test_api/test_watchlist.py`

**Step 1: Write the failing tests**

```python
def test_get_alerts_returns_filterable_results(client, seeded_alerts):
    ...


def test_get_metrics_history_returns_ordered_points(client, seeded_snapshots):
    ...


def test_get_watchlist_returns_pinned_aave(client, seeded_watchlist):
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api/test_alerts.py tests/test_api/test_metrics.py tests/test_api/test_watchlist.py -v`
Expected: FAIL because the routes and schemas do not exist.

**Step 3: Write minimal implementation**

Expose:

- `GET /api/alerts`
- `PATCH /api/alerts/{id}/review`
- `GET /api/metrics/latest`
- `GET /api/metrics/history`
- `GET /api/watchlist`
- `POST /api/watchlist/refresh`
- `GET /api/health`
- `GET /api/health/sources`

Return JSON only. Keep handlers thin and move DB logic into repository helpers.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_api/test_alerts.py tests/test_api/test_metrics.py tests/test_api/test_watchlist.py tests/test_api/test_health.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/deps.py src/api/schemas.py src/api/routes/alerts.py src/api/routes/metrics.py src/api/routes/watchlist.py src/api/routes/health.py src/main.py tests/test_api/test_alerts.py tests/test_api/test_metrics.py tests/test_api/test_watchlist.py tests/test_api/test_health.py
git commit -m "feat: add internal review api routes"
```

### Task 12: Add End-to-End Phase 1 Smoke Coverage and Final Verification

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_integration/test_phase1_smoke.py`
- Modify: `.env.example`
- Optional create: `README.md`

**Step 1: Write the failing test**

```python
def test_phase1_pipeline_writes_snapshot_and_alert(test_app, seeded_query_results):
    """
    1. run one Dune collection
    2. persist snapshots
    3. run rule engine
    4. assert one alert appears in GET /api/alerts
    """
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration/test_phase1_smoke.py::test_phase1_pipeline_writes_snapshot_and_alert -v`
Expected: FAIL until the full pipeline is wired together.

**Step 3: Write minimal implementation**

Add the missing glue:

- shared pytest fixtures
- in-memory or test Postgres setup
- orchestration helpers needed by the smoke test
- `.env.example` entries for every active Phase 1 variable

**Step 4: Run test to verify it passes**

Run:
- `pytest tests/test_integration/test_phase1_smoke.py -v`
- `pytest -v`

Expected: all tests PASS

**Step 5: Commit**

```bash
git add tests/conftest.py tests/test_integration/test_phase1_smoke.py .env.example README.md
git commit -m "test: add end-to-end phase1 smoke coverage"
```

## Final Verification Checklist

Before calling Phase 1 implementation complete, run all of the following and record the output:

1. `alembic upgrade head`
2. `pytest -v`
3. `python -m compileall src`
4. `uvicorn src.main:create_app --factory --host 127.0.0.1 --port 8000`
5. `curl http://127.0.0.1:8000/api/health`
6. `curl "http://127.0.0.1:8000/api/alerts"`

## Expected Deliverables

At the end of this plan, the repository should contain:

- a bootable FastAPI backend
- PostgreSQL schema and migrations
- Dune-first core collectors
- DefiLlama ecosystem collectors and Aave special handling
- hybrid ecosystem watchlist support
- deterministic alert rule engine
- internal alert review APIs
- scheduler wiring
- end-to-end smoke coverage

## Open Items to Confirm During Execution

- the exact Dune table names available for Mantle activity queries
- the exact Dune query shape for DEX volume aggregation
- the exact L2Beat endpoint stability for TVS
- whether `README.md` should be added now or deferred
- whether a local Docker-based Postgres test flow is preferred over a shared development database
