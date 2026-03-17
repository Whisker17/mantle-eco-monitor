# Stablecoin Transfer Scope Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move token-level stablecoin transfer rows from `core` to `stablecoin` for both new writes and existing database rows, without affecting aggregated transfer rows or other stablecoin metrics.

**Architecture:** Change the Dune collector so token-level stablecoin transfer records are written with `scope = stablecoin` while keeping the aggregated `entity = mantle` transfer volume row under `core`. Add a targeted Alembic data migration that rewrites only existing token-level transfer rows matching the approved predicates.

**Tech Stack:** Python 3.13, pytest, SQLAlchemy async, Alembic, Dune ingestion, SQLite/PostgreSQL migration tests.

---

### Task 1: Lock failing ingestion tests for token-level stablecoin scope

**Files:**
- Modify: `tests/test_ingestion/test_dune_client.py`

**Step 1: Write the failing test**

Add assertions proving:

- token-level rows like `mantle:USDT` use `scope = stablecoin`
- aggregated `entity = mantle` transfer volume still uses `scope = core`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingestion/test_dune_client.py -k stablecoin_breakdown -v`
Expected: FAIL because token-level rows are currently written with `scope = core`.

### Task 2: Lock failing migration test for historical correction

**Files:**
- Create: `tests/test_db/test_scope_migration.py`

**Step 1: Write the failing test**

Add a migration-focused test proving:

- old rows with `scope = core`, `entity LIKE 'mantle:%'`, and stablecoin transfer metric names are updated to `scope = stablecoin`
- aggregated `entity = mantle` transfer rows are left unchanged
- unrelated rows are left unchanged

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_db/test_scope_migration.py -v`
Expected: FAIL because no migration exists yet.

### Task 3: Implement new write semantics in the Dune collector

**Files:**
- Modify: `src/ingestion/dune.py`
- Possibly modify: related tests from Task 1

**Step 1: Write the minimal implementation**

Update the stablecoin breakdown mapper so:

- token-level rows use `scope = stablecoin`
- aggregated `entity = mantle` transfer volume continues to use `scope = core`

**Step 2: Run focused tests to verify they pass**

Run: `pytest tests/test_ingestion/test_dune_client.py -k stablecoin_breakdown -v`
Expected: PASS

### Task 4: Add the Alembic migration for existing rows

**Files:**
- Create: `alembic/versions/0004_stablecoin_scope_fix.py`
- Possibly modify: related tests from Task 2

**Step 1: Write the minimal implementation**

Add a data migration that updates only rows matching:

- `scope = 'core'`
- `entity LIKE 'mantle:%'`
- `metric_name IN ('stablecoin_transfer_volume', 'stablecoin_transfer_tx_count')`

setting `scope = 'stablecoin'`.

**Step 2: Run focused tests to verify they pass**

Run: `pytest tests/test_db/test_scope_migration.py -v`
Expected: PASS

### Task 5: Run affected regression verification

**Files:**
- No code changes expected

**Step 1: Run the affected regression suite**

Run: `pytest tests/test_ingestion/test_dune_client.py tests/test_services/test_dune_sync.py tests/test_scheduler/test_runtime.py tests/test_integration/test_phase1_smoke.py tests/test_db/test_scope_migration.py -v`
Expected: PASS

**Step 2: Run full verification**

Run: `pytest`
Expected: PASS
