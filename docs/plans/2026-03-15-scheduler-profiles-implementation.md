# Scheduler Profiles Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add TOML-driven scheduler profiles so production can use low-frequency polling while development and CI use faster or manual scheduling behavior.

**Architecture:** Introduce a scheduler configuration loader that reads `config/scheduler.toml`, resolves a selected profile, and dynamically builds APScheduler triggers for known job callables. Keep collection jobs unchanged; add a shared job registry plus a manual dispatch helper for local testing.

**Tech Stack:** Python 3.12, FastAPI, APScheduler 4, pydantic-settings, TOML parsing with the standard library `tomllib`, pytest

---

### Task 1: Add scheduler profile settings

**Files:**
- Modify: `config/settings.py`
- Modify: `tests/test_config/test_settings.py`

**Step 1: Write the failing tests**

Add assertions covering:

- default `scheduler_profile == "prod"`
- default `scheduler_config_path == "config/scheduler.toml"`
- explicit overrides when constructing `Settings(...)`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config/test_settings.py -v`
Expected: FAIL because the new settings fields do not exist.

**Step 3: Write minimal implementation**

Update `Settings` with:

- `scheduler_profile: str = "prod"`
- `scheduler_config_path: str = "config/scheduler.toml"`

Keep the current `.env` behavior unchanged.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config/test_settings.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add config/settings.py tests/test_config/test_settings.py
git commit -m "feat: add scheduler profile settings"
```

### Task 2: Add TOML scheduler configuration

**Files:**
- Create: `config/scheduler.toml`
- Modify: `.env.example`

**Step 1: Write the config file**

Create a TOML file with profiles:

- `prod`
- `dev_live`
- `ci`

Include the recommended job modes and cadence from the design doc.

**Step 2: Document configuration entry points**

Add commented examples to `.env.example` for:

- `SCHEDULER_PROFILE=prod`
- `SCHEDULER_PROFILE=dev_live`
- `SCHEDULER_CONFIG_PATH=config/scheduler.toml`

**Step 3: Verify file shape manually**

Run: `python - <<'PY'\nimport tomllib\nfrom pathlib import Path\nprint(tomllib.loads(Path('config/scheduler.toml').read_text()))\nPY`
Expected: prints a parsed dict without exceptions

**Step 4: Commit**

```bash
git add config/scheduler.toml .env.example
git commit -m "feat: add scheduler profile config"
```

### Task 3: Build a scheduler config loader

**Files:**
- Modify: `src/scheduler/jobs.py`
- Test: `tests/test_scheduler/test_jobs.py`

**Step 1: Write the failing tests**

Add tests for helper functions that:

- load the active profile from TOML
- allow `Settings.scheduler_profile` to override TOML `active_profile`
- reject unknown profiles
- reject unknown job ids in the TOML file

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scheduler/test_jobs.py -v`
Expected: FAIL because the loader helpers do not exist.

**Step 3: Write minimal implementation**

In `src/scheduler/jobs.py`:

- add a `JOB_REGISTRY` mapping job ids to existing coroutine functions
- add a `load_scheduler_profile(settings)` helper using `tomllib`
- add validation for profile existence and job id membership in `JOB_REGISTRY`

Use `pathlib.Path` for reading the TOML file.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_scheduler/test_jobs.py -v`
Expected: PASS for the new loader tests

**Step 5: Commit**

```bash
git add src/scheduler/jobs.py tests/test_scheduler/test_jobs.py
git commit -m "feat: load scheduler profiles from toml"
```

### Task 4: Replace hard-coded schedules with dynamic triggers

**Files:**
- Modify: `src/scheduler/jobs.py`
- Test: `tests/test_scheduler/test_jobs.py`

**Step 1: Write the failing tests**

Add coverage for:

- `cron` mode registration
- `interval` mode registration
- `manual` mode skipping registration
- `disabled` mode skipping registration

Verify expected schedule ids in the built scheduler for both `prod` and `dev_live`.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scheduler/test_jobs.py -v`
Expected: FAIL because `build_scheduler()` still uses `SCHEDULE_CONFIG`.

**Step 3: Write minimal implementation**

Refactor `build_scheduler()` to:

- accept an optional `Settings` instance for testability
- load the selected profile
- create `CronTrigger` or `IntervalTrigger` per job mode
- register only runnable jobs

Preserve current job functions.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_scheduler/test_jobs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/scheduler/jobs.py tests/test_scheduler/test_jobs.py
git commit -m "feat: build scheduler from profile triggers"
```

### Task 5: Honor profile-level scheduler disablement at startup

**Files:**
- Modify: `src/main.py`
- Modify: `src/scheduler/jobs.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing tests**

Add a test where:

- `Settings.scheduler_enabled` is `True`
- selected profile has `scheduler_enabled = false`
- `lifespan()` does not start the scheduler

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -v`
Expected: FAIL because startup only checks `settings.scheduler_enabled`.

**Step 3: Write minimal implementation**

Add a helper such as `is_scheduler_enabled(settings)` or return the profile metadata from the loader, then update `lifespan()` to respect both settings and profile state.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/main.py src/scheduler/jobs.py tests/test_main.py
git commit -m "feat: honor scheduler profile enablement"
```

### Task 6: Add manual job dispatch for local testing

**Files:**
- Modify: `src/scheduler/jobs.py`
- Test: `tests/test_scheduler/test_jobs.py`

**Step 1: Write the failing tests**

Add tests for a helper like `run_job_now(job_id)` that:

- dispatches a known job id
- raises a clear error for unknown ids
- rejects job ids marked `disabled`

Use monkeypatching to avoid external network calls.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scheduler/test_jobs.py -v`
Expected: FAIL because no manual dispatch helper exists.

**Step 3: Write minimal implementation**

Add a coroutine helper in `src/scheduler/jobs.py` that:

- validates the job id against `JOB_REGISTRY`
- optionally checks profile mode
- awaits the underlying coroutine function

Do not add HTTP surface area in this task.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_scheduler/test_jobs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/scheduler/jobs.py tests/test_scheduler/test_jobs.py
git commit -m "feat: add manual scheduler job dispatch"
```

### Task 7: Add a lightweight local CLI entry point

**Files:**
- Modify: `src/scheduler/jobs.py`
- Optionally Create: `src/scheduler/__main__.py`
- Test: `tests/test_scheduler/test_jobs.py`

**Step 1: Write the failing test**

If using a module entry point, add a test that exercises argument parsing for:

- `python -m src.scheduler run core_defillama`

If direct CLI testing is awkward, test the parser helper instead.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scheduler/test_jobs.py -v`
Expected: FAIL because no CLI entry point exists.

**Step 3: Write minimal implementation**

Expose a small CLI that supports:

- `list` to show known jobs and active modes
- `run <job_id>` to execute a job immediately

Reuse the same registry and profile loader.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_scheduler/test_jobs.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/scheduler/jobs.py src/scheduler/__main__.py tests/test_scheduler/test_jobs.py
git commit -m "feat: add scheduler job cli"
```

### Task 8: Verify the scheduler end-to-end

**Files:**
- Test: `tests/test_config/test_settings.py`
- Test: `tests/test_scheduler/test_jobs.py`
- Test: `tests/test_main.py`

**Step 1: Run targeted verification**

Run: `pytest tests/test_config/test_settings.py tests/test_scheduler/test_jobs.py tests/test_main.py -v`
Expected: PASS

**Step 2: Run broader regression checks**

Run: `pytest tests/test_scheduler/test_runtime.py tests/test_api/test_health.py -v`
Expected: PASS

**Step 3: Manual smoke check**

Run: `python -m src.scheduler list`
Expected: prints the active profile and registered jobs without traceback

Run: `python -m src.scheduler run source_health`
Expected: completes with a structured result or a clear upstream error message

**Step 4: Commit**

```bash
git add config/settings.py config/scheduler.toml .env.example src/main.py src/scheduler/jobs.py src/scheduler/__main__.py tests/test_config/test_settings.py tests/test_scheduler/test_jobs.py tests/test_main.py
git commit -m "feat: add environment-aware scheduler profiles"
```

