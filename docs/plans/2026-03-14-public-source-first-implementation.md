# Public Source First Data Strategy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the Dune-first source ownership with a public-source-first collection strategy, add a live public coverage test, and update collectors to use the currently valid public endpoints.

**Architecture:** Keep the existing collector structure, but reassign core metric ownership to DefiLlama, Growthepie, L2Beat, and CoinGecko based on validated public coverage. Add one explicit live integration test for public endpoint reachability and metric coverage, while keeping unit tests local and fixture-driven. Remove stale endpoint assumptions so the code matches current public APIs.

**Tech Stack:** Python 3.12, httpx, pytest, pytest-asyncio, FastAPI codebase, DefiLlama public APIs, Growthepie public APIs, L2Beat public APIs, optional CoinGecko, optional Dune

---

## Reference Docs

- Read first: `specs/DESIGN.md`
- Design superseding the old source matrix: `docs/plans/2026-03-14-public-source-first-design.md`
- Existing implementation plan for baseline context: `docs/plans/2026-03-13-mantle-monitor-phase1-implementation.md`
- Execution skills to use during implementation:
  - `@superpowers/test-driven-development`
  - `@superpowers/systematic-debugging`
  - `@superpowers/verification-before-completion`

## Scope Guardrails

- Do not add new paid data sources.
- Do not remove Dune support for metrics that remain uncovered.
- Do not make live network tests part of the default test suite.
- Do not attempt methodology reconciliation beyond the approved source ownership matrix.

### Task 1: Update the Source Design Docs

**Files:**
- Modify: `specs/DESIGN.md`
- Create: `docs/plans/2026-03-14-public-source-first-design.md`

**Step 1: Write the failing test**

Create a short manual checklist instead of an executable test:

```text
- Section 3.1 no longer says "Dune-first"
- Core metric table reflects public-source-first ownership
- Section 3.2 points ecosystem metrics to DefiLlama public endpoints
- Section 3.3 marks Dune as optional instead of primary
```

**Step 2: Run test to verify it fails**

Run: `rg -n "Dune-first|Execute saved query over Mantle activity tables|api/protocol" specs/DESIGN.md`
Expected: Matches show the old design is still present.

**Step 3: Write minimal implementation**

Update sections 3.1, 3.2, and 3.3 in `specs/DESIGN.md` to match the approved public-source-first strategy and add the new design document.

**Step 4: Run test to verify it passes**

Run: `rg -n "public-source-first|api.growthepie.com|/api/scaling/tvs/mantle|https://api.llama.fi/protocol" specs/DESIGN.md docs/plans/2026-03-14-public-source-first-design.md`
Expected: Matches show the new ownership model and current endpoints.

**Step 5: Commit**

```bash
git add specs/DESIGN.md docs/plans/2026-03-14-public-source-first-design.md
git commit -m "docs: redefine mantle data sources around public endpoints"
```

### Task 2: Add a Live Public Coverage Test Harness

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/test_ingestion/test_public_source_coverage_live.py`

**Step 1: Write the failing test**

```python
import pytest


@pytest.mark.live
def test_public_sources_cover_required_metrics():
    assert False, "replace with live endpoint coverage assertions"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingestion/test_public_source_coverage_live.py -v`
Expected: FAIL with the placeholder assertion.

**Step 3: Write minimal implementation**

Replace the placeholder with a live test that:

- hits DefiLlama, Growthepie, and L2Beat public endpoints
- confirms Mantle records exist
- confirms the approved source matrix can provide:
  - `tvl`
  - `total_value_secured`
  - `daily_active_users`
  - `active_addresses`
  - `stablecoin_supply`
  - `stablecoin_mcap`
  - `chain_transactions`
  - `dex_volume`
  - `mnt_market_cap`
- confirms the known public gaps:
  - `stablecoin_transfer_volume`
  - `mnt_volume`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingestion/test_public_source_coverage_live.py -m live -v`
Expected: PASS when the network is available and the providers respond normally.

**Step 5: Commit**

```bash
git add pyproject.toml tests/test_ingestion/test_public_source_coverage_live.py
git commit -m "test: add live public source coverage check"
```

### Task 3: Fix Growthepie Collector Endpoints and Ownership

**Files:**
- Modify: `src/ingestion/growthepie.py`
- Modify: `tests/test_ingestion/test_growthepie.py`

**Step 1: Write the failing test**

```python
def test_growthepie_uses_public_dot_com_base_url():
    collector = GrowthepieCollector()
    assert collector.BASE == "https://api.growthepie.com"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingestion/test_growthepie.py::test_growthepie_uses_public_dot_com_base_url -v`
Expected: FAIL because the collector still points at `.xyz`.

**Step 3: Write minimal implementation**

Update the collector to:

- use `https://api.growthepie.com`
- pull from a current public endpoint
- treat `daa` as both `daily_active_users` and `active_addresses`
- keep `txcount` mapped to `chain_transactions`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingestion/test_growthepie.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ingestion/growthepie.py tests/test_ingestion/test_growthepie.py
git commit -m "feat: align growthepie collector with public mantle metrics"
```

### Task 4: Fix L2Beat Collector to Use Current Public Endpoints

**Files:**
- Modify: `src/ingestion/l2beat.py`
- Modify: `tests/test_ingestion/test_l2beat.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_l2beat_collector_uses_tvs_endpoint(l2beat_collector):
    records = await l2beat_collector.collect()
    assert records[0].metric_name == "total_value_secured"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingestion/test_l2beat.py -v`
Expected: FAIL because the mock payload shape no longer matches the stale endpoint contract.

**Step 3: Write minimal implementation**

Update the collector to:

- call `/api/scaling/tvs/mantle`
- parse `data.chart.data`
- compute TVS from native, canonical, and external components
- keep the public source link to the Mantle project page

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingestion/test_l2beat.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ingestion/l2beat.py tests/test_ingestion/test_l2beat.py
git commit -m "feat: update l2beat collector to current tvs api"
```

### Task 5: Extend DefiLlama Collector for Public Core Coverage

**Files:**
- Modify: `src/ingestion/defillama.py`
- Modify: `tests/test_ingestion/test_defillama.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_defillama_collect_includes_chain_dex_volume(defillama_collector):
    records = await defillama_collector.collect()
    assert "dex_volume" in {r.metric_name for r in records}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingestion/test_defillama.py::test_defillama_collect_includes_chain_dex_volume -v`
Expected: FAIL because core collection does not yet include chain DEX volume.

**Step 3: Write minimal implementation**

Add chain-level DEX volume collection from `https://api.llama.fi/overview/dexs/Mantle` and expose it as the core `dex_volume` metric.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingestion/test_defillama.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ingestion/defillama.py tests/test_ingestion/test_defillama.py
git commit -m "feat: add public chain dex volume to defillama collector"
```

### Task 6: Fix DefiLlama Protocol Adapters to Current Endpoint Paths

**Files:**
- Modify: `src/ingestion/defillama.py`
- Modify: `src/protocols/aave.py`
- Modify: `src/protocols/dex.py`
- Modify: `tests/test_protocols/test_aave_adapter.py`
- Modify: `tests/test_protocols/test_watchlist.py`

**Step 1: Write the failing test**

```python
def test_aave_adapter_uses_current_defillama_protocol_path():
    assert AaveAdapter.DEFILLAMA_URL == "https://api.llama.fi/protocol/aave-v3"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_protocols/test_aave_adapter.py -v`
Expected: FAIL because the adapter still points at `/api/protocol/...`.

**Step 3: Write minimal implementation**

Update all protocol detail requests from `/api/protocol/{slug}` to `/protocol/{slug}` and adjust any payload parsing needed for the current response shape.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_protocols/test_aave_adapter.py tests/test_protocols/test_watchlist.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ingestion/defillama.py src/protocols/aave.py src/protocols/dex.py tests/test_protocols/test_aave_adapter.py tests/test_protocols/test_watchlist.py
git commit -m "fix: align defillama protocol adapters with current api paths"
```

### Task 7: Reassign Core Metric Ownership Away From Dune

**Files:**
- Modify: `src/ingestion/dune.py`
- Modify: `config/settings.py`
- Modify: `tests/test_ingestion/test_dune_client.py`
- Modify: `tests/test_config/test_settings.py`

**Step 1: Write the failing test**

```python
def test_dune_metric_query_map_keeps_only_uncovered_metrics():
    assert set(METRIC_QUERY_MAP) == {"stablecoin_transfer_volume"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingestion/test_dune_client.py::test_dune_metric_query_map_keeps_only_uncovered_metrics -v`
Expected: FAIL because Dune still owns multiple core metrics.

**Step 3: Write minimal implementation**

Reduce Dune ownership to only the metrics still not covered by the approved public-source-first strategy, and remove obsolete settings if they are no longer consumed.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingestion/test_dune_client.py tests/test_config/test_settings.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ingestion/dune.py config/settings.py tests/test_ingestion/test_dune_client.py tests/test_config/test_settings.py
git commit -m "refactor: shrink dune ownership to uncovered metrics"
```

### Task 8: Verify the Public Source First Flow End-to-End

**Files:**
- Modify: `tests/test_integration/test_phase1_smoke.py`
- Modify: `tests/test_scheduler/test_jobs.py`

**Step 1: Write the failing test**

```python
def test_phase1_smoke_uses_public_source_first_metric_mix():
    assert False, "replace with smoke assertions for the new source matrix"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration/test_phase1_smoke.py tests/test_scheduler/test_jobs.py -v`
Expected: FAIL because the old source expectations still exist.

**Step 3: Write minimal implementation**

Update the smoke expectations so they reflect:

- Growthepie ownership for activity metrics
- DefiLlama ownership for TVL, stablecoins, DEX volume, and ecosystem metrics
- L2Beat ownership for TVS
- optional Dune ownership only for uncovered metrics

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_integration/test_phase1_smoke.py tests/test_scheduler/test_jobs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_integration/test_phase1_smoke.py tests/test_scheduler/test_jobs.py
git commit -m "test: update smoke coverage for public source first strategy"
```

### Task 9: Run Final Verification

**Files:**
- No file changes

**Step 1: Write the failing test**

Use the completed suite as the verification target.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingestion -v`
Expected: Any remaining failures reveal integration gaps before final verification.

**Step 3: Write minimal implementation**

Fix only the specific failures discovered during verification.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingestion tests/test_protocols tests/test_config tests/test_integration/test_phase1_smoke.py -v`
Expected: PASS

Then run: `pytest tests/test_api tests/test_scheduler tests/test_rules tests/test_db -v`
Expected: PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "test: verify public source first ingestion strategy"
```
