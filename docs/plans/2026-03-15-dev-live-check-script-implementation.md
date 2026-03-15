# Dev Live Check Script Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a local shell script that can start the app in `dev_live`, run the most useful availability checks, and stop only the process it launched.

**Architecture:** Implement a single `scripts/dev_live_check.sh` entry point with `up`, `check`, `full`, and `down` subcommands. Keep the script thin by reusing existing HTTP health endpoints and the existing `python -m src.scheduler run <job_id>` CLI, and make it testable through environment-based command overrides.

**Tech Stack:** POSIX shell (`bash`), `curl`, `uvicorn`, existing Python scheduler CLI, pytest, subprocess-based script tests

---

### Task 1: Add script test scaffolding and git-ignore support

**Files:**
- Modify: `.gitignore`
- Create: `tests/test_scripts/test_dev_live_check.py`

**Step 1: Write the failing tests**

Add initial tests for:

- `up` exits with code `1` when `DATABASE_URL` is missing
- `check` exits with code `2` when the health endpoint is unreachable

Use `subprocess.run()` and environment overrides for script dependencies.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scripts/test_dev_live_check.py -v`
Expected: FAIL because the script does not exist yet.

**Step 3: Write minimal implementation support**

Add `.tmp/` to `.gitignore` so PID and log artifacts stay untracked.

**Step 4: Run test to verify it still fails for the right reason**

Run: `pytest tests/test_scripts/test_dev_live_check.py -v`
Expected: FAIL because `scripts/dev_live_check.sh` is still missing, not because `.tmp/` is tracked.

**Step 5: Commit**

```bash
git add .gitignore tests/test_scripts/test_dev_live_check.py
git commit -m "test: add dev live check script scaffolding"
```

### Task 2: Create the script skeleton with argument parsing

**Files:**
- Create: `scripts/dev_live_check.sh`
- Test: `tests/test_scripts/test_dev_live_check.py`

**Step 1: Write the failing test**

Add tests for:

- unknown subcommand exits non-zero
- `up`, `check`, `full`, and `down` are recognized

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scripts/test_dev_live_check.py -v`
Expected: FAIL because the script does not parse commands yet.

**Step 3: Write minimal implementation**

Create `scripts/dev_live_check.sh` with:

- `#!/usr/bin/env bash`
- `set -euo pipefail`
- command dispatch for `up`, `check`, `full`, `down`
- shared env defaults:
  - `APP_HOST`
  - `APP_PORT`
  - `WAIT_SECONDS`
  - `TMP_DIR`
  - `SCHEDULER_PROFILE`
  - `CURL_BIN`
  - `PYTHON_BIN`
  - `UVICORN_BIN`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_scripts/test_dev_live_check.py -v`
Expected: PASS for parser-level checks

**Step 5: Commit**

```bash
git add scripts/dev_live_check.sh tests/test_scripts/test_dev_live_check.py
git commit -m "feat: add dev live check script skeleton"
```

### Task 3: Implement `up` and `down`

**Files:**
- Modify: `scripts/dev_live_check.sh`
- Test: `tests/test_scripts/test_dev_live_check.py`

**Step 1: Write the failing tests**

Add tests for:

- `up` requires `DATABASE_URL`
- `up` writes PID and log paths under `TMP_DIR`
- `down` removes only the PID file it manages

Use fake `uvicorn` and fake `kill` shims via temporary executables in the test PATH or direct env overrides.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scripts/test_dev_live_check.py -v`
Expected: FAIL because `up`/`down` are stubs.

**Step 3: Write minimal implementation**

Implement:

- `require_env DATABASE_URL`
- `ensure_tmp_dir`
- `start_server`
- `stop_server`

Write PID to `${TMP_DIR}/dev_live.pid` and logs to `${TMP_DIR}/dev_live.log`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_scripts/test_dev_live_check.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/dev_live_check.sh tests/test_scripts/test_dev_live_check.py
git commit -m "feat: implement dev live script process control"
```

### Task 4: Implement `check` health and source verification

**Files:**
- Modify: `scripts/dev_live_check.sh`
- Test: `tests/test_scripts/test_dev_live_check.py`

**Step 1: Write the failing tests**

Add tests for:

- `/api/health` unreachable returns exit `2`
- failing `source_health` manual job returns exit `3`
- successful `source_health`, `core_coingecko`, and `core_l2beat` checks print a summary block

Mock HTTP responses with a fake `curl` shim and scheduler job responses with a fake `python` shim.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scripts/test_dev_live_check.py -v`
Expected: FAIL because `check` does not yet perform these operations.

**Step 3: Write minimal implementation**

Implement `check` to:

- call `/api/health`
- run the three manual scheduler jobs
- call `/api/health/sources`
- print summary fields

Keep JSON parsing lightweight, using Python one-liners if shell-only parsing becomes brittle.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_scripts/test_dev_live_check.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/dev_live_check.sh tests/test_scripts/test_dev_live_check.py
git commit -m "feat: add dev live health and source checks"
```

### Task 5: Implement key metric validation and `full`

**Files:**
- Modify: `scripts/dev_live_check.sh`
- Test: `tests/test_scripts/test_dev_live_check.py`

**Step 1: Write the failing tests**

Add tests for:

- missing `mnt_volume` or `total_value_secured` returns exit `4`
- `full` waits for `/api/health` readiness before running `check`
- successful `full` returns `0`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scripts/test_dev_live_check.py -v`
Expected: FAIL because metric validation and readiness polling do not exist yet.

**Step 3: Write minimal implementation**

Implement:

- metric fetches against `/api/metrics/latest`
- readiness polling loop for `full`
- summary lines for metric presence

Keep timeouts bounded by `WAIT_SECONDS`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_scripts/test_dev_live_check.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/dev_live_check.sh tests/test_scripts/test_dev_live_check.py
git commit -m "feat: finish dev live check workflow"
```

### Task 6: Manual smoke verification and docs touch-up

**Files:**
- Modify: `.env.example`
- Modify: `HANDOFF.md`
- Modify: `docs/project-status.md`

**Step 1: Add minimal documentation**

Document:

- `SCHEDULER_PROFILE=dev_live`
- `./scripts/dev_live_check.sh full`
- `./scripts/dev_live_check.sh down`

**Step 2: Run targeted automated verification**

Run: `pytest tests/test_scripts/test_dev_live_check.py -v`
Expected: PASS

**Step 3: Run full regression suite**

Run: `pytest -q`
Expected: PASS

**Step 4: Run manual smoke check**

Run: `DATABASE_URL=sqlite+aiosqlite:///./dev-live-check.db ./scripts/dev_live_check.sh full`
Expected: script exits `0` or reports a clear provider-specific degradation

Run: `./scripts/dev_live_check.sh down`
Expected: managed process stops and PID file is removed

**Step 5: Commit**

```bash
git add .env.example HANDOFF.md docs/project-status.md scripts/dev_live_check.sh tests/test_scripts/test_dev_live_check.py .gitignore
git commit -m "feat: add dev live check script"
```

