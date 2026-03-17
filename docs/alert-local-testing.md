# Local Alert Testing

This guide explains how to test alert behavior locally with Docker, how to trigger the deterministic alert scenarios, what each scenario should produce, and what the current implementation does not do yet.

## Scope

This workflow is for local alert verification only.

- It does not use Lark.
- It does not require historical bootstrap.
- It is intended to validate current rule behavior, stored `alert_events`, and current local alert output formatting.
- It does not claim routing behavior by severity beyond what the code actually does today.

## 1. Local Docker Workflow

Prepare a local `.env` first. `docker compose config` and `docker compose up` both expect `.env` to exist because `docker-compose.yml` references `env_file`.

Recommended local flags:

```dotenv
POSTGRES_DB=mantle_monitor
POSTGRES_USER=monitor
POSTGRES_PASSWORD=password

LARK_DELIVERY_ENABLED=false
ALERT_LOCAL_OUTPUT_ENABLED=true
ALERT_LOCAL_OUTPUT_DIR=logs/alerts
```

Notes:

- You do not need to set `DATABASE_URL` manually for Docker Compose. The app service injects a container-local database URL that points to `db`.
- Keep `LARK_DELIVERY_ENABLED=false` for this workflow.
- Keep `ALERT_LOCAL_OUTPUT_ENABLED=true` if you want runtime delivery paths to write local files.

Start the stack:

```bash
docker compose up -d --build
```

Check status:

```bash
docker compose ps
docker compose logs app --tail=100
```

Stop the stack:

```bash
docker compose down
```

## 2. Local Log Output

The local alert sink is controlled by:

- `ALERT_LOCAL_OUTPUT_ENABLED`
- `ALERT_LOCAL_OUTPUT_DIR`

Default output directory:

- `logs/alerts/`

Docker mounts the host log directory into the container:

- host: `./logs`
- container: `/app/logs`

Generated files are ignored by git because `.gitignore` contains `logs/`.

File naming is deterministic and includes:

- UTC detection timestamp
- entity
- metric
- trigger reason
- alert id

Example:

```text
logs/alerts/20260317T101500Z_scenario-threshold-up-7d-tvl_tvl_threshold_25pct_7d_12.log
```

## 3. Current Output Format

When the local alert sink is invoked, each alert log is rendered in this order:

1. `Metric`
2. `Movement`
3. `Current Value`
4. `Status`
5. `Source`
6. `Detected`
7. `Suggested Draft Copy`
8. `Action Required`

The local sink derives these lines from the current alert card semantics, then normalizes them to plain text.

Current field behavior:

- `Metric`: humanized from `metric_name`
- `Movement`: derived from `change_pct` and `time_window`
- `Current Value`: uses `formatted_value` when present, otherwise compact numeric formatting
- `Status`: derived from alert semantics
- `Source`: derived from `source_platform` and `source_ref`
- `Detected`: rendered in UTC+8 and currently labeled `SGT`
- `Suggested Draft Copy`: placeholder text
- `Action Required`: fixed placeholder block

Example shape:

```text
Metric: TVL (Total Value Locked)

Movement: +25.00% (7D)

Current Value: $~125.0M

Status: SIGNIFICANT UPWARD MOVE

Source: DefiLlama (https://...)

Detected: March 15, 2026 - 08:00 SGT

Suggested Draft Copy: Placeholder - draft copy not generated yet.

Action Required:
- Social: Review alert context and refine for posting
- Design: Prepare metric card or lightweight visual
- Target post window: Within 6 hours of alert
```

## 4. Important Current Limitation

The deterministic seed scenarios do not currently write local log files by themselves.

Reason:

- `python -m src.admin seed alert-scenario ...` persists snapshots and `alert_events`
- local file output is produced by `NotificationService.deliver_alerts()`
- the admin seed commands do not call `NotificationService.deliver_alerts()`

What the seed scenarios are good for today:

- validating rule triggers
- validating `alert_events`
- validating expected trigger sets returned by the scenario JSON
- validating snapshot coverage behavior

What the seed scenarios do not do today:

- they do not replay those seeded alerts into `logs/alerts/`

Use the seed scenarios to validate alert generation and inspect the database. Use runtime collection paths that call `NotificationService` if you need end-to-end local file delivery.

## 5. Rule Reference

### Threshold

Threshold alerts are generated when percentage change crosses the configured threshold for a metric.

Active comparison windows:

- `7d`
- `mtd`

Current severity thresholds:

- most metrics: `minor >= 10%`, `moderate >= 15%`, `high >= 20%`, `critical >= 30%`
- `utilization`: `minor >= 5%`, `moderate >= 10%`, `high >= 15%`, `critical >= 20%`

Trigger reason format:

- `threshold_{pct}pct_{window}`

Current note:

- the local testing guide does not claim any special delivery routing by severity, because the current local workflow does not implement severity-based routing behavior.

### Decline

Decline alerts are generated when change is `<= -20%` in `7d` or `mtd`.

Trigger reason format:

- `decline_{pct}pct_{window}`

Current status text on the rendered output:

- `SHARP DECLINE`

### ATH

The intended ATH rule is `new_ath` when current value exceeds historical maximum.

Current implementation reality:

- the real persisted-snapshot path currently does not emit `new_ath` in the `ath_tvl` seed scenario
- current ATH lookup includes the just-inserted current snapshot in the comparison set
- as a result, `ath_tvl` is documented as a current limitation scenario, not as a positive ATH trigger scenario

This is a real current limitation, not an omitted test.

### Milestone

Milestone alerts are generated when a metric crosses a configured milestone between the previous snapshot and the current snapshot.

Trigger reason format:

- `milestone_{label}`

Example currently covered by local scenario:

- `milestone_$1.00B`

### Multi-Signal

Multi-signal alerts are generated when the same entity has at least two `high` or `critical` alerts in the same evaluation cycle.

Trigger reason format:

- `multi_signal:{metric1}, {metric2}, ...`

Current implementation detail:

- the summary contract should include the full trigger set, not only the multi-signal trigger itself

### Cooldown

Cooldown suppresses duplicate alerts for the same:

- `entity`
- `metric_name`
- `trigger_reason`

The deterministic `cooldown_repeat_block` scenario validates:

- first pass creates `threshold_25pct_7d`
- second pass creates no duplicate alert

Current caveat:

- the scenario normalizes SQLite-read naive datetimes back to `UTC` for the cooldown check
- this patch is local to the scenario helper and restored in `finally`
- this is acceptable for current serial CLI/test usage, but it is not a general concurrency-safe pattern

### Coverage Suppression

Coverage suppression prevents sparse data from generating misleading threshold or decline alerts.

`7d` coverage rule:

- the series must span back to `current_day - 7`
- at least 6 of the 8 natural days in the window must be present

`mtd` coverage rule:

- the first snapshot in the month must be no later than day 2
- month coverage through the current day must be at least 80%

If coverage is insufficient:

- snapshots are still stored
- the affected threshold or decline alert is not generated

### Token-Level Suppression

The rule engine suppresses alerts for token-level stablecoin breakdown entities on:

- `stablecoin_transfer_volume`
- `stablecoin_transfer_tx_count`

Current entity shape:

- `mantle:*`

This prevents token-level stablecoin breakdown rows from generating duplicate alerts.

## 6. Metric Naming Note

Use `total_value_secured` as the internal identifier in docs, scripts, and filters.

Do not use `tvs` as the canonical internal identifier for local testing guidance.

The current card formatter still contains a `tvs` label mapping, but the ingestion and monitoring code paths use `total_value_secured`.

## 7. Scenario Command Matrix

Run one scenario:

```bash
docker compose exec app python -m src.admin seed alert-scenario threshold_up_7d_tvl
```

Run every scenario:

```bash
docker compose exec app python -m src.admin seed alert-scenarios --all
```

Run selected scenarios:

```bash
docker compose exec app python -m src.admin seed alert-scenarios --only threshold_up_7d_tvl,multi_signal_core
```

Scenario matrix:

| Scenario | Command | Expected Trigger Reasons | Expected Non-Outputs | Notes |
|---|---|---|---|---|
| `threshold_up_7d_tvl` | `docker compose exec app python -m src.admin seed alert-scenario threshold_up_7d_tvl` | `['threshold_25pct_7d']` | No `new_ath` on current real path | Positive 7D threshold scenario |
| `decline_7d_dau` | `docker compose exec app python -m src.admin seed alert-scenario decline_7d_dau` | `['decline_25pct_7d', 'multi_signal:daily_active_users', 'threshold_25pct_7d']` | No empty result set | Decline also produces threshold and multi-signal on the current engine path |
| `threshold_mtd_active_addresses` | `docker compose exec app python -m src.admin seed alert-scenario threshold_mtd_active_addresses` | `['threshold_15pct_7d', 'threshold_20pct_mtd']` | No decline alert | Real path emits both 7D and MTD threshold alerts |
| `ath_tvl` | `docker compose exec app python -m src.admin seed alert-scenario ath_tvl` | `[]` | No `new_ath` | Current implementation limitation |
| `milestone_tvl_1b` | `docker compose exec app python -m src.admin seed alert-scenario milestone_tvl_1b` | `['milestone_$1.00B']` | No threshold requirement | Positive milestone scenario |
| `multi_signal_core` | `docker compose exec app python -m src.admin seed alert-scenario multi_signal_core` | `['multi_signal:dex_volume, tvl', 'threshold_25pct_7d', 'threshold_35pct_7d']` | No empty result set | Multi-signal plus its component threshold alerts |
| `no_alert_low_coverage_7d` | `docker compose exec app python -m src.admin seed alert-scenario no_alert_low_coverage_7d` | `[]` | No threshold or decline alert | Snapshots are written, alert generation is silent |
| `no_alert_sparse_mtd` | `docker compose exec app python -m src.admin seed alert-scenario no_alert_sparse_mtd` | `[]` | No threshold or decline alert | Sparse month remains silent |
| `cooldown_repeat_block` | `docker compose exec app python -m src.admin seed alert-scenario cooldown_repeat_block` | First pass `['threshold_25pct_7d']`, second pass `[]` | No duplicate second alert | Cooldown suppression validation |

## 8. How To Validate Results

After running a scenario, inspect the returned JSON first. The scenario contract is intended to reflect the real engine output.

Inspect alerts:

```bash
docker compose exec app python -m src.admin inspect alerts --limit 20
```

Inspect scenario snapshots:

```bash
docker compose exec app python -m src.admin inspect snapshots --entity scenario-threshold-up-7d-tvl --metric tvl --limit 20
```

Useful patterns:

- positive scenarios should return non-empty `actual_trigger_reasons`
- negative scenarios should return `actual_trigger_reasons: []`
- cooldown scenario should show first-pass output and second-pass silence
- `ath_tvl` should explicitly show its limitation rather than claiming success

## 9. Local Log Expectations

Current reality:

- `seed alert-scenario` and `seed alert-scenarios` do not directly write files under `logs/alerts/`
- if you run those commands and no new local alert logs appear, that is expected with the current implementation

What should still be true when local logs are produced through runtime delivery paths:

- logs appear under `logs/alerts/`
- each file uses the normalized field order shown above
- `Action Required` is always present as the current placeholder block

## 10. Practical Caveats

- `docker compose config` expects `.env` to exist because the compose file uses `env_file`
- `total_value_secured` is the internal identifier to use in filters and docs
- `Detected` is rendered in UTC+8 and labeled `SGT`
- `ath_tvl` is a documented current limitation, not a passing ATH scenario
- the cooldown scenario uses a local SQLite datetime normalization patch so the real cooldown path can be exercised in tests
