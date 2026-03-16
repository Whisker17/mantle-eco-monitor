# Bot Tool-Calling Routing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the bot's free-form JSON fallback parser with OpenAI-compatible function calling while preserving the existing deterministic metric fast path and all current non-metric read-only bot capabilities.

**Architecture:** The bot keeps a two-layer router. Common metric requests continue to use the existing deterministic parser with zero LLM dependency. Requests that miss the deterministic parser fall through to an LLM tool-calling layer. That slow path must expose tool schemas for all currently supported read-only intents, not just metrics, so existing alert, health, watchlist, and summary queries do not regress. Unsupported and no-data responses remain deterministic application text.

**Tech Stack:** Python 3.12+, OpenAI-compatible `chat/completions`, OpenRouter tool calling, FastAPI service layer, SQLAlchemy async sessions, pytest

---

## Scope For This Phase

This phase changes the bot's slow-path routing layer from:

- prompt text
- free-form JSON string response
- `json.loads`
- manual validation

to:

- explicit tool schema
- `tool_choice`
- structured tool-call arguments
- existing normalization before dispatch

This phase must preserve all currently supported read-only bot intents:

- `metric_latest`
- `metric_history`
- `recent_alerts`
- `alerts_list`
- `health_status`
- `source_health`
- `watchlist`
- `daily_summary`

This plan supersedes the older metric-only tool-calling plan because a metric-only tool layer would incorrectly downgrade existing non-metric queries to `unsupported`.

## Current Code State To Preserve

The following behaviors already exist in the current worktree and must survive the refactor:

- deterministic metric fast path in [src/services/bot_query.py](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/.worktrees/codex-bot-catalog-routing/src/services/bot_query.py)
- metric/entity normalization in [src/services/bot_query.py](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/.worktrees/codex-bot-catalog-routing/src/services/bot_query.py)
- deterministic unsupported/no-data fallback text in [src/services/bot_query.py](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/.worktrees/codex-bot-catalog-routing/src/services/bot_query.py)
- parser-path logging in [src/services/bot_query.py](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/.worktrees/codex-bot-catalog-routing/src/services/bot_query.py)

Those are not fresh feature tasks anymore. They are migration constraints and must be re-verified after the tool-calling refactor.

### Task 0: Verify the current model supports OpenRouter tool calling

**Files:**
- Modify if needed: `config/settings.py`
- Test command only unless default model must change

**Step 1: Run a live tool-calling probe against the currently configured model**

Run a direct `chat/completions` request with:

- current `LLM_MODEL`
- a single trivial tool
- `tool_choice: "auto"`

Expected:

- if the model supports tool calling, the response should contain either a valid `tool_calls` entry or a normal assistant response without a transport-level rejection
- if the model rejects `tools`, the response will make the incompatibility obvious

**Step 2: If unsupported, decide the default-model fix**

If the current default model does not support tool calling reliably:

- update the default in [config/settings.py](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/.worktrees/codex-bot-catalog-routing/config/settings.py) to a tool-capable low-cost model
- keep the environment variable override behavior intact

Do not proceed with implementation while the chosen default path is incompatible with `tools`.

**Step 3: Record the outcome**

If a default-model change was required, commit it separately:

```bash
git add config/settings.py
git commit -m "chore: default bot llm model to tool-capable option"
```

### Task 1: Extend the catalog to define tool schemas for all supported intents

**Files:**
- Modify: `src/services/bot_catalog.py`
- Test: `tests/test_services/test_bot_query.py`

**Step 1: Write the failing tests**

Add tests proving the catalog exports tool definitions for all current read-only intents:

- `metric_latest`
- `metric_history`
- `recent_alerts`
- `alerts_list`
- `health_status`
- `source_health`
- `watchlist`
- `daily_summary`

The tests should assert:

- tool names match internal intent names
- metric tools enumerate canonical entities
- metric tools enumerate canonical metric ids
- `metric_history.days` has numeric bounds
- simpler tools like `health_status` and `watchlist` expose empty or minimal parameter objects

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_services/test_bot_query.py -k tool_definitions -v
```

Expected: FAIL because the current catalog only exposes alias data.

**Step 3: Write minimal implementation**

Teach `BotCatalog` to expose:

- canonical entities
- canonical metric ids
- tool schemas for all currently supported intents

Keep the schema explicit and static. Do not add dynamic reflection over handlers.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_services/test_bot_query.py -k tool_definitions -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/services/bot_catalog.py tests/test_services/test_bot_query.py
git commit -m "feat: add bot tool schemas for read-only intents"
```

### Task 2: Add a structured tool-calling API to `LLMClient`

**Files:**
- Modify: `src/services/llm.py`
- Test: `tests/test_services/test_llm.py`

**Step 1: Write the failing tests**

Add tests covering:

- request body includes `tools`
- request body includes `tool_choice`
- request body does not require `response_format` on the tool-calling path
- tool-calling helper returns a structured result
- only the first tool call is used when multiple are returned
- invalid tool-call arguments return `None`
- unknown tool names return `None`
- tool-calling parse failures do not crash the bot request path

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_services/test_llm.py -k tool_calling -v
```

Expected: FAIL because `LLMClient` currently only returns plain assistant text.

**Step 3: Write minimal implementation**

Add a dedicated helper such as:

- `complete_with_tools(...) -> ToolCallResult | None`

Use an explicit return type, for example:

```python
@dataclass
class ToolCallResult:
    tool_name: str
    arguments: dict[str, Any]
    raw_tool_call: dict[str, Any]
```

Implementation rules:

- use `tool_choice="auto"`
- if no tool call is returned, return `None`
- if multiple tool calls are returned, use only the first one
- if the API returns a tool-calling payload with invalid JSON arguments, return `None`
- if the returned tool name is unknown to the caller, return `None`
- if parsing the tool-call payload fails, return `None` rather than raising an unhandled exception
- keep `complete()` unchanged for answer generation

Do not keep `response_format={"type":"json_object"}` on the tool-calling path. Tool schema already provides the structure.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_services/test_llm.py -k tool_calling -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/services/llm.py tests/test_services/test_llm.py
git commit -m "feat: add llm tool calling support"
```

### Task 3: Replace the JSON fallback parser with tool calling for all intents

**Files:**
- Modify: `src/services/bot_query.py`
- Test: `tests/test_services/test_bot_query.py`

**Step 1: Write the failing tests**

Add tests for slow-path routing that now must go through tool calling:

- metric latest via tool call
- metric history via tool call
- recent alerts via tool call
- alerts list via tool call
- health status via tool call
- source health via tool call
- watchlist via tool call
- daily summary via tool call
- missing tool call returns deterministic `unsupported`

The key regression test: non-metric read-only requests must still work after the refactor.
Also update the existing fake LLM test doubles so they support both:

- `complete()` for final answer generation
- `complete_with_tools()` for the routing slow path

Without that fixture update, the current bot-query tests will fail for the wrong reason.

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_services/test_bot_query.py -k "tool_call" -v
```

Expected: FAIL because the service still parses free-form JSON today.

**Step 3: Write minimal implementation**

Refactor the slow path so that:

1. deterministic metric parser runs first
2. if it misses, the service sends the read-only tool schema to the LLM
3. returned tool name maps directly to internal intent
4. tool arguments are normalized and validated before dispatch
5. no usable tool call means deterministic `unsupported`

Remove the legacy JSON parser path from the metric/non-metric fallback layer once all supported intents are covered by tools.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_services/test_bot_query.py -k "tool_call" -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/services/bot_query.py tests/test_services/test_bot_query.py
git commit -m "refactor: route bot fallback through tool calling"
```

### Task 4: Re-verify the existing deterministic metric fast path

**Files:**
- Verify existing: `src/services/bot_query.py`
- Test: `tests/test_services/test_bot_query.py`

**Step 1: Confirm the existing fast-path tests still exist or tighten them**

The migration must preserve deterministic handling for:

- `query mantle tvl`
- `mantle tvl latest`
- `show mantle tvl 7d`
- `what is mantle tvl`
- `current mantle tvl`
- `check mantle tvl`

These tests should fail if the tool-calling slow path is invoked.

**Step 2: Run the focused verification**

Run:

```bash
pytest tests/test_services/test_bot_query.py -k "without_llm_parser or current_mantle_tvl or check_mantle_tvl" -v
```

Expected: PASS on the migrated implementation.

**Step 3: Only change implementation if the refactor broke the fast path**

Do not rewrite the deterministic parser from scratch if it already passes. This task is a migration guardrail.

**Step 4: Commit only if code changes were needed**

```bash
git add src/services/bot_query.py tests/test_services/test_bot_query.py
git commit -m "fix: preserve deterministic metric bot fast path"
```

### Task 5: Re-verify normalization and deterministic fallback behavior

**Files:**
- Verify existing: `src/services/bot_query.py`
- Test: `tests/test_services/test_bot_query.py`

**Step 1: Confirm focused tests cover**

- tool-call payload normalization for `Mantle` / `TVL`
- tool-call payload normalization for `DEX volume`
- deterministic no-data fallback
- deterministic unsupported fallback

**Step 2: Run the focused verification**

Run:

```bash
pytest tests/test_services/test_bot_query.py -k "normalizes_llm_metric or no_internal_data or unsupported_prompt" -v
```

Expected: PASS on the migrated implementation.

**Step 3: Only change implementation if the refactor broke existing guarantees**

Do not re-implement these behaviors if the current worktree already preserves them after the tool-calling migration.

**Step 4: Commit only if code changes were needed**

```bash
git add src/services/bot_query.py tests/test_services/test_bot_query.py
git commit -m "fix: preserve bot normalization and fallback guarantees"
```

### Task 6: Re-verify and adapt parser-path logging

**Files:**
- Verify existing: `src/services/bot_query.py`
- Test: `tests/test_services/test_bot_query.py`

**Step 1: Update the logging expectations to match the new slow path**

After the migration, the parser-path logs should distinguish:

- `path=deterministic`
- `path=tool_call`

and should record:

- raw tool-call result
- normalized dispatch payload
- no-data misses

**Step 2: Run the focused verification**

Run:

```bash
pytest tests/test_services/test_bot_query.py -k logs_ -v
```

Expected: PASS

**Step 3: Only change implementation if the logging no longer matches the migrated routing**

The current worktree already logs parser behavior. This task is to preserve and adapt it, not to start logging from zero.

**Step 4: Commit only if code changes were needed**

```bash
git add src/services/bot_query.py tests/test_services/test_bot_query.py
git commit -m "chore: preserve bot parser routing logs"
```

### Task 7: Run focused and full verification

**Files:**
- Test: `tests/test_services/test_bot_query.py`
- Test: `tests/test_services/test_llm.py`
- Test: `tests/test_api/test_lark_integration.py`
- Test: `tests/test_services/test_query_tools.py`
- Test: `tests/test_integrations/test_lark_cards.py`

**Step 1: Run the focused bot and LLM suites**

Run:

```bash
pytest tests/test_services/test_bot_query.py tests/test_services/test_llm.py -v
```

Expected: PASS

**Step 2: Run callback and read-only integration coverage**

Run:

```bash
pytest tests/test_api/test_lark_integration.py tests/test_services/test_query_tools.py tests/test_integrations/test_lark_cards.py -v
```

Expected: PASS

**Step 3: Run the full suite**

Run:

```bash
pytest
```

Expected: PASS with only the existing intentional skips.

**Step 4: Commit the final verification state**

```bash
git add .
git commit -m "test: verify bot tool-calling routing"
```

## Notes And Trade-Offs

- Tool schema `enum` constraints improve routing precision, but every newly queryable metric must be added to the canonical metric list before the tool layer can expose it.
- Keep the deterministic parser because it is still the best low-latency and zero-cost path for common metric queries.
- Tool calling removes the need for `response_format={"type":"json_object"}` on the parser slow path.
- If the selected model still needs extra steering, add a very small number of few-shot examples around tool selection, but do not reintroduce the old free-form JSON parser pattern.

## Deferred TODO After This Phase

- extend deterministic parsing beyond metrics if there is clear high-volume demand
- decide whether answer-generation should also become tool-aware
- evaluate whether slash-command escape hatches are worth adding for power users
- expand the catalog/tool schema to protocol-level ecosystem metric queries
