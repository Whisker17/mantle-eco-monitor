# Bot Readonly Whitelist Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expand the Lark bot whitelist to cover the project's suitable read-only query surface while keeping all mutation and external-action paths disabled.

**Architecture:** Keep the existing LLM-first routing model, extend the validated intent whitelist, add internal read-only query helpers for health, source health, watchlist, daily summary, and broader alert queries, then route bot requests to those helpers through explicit handlers.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async ORM, Pydantic, pytest

---

### Task 1: Extend internal read-only query helpers

**Files:**
- Modify: `src/services/query_tools.py`
- Test: `tests/test_services/test_query_tools.py`

**Step 1: Write the failing tests**

Add coverage for:

- listing alerts with optional read-only filters
- loading health status from source runs
- loading source health rows
- loading active watchlist entries
- existing daily summary helper still returning read-only context

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_services/test_query_tools.py -q`
Expected: FAIL because the new helpers do not exist yet.

**Step 3: Write minimal implementation**

Add focused helper functions that return serialized dicts for:

- `get_alerts_list(...)`
- `get_health_status(...)`
- `get_source_health(...)`
- `get_watchlist(...)`

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_services/test_query_tools.py -q`
Expected: PASS

### Task 2: Extend bot intents and dispatch

**Files:**
- Modify: `src/services/bot_query.py`
- Test: `tests/test_services/test_bot_query.py`

**Step 1: Write the failing tests**

Add coverage for:

- `alerts_list`
- `health_status`
- `source_health`
- `watchlist`
- `daily_summary`
- mutation-style requests like refresh/review staying unsupported

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_services/test_bot_query.py -q`
Expected: FAIL because the new intents are not yet validated or routed.

**Step 3: Write minimal implementation**

- extend the parse prompt
- validate the new intent payloads
- map each new intent to a read-only handler
- keep unsupported and mutation-like requests on the constrained fallback path

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_services/test_bot_query.py -q`
Expected: PASS

### Task 3: Full verification

**Files:**
- No additional code changes unless verification exposes issues

**Step 1: Run targeted verification**

Run: `python -m pytest tests/test_services/test_query_tools.py tests/test_services/test_bot_query.py -q`
Expected: PASS

**Step 2: Run full suite verification**

Run: `python -m pytest -q`
Expected: PASS

