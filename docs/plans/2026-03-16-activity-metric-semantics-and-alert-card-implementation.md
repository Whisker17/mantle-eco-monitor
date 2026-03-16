# Activity Metric Semantics And Alert Card Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split `daily_active_users` and `active_addresses` into accurate Dune-backed metrics and update Lark alert cards to match the approved readable product format.

**Architecture:** Keep the Dune sync pipeline generic and push metric-specific smoothing into the Dune SQL layer. Remove the inaccurate Growthepie dual-mapping for activity metrics so the system has one authoritative source of truth for those metrics. Update the pure Lark card builder to render emoji-enhanced, human-readable alert cards without changing delivery transport behavior.

**Tech Stack:** Python 3.13, pytest, SQLAlchemy async, Dune SQL, pure dict-based Lark card builders

---

### Task 1: Define failing tests for activity metric ownership

**Files:**
- Modify: `tests/test_ingestion/test_growthepie.py`
- Modify: `tests/test_ingestion/test_dune_client.py`

**Step 1: Write the failing tests**

Add tests that assert:

- Growthepie no longer emits `daily_active_users`
- Growthepie no longer emits `active_addresses`
- Dune daily active users rows are still mapped to `daily_active_users`
- Dune active address rows are still mapped to `active_addresses`

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ingestion/test_growthepie.py tests/test_ingestion/test_dune_client.py -v`
Expected: FAIL because Growthepie still emits both activity metrics and existing test fixtures reflect the old assumption.

**Step 3: Commit**

```bash
git add tests/test_ingestion/test_growthepie.py tests/test_ingestion/test_dune_client.py
git commit -m "test: redefine activity metric source ownership"
```

### Task 2: Define failing tests for alert card formatting

**Files:**
- Modify: `tests/test_integrations/test_lark_cards.py`

**Step 1: Write the failing tests**

Update alert-card tests to assert:

- emoji prefixes appear in the approved sections
- movement is shown with exactly two decimal places
- raw values are compacted into human-readable units
- detected time uses `SGT`
- source renders as `Name (url)`

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_integrations/test_lark_cards.py -v`
Expected: FAIL because the current builder does not yet match the revised formatting.

**Step 3: Commit**

```bash
git add tests/test_integrations/test_lark_cards.py
git commit -m "test: lock revised lark alert card format"
```

### Task 3: Implement metric semantics changes

**Files:**
- Modify: `src/ingestion/growthepie.py`
- Modify: `queries/dune/daily_active_users.sql`
- Possibly modify: `tests/test_ingestion/test_growthepie.py`
- Possibly modify: `tests/test_ingestion/test_dune_client.py`

**Step 1: Write the minimal implementation**

Make Growthepie stop emitting `daily_active_users` and `active_addresses`.

Update the Dune daily active users SQL so it returns a 7-day rolling average series while preserving the `day` + `value` contract expected by the collector and sync service.

**Step 2: Run focused tests to verify they pass**

Run: `pytest tests/test_ingestion/test_growthepie.py tests/test_ingestion/test_dune_client.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/ingestion/growthepie.py queries/dune/daily_active_users.sql tests/test_ingestion/test_growthepie.py tests/test_ingestion/test_dune_client.py
git commit -m "fix: separate activity metric semantics"
```

### Task 4: Implement revised alert card presentation

**Files:**
- Modify: `src/integrations/lark/cards.py`
- Possibly modify: `tests/test_integrations/test_lark_cards.py`

**Step 1: Write the minimal implementation**

Update alert-card rendering to:

- add emoji prefixes
- format movement with two decimal places
- compact raw values into readable units
- render `SGT` timestamps
- include source URLs inline as `Name (url)`

**Step 2: Run focused tests to verify they pass**

Run: `pytest tests/test_integrations/test_lark_cards.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/integrations/lark/cards.py tests/test_integrations/test_lark_cards.py
git commit -m "fix: refine lark alert card readability"
```

### Task 5: Run broader regression verification

**Files:**
- No code changes expected

**Step 1: Run targeted regression coverage**

Run: `pytest tests/test_ingestion/test_growthepie.py tests/test_ingestion/test_dune_client.py tests/test_integrations/test_lark_cards.py tests/test_services/test_notifications.py tests/test_services/test_dune_sync.py tests/test_scheduler/test_jobs.py tests/test_scheduler/test_runtime.py -v`
Expected: PASS

**Step 2: Run full verification**

Run: `pytest`
Expected: PASS

**Step 3: Commit if verification-driven fixes were required**

```bash
git add <only files changed by verification fixes>
git commit -m "test: verify activity metric and alert card regressions"
```
