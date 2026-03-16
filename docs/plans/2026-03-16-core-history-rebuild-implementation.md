# Core History Rebuild Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend core rebuild coverage so `tvl` and `mnt_volume` can be safely cleared and repopulated with real historical data instead of only the latest point.

**Architecture:** Keep the current admin rebuild flow, but expand the affected target set and rerun the right core jobs after clearing. Make `DefiLlamaCollector` emit Mantle TVL history from the existing historical endpoint, and make `CoinGeckoCollector` emit daily `mnt_volume` history from CoinGecko market chart data so rebuild repopulates history instead of a single latest row.

**Tech Stack:** Python 3.13, pytest, SQLAlchemy async, httpx, FastAPI admin CLI, DefiLlama and CoinGecko collectors.

---

### Task 1: Lock failing ingestion tests for core history collection

**Files:**
- Modify: `tests/test_ingestion/test_defillama.py`
- Modify: `tests/test_ingestion/test_coingecko.py`

**Step 1: Write the failing tests**

Add tests proving:

- `DefiLlamaCollector._collect_chain_tvl()` returns the full Mantle daily history from the historical endpoint, not just the last point
- `CoinGeckoCollector.collect()` maps daily `mnt_volume` history from CoinGecko chart data, not just the current snapshot

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ingestion/test_defillama.py tests/test_ingestion/test_coingecko.py -k "history or chain_tvl" -v`
Expected: FAIL because both collectors currently collapse history to one latest record.

### Task 2: Lock failing admin rebuild tests for expanded core coverage

**Files:**
- Modify: `tests/test_admin/test_seed.py`

**Step 1: Write the failing tests**

Add tests proving:

- rebuild clears automated `core/mantle/tvl` and `core/mantle/mnt_volume`
- rebuild reruns `core_defillama` and `core_coingecko` in addition to the existing jobs

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_admin/test_seed.py -k "rebuild" -v`
Expected: FAIL because rebuild currently excludes these targets and jobs.

### Task 3: Implement historical core collectors

**Files:**
- Modify: `src/ingestion/defillama.py`
- Modify: `src/ingestion/coingecko.py`

**Step 1: Write the minimal implementation**

- return all historical Mantle TVL points from DefiLlama
- fetch `market_chart` daily total volume from CoinGecko and map each day to `mnt_volume`

**Step 2: Run focused tests to verify they pass**

Run: `pytest tests/test_ingestion/test_defillama.py tests/test_ingestion/test_coingecko.py -v`
Expected: PASS

### Task 4: Expand rebuild coverage to the new core series

**Files:**
- Modify: `src/admin/rebuild.py`
- Possibly modify: related tests from Task 2

**Step 1: Write the minimal implementation**

- add `core/mantle/tvl` and `core/mantle/mnt_volume` to the rebuild target list
- add `core_defillama` and `core_coingecko` ahead of ecosystem jobs in rebuild order

**Step 2: Run focused tests to verify they pass**

Run: `pytest tests/test_admin/test_seed.py -v`
Expected: PASS

### Task 5: Run regression verification

**Files:**
- No code changes expected

**Step 1: Run the affected regression suite**

Run: `pytest tests/test_ingestion/test_defillama.py tests/test_ingestion/test_coingecko.py tests/test_admin/test_collect.py tests/test_admin/test_seed.py tests/test_admin/test_cli.py -v`
Expected: PASS
