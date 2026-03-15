# Lark Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Lark app integration that can deliver alert cards, deliver AI-written daily summaries, and answer natural-language Lark bot queries with source URLs.

**Architecture:** Keep `metric_snapshots` and `alert_events` as the source of truth, add persistent delivery tracking, send Lark messages only after data commits succeed, and constrain LLM usage to intent parsing and response synthesis over deterministic local query results.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async ORM, APScheduler 4, httpx, pytest, Alembic, Lark OpenAPI, external OpenAI-compatible LLM API

---

### Task 1: Add Lark and LLM settings

**Files:**
- Modify: `config/settings.py`
- Modify: `.env.example`
- Test: `tests/test_config/test_settings.py`

**Step 1: Write the failing settings tests**

Add assertions for new fields:

- `lark_bot_enabled`
- `lark_app_id`
- `lark_app_secret`
- `lark_verification_token`
- `lark_encrypt_key`
- `lark_environment`
- `lark_alert_chat_id_dev`
- `lark_alert_chat_id_prod`
- `lark_summary_chat_id_dev`
- `lark_summary_chat_id_prod`
- `llm_api_base`
- `llm_api_key`
- `llm_model`
- `llm_timeout_seconds`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config/test_settings.py -v`
Expected: FAIL because the new settings fields do not exist yet.

**Step 3: Write minimal implementation**

Extend `Settings` with string defaults for optional secrets and a sane timeout default, for example:

```python
class Settings(BaseSettings):
    lark_bot_enabled: bool = False
    lark_app_id: str = ""
    lark_app_secret: str = ""
    lark_verification_token: str = ""
    lark_encrypt_key: str = ""
    lark_environment: str = "dev"
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: int = 30
```

**Step 4: Document the env surface**

Add the corresponding commented variables to `.env.example`, including separate chat ids for `dev` and `prod`.

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_config/test_settings.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add config/settings.py .env.example tests/test_config/test_settings.py
git commit -m "feat: add lark and llm runtime settings"
```

### Task 2: Add delivery tracking persistence

**Files:**
- Create: `alembic/versions/0002_delivery_events.py`
- Modify: `src/db/models.py`
- Modify: `src/db/repositories.py`
- Test: `tests/test_db/test_models.py`
- Test: `tests/test_db/test_repositories.py`
- Test: `tests/test_db/test_alembic_async_migration.py`
- Test: `tests/test_db/test_migration_smoke.py`

**Step 1: Write the failing model and repository tests**

Add coverage for a new `DeliveryEvent` model with columns such as:

- `channel`
- `entity_type`
- `entity_id`
- `logical_key`
- `environment`
- `status`
- `attempt_count`
- `last_error`
- `delivered_at`
- `created_at`
- `updated_at`

Also add repository tests for:

- creating a pending delivery row
- marking a row as delivered
- marking a row as failed and incrementing `attempt_count`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_db/test_models.py tests/test_db/test_repositories.py tests/test_db/test_alembic_async_migration.py tests/test_db/test_migration_smoke.py -v`
Expected: FAIL because `delivery_events` does not exist.

**Step 3: Write minimal implementation**

Add the SQLAlchemy model and repository helpers, for example:

```python
async def create_delivery_event(session: AsyncSession, **kwargs) -> DeliveryEvent:
    event = DeliveryEvent(**kwargs)
    session.add(event)
    await session.flush()
    return event
```

and:

```python
async def mark_delivery_event(session: AsyncSession, event: DeliveryEvent, *, status: str, error: str | None = None):
    event.status = status
    event.last_error = error
    event.attempt_count += 1
```

**Step 4: Add the Alembic migration**

Create `0002_delivery_events.py` to create the table and its unique lookup index on `logical_key`.

**Step 5: Run the DB tests again**

Run: `pytest tests/test_db/test_models.py tests/test_db/test_repositories.py tests/test_db/test_alembic_async_migration.py tests/test_db/test_migration_smoke.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add alembic/versions/0002_delivery_events.py src/db/models.py src/db/repositories.py tests/test_db/test_models.py tests/test_db/test_repositories.py tests/test_db/test_alembic_async_migration.py tests/test_db/test_migration_smoke.py
git commit -m "feat: add delivery event persistence"
```

### Task 3: Add constrained query tools and an external LLM adapter

**Files:**
- Create: `src/services/__init__.py`
- Create: `src/services/query_tools.py`
- Create: `src/services/llm.py`
- Test: `tests/test_services/test_query_tools.py`
- Test: `tests/test_services/test_llm.py`

**Step 1: Write the failing query tool tests**

Add tests for helpers that return structured data with source URLs:

- `get_latest_metric(...)`
- `get_metric_history(...)`
- `get_recent_alerts(...)`
- `get_daily_summary_context(...)`

Each result should include `source_platform` and `source_ref` when present.

**Step 2: Write the failing LLM adapter test**

Add a mocked `httpx` test showing an OpenAI-compatible chat-completions wrapper sends:

- the configured `Authorization` header
- the configured `model`
- a JSON request body with `messages`

and extracts the text content from the response.

**Step 3: Run tests to verify they fail**

Run: `pytest tests/test_services/test_query_tools.py tests/test_services/test_llm.py -v`
Expected: FAIL because the services do not exist.

**Step 4: Write minimal implementation**

Keep `query_tools` deterministic and narrow. Keep `llm.py` transport-only, for example:

```python
class LLMClient:
    async def complete_json(self, messages: list[dict]) -> str:
        ...
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_services/test_query_tools.py tests/test_services/test_llm.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/services/__init__.py src/services/query_tools.py src/services/llm.py tests/test_services/test_query_tools.py tests/test_services/test_llm.py
git commit -m "feat: add query tools and llm adapter"
```

### Task 4: Add the Lark client and card builders

**Files:**
- Create: `src/integrations/lark/__init__.py`
- Create: `src/integrations/lark/client.py`
- Create: `src/integrations/lark/cards.py`
- Test: `tests/test_integrations/test_lark_client.py`
- Test: `tests/test_integrations/test_lark_cards.py`

**Step 1: Write the failing Lark client tests**

Cover:

- fetching a tenant token from the auth endpoint
- caching the token until expiry
- sending a card message to a chat id

Use `httpx.MockTransport` so no live credentials are needed.

**Step 2: Write the failing card-rendering tests**

Add tests for:

- alert card content
- daily summary card content
- bot reply card content with a source URL section

**Step 3: Run tests to verify they fail**

Run: `pytest tests/test_integrations/test_lark_client.py tests/test_integrations/test_lark_cards.py -v`
Expected: FAIL because the integration module does not exist.

**Step 4: Write minimal implementation**

The client should expose narrow methods such as:

```python
class LarkClient:
    async def send_card(self, chat_id: str, card: dict) -> dict:
        ...
```

Keep card builders pure so they are easy to snapshot-test.

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_integrations/test_lark_client.py tests/test_integrations/test_lark_cards.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/integrations/lark/__init__.py src/integrations/lark/client.py src/integrations/lark/cards.py tests/test_integrations/test_lark_client.py tests/test_integrations/test_lark_cards.py
git commit -m "feat: add lark client and cards"
```

### Task 5: Deliver persisted alerts to Lark

**Files:**
- Create: `src/services/notifications.py`
- Modify: `src/scheduler/runtime.py`
- Test: `tests/test_services/test_notifications.py`
- Test: `tests/test_scheduler/test_runtime.py`

**Step 1: Write the failing notification tests**

Add coverage for:

- resolving the correct `alert` chat id from `lark_environment`
- creating a `delivery_events` row per alert
- skipping sends when `lark_delivery_enabled` is `False`
- marking a delivery row as `failed` when the Lark client raises

**Step 2: Write the failing runtime integration test**

Add a `run_collection_job(...)` test showing:

- alert rows are committed
- notification send is attempted after commit
- Lark send failure does not change the returned job status from `success`

**Step 3: Run tests to verify they fail**

Run: `pytest tests/test_services/test_notifications.py tests/test_scheduler/test_runtime.py -v`
Expected: FAIL because no alert notification service exists.

**Step 4: Write minimal implementation**

Introduce a notification service like:

```python
class NotificationService:
    async def deliver_alerts(self, alerts: list[AlertEvent]) -> None:
        ...
```

Refactor `run_collection_job()` so it returns committed alerts, then calls notification delivery after the DB transaction succeeds.

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_services/test_notifications.py tests/test_scheduler/test_runtime.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/services/notifications.py src/scheduler/runtime.py tests/test_services/test_notifications.py tests/test_scheduler/test_runtime.py
git commit -m "feat: deliver alerts to lark after commit"
```

### Task 6: Add the AI daily summary job

**Files:**
- Create: `src/services/daily_summary.py`
- Modify: `src/scheduler/jobs.py`
- Modify: `config/scheduler.toml`
- Test: `tests/test_services/test_daily_summary.py`
- Test: `tests/test_scheduler/test_jobs.py`

**Step 1: Write the failing summary service tests**

Add tests that:

- compute the previous natural-day window in `Asia/Shanghai`
- collect core metrics, notable alerts, and source URLs
- call the LLM adapter with structured summary context
- hand the rendered card to the notification service

**Step 2: Write the failing scheduler tests**

Add assertions that `daily_summary`:

- is registered in `prod`
- is `manual` in `dev_live`
- is `disabled` in `ci`

**Step 3: Run tests to verify they fail**

Run: `pytest tests/test_services/test_daily_summary.py tests/test_scheduler/test_jobs.py -v`
Expected: FAIL because the summary service and job do not exist.

**Step 4: Write minimal implementation**

Add a scheduler job like:

```python
async def daily_summary_job():
    ...
```

and register it in `JOB_REGISTRY` plus `config/scheduler.toml`.

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_services/test_daily_summary.py tests/test_scheduler/test_jobs.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/services/daily_summary.py src/scheduler/jobs.py config/scheduler.toml tests/test_services/test_daily_summary.py tests/test_scheduler/test_jobs.py
git commit -m "feat: add lark daily summary job"
```

### Task 7: Add bot-query intent handling

**Files:**
- Create: `src/services/bot_query.py`
- Test: `tests/test_services/test_bot_query.py`

**Step 1: Write the failing bot query tests**

Cover:

- latest-metric question such as `@bot mantle tvl latest`
- history question such as `@bot show mantle dex volume 7d`
- recent-alert question
- unsupported prompt fallback

Require the final response payload to include:

- a conclusion
- key values
- at least one source URL when data contains `source_ref`

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_services/test_bot_query.py -v`
Expected: FAIL because the bot query service does not exist.

**Step 3: Write minimal implementation**

Use a two-stage service:

```python
class BotQueryService:
    async def handle_message(self, text: str) -> dict:
        intent = await self._parse_intent(text)
        result = await self._execute(intent)
        return await self._synthesize_answer(result)
```

Validate the parsed intent against a fixed schema before any query runs.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_services/test_bot_query.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/services/bot_query.py tests/test_services/test_bot_query.py
git commit -m "feat: add lark bot query service"
```

### Task 8: Add the Lark callback endpoint

**Files:**
- Create: `src/integrations/lark/signature.py`
- Create: `src/integrations/lark/router.py`
- Modify: `src/main.py`
- Test: `tests/test_api/test_lark_integration.py`

**Step 1: Write the failing callback API tests**

Add tests for:

- challenge verification request handling
- invalid verification token or signature rejection
- valid message event dispatch to `BotQueryService`
- ignoring duplicate event ids

Mock the downstream services so the tests stay offline.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api/test_lark_integration.py tests/test_main.py -v`
Expected: FAIL because the route is not mounted.

**Step 3: Write minimal implementation**

Expose a callback route such as:

```python
@router.post("/api/integrations/lark/events")
async def handle_lark_event(...):
    ...
```

Mount it in `create_app()` and keep the route thin.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api/test_lark_integration.py tests/test_main.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/integrations/lark/signature.py src/integrations/lark/router.py src/main.py tests/test_api/test_lark_integration.py
git commit -m "feat: add lark callback endpoint"
```

### Task 9: Verify the integrated flow

**Files:**
- Test: `tests/test_config/test_settings.py`
- Test: `tests/test_db/test_models.py`
- Test: `tests/test_db/test_repositories.py`
- Test: `tests/test_db/test_alembic_async_migration.py`
- Test: `tests/test_db/test_migration_smoke.py`
- Test: `tests/test_integrations/test_lark_client.py`
- Test: `tests/test_integrations/test_lark_cards.py`
- Test: `tests/test_services/test_query_tools.py`
- Test: `tests/test_services/test_llm.py`
- Test: `tests/test_services/test_notifications.py`
- Test: `tests/test_services/test_daily_summary.py`
- Test: `tests/test_services/test_bot_query.py`
- Test: `tests/test_scheduler/test_jobs.py`
- Test: `tests/test_scheduler/test_runtime.py`
- Test: `tests/test_api/test_lark_integration.py`

**Step 1: Run the targeted verification suite**

Run: `pytest tests/test_config/test_settings.py tests/test_db/test_models.py tests/test_db/test_repositories.py tests/test_db/test_alembic_async_migration.py tests/test_db/test_migration_smoke.py tests/test_integrations/test_lark_client.py tests/test_integrations/test_lark_cards.py tests/test_services/test_query_tools.py tests/test_services/test_llm.py tests/test_services/test_notifications.py tests/test_services/test_daily_summary.py tests/test_services/test_bot_query.py tests/test_scheduler/test_jobs.py tests/test_scheduler/test_runtime.py tests/test_api/test_lark_integration.py -v`
Expected: PASS

**Step 2: Run an existing regression slice**

Run: `pytest tests/test_api/test_alerts.py tests/test_api/test_metrics.py tests/test_main.py -v`
Expected: PASS

**Step 3: Manual scheduler sanity check**

Run: `python -m src.scheduler list`
Expected: `daily_summary` appears with the correct mode for the active profile.

**Step 4: Manual callback sanity check**

Run a local POST against `/api/integrations/lark/events` with a mocked challenge payload.
Expected: challenge is echoed correctly and no traceback is logged.
