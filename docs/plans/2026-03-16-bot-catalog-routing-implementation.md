# Bot Catalog Routing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make bot metric queries route through a catalog-driven, partially deterministic parser so common natural-language requests resolve to internal read-only query handlers reliably.

**Architecture:** Keep the current two-stage bot flow, but reduce prompt fragility. Add a local query capability catalog, alias normalization, and deterministic parsing for common metric requests before falling back to the LLM router. Keep the first phase narrow: stabilize metric latest/history queries first, then expand the same pattern to alerts, health, watchlist, and summaries.

**Tech Stack:** Python 3.12+, FastAPI service layer, SQLAlchemy async sessions, pytest, existing `BotQueryService`, existing `query_tools`

---

## Scope For Phase 1

This phase only covers metric query routing.

Supported examples for this phase:

- `mantle tvl latest`
- `query mantle tvl`
- `show mantle tvl 7d`
- `mantle dex volume`
- `show mantle dex volume 30d`

Out of scope for this phase:

- alert intent refactor
- health/source-health refactor
- watchlist refactor
- daily summary refactor
- external actions or generic tool calling

### Task 1: Add the query capability catalog

**Files:**
- Create: `src/services/bot_catalog.py`
- Modify: `src/services/bot_query.py`
- Test: `tests/test_services/test_bot_query.py`

**Step 1: Write the failing tests**

Add tests that assert the catalog knows the metric query capabilities and accepted aliases:

```python
def test_metric_catalog_exposes_latest_and_history_capabilities():
    catalog = build_bot_catalog()
    assert "metric_latest" in catalog.intents
    assert "metric_history" in catalog.intents
    assert catalog.metric_aliases["TVL"] == "tvl"
    assert catalog.metric_aliases["dex volume"] == "dex_volume"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_services/test_bot_query.py -k catalog -v`
Expected: FAIL because `bot_catalog.py` and the catalog helpers do not exist yet.

**Step 3: Write minimal implementation**

Create a small catalog module that defines:

- supported intents for phase 1
- canonical metric aliases
- canonical entity aliases
- default routing rule: bare metric request without a window means `metric_latest`

Use plain data structures first. Do not add generic plugin machinery.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_services/test_bot_query.py -k catalog -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/services/bot_catalog.py src/services/bot_query.py tests/test_services/test_bot_query.py
git commit -m "feat: add bot metric query catalog"
```

### Task 2: Add deterministic metric parsing for common requests

**Files:**
- Modify: `src/services/bot_query.py`
- Test: `tests/test_services/test_bot_query.py`

**Step 1: Write the failing tests**

Add focused tests for the most common requests that should not require the LLM router:

```python
@pytest.mark.asyncio
async def test_bot_query_service_routes_query_mantle_tvl_without_llm_parser(...):
    ...
    result = await service.handle_message("query mantle tvl", now=seeded_data)
    assert result["intent"] == "metric_latest"
    assert result["data"]["metric_name"] == "tvl"

@pytest.mark.asyncio
async def test_bot_query_service_routes_mantle_tvl_7d_to_metric_history(...):
    ...
    result = await service.handle_message("show mantle tvl 7d", now=seeded_data)
    assert result["intent"] == "metric_history"
    assert result["data"]["metric_name"] == "tvl"
```

Use a fake LLM that fails if the parse stage is called, so the test proves deterministic routing happened first.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_services/test_bot_query.py -k "query_mantle_tvl or 7d_to_metric_history" -v`
Expected: FAIL because the current implementation always asks the LLM to parse intent first.

**Step 3: Write minimal implementation**

In `BotQueryService`, add a deterministic pre-parser that handles:

- optional verbs: `query`, `show`, `get`
- canonical entity + metric pairs
- optional time windows like `7d`, `30d`
- implied latest query when no time window is given

Keep the parser narrow and explicit. If it cannot confidently match, let the existing LLM parser handle the message.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_services/test_bot_query.py -k "query_mantle_tvl or 7d_to_metric_history" -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/services/bot_query.py tests/test_services/test_bot_query.py
git commit -m "feat: add deterministic metric bot parser"
```

### Task 3: Normalize entity and metric aliases before dispatch

**Files:**
- Modify: `src/services/bot_query.py`
- Possibly modify: `src/services/query_tools.py`
- Test: `tests/test_services/test_bot_query.py`

**Step 1: Write the failing tests**

Add tests proving normalization closes the current case-sensitivity gap:

```python
@pytest.mark.asyncio
async def test_bot_query_service_normalizes_mantle_and_tvl_aliases(...):
    ...
    result = await service.handle_message("@bot Mantle TVL latest", now=seeded_data)
    assert result["data"]["entity"] == "mantle"
    assert result["data"]["metric_name"] == "tvl"
```

Also add one alias case such as `dex volume -> dex_volume`.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_services/test_bot_query.py -k normalize -v`
Expected: FAIL because the current code dispatches whatever the LLM returns without normalization.

**Step 3: Write minimal implementation**

Normalize parsed payloads before `_execute_intent()`:

- lowercase entity aliases
- lowercase / canonicalize metric aliases
- convert human phrases to internal metric ids

Keep the normalization local to bot routing. Do not change database rows or external API contract.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_services/test_bot_query.py -k normalize -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/services/bot_query.py tests/test_services/test_bot_query.py
git commit -m "fix: normalize bot metric query aliases"
```

### Task 4: Constrain the LLM parser with the catalog

**Files:**
- Modify: `src/services/bot_query.py`
- Test: `tests/test_services/test_bot_query.py`

**Step 1: Write the failing tests**

Add a test that inspects the parser prompt and proves it includes:

- supported metric intents
- canonical metrics
- canonical entities
- the rule that a bare metric query defaults to `metric_latest`

```python
@pytest.mark.asyncio
async def test_bot_query_service_parser_prompt_includes_catalog_constraints(...):
    ...
    await service.handle_message("mantle tvl latest", now=seeded_data)
    parser_prompt = llm_client.messages[0]
    assert "metric_latest" in parser_prompt[0]["content"]
    assert "tvl" in parser_prompt[0]["content"]
    assert "bare metric request defaults to metric_latest" in parser_prompt[0]["content"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_services/test_bot_query.py -k parser_prompt_includes_catalog_constraints -v`
Expected: FAIL because the current parser prompt is generic and does not describe the internal catalog.

**Step 3: Write minimal implementation**

Rewrite the parser prompt so the LLM is no longer guessing from a vague whitelist. It should explicitly receive:

- the metric query catalog
- allowed JSON schema
- canonical entity names
- canonical metric ids
- alias examples
- the default-latest rule

Keep the prompt narrow to phase-1 metric intents. Do not expand the prompt to unrelated capabilities yet.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_services/test_bot_query.py -k parser_prompt_includes_catalog_constraints -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/services/bot_query.py tests/test_services/test_bot_query.py
git commit -m "refactor: constrain bot llm parser with metric catalog"
```

### Task 5: Replace misleading fallback text with deterministic no-data guidance

**Files:**
- Modify: `src/services/bot_query.py`
- Test: `tests/test_services/test_bot_query.py`

**Step 1: Write the failing tests**

Add tests for the two fallback classes:

- unsupported request
- supported metric request with no internal data

The key assertion: neither response should mention external actions for plain read-only metric queries.

```python
@pytest.mark.asyncio
async def test_bot_query_service_no_data_fallback_does_not_talk_about_external_actions(...):
    ...
    result = await service.handle_message("mantle unknown_metric latest", now=seeded_data)
    assert "external actions" not in result["answer"].lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_services/test_bot_query.py -k external_actions -v`
Expected: FAIL because the current fallback prompt always mentions external actions.

**Step 3: Write minimal implementation**

Split fallback handling into deterministic responses:

- unsupported read-only request: explain what read-only queries are supported
- no internal data: explain that the request shape is supported, but matching internal data was not found

Use static application text first. Do not route fallback wording back through the LLM in phase 1.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_services/test_bot_query.py -k external_actions -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/services/bot_query.py tests/test_services/test_bot_query.py
git commit -m "fix: use deterministic bot fallback responses"
```

### Task 6: Run the focused and full verification suites

**Files:**
- Test: `tests/test_services/test_bot_query.py`
- Test: `tests/test_api/test_lark_integration.py`
- Test: `tests/test_services/test_query_tools.py`
- Test: `tests/test_integrations/test_lark_cards.py`

**Step 1: Run focused bot routing tests**

Run:

```bash
pytest tests/test_services/test_bot_query.py -v
```

Expected: PASS

**Step 2: Run integration coverage around the callback path**

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
git commit -m "test: verify bot metric catalog routing"
```

## Deferred TODO After Phase 1

These are intentionally not part of the first implementation slice, but should be kept visible:

- apply the same catalog pattern to `alerts_list` and `recent_alerts`
- apply the same catalog pattern to `health_status` and `source_health`
- apply the same catalog pattern to `watchlist`
- apply the same catalog pattern to `daily_summary`
- decide whether alert/health/watchlist fallbacks should remain deterministic or regain controlled LLM phrasing
- add structured runtime logging for:
  - chosen parser path (`deterministic` vs `llm`)
  - normalized entity/metric ids
  - no-data misses after normalization
- consider small synonym tables for protocol names and ecosystem metrics
- evaluate whether the LLM parser should move from free-text prompt parsing to strict JSON-schema/tool-call style output

## Open Questions To Revisit Later

- whether `recent_alerts` should remain a distinct intent or be folded fully into `alerts_list`
- whether metric scope should become an explicit user-facing parameter in bot queries
- whether the bot should surface supported metrics dynamically when a user asks for an unknown metric

