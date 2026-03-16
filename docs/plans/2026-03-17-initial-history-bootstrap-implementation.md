# Initial History Bootstrap Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an explicit manual bootstrap flow that seeds full Dune history, full Mantle TVL history, and 90-day history for all other supported metrics, while leaving daily scheduled jobs to persist only the newest available row.

**Architecture:** Introduce a new admin bootstrap command and service that orchestrate source-specific history collectors. Keep regular `collect()` methods latest-only, add dedicated history methods for bootstrap-only use, remove startup-time implicit Dune bootstrapping, and make routine Dune sync incremental-only instead of implicit full bootstrap.

**Tech Stack:** Python 3.13, pytest, FastAPI lifespan hooks, SQLAlchemy async, httpx, APScheduler, admin CLI modules, source collectors, protocol adapters.

---

### Task 1: Lock failing tests for routine latest-only collection behavior

**Files:**
- Modify: `tests/test_ingestion/test_l2beat.py`
- Modify: `tests/test_ingestion/test_growthepie.py`
- Modify: `tests/test_ingestion/test_defillama.py`
- Modify: `tests/test_ingestion/test_coingecko.py`

**Step 1: Write the failing tests**

Add tests proving:

- `L2BeatCollector.collect()` still returns only the newest row while a new history method returns the newest 90-day window
- `GrowthepieCollector.collect()` persists only the newest Mantle day per mapped metric while a history helper can return a 90-day slice
- `DefiLlamaCollector.collect()` remains latest-only for routine collection, while bootstrap-only helpers can return history for chain TVL, stablecoin supply, chain dex volume, and chain stablecoin USD history
- `CoinGeckoCollector.collect()` remains latest-only while a history helper can return a 90-day slice

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ingestion/test_l2beat.py tests/test_ingestion/test_growthepie.py tests/test_ingestion/test_defillama.py tests/test_ingestion/test_coingecko.py -v`
Expected: FAIL because the collectors do not yet expose the required bootstrap/history split and Growthepie routine collection still maps all rows.

### Task 2: Lock failing tests for bootstrap CLI and orchestration

**Files:**
- Modify: `tests/test_admin/test_cli.py`
- Modify: `tests/test_admin/test_collect.py`
- Modify: `tests/test_admin/test_seed.py`
- Possibly create: `tests/test_admin/test_bootstrap.py`

**Step 1: Write the failing tests**

Add tests proving:

- admin CLI parses `bootstrap initial-history`
- dry-run bootstrap reports the source plan without writing
- applied bootstrap runs the expected jobs in order
- bootstrap uses full history for Mantle chain `tvl` and Dune metrics
- bootstrap uses 90-day windows for all other supported historical metrics

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_admin/test_cli.py tests/test_admin/test_seed.py tests/test_admin/test_collect.py tests/test_admin/test_bootstrap.py -v`
Expected: FAIL because there is no bootstrap command or orchestration service yet.

### Task 3: Lock failing tests for routine Dune semantics and startup behavior

**Files:**
- Modify: `tests/test_services/test_dune_sync.py`
- Modify: `tests/test_main.py`

**Step 1: Write the failing tests**

Add tests proving:

- routine Dune sync on missing state does not backfill full history
- routine Dune sync advances only the newest completed day when no state exists
- FastAPI startup no longer creates a background Dune sync task

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_services/test_dune_sync.py tests/test_main.py -v`
Expected: FAIL because Dune still bootstraps on missing state and app startup still launches background Dune sync.

### Task 4: Implement history helpers for core collectors

**Files:**
- Modify: `src/ingestion/l2beat.py`
- Modify: `src/ingestion/growthepie.py`
- Modify: `src/ingestion/defillama.py`
- Modify: `src/ingestion/coingecko.py`
- Possibly modify: related tests from Task 1

**Step 1: Write the minimal implementation**

Add explicit history helpers that return:

- full Mantle chain TVL history for bootstrap
- 90-day slices for L2Beat, Growthepie, CoinGecko, and the eligible DefiLlama core metrics

Keep `collect()` methods latest-only for routine scheduler use.

**Step 2: Run focused tests to verify they pass**

Run: `pytest tests/test_ingestion/test_l2beat.py tests/test_ingestion/test_growthepie.py tests/test_ingestion/test_defillama.py tests/test_ingestion/test_coingecko.py -v`
Expected: PASS

### Task 5: Implement bootstrap orchestration and admin CLI

**Files:**
- Create: `src/admin/bootstrap.py`
- Modify: `src/admin/__main__.py`
- Modify: `src/admin/runtime.py`
- Possibly modify: `src/admin/collect.py`
- Possibly modify: related tests from Task 2

**Step 1: Write the minimal implementation**

Add a bootstrap command such as:

```bash
python -m src.admin bootstrap initial-history --apply
```

The service should:

- dry-run when `--apply` is omitted
- refresh watchlist first
- run core history bootstrap
- run Dune full-history bootstrap
- run Aave bootstrap
- run curated ecosystem bootstrap

Use existing collection/runtime helpers where possible so writes and source runs stay consistent.

**Step 2: Run focused tests to verify they pass**

Run: `pytest tests/test_admin/test_cli.py tests/test_admin/test_seed.py tests/test_admin/test_collect.py tests/test_admin/test_bootstrap.py -v`
Expected: PASS

### Task 6: Implement ecosystem bootstrap history with strict Mantle volume semantics

**Files:**
- Modify: `src/protocols/aave.py`
- Modify: `src/protocols/generic.py`
- Modify: `src/protocols/dex.py`
- Modify: `src/protocols/aggregate.py`
- Possibly create: `src/protocols/history.py`
- Modify: `src/admin/bootstrap.py`
- Possibly modify: `tests/test_protocols/test_aave_adapter.py`
- Possibly modify: `tests/test_protocols/test_dex_adapter.py`
- Possibly create: bootstrap-focused ecosystem history tests

**Step 1: Write the minimal implementation**

Add bootstrap-only history collection for:

- ecosystem protocol `tvl` over 90 days
- Aave `tvl`, `supply`, `borrowed`, and `utilization` over 90 days
- ecosystem DEX `volume` over 90 days only when the history endpoint is chain-faithful for Mantle

Skip multichain DEX volume history when only protocol-wide historical series is available.

**Step 2: Run focused tests to verify they pass**

Run: `pytest tests/test_protocols/test_aave_adapter.py tests/test_protocols/test_dex_adapter.py tests/test_admin/test_bootstrap.py -v`
Expected: PASS

### Task 7: Make routine Dune sync incremental-only and remove startup Dune bootstrap

**Files:**
- Modify: `src/services/dune_sync.py`
- Modify: `src/main.py`
- Modify: `src/scheduler/jobs.py`
- Possibly modify: related tests from Task 3

**Step 1: Write the minimal implementation**

- remove the startup-created background Dune sync task
- add explicit bootstrap mode for Dune history initialization
- keep routine `core_dune` runs incremental-only so scheduler does not full-backfill on missing state

**Step 2: Run focused tests to verify they pass**

Run: `pytest tests/test_services/test_dune_sync.py tests/test_main.py tests/test_scheduler/test_jobs.py -v`
Expected: PASS

### Task 8: Run affected regression verification

**Files:**
- No code changes expected

**Step 1: Run the affected regression suite**

Run: `pytest tests/test_ingestion/test_l2beat.py tests/test_ingestion/test_growthepie.py tests/test_ingestion/test_defillama.py tests/test_ingestion/test_coingecko.py tests/test_protocols/test_aave_adapter.py tests/test_protocols/test_dex_adapter.py tests/test_admin/test_cli.py tests/test_admin/test_collect.py tests/test_admin/test_seed.py tests/test_admin/test_bootstrap.py tests/test_services/test_dune_sync.py tests/test_main.py tests/test_scheduler/test_jobs.py -v`
Expected: PASS

**Step 2: Run full verification**

Run: `pytest`
Expected: PASS
