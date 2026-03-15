# Bot Internal Routing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Preserve LLM-based intent parsing while hardening the Lark bot so execution stays on an explicit internal-only routing path.

**Architecture:** Keep the existing two-stage LLM pipeline, but make the internal whitelist explicit, add a reserved config flag for future external actions, enforce the bot enablement flag at the router, and ensure unsupported requests only produce constrained explanatory text instead of executing any action.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async ORM, Pydantic Settings, pytest

---

### Task 1: Add settings and router guardrails

**Files:**
- Modify: `config/settings.py`
- Modify: `.env.example`
- Modify: `src/integrations/lark/router.py`
- Test: `tests/test_config/test_settings.py`
- Test: `tests/test_api/test_lark_integration.py`

**Step 1: Write the failing tests**

Add test coverage for:

- `bot_external_actions_enabled` defaulting to `False`
- overriding `bot_external_actions_enabled`
- rejecting Lark bot message processing when `lark_bot_enabled` is `False`

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config/test_settings.py tests/test_api/test_lark_integration.py -q`
Expected: FAIL because the new setting and router behavior do not exist yet.

**Step 3: Write minimal implementation**

- add `bot_external_actions_enabled: bool = False` to settings
- document `BOT_EXTERNAL_ACTIONS_ENABLED=false` in `.env.example`
- make the Lark callback route reject message events when `lark_bot_enabled` is `False`

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config/test_settings.py tests/test_api/test_lark_integration.py -q`
Expected: PASS

### Task 2: Harden the bot query contract

**Files:**
- Modify: `src/services/bot_query.py`
- Test: `tests/test_services/test_bot_query.py`

**Step 1: Write the failing tests**

Add coverage for:

- unsupported prompts using the LLM to generate a constrained explanation
- unsupported prompts not executing any internal handler
- supported prompts still calling the query helpers through the whitelist
- supported prompts with no internal data returning a constrained explanation instead of fabricated results

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_services/test_bot_query.py -q`
Expected: FAIL because the current service uses a fixed unsupported message and lacks an explicit dispatch map.

**Step 3: Write minimal implementation**

- replace implicit match-based dispatch with an explicit intent-to-handler map
- add a dedicated unsupported-response LLM prompt
- make empty internal results return the constrained explanation path
- align the supported-capability text with the actual whitelist

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_services/test_bot_query.py -q`
Expected: PASS

### Task 3: Verify the combined behavior

**Files:**
- No code changes required unless failures appear

**Step 1: Run targeted verification**

Run: `python -m pytest tests/test_config/test_settings.py tests/test_api/test_lark_integration.py tests/test_services/test_bot_query.py -q`
Expected: PASS

**Step 2: Run full suite verification**

Run: `python -m pytest -q`
Expected: PASS

