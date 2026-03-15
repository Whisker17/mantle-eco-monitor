# Stablecoin Breakdown Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Store daily per-token stablecoin transfer volume and transaction counts for Mantle while preserving the aggregate Mantle stablecoin transfer volume metric.

**Architecture:** Change the Dune SQL to return `day + symbol + volume + tx_count`, teach the Dune collector to expand those rows into per-token and aggregate `MetricRecord`s, and explicitly skip alerts for the per-token detail entities. Reuse the existing `metric_snapshots` table and metrics APIs.

**Tech Stack:** Python 3.13, pytest, Dune SQL, FastAPI, SQLAlchemy

---

### Task 1: Document the behavior in tests first

**Files:**
- Modify: `tests/test_ingestion/test_dune_client.py`
- Test: `tests/test_integration/test_phase1_smoke.py`

**Step 1: Write the failing collector test**

Add a test showing that one Dune row with `symbol`, `volume`, and `tx_count` produces:

- `mantle:USDT / stablecoin_transfer_volume`
- `mantle:USDT / stablecoin_transfer_tx_count`
- `mantle / stablecoin_transfer_volume`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingestion/test_dune_client.py::test_dune_collector_maps_stablecoin_breakdown_rows_to_token_and_aggregate_metrics -v`
Expected: FAIL because the current collector only reads `value`.

**Step 3: Write the failing alert test**

Add a test showing that inserting a `mantle:USDT / stablecoin_transfer_volume` snapshot and evaluating rules produces no alerts.

**Step 4: Run test to verify it fails**

Run: `pytest tests/test_integration/test_phase1_smoke.py::test_rule_engine_skips_token_level_stablecoin_breakdown_alerts -v`
Expected: FAIL because the current rule engine treats the snapshot like any other metric.

### Task 2: Implement the Dune query and collector changes

**Files:**
- Modify: `queries/dune/stablecoin_transfer_volume.sql`
- Modify: `src/ingestion/dune.py`

**Step 1: Update the Dune SQL**

Return:

- `day`
- `symbol`
- `volume`
- `tx_count`

using the Mantle top-6 stablecoin address whitelist, excluding zero-address mint/burn transfers and the current partial day.

**Step 2: Update Dune collector mapping**

Implement stablecoin-specific row mapping so the collector:

- emits per-token volume snapshots
- emits per-token tx-count snapshots
- aggregates daily volume across tokens into the Mantle-level total snapshot

**Step 3: Run the targeted collector tests**

Run: `pytest tests/test_ingestion/test_dune_client.py -v`
Expected: PASS

### Task 3: Suppress alerts for token-level detail snapshots

**Files:**
- Modify: `src/rules/engine.py`
- Test: `tests/test_integration/test_phase1_smoke.py`

**Step 1: Implement a focused guard**

Skip alert evaluation for:

- `entity` beginning with `mantle:`
- metric names `stablecoin_transfer_volume` and `stablecoin_transfer_tx_count`

**Step 2: Run the alert test**

Run: `pytest tests/test_integration/test_phase1_smoke.py::test_rule_engine_skips_token_level_stablecoin_breakdown_alerts -v`
Expected: PASS

### Task 4: Verify end-to-end behavior

**Files:**
- Modify: none
- Test: `tests/test_scheduler/test_runtime.py`

**Step 1: Run targeted regression tests**

Run: `pytest tests/test_ingestion/test_dune_client.py tests/test_integration/test_phase1_smoke.py tests/test_scheduler/test_runtime.py -v`
Expected: PASS

**Step 2: Run a broader suite if targeted tests pass**

Run: `pytest tests/test_ingestion/test_dune_client.py tests/test_rules/test_thresholds.py tests/test_integration/test_phase1_smoke.py tests/test_scheduler/test_runtime.py -v`
Expected: PASS
