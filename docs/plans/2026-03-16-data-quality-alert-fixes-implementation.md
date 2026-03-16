# Data Quality Alert Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent false alerts from sparse history, correct Aave TVL semantics, replace dynamic ecosystem protocol selection with the approved fixed list, and provide a safe rebuild path for affected historical data.

**Architecture:** Tighten window-based alert eligibility at the repository/rule boundary so sparse history suppresses alerts without blocking data writes. Introduce explicit curated watchlist configuration and a small aggregated-protocol adapter path so ecosystem collection matches the approved product list. Keep manual data insertion intact while adding targeted rebuild utilities for stale automated history.

**Tech Stack:** Python 3.13, pytest, SQLAlchemy async, FastAPI service modules, DefiLlama adapters, Dune sync, CSV-backed debugging evidence

---

### Task 1: Lock failing tests for sparse-history alert suppression

**Files:**
- Modify: `tests/test_db/test_repositories.py`
- Modify: `tests/test_rules/test_thresholds.py`
- Modify: `tests/test_rules/test_cooldown.py`
- Possibly modify: `tests/test_scheduler/test_runtime.py`

**Step 1: Write the failing tests**

Add tests that prove:

- a metric with only 2 daily rows cannot produce a `7D` threshold alert
- a month with large gaps cannot produce an `MTD` threshold alert
- manual snapshot insertion still persists records even when alert windows are invalid

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db/test_repositories.py tests/test_rules/test_thresholds.py tests/test_rules/test_cooldown.py tests/test_scheduler/test_runtime.py -v`
Expected: FAIL because the current window lookup treats sparse history as valid.

**Step 3: Commit**

```bash
git add tests/test_db/test_repositories.py tests/test_rules/test_thresholds.py tests/test_rules/test_cooldown.py tests/test_scheduler/test_runtime.py
git commit -m "test: define sparse-history alert suppression"
```

### Task 2: Lock failing tests for Aave TVL semantics

**Files:**
- Modify: `tests/test_protocols/test_aave_adapter.py`

**Step 1: Write the failing tests**

Add tests showing:

- Aave TVL comes from the direct DefiLlama TVL path instead of `supply - borrowed`
- Aave TVL stays non-negative even when `borrowed > supply`

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_protocols/test_aave_adapter.py -v`
Expected: FAIL because the current adapter still derives TVL from `supply - borrowed`.

**Step 3: Commit**

```bash
git add tests/test_protocols/test_aave_adapter.py
git commit -m "test: redefine aave tvl semantics"
```

### Task 3: Lock failing tests for fixed watchlist and aggregated protocols

**Files:**
- Modify: `tests/test_protocols/test_watchlist.py`
- Modify: `tests/test_protocols/test_registry.py`
- Possibly modify: `tests/test_scheduler/test_runtime.py`

**Step 1: Write the failing tests**

Add tests proving:

- the watchlist contains exactly the approved fixed protocols
- no dynamic TVL-based fill logic remains
- aggregated slugs resolve to aggregated adapters
- DEX metrics are assigned only to the approved DEX protocol set

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_protocols/test_watchlist.py tests/test_protocols/test_registry.py tests/test_scheduler/test_runtime.py -v`
Expected: FAIL because the current watchlist is still dynamic and the registry has no aggregated adapters.

**Step 3: Commit**

```bash
git add tests/test_protocols/test_watchlist.py tests/test_protocols/test_registry.py tests/test_scheduler/test_runtime.py
git commit -m "test: define fixed mantle ecosystem watchlist"
```

### Task 4: Implement coverage-aware comparison logic

**Files:**
- Modify: `src/db/repositories.py`
- Modify: `src/rules/engine.py`
- Possibly modify: related tests from Task 1

**Step 1: Write the minimal implementation**

Implement window-validity checks for `7D` and `MTD` comparisons so alerts are skipped when history coverage is insufficient, while snapshot persistence remains unchanged.

**Step 2: Run focused tests to verify they pass**

Run: `pytest tests/test_db/test_repositories.py tests/test_rules/test_thresholds.py tests/test_rules/test_cooldown.py tests/test_scheduler/test_runtime.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/db/repositories.py src/rules/engine.py tests/test_db/test_repositories.py tests/test_rules/test_thresholds.py tests/test_rules/test_cooldown.py tests/test_scheduler/test_runtime.py
git commit -m "fix: suppress alerts for sparse history windows"
```

### Task 5: Implement corrected Aave TVL behavior

**Files:**
- Modify: `src/protocols/aave.py`
- Possibly modify: related tests from Task 2

**Step 1: Write the minimal implementation**

Update the adapter so:

- `supply`, `borrowed`, and `utilization` continue to come from Mantle chain entries
- `tvl` comes from the direct DefiLlama protocol TVL series instead of `supply - borrowed`

**Step 2: Run focused tests to verify they pass**

Run: `pytest tests/test_protocols/test_aave_adapter.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/protocols/aave.py tests/test_protocols/test_aave_adapter.py
git commit -m "fix: read aave tvl directly from defillama"
```

### Task 6: Implement fixed watchlist and aggregated adapters

**Files:**
- Modify: `config/watchlist_seed.py`
- Modify: `src/protocols/watchlist.py`
- Modify: `src/protocols/registry.py`
- Create: `src/protocols/aggregate.py`
- Possibly modify: related tests from Task 3

**Step 1: Write the minimal implementation**

Replace dynamic watchlist ranking with the approved fixed list and add aggregated adapter support for:

- `merchant-moe`
- `stargate-finance`
- `woofi`

Ensure aggregated DEX behavior matches the approved TVL and volume rules.

**Step 2: Run focused tests to verify they pass**

Run: `pytest tests/test_protocols/test_watchlist.py tests/test_protocols/test_registry.py tests/test_scheduler/test_runtime.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add config/watchlist_seed.py src/protocols/watchlist.py src/protocols/registry.py src/protocols/aggregate.py tests/test_protocols/test_watchlist.py tests/test_protocols/test_registry.py tests/test_scheduler/test_runtime.py
git commit -m "feat: replace dynamic ecosystem watchlist with fixed set"
```

### Task 7: Add targeted rebuild tooling for stale history

**Files:**
- Modify: `src/admin/seed.py`
- Possibly create: `src/admin/rebuild.py`
- Modify: admin CLI/tests as needed
- Test: `tests/test_admin/test_seed.py`
- Test: `tests/test_admin/test_cli.py`

**Step 1: Write the failing tests**

Add tests for a targeted rebuild command or helper that clears affected automated snapshots for selected metric/entity pairs without removing the ability to insert manual snapshots afterward.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_admin/test_seed.py tests/test_admin/test_cli.py -v`
Expected: FAIL because no rebuild helper exists yet.

**Step 3: Write minimal implementation**

Add a targeted rebuild utility for the affected history slices called out in the design.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_admin/test_seed.py tests/test_admin/test_cli.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/admin tests/test_admin
git commit -m "feat: add targeted history rebuild tooling"
```

### Task 8: Run full regression verification

**Files:**
- No code changes expected

**Step 1: Run targeted regression suite**

Run: `pytest tests/test_db/test_repositories.py tests/test_rules/test_thresholds.py tests/test_rules/test_cooldown.py tests/test_protocols/test_aave_adapter.py tests/test_protocols/test_watchlist.py tests/test_protocols/test_registry.py tests/test_scheduler/test_runtime.py tests/test_scheduler/test_jobs.py tests/test_admin/test_seed.py tests/test_admin/test_cli.py -v`
Expected: PASS

**Step 2: Run full verification**

Run: `pytest`
Expected: PASS

**Step 3: Commit if verification-driven fixes were needed**

```bash
git add <only files changed by verification fixes>
git commit -m "test: verify data quality alert fixes"
```
