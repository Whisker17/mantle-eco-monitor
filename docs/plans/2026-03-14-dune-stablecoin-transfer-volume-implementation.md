# Dune Stablecoin Transfer Volume Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure `stablecoin_transfer_volume` is covered by deterministic local tests, runtime orchestration tests, and a manually-triggered live Dune verification test.

**Architecture:** Keep the current Dune collector design, but add coverage at three layers: collector behavior, scheduler wiring, and live Dune verification. Avoid coupling the live Dune test to database writes so it remains a narrow connectivity-and-shape check.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, httpx, Dune API, existing scheduler runtime

---

### Task 1: Add Failing Collector Tests

**Files:**
- Modify: `tests/test_ingestion/test_dune_client.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_dune_collector_collects_stablecoin_transfer_volume_when_configured():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingestion/test_dune_client.py -v`
Expected: FAIL because `collect()` behavior is not explicitly covered yet.

**Step 3: Write minimal implementation**

Add assertions that:

- `collect()` returns `stablecoin_transfer_volume` when the query id is configured
- `collect()` skips work when the query id is missing

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ingestion/test_dune_client.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_ingestion/test_dune_client.py
git commit -m "test: cover dune stablecoin transfer volume collection"
```

### Task 2: Add Runtime Wiring Tests

**Files:**
- Modify: `tests/test_scheduler/test_jobs.py`
- Modify: `tests/test_scheduler/test_runtime.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_core_dune_job_uses_configured_dune_collector(monkeypatch):
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scheduler/test_jobs.py tests/test_scheduler/test_runtime.py -v`
Expected: FAIL because this Dune-specific runtime path is not explicitly covered yet.

**Step 3: Write minimal implementation**

Add tests that prove:

- `core_dune_job()` wires a `DuneCollector` with the current settings
- the runtime pipeline can persist a `stablecoin_transfer_volume` snapshot and source run

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_scheduler/test_jobs.py tests/test_scheduler/test_runtime.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_scheduler/test_jobs.py tests/test_scheduler/test_runtime.py
git commit -m "test: cover dune runtime wiring for stablecoin volume"
```

### Task 3: Add Manual Live Dune Test

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/test_ingestion/test_dune_live.py`

**Step 1: Write the failing test**

```python
@pytest.mark.live_dune
def test_live_dune_stablecoin_transfer_volume():
    assert False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingestion/test_dune_live.py -v`
Expected: FAIL before the real guarded implementation is added.

**Step 3: Write minimal implementation**

Replace the placeholder with a live test that:

- only runs when `RUN_LIVE_DUNE_TESTS=1`
- requires `DUNE_API_KEY`
- requires `DUNE_STABLECOIN_VOLUME_QUERY_ID`
- verifies the live collector returns `stablecoin_transfer_volume` records for Mantle

**Step 4: Run test to verify it passes**

Run: `RUN_LIVE_DUNE_TESTS=1 pytest tests/test_ingestion/test_dune_live.py -m live_dune -v`
Expected: PASS if live credentials and query id are available; otherwise skip or report the missing configuration.

**Step 5: Commit**

```bash
git add pyproject.toml tests/test_ingestion/test_dune_live.py
git commit -m "test: add manual live dune stablecoin volume check"
```
