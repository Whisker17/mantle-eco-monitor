# OpenRouter Provider Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make OpenRouter the default LLM provider and model while keeping the current OpenAI-compatible client interface.

**Architecture:** Update the shared settings defaults to OpenRouter, add lightweight app metadata fields for OpenRouter-friendly headers, and extend the shared `LLMClient` to send those headers on every request. Keep all higher-level services unchanged so the provider swap stays isolated to configuration and transport code.

**Tech Stack:** Python 3.13, pydantic-settings, httpx, pytest

---

### Task 1: Update settings defaults for OpenRouter

**Files:**
- Modify: `config/settings.py`
- Modify: `.env.example`
- Test: `tests/test_config/test_settings.py`

**Step 1: Write the failing settings tests**

Add assertions that defaults are:

- `llm_api_base == "https://openrouter.ai/api/v1"`
- `llm_model == "nvidia/nemotron-3-super-120b-a12b:free"`
- `llm_app_name == "mantle-eco-monitor"`
- `llm_app_url == "https://github.com/Whisker17/mantle-eco-monitor"`

Also extend the override test to verify these fields can be overridden explicitly.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config/test_settings.py -v`
Expected: FAIL because the defaults are empty and the new metadata fields do not exist.

**Step 3: Write minimal implementation**

In `config/settings.py`, update:

```python
llm_api_base: str = "https://openrouter.ai/api/v1"
llm_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
llm_app_name: str = "mantle-eco-monitor"
llm_app_url: str = "https://github.com/Whisker17/mantle-eco-monitor"
```

Update `.env.example` so the LLM section reflects the same defaults and still leaves `LLM_API_KEY` blank.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config/test_settings.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add config/settings.py .env.example tests/test_config/test_settings.py
git commit -m "feat: default llm settings to openrouter"
```

### Task 2: Add OpenRouter-friendly request headers to the shared LLM client

**Files:**
- Modify: `src/services/llm.py`
- Test: `tests/test_services/test_llm.py`

**Step 1: Write the failing LLM client test**

Extend the existing request-capture test to assert the client sends:

- `Authorization: Bearer <key>`
- `HTTP-Referer: <llm_app_url>`
- `X-Title: <llm_app_name>`

and still posts to:

- `{api_base}/chat/completions`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_services/test_llm.py -v`
Expected: FAIL because the client currently sends only `Authorization`.

**Step 3: Write minimal implementation**

Update `LLMClient` to accept:

- `app_name`
- `app_url`

and include them in the request headers.

Example shape:

```python
headers={
    "Authorization": f"Bearer {self._api_key}",
    "HTTP-Referer": self._app_url,
    "X-Title": self._app_name,
}
```

Keep the request body unchanged.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_services/test_llm.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/services/llm.py tests/test_services/test_llm.py
git commit -m "feat: add openrouter headers to llm client"
```

### Task 3: Thread the new metadata through existing LLM call sites

**Files:**
- Modify: `src/scheduler/jobs.py`
- Modify: `src/integrations/lark/router.py`
- Test: no new test file required if existing coverage stays green

**Step 1: Update the existing construction sites**

Pass the new settings through every `LLMClient(...)` call, specifically in:

- `daily_summary_job()`
- `_build_bot_query_service()`

Use:

- `app_name=settings.llm_app_name`
- `app_url=settings.llm_app_url`

**Step 2: Run targeted regression tests**

Run: `pytest tests/test_services/test_daily_summary.py tests/test_services/test_bot_query.py tests/test_api/test_lark_integration.py tests/test_scheduler/test_jobs.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/scheduler/jobs.py src/integrations/lark/router.py
git commit -m "feat: thread openrouter metadata through llm callers"
```

### Task 4: Verify end-to-end regression for the provider swap

**Files:**
- Test: `tests/test_config/test_settings.py`
- Test: `tests/test_services/test_llm.py`
- Test: `tests/test_services/test_daily_summary.py`
- Test: `tests/test_services/test_bot_query.py`
- Test: `tests/test_api/test_lark_integration.py`
- Test: `tests/test_scheduler/test_jobs.py`

**Step 1: Run the focused verification suite**

Run: `pytest tests/test_config/test_settings.py tests/test_services/test_llm.py tests/test_services/test_daily_summary.py tests/test_services/test_bot_query.py tests/test_api/test_lark_integration.py tests/test_scheduler/test_jobs.py -v`
Expected: PASS

**Step 2: Run the full test suite**

Run: `pytest`
Expected: PASS with the same live-test skips as before
