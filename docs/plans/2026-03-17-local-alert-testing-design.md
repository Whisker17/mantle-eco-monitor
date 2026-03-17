# Local Alert Testing Design

**Date:** 2026-03-17
**Status:** Approved in discussion on 2026-03-17, then cross-checked against `specs/alert-rules-spec.md`.

## Goal

Add a local-only alert testing path that:

- runs in Docker without historical bootstrap or Lark delivery
- preserves the real alert generation pipeline
- writes deterministic alert outputs to local log files for manual review
- provides repeatable manual data-insertion scenarios that cover the implemented alert rules
- documents the current alert rules, trigger conditions, expected outputs, and local validation flow

## Constraints

- Do not modify `main`; work must happen on an isolated branch/worktree.
- Do not backfill historical production data.
- Do not call Lark during this test flow.
- Keep the existing alert formatting contract:
  - `Metric`
  - `Movement`
  - `Current Value`
  - `Status`
  - `Source`
  - `Detected`
  - `Suggested Draft Copy`
  - `Action Required`
- Local testing must work with `docker compose`.

## Existing Code Reality

- Alerts are produced by the real rule engine from `MetricSnapshot` rows, not by the notification layer.
- `NotificationService` is the final delivery hop and is currently Lark-oriented.
- The repository already has a narrow manual alert seed path: `python -m src.admin seed alert-spike`.
- Current implemented alert classes are:
  - threshold
  - decline
  - ATH
  - milestone
  - multi-signal
  - cooldown suppression
  - token-level stablecoin suppression
  - 7D / MTD coverage suppression

## Design Decision

Use the existing alert generation pipeline unchanged and add a second delivery sink for local file output.

This keeps the behavior under test close to production:

1. manual scenario inserts snapshots
2. `RuleEngine` evaluates the latest snapshots
3. `AlertEvent` rows are persisted
4. `NotificationService` renders the same alert payload shape already used for Lark cards
5. instead of sending to Lark, the local sink writes deterministic log files under `logs/`

This avoids building a fake notification path that could drift away from real alert behavior.

## Local Output Architecture

### Settings

Add local alert output settings:

- `alert_local_output_enabled: bool = False`
- `alert_local_output_dir: str = "logs/alerts"`

The local test profile will use:

- `lark_delivery_enabled = false`
- `alert_local_output_enabled = true`

### Notification Flow

Extend `NotificationService.deliver_alerts()` so alert delivery can fan out to:

- existing Lark sink when enabled
- new local file sink when enabled

The local sink should:

- serialize the same alert payload fields used by the alert card formatter
- reuse the current content semantics so local review matches the expected Lark content contract
- write one file per alert

### File Layout

- directory: `logs/alerts/`
- file naming: timestamp + entity + metric + trigger reason
- example:
  - `logs/alerts/20260317T101500Z_mantle_tvl_threshold_25pct_7d.log`

Each file contains the approved field order:

```text
Metric: ...
Movement: ...
Current Value: ...
Status: ...
Source: ...
Detected: ...
Suggested Draft Copy: ...
Action Required: ...
```

### Docker Integration

Update `docker-compose.yml` so the app container binds the repository `logs/` directory into the container. This keeps generated files visible on the host during local testing.

Add `logs/` to `.gitignore`.

## Scenario Design

Replace the single-purpose alert spike seed with a deterministic scenario runner.

### Command Shape

Support:

- single scenario:
  - `python -m src.admin seed alert-scenario <scenario_name>`
- batch run:
  - `python -m src.admin seed alert-scenarios --all`
  - `python -m src.admin seed alert-scenarios --only threshold_up_7d_tvl,ath_tvl`

Each run returns JSON including:

- scenario name
- snapshots inserted
- alerts created
- expected alert reasons
- actual alert reasons
- written log files

### Determinism Rules

- Use fixed timestamps per scenario.
- Use scenario-specific entity names to avoid interfering with cooldown state.
- Insert complete snapshot sets required by the relevant window logic.
- Keep negative-control scenarios that write snapshots but intentionally produce no alerts.

### Planned Scenario Matrix

Positive scenarios:

- `threshold_up_7d_tvl`
- `decline_7d_dau`
- `threshold_mtd_active_addresses`
- `ath_tvl`
- `milestone_tvl_1b`
- `multi_signal_core`
- `cooldown_repeat_block`

Negative scenarios:

- `no_alert_low_coverage_7d`
- `no_alert_sparse_mtd`

## Documentation Deliverables

### 1. Design Record

Create:

- `docs/plans/2026-03-17-local-alert-testing-design.md`

Purpose:

- capture the architecture choice
- record the scenario strategy
- record the local sink decision

### 2. Operator-Facing Alert Test Spec

Create:

- `docs/alert-local-testing.md`

Contents:

- purpose and scope
- local Docker workflow
- local alert output format
- implemented alert rule explanations
- scenario-by-scenario trigger instructions
- expected outputs and non-outputs
- validation steps
- known boundaries

## Rule Documentation Scope

The operator-facing document should describe the implemented rules in code terms, not aspirational product terms.

It must cover:

- threshold alerts
- decline alerts
- ATH alerts
- milestone alerts
- multi-signal alerts
- cooldown behavior
- 7D / MTD coverage suppression
- token-level stablecoin suppression

Each rule section should include:

- trigger condition
- required history shape
- expected `trigger_reason`
- expected `Status`
- expected log characteristics
- cases that should not emit alerts

## Cross-Check Against `specs/alert-rules-spec.md`

The external spec is directionally aligned with this design, but the implementation and documentation must stay grounded in current code reality.

### Accepted from the spec

- deterministic, auditable local alert testing
- the five primary alert classes
- 7D and MTD as the active threshold/decline windows
- cooldown and multi-signal suppression coverage
- the approved card/log field order and status semantics
- local documentation that explains exactly when alerts do and do not trigger

### Corrections required while implementing

1. Use the current internal metric identifier `total_value_secured`, not `tvs`, when documenting rules and scenarios.
2. Do not claim severity-based feed routing that the current code does not implement. The local test sink should reflect what the system actually generates.
3. Document time display using the current formatter behavior: UTC+8 output labeled as `SGT`, because that is the existing content contract under test.
4. Treat multi-signal `Current Value` as an implementation detail, because the current code uses the first grouped alert's value.

## Non-Goals

- changing rule thresholds
- changing alert rule semantics
- rebuilding historical production data
- shipping real AI draft copy generation
- changing daily summary behavior
- removing the existing Lark delivery path

## Validation

Implementation is complete only when:

- local Docker startup works with the new log directory mount
- local alert output files are written when scenarios trigger alerts
- no output files are written for negative-control scenarios
- scenario summaries match expected alert reasons
- the operator-facing rule document matches current code behavior
