# Local Alert Testing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a local-only alert testing workflow that writes alert outputs to host-visible log files, supports deterministic manual trigger scenarios, and documents the current alert rules and validation flow.

**Architecture:** Keep alert generation unchanged and extend the delivery layer with an optional local file sink controlled by settings. Build deterministic admin seed scenarios that insert snapshots and run the real rule engine, then document the implemented rule behavior and Docker-based validation workflow around those scenarios.

**Tech Stack:** Python 3.13, pytest, FastAPI service modules, SQLAlchemy async models, argparse admin CLI, Docker Compose

---

### Task 1: Add Local Alert Output Settings

**Files:**
- Modify: `config/settings.py`
- Modify: `tests/test_config/test_settings.py`

**Step 1: Write the failing test**

Add settings assertions for:

- `alert_local_output_enabled` defaulting to `False`
- `alert_local_output_dir` defaulting to `logs/alerts`
- explicit override support in constructor and `.env`

Example test shape:

```python
def test_settings_defaults():
    settings = Settings(_env_file=None, database_url="sqlite+aiosqlite:///tmp.db")
    assert settings.alert_local_output_enabled is False
    assert settings.alert_local_output_dir == "logs/alerts"
```

**Step 2: Run test to verify it fails**

Run: `/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/.venv/bin/pytest tests/test_config/test_settings.py -v`
Expected: FAIL because the settings fields do not exist yet.

**Step 3: Write minimal implementation**

Add the two settings fields to `Settings` in `config/settings.py`.

**Step 4: Run test to verify it passes**

Run: `/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/.venv/bin/pytest tests/test_config/test_settings.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add config/settings.py tests/test_config/test_settings.py
git commit -m "feat: add local alert output settings"
```

### Task 2: Add Local Alert File Sink in NotificationService

**Files:**
- Modify: `src/services/notifications.py`
- Modify: `tests/test_services/test_notifications.py`

**Step 1: Write the failing tests**

Add tests proving:

- when `alert_local_output_enabled=True`, `deliver_alerts()` writes one log file per alert under the configured directory
- the written file contains the approved field order:
  - `Metric`
  - `Movement`
  - `Current Value`
  - `Status`
  - `Source`
  - `Detected`
  - `Suggested Draft Copy`
  - `Action Required`
- local sink delivery is recorded with its own `DeliveryEvent.channel`, such as `local_alert_log`
- disabling Lark while enabling local output still writes local files without calling the Lark client

Example assertion shape:

```python
assert "Metric: TVL (Total Value Locked)" in content
assert "Status: NEW ALL-TIME HIGH" in content
assert deliveries[0].channel == "local_alert_log"
```

**Step 2: Run test to verify it fails**

Run: `/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/.venv/bin/pytest tests/test_services/test_notifications.py -v`
Expected: FAIL because no local file sink exists yet.

**Step 3: Write minimal implementation**

Implement in `src/services/notifications.py`:

- local sink enablement checks
- host directory creation
- deterministic filename generation
- log body rendering in the approved field order
- delivery bookkeeping for the local sink
- separate logical key namespace from Lark delivery

Do not change the existing alert serialization contract beyond what the local sink needs to render the same content semantics.

**Step 4: Run test to verify it passes**

Run: `/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/.venv/bin/pytest tests/test_services/test_notifications.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/services/notifications.py tests/test_services/test_notifications.py
git commit -m "feat: add local alert log sink"
```

### Task 3: Add Scenario Runner for Deterministic Alert Seeding

**Files:**
- Modify: `src/admin/seed.py`
- Modify: `src/admin/__main__.py`
- Modify: `tests/test_admin/test_seed.py`
- Modify: `tests/test_admin/test_cli.py`

**Step 1: Write the failing tests**

Add tests covering:

- parsing `seed alert-scenario <scenario_name>`
- parsing `seed alert-scenarios --all`
- a positive scenario that inserts snapshots and creates expected alert reasons
- a negative scenario that inserts snapshots but creates zero alerts because coverage rules suppress them
- a cooldown scenario where the second evaluation does not create a duplicate alert

Keep scenario entities unique and deterministic in tests.

Example test shape:

```python
result = await seed_alert_scenario(session_factory, "threshold_up_7d_tvl")
assert result["alerts_created"] >= 1
assert "threshold_25pct_7d" in result["actual_trigger_reasons"]
```

**Step 2: Run test to verify it fails**

Run: `/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/.venv/bin/pytest tests/test_admin/test_seed.py tests/test_admin/test_cli.py -v`
Expected: FAIL because the new CLI commands and scenario runner do not exist yet.

**Step 3: Write minimal implementation**

Implement:

- scenario definitions in `src/admin/seed.py`
- helper functions that insert exact `MetricRecord` sequences for each scenario
- result summaries listing expected and actual trigger reasons
- CLI wiring in `src/admin/__main__.py`

Initial scenario set:

- `threshold_up_7d_tvl`
- `decline_7d_dau`
- `threshold_mtd_active_addresses`
- `ath_tvl`
- `milestone_tvl_1b`
- `multi_signal_core`
- `cooldown_repeat_block`
- `no_alert_low_coverage_7d`
- `no_alert_sparse_mtd`

**Step 4: Run test to verify it passes**

Run: `/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/.venv/bin/pytest tests/test_admin/test_seed.py tests/test_admin/test_cli.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/admin/seed.py src/admin/__main__.py tests/test_admin/test_seed.py tests/test_admin/test_cli.py
git commit -m "feat: add local alert scenario runner"
```

### Task 4: Wire Docker Host Logs and Ignore Local Output

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.gitignore`

**Step 1: Write the failing verification**

First verify the current compose file does not mount a host logs directory:

Run: `docker compose config`
Expected: PASS, but output does not show a bind mount for `logs/`.

**Step 2: Write minimal implementation**

Update:

- `docker-compose.yml` to mount `./logs` into the app container
- `.gitignore` to ignore `logs/`

**Step 3: Run verification**

Run: `docker compose config`
Expected: PASS, and output shows the app service mounting the `logs/` directory.

**Step 4: Commit**

```bash
git add docker-compose.yml .gitignore
git commit -m "chore: mount local alert logs in docker compose"
```

### Task 5: Write the Operator-Facing Local Alert Rule Guide

**Files:**
- Create: `docs/alert-local-testing.md`

**Step 1: Write the document**

Document:

- local Docker workflow
- required env flags
- log directory layout
- rule explanations for:
  - threshold
  - decline
  - ATH
  - milestone
  - multi-signal
  - cooldown
  - coverage suppression
  - token-level suppression
- exact scenario command matrix
- expected outputs and non-outputs

Keep the document aligned to current implementation reality:

- use `total_value_secured` as the internal identifier
- do not claim severity routing not implemented in code
- describe detected time as current UTC+8 `SGT` formatter output

**Step 2: Run documentation verification**

Run: `rg -n "threshold_up_7d_tvl|multi_signal_core|cooldown_repeat_block|total_value_secured|Action Required" docs/alert-local-testing.md`
Expected: PASS with matches for the scenario matrix, metric identifier note, and output field description.

**Step 3: Commit**

```bash
git add docs/alert-local-testing.md
git commit -m "docs: add local alert testing guide"
```

### Task 6: Run Focused Regression Verification

**Files:**
- No code changes expected

**Step 1: Run focused tests**

Run:

```bash
/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/.venv/bin/pytest \
  tests/test_config/test_settings.py \
  tests/test_services/test_notifications.py \
  tests/test_admin/test_seed.py \
  tests/test_admin/test_cli.py -v
```

Expected: PASS

**Step 2: Run compose verification**

Run: `docker compose config`
Expected: PASS

**Step 3: Run full regression**

Run: `/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/.venv/bin/pytest`
Expected: PASS

**Step 4: Commit if verification-driven fixes were needed**

```bash
git add <only files changed by verification fixes>
git commit -m "test: verify local alert testing workflow"
```
