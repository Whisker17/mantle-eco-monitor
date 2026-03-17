# Admin CLI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a single `python -m src.admin` CLI for read-only inspection, manual collection, and scenario-based fake data seeding to support debugging and operations.

**Architecture:** Build one Python CLI entry point rather than multiple shell scripts. Reuse the existing `Settings`, session factory, repositories, scheduler/runtime functions, and rule engine so the CLI behaves like the application itself. Keep the first version intentionally narrow: `inspect`, `collect job`, and `seed alert-spike`.

**Tech Stack:** Python 3.12+, argparse, SQLAlchemy async sessions, existing repository/runtime services, pytest

---

## Scope

First version commands:

- `python -m src.admin inspect overview`
- `python -m src.admin inspect snapshots --entity <entity> --metric <metric> --limit <n>`
- `python -m src.admin inspect alerts --entity <entity> --metric <metric> --limit <n>`
- `python -m src.admin inspect runs --source <platform> --limit <n>`
- `python -m src.admin collect job <job_id> [--dry-run]`
- `python -m src.admin seed alert-spike --entity <entity> --metric <metric> --previous <value> --current <value> [--no-evaluate-rules]`

Out of scope for this version:

- generic arbitrary row insertion commands
- arbitrary SQL execution
- HTTP debug endpoints
- a TUI or curses-style interface
- seed scenarios beyond `alert-spike`

### Task 1: Add the CLI entry point and parser skeleton

**Files:**
- Create: `src/admin/__init__.py`
- Create: `src/admin/__main__.py`
- Test: `tests/test_admin/test_cli.py`

**Step 1: Write the failing tests**

Add parser-level tests that assert:

- `python -m src.admin inspect overview`
- `python -m src.admin inspect snapshots --entity mantle --metric tvl`
- `python -m src.admin collect job core_defillama`
- `python -m src.admin seed alert-spike --entity mantle --metric tvl --previous 100 --current 200`

all parse to the expected command tree.

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_admin/test_cli.py -k parser -v
```

Expected: FAIL because `src.admin` does not exist yet.

**Step 3: Write minimal implementation**

Create a small argparse-based CLI with top-level subcommands:

- `inspect`
- `collect`
- `seed`

Add nested subcommands:

- `inspect overview`
- `inspect snapshots`
- `inspect alerts`
- `inspect runs`
- `collect job`
- `seed alert-spike`

Do not implement business logic yet. Return structured dispatch targets from the parser.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_admin/test_cli.py -k parser -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/admin/__init__.py src/admin/__main__.py tests/test_admin/test_cli.py
git commit -m "feat: add admin cli parser"
```

### Task 2: Add shared admin runtime helpers for DB/session access

**Files:**
- Create: `src/admin/runtime.py`
- Modify: `src/admin/__main__.py`
- Test: `tests/test_admin/test_cli.py`

**Step 1: Write the failing tests**

Add tests for helper functions that:

- build a `Settings` instance only when needed
- build an async session factory
- support invoking async command handlers from the CLI main entry point

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_admin/test_cli.py -k runtime -v
```

Expected: FAIL because the runtime helpers do not exist yet.

**Step 3: Write minimal implementation**

Create a small `runtime.py` that provides:

- settings loading
- engine/session factory creation
- helper for running async handlers

Do not duplicate logic from the app unless needed for CLI isolation.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_admin/test_cli.py -k runtime -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/admin/runtime.py src/admin/__main__.py tests/test_admin/test_cli.py
git commit -m "feat: add admin cli runtime helpers"
```

### Task 3: Implement `inspect overview`

**Files:**
- Create: `src/admin/inspect.py`
- Modify: `src/admin/__main__.py`
- Test: `tests/test_admin/test_inspect.py`

**Step 1: Write the failing tests**

Add a test that seeds:

- `metric_snapshots`
- `alert_events`
- `source_runs`
- `watchlist_protocols`

and asserts `inspect overview` returns:

- table counts
- latest snapshots
- latest alerts
- latest runs

Use a real sqlite-backed test DB like the existing service tests do.

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_admin/test_inspect.py -k overview -v
```

Expected: FAIL because the inspect handler does not exist yet.

**Step 3: Write minimal implementation**

Implement `inspect overview` to:

- query counts from each table
- fetch a small fixed number of recent rows
- print a readable summary

Keep output stable and simple. Avoid fancy formatting.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_admin/test_inspect.py -k overview -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/admin/inspect.py src/admin/__main__.py tests/test_admin/test_inspect.py
git commit -m "feat: add admin inspect overview"
```

### Task 4: Implement filtered `inspect snapshots`, `inspect alerts`, and `inspect runs`

**Files:**
- Modify: `src/admin/inspect.py`
- Modify: `src/admin/__main__.py`
- Test: `tests/test_admin/test_inspect.py`

**Step 1: Write the failing tests**

Add tests for:

- `inspect snapshots --entity mantle --metric tvl --limit 10`
- `inspect alerts --entity mantle --metric tvl --limit 10`
- `inspect runs --source defillama --limit 10`

Each test should assert the correct filtered rows are returned and ordered newest-first.

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_admin/test_inspect.py -k "snapshots or alerts or runs" -v
```

Expected: FAIL because only overview exists.

**Step 3: Write minimal implementation**

Add filtered query handlers for:

- snapshots
- alerts
- runs

Reuse the existing SQLAlchemy models directly. Do not call HTTP routes.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_admin/test_inspect.py -k "snapshots or alerts or runs" -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/admin/inspect.py src/admin/__main__.py tests/test_admin/test_inspect.py
git commit -m "feat: add filtered admin inspect commands"
```

### Task 5: Implement `collect job` with optional `--dry-run`

**Files:**
- Create: `src/admin/collect.py`
- Modify: `src/admin/__main__.py`
- Test: `tests/test_admin/test_collect.py`

**Step 1: Write the failing tests**

Add tests that assert:

- `collect job core_defillama` dispatches to the known job
- `collect job unknown_job` fails cleanly
- `collect job core_defillama --dry-run` does not write `metric_snapshots` or `source_runs`

Use monkeypatching around scheduler/runtime functions where appropriate.

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_admin/test_collect.py -v
```

Expected: FAIL because collect handlers do not exist yet.

**Step 3: Write minimal implementation**

Implement:

- job id validation against the existing scheduler job registry
- normal execution path using existing runtime functions
- `--dry-run` path that collects and prints records without committing them

Keep the dry-run behavior explicit and side-effect-free.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_admin/test_collect.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/admin/collect.py src/admin/__main__.py tests/test_admin/test_collect.py
git commit -m "feat: add admin collect job command"
```

### Task 6: Implement `seed alert-spike`

**Files:**
- Create: `src/admin/seed.py`
- Modify: `src/admin/__main__.py`
- Test: `tests/test_admin/test_seed.py`

**Step 1: Write the failing tests**

Add end-to-end tests for:

- `seed alert-spike --entity mantle --metric tvl --previous 100 --current 200`
  - inserts two snapshots
  - writes one or more `alert_events`
- `seed alert-spike ... --no-evaluate-rules`
  - inserts snapshots
  - writes no `alert_events`

The test DB should assert actual persisted rows, not just stdout.

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_admin/test_seed.py -v
```

Expected: FAIL because seed handlers do not exist yet.

**Step 3: Write minimal implementation**

Implement a scenario seed command that:

- inserts a baseline snapshot
- inserts a higher/lower snapshot that can trigger alert evaluation
- uses existing repository/model logic
- optionally runs `RuleEngine` and persists resulting `alert_events`

Default behavior:

- write snapshots
- evaluate rules
- persist alerts

Optional behavior:

- `--no-evaluate-rules` skips alert generation

**Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_admin/test_seed.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/admin/seed.py src/admin/__main__.py tests/test_admin/test_seed.py
git commit -m "feat: add admin alert spike seed command"
```

### Task 7: Document usage and run full verification

**Files:**
- Modify: `docs/runbook.md`
- Possibly modify: `docs/vps-deployment-and-lark-e2e-guide.md`
- Test: `tests/test_admin/test_cli.py`
- Test: `tests/test_admin/test_inspect.py`
- Test: `tests/test_admin/test_collect.py`
- Test: `tests/test_admin/test_seed.py`

**Step 1: Add concise operator docs**

Document:

- how to run `python -m src.admin` locally
- how to run it in Docker via `docker compose exec app python -m src.admin ...`
- examples for `inspect`, `collect`, and `seed`

**Step 2: Run focused admin test suites**

Run:

```bash
pytest tests/test_admin/test_cli.py tests/test_admin/test_inspect.py tests/test_admin/test_collect.py tests/test_admin/test_seed.py -v
```

Expected: PASS

**Step 3: Run full suite**

Run:

```bash
pytest
```

Expected: PASS with only the existing intentional skips.

**Step 4: Commit**

```bash
git add docs/runbook.md docs/vps-deployment-and-lark-e2e-guide.md src/admin tests/test_admin
git commit -m "docs: add admin cli usage"
```

## Notes

- Keep the CLI intentionally operational, not developer-framework-like.
- Avoid arbitrary SQL execution. The point is safe, repeatable admin tasks.
- Use existing business logic where possible so the CLI mirrors production behavior.
- Prefer deterministic seed scenarios over free-form raw row insertion in this first version.

