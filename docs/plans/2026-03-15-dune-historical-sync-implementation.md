# Dune Historical Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Dune historical sync pipeline that backfills daily history, catches up exactly after downtime, applies small correction windows, and keeps `ATH` calculations accurate without replaying historical alerts.

**Architecture:** Introduce a dedicated sync-state table plus a normalized `collected_day` key for daily snapshot upserts, extend Dune SQL and the Dune client to fetch explicit date ranges, and replace the current generic Dune collection path with a sync-aware job that can bootstrap, catch up, and run silently when rebuilding history. Keep startup non-blocking by launching the Dune sync in the background after the scheduler starts.

**Tech Stack:** Python 3.12, FastAPI, APScheduler, SQLAlchemy, Alembic, pytest, Dune SQL

---

### Task 0: Prepare an isolated implementation workspace

**Files:**
- Modify: none
- Create: none
- Test: none

**Step 1: Create a dedicated worktree before touching code**

Run:

```bash
git worktree add .worktrees/dune-historical-sync -b codex/dune-historical-sync
```

Expected: a new worktree rooted at `.worktrees/dune-historical-sync` on branch `codex/dune-historical-sync`.

**Step 2: Verify the worktree is clean**

Run:

```bash
git -C .worktrees/dune-historical-sync status --short
```

Expected: no output.

### Task 1: Lock the storage semantics in failing tests

**Files:**
- Modify: `tests/test_db/test_models.py`
- Modify: `tests/test_db/test_repositories.py`
- Modify: `tests/test_db/test_migration_smoke.py`
- Modify: `tests/test_db/test_alembic_async_migration.py`

**Step 1: Add a failing model test for the new sync-state table and snapshot day key**

Add assertions like:

```python
def test_metric_snapshot_has_required_columns():
    cols = {c.name for c in MetricSnapshot.__table__.columns}
    assert {"collected_day"} <= cols

def test_metric_sync_state_has_required_columns():
    cols = {c.name for c in MetricSyncState.__table__.columns}
    assert {
        "source_platform",
        "scope",
        "entity",
        "metric_name",
        "last_synced_date",
        "last_backfilled_date",
        "backfill_status",
        "last_sync_status",
        "last_error",
    } <= cols
```

**Step 2: Run the model tests to confirm they fail**

Run:

```bash
pytest tests/test_db/test_models.py -v
```

Expected: FAIL because `MetricSyncState` and `collected_day` do not exist yet.

**Step 3: Add failing repository tests for daily upsert and sync-state persistence**

Add tests proving:

```python
@pytest.mark.asyncio
async def test_snapshot_repository_updates_existing_daily_snapshot(async_session):
    day = datetime(2026, 3, 15, tzinfo=timezone.utc)
    first = _make_record(value="100", collected_at=day)
    corrected = _make_record(value="125", collected_at=day + timedelta(hours=3))

    await upsert_snapshots(async_session, [first])
    await async_session.commit()
    await upsert_snapshots(async_session, [corrected])
    await async_session.commit()

    stored = (await async_session.execute(select(MetricSnapshot))).scalar_one()
    assert stored.value == Decimal("125")
```

and:

```python
@pytest.mark.asyncio
async def test_metric_sync_state_repository_tracks_last_synced_date(async_session):
    state = await upsert_metric_sync_state(
        async_session,
        source_platform="dune",
        scope="core",
        entity="mantle",
        metric_name="daily_active_users",
        last_synced_date=date(2026, 3, 12),
        last_sync_status="success",
    )
    assert state.last_synced_date == date(2026, 3, 12)
```

**Step 4: Run the repository tests to confirm they fail**

Run:

```bash
pytest tests/test_db/test_repositories.py -v
```

Expected: FAIL because the repository still skips duplicate daily rows and has no sync-state helpers.

### Task 2: Add the schema and repository primitives

**Files:**
- Modify: `src/db/models.py`
- Modify: `src/db/repositories.py`
- Create: `alembic/versions/0003_metric_sync_states.py`
- Modify: `tests/test_db/test_models.py`
- Modify: `tests/test_db/test_repositories.py`
- Modify: `tests/test_db/test_migration_smoke.py`
- Modify: `tests/test_db/test_alembic_async_migration.py`

**Step 1: Add `collected_day` and `MetricSyncState` to the ORM models**

Implement fields shaped like:

```python
class MetricSnapshot(Base):
    collected_day: Mapped[date] = mapped_column(Date, nullable=False)

class MetricSyncState(Base):
    __tablename__ = "metric_sync_states"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_platform: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    entity: Mapped[str] = mapped_column(Text, nullable=False)
    metric_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_synced_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_backfilled_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    backfill_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    last_sync_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Add indexes plus a unique key covering `source_platform + scope + entity + metric_name`. Add a unique key covering `scope + entity + metric_name + collected_day` on snapshots.

**Step 2: Create the Alembic migration**

Migration responsibilities:

- add `collected_day`
- backfill `collected_day` from `collected_at`
- create the snapshot daily unique constraint
- create `metric_sync_states`
- add indexes needed for lookup and status queries

**Step 3: Replace insert-only snapshot writes with upsert helpers**

Implement repository functions such as:

```python
async def upsert_snapshots(...):
    ...

async def get_metric_sync_state(...):
    ...

async def upsert_metric_sync_state(...):
    ...
```

Populate `collected_day = rec.collected_at.date()` on every write.

**Step 4: Run the DB-focused test subset**

Run:

```bash
pytest tests/test_db/test_models.py tests/test_db/test_repositories.py tests/test_db/test_migration_smoke.py tests/test_db/test_alembic_async_migration.py -v
```

Expected: PASS.

**Step 5: Commit the schema slice**

Run:

```bash
git add src/db/models.py src/db/repositories.py alembic/versions/0003_metric_sync_states.py tests/test_db/test_models.py tests/test_db/test_repositories.py tests/test_db/test_migration_smoke.py tests/test_db/test_alembic_async_migration.py
git commit -m "feat: add dune sync state storage"
```

### Task 3: Parameterize the Dune query layer with date ranges

**Files:**
- Modify: `config/settings.py`
- Modify: `src/ingestion/dune.py`
- Modify: `queries/dune/daily_active_users.sql`
- Modify: `queries/dune/active_addresses.sql`
- Modify: `queries/dune/chain_transactions.sql`
- Modify: `queries/dune/stablecoin_transfer_volume.sql`
- Modify: `tests/test_ingestion/test_dune_client.py`

**Step 1: Write failing Dune client tests for range-aware queries**

Add tests proving the client can request a specific interval:

```python
@pytest.mark.asyncio
async def test_dune_client_executes_query_with_date_parameters():
    ...
    rows = await client.get_query_result(
        query_id=42,
        params={"start_date": "2026-03-01", "end_date": "2026-03-05"},
    )
    assert rows == [{"day": "2026-03-01", "value": 1}]
```

and that `METRIC_QUERY_MAP` expands to all configured Dune metrics.

**Step 2: Run the targeted Dune tests to confirm they fail**

Run:

```bash
pytest tests/test_ingestion/test_dune_client.py -v
```

Expected: FAIL because the client only supports `get_latest_result()` and only one metric mapping is configured.

**Step 3: Add settings and query specs**

Extend settings with:

```python
dune_daily_active_users_query_id: int = 0
dune_active_addresses_query_id: int = 0
dune_chain_transactions_query_id: int = 0
dune_sync_correction_lookback_days: int = 2
dune_sync_chunk_days: int = 31
```

In `src/ingestion/dune.py`, define metric specs that include:

- metric name
- settings attribute for query ID
- entity
- scope
- bootstrap start date

**Step 4: Convert Dune SQL files from fixed lookbacks to explicit parameters**

Update the SQL shape from:

```sql
where block_time >= now() - interval '30' day
```

to parameterized filters like:

```sql
where block_time >= cast('{{start_date}}' as timestamp)
  and block_time < cast('{{end_date}}' as timestamp) + interval '1' day
```

Apply the same pattern to the stablecoin query using `evt_block_time`.

**Step 5: Implement a range-aware Dune client API**

Add a method shaped like:

```python
async def get_query_result(
    self,
    query_id: int,
    *,
    params: dict[str, str] | None = None,
) -> list[dict]:
    ...
```

Keep `health_check()` lightweight and independent from a full sync.

**Step 6: Run the Dune test subset**

Run:

```bash
pytest tests/test_ingestion/test_dune_client.py -v
```

Expected: PASS.

**Step 7: Commit the query-layer slice**

Run:

```bash
git add config/settings.py src/ingestion/dune.py queries/dune/daily_active_users.sql queries/dune/active_addresses.sql queries/dune/chain_transactions.sql queries/dune/stablecoin_transfer_volume.sql tests/test_ingestion/test_dune_client.py
git commit -m "feat: parameterize dune historical queries"
```

### Task 4: Build the Dune sync service and runtime integration

**Files:**
- Create: `src/services/dune_sync.py`
- Modify: `src/scheduler/runtime.py`
- Modify: `src/scheduler/jobs.py`
- Modify: `tests/test_services/test_dune_sync.py`
- Modify: `tests/test_scheduler/test_runtime.py`
- Modify: `tests/test_scheduler/test_jobs.py`

**Step 1: Write failing sync-service tests for bootstrap, catch-up, and correction windows**

Create tests like:

```python
@pytest.mark.asyncio
async def test_dune_sync_service_bootstraps_metric_from_start_date(...):
    result = await service.sync_metric("daily_active_users", today=date(2026, 3, 15))
    assert result.inserted_days == 14
    assert result.last_synced_date == date(2026, 3, 14)
```

```python
@pytest.mark.asyncio
async def test_dune_sync_service_catches_up_only_missing_days(...):
    state.last_synced_date = date(2026, 3, 10)
    await session.commit()
    result = await service.sync_metric("daily_active_users", today=date(2026, 3, 15))
    assert result.fetched_start == date(2026, 3, 9)
    assert result.fetched_end == date(2026, 3, 14)
```

```python
@pytest.mark.asyncio
async def test_dune_sync_service_rewrites_corrected_days_via_upsert(...):
    ...
    assert stored.value == Decimal("125")
```

**Step 2: Run the new sync tests to confirm they fail**

Run:

```bash
pytest tests/test_services/test_dune_sync.py tests/test_scheduler/test_runtime.py -v
```

Expected: FAIL because no sync service exists and runtime still uses `run_collection_job()` for Dune.

**Step 3: Implement `DuneSyncService`**

The service should:

- enumerate configured Dune metric specs
- load or create `metric_sync_states`
- compute bootstrap or catch-up intervals
- apply `correction_lookback_days`
- fetch Dune rows in `chunk_days` slices
- map rows into `MetricRecord`s
- upsert snapshots
- update sync state after each successful chunk

Use a result object shaped like:

```python
@dataclass
class DuneSyncResult:
    metrics_processed: int
    records_written: int
    advanced_metrics: list[str]
    backlog_days: int
```

**Step 4: Replace the Dune runtime path with a sync-aware job**

In `src/scheduler/jobs.py`, change `core_dune_job()` so it uses `DuneSyncService` instead of `run_collection_job()`. In `src/scheduler/runtime.py`, add any helper needed for:

- source-run logging
- per-metric failure isolation
- optional alert evaluation on the terminal synced day only

Update scheduler tests to keep `core_dune` registered and runnable.

**Step 5: Run the sync and scheduler test subset**

Run:

```bash
pytest tests/test_services/test_dune_sync.py tests/test_scheduler/test_runtime.py tests/test_scheduler/test_jobs.py -v
```

Expected: PASS.

**Step 6: Commit the sync-service slice**

Run:

```bash
git add src/services/dune_sync.py src/scheduler/runtime.py src/scheduler/jobs.py tests/test_services/test_dune_sync.py tests/test_scheduler/test_runtime.py tests/test_scheduler/test_jobs.py
git commit -m "feat: add dune historical sync service"
```

### Task 5: Keep startup non-blocking and alerts quiet during rebuilds

**Files:**
- Modify: `src/main.py`
- Modify: `tests/test_main.py`
- Modify: `src/services/dune_sync.py`
- Modify: `tests/test_services/test_dune_sync.py`

**Step 1: Write failing tests for startup kickoff and silent backlog handling**

Add tests proving:

```python
@pytest.mark.asyncio
async def test_lifespan_starts_background_dune_sync_task(...):
    ...
    assert fake_task_created is True
```

and:

```python
@pytest.mark.asyncio
async def test_dune_sync_service_skips_alerts_when_backlog_exceeds_one_day(...):
    ...
    assert alerts_created == 0
```

**Step 2: Run the startup and alert tests to confirm they fail**

Run:

```bash
pytest tests/test_main.py tests/test_services/test_dune_sync.py -v
```

Expected: FAIL because startup does not trigger a background sync and the service has no backlog-aware alert gating.

**Step 3: Implement the startup kickoff**

In `src/main.py`, after the scheduler starts, launch a background Dune sync task without blocking the lifespan context. The kickoff must:

- respect scheduler enablement
- log failures instead of crashing startup
- avoid duplicate work when Dune is disabled or unconfigured

**Step 4: Gate alerts to steady-state single-day advances only**

In `src/services/dune_sync.py`, only evaluate alerts when:

- the run is not an initial bootstrap
- the backlog is exactly one newly completed day
- the run advanced `last_synced_date`

Do not evaluate alerts for pure correction rewrites or multi-day catch-up.

**Step 5: Run the startup and alert subset**

Run:

```bash
pytest tests/test_main.py tests/test_services/test_dune_sync.py -v
```

Expected: PASS.

**Step 6: Commit the startup and alert slice**

Run:

```bash
git add src/main.py src/services/dune_sync.py tests/test_main.py tests/test_services/test_dune_sync.py
git commit -m "feat: trigger dune sync on startup"
```

### Task 6: Verify the full historical-sync path

**Files:**
- Modify: none
- Test: `tests/test_db/test_models.py`
- Test: `tests/test_db/test_repositories.py`
- Test: `tests/test_db/test_migration_smoke.py`
- Test: `tests/test_db/test_alembic_async_migration.py`
- Test: `tests/test_ingestion/test_dune_client.py`
- Test: `tests/test_services/test_dune_sync.py`
- Test: `tests/test_scheduler/test_runtime.py`
- Test: `tests/test_scheduler/test_jobs.py`
- Test: `tests/test_main.py`

**Step 1: Run the focused regression suite**

Run:

```bash
pytest tests/test_db/test_models.py tests/test_db/test_repositories.py tests/test_db/test_migration_smoke.py tests/test_db/test_alembic_async_migration.py tests/test_ingestion/test_dune_client.py tests/test_services/test_dune_sync.py tests/test_scheduler/test_runtime.py tests/test_scheduler/test_jobs.py tests/test_main.py -v
```

Expected: PASS.

**Step 2: Run the project smoke suite that covers app startup and database wiring**

Run:

```bash
pytest tests/test_integration/test_phase1_smoke.py -v
```

Expected: PASS.

**Step 3: Check the resulting schema diff and git state**

Run:

```bash
git status --short
```

Expected: only the intended historical-sync changes are present.

**Step 4: Commit the verification pass if follow-up edits were needed**

Run:

```bash
git add .
git commit -m "test: verify dune historical sync flow"
```
