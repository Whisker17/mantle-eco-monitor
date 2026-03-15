# Dev Live Check Script Design

> Design for a local shell script that starts the service in `dev_live` mode and verifies end-to-end availability with existing health and scheduler interfaces.

**Goal:** Add a single local shell entry point that can boot the app in `dev_live`, run the most useful diagnostics, and report whether the service is actually usable.

**Status:** Approved in discussion on 2026-03-15.

---

## Context

The service now supports scheduler profiles through `config/scheduler.toml`. In `dev_live`, only a small subset of jobs run automatically:

- `source_health` every 2 minutes
- `core_coingecko` every 5 minutes
- `core_l2beat` every 15 minutes

The rest of the data jobs are `manual`. That makes development faster, but it also means the operator needs a convenient way to:

- boot the service with the right profile
- confirm the app and database are reachable
- trigger the useful manual checks immediately
- inspect whether critical metrics are actually being written

The project already has the right runtime surfaces:

- `GET /api/health`
- `GET /api/health/sources`
- `GET /api/metrics/latest`
- `python -m src.scheduler run <job_id>`

The missing piece is a single local workflow wrapper.

## Problem

Starting the service in `dev_live` currently requires multiple manual steps and ad-hoc shell commands. This slows down local testing and makes it harder to tell whether a failure is caused by:

- the web process not starting
- database connectivity
- source-health failures
- missing snapshot inserts
- or just forgetting to run a manual job

## Goals

- Provide one shell script for local `dev_live` bring-up and verification.
- Reuse existing API and scheduler CLI, not a parallel debug path.
- Make failure reasons visible through distinct exit codes.
- Avoid killing unrelated local processes.
- Keep the script testable with lightweight command overrides.

## Non-Goals

- Replacing process managers like Docker Compose, systemd, or supervisord.
- Creating a production health checker.
- Adding a new FastAPI diagnostics endpoint.
- Running migrations automatically.

## Recommended Interface

Create `scripts/dev_live_check.sh` with four subcommands:

- `up`
- `check`
- `full`
- `down`

Default environment:

- `SCHEDULER_PROFILE=dev_live`
- `APP_HOST=127.0.0.1`
- `APP_PORT=8000`
- `WAIT_SECONDS=30`
- `TMP_DIR=.tmp`

Artifacts written by the script:

- PID file: `.tmp/dev_live.pid`
- Log file: `.tmp/dev_live.log`

This requires `.tmp/` to be ignored in git.

## Command Semantics

### `up`

Purpose: start the app in the background with the right profile.

Behavior:

- require `DATABASE_URL` to be present
- fail if the target port is already occupied
- create `.tmp/` if needed
- start `uvicorn src.main:create_app --factory --host "$APP_HOST" --port "$APP_PORT"`
- force `SCHEDULER_PROFILE=dev_live` unless explicitly overridden
- write PID and append logs

### `check`

Purpose: inspect current availability without starting the app.

Behavior:

1. call `GET /api/health`
2. fail fast if the app is unreachable
3. run `python -m src.scheduler run source_health`
4. run `python -m src.scheduler run core_coingecko`
5. run `python -m src.scheduler run core_l2beat`
6. call `GET /api/health/sources`
7. call:
   - `/api/metrics/latest?entity=mantle&metric_name=mnt_volume`
   - `/api/metrics/latest?entity=mantle&metric_name=total_value_secured`
8. print a compact summary

### `full`

Purpose: run the full local workflow.

Behavior:

- call `up`
- poll `/api/health` until ready or timeout
- call `check`

### `down`

Purpose: stop only the process started by this script.

Behavior:

- read `.tmp/dev_live.pid`
- if the PID exists and is alive, send `TERM`
- remove the PID file
- never use broad process-name matching

## Exit Codes

- `0`: service reachable, checks completed, and key data paths produced results
- `1`: local prerequisites missing, such as `DATABASE_URL` or required binaries
- `2`: app unreachable or startup did not become ready before timeout
- `3`: manual scheduler job failed
- `4`: app reachable but key metric data was still missing after checks

## Reused Surfaces

The script should not inspect the database directly. It should rely on:

- `/api/health` for app, DB, and next scheduled run
- `/api/health/sources` for recent source execution outcomes
- `/api/metrics/latest` for proof that the data path produced snapshots
- `python -m src.scheduler run <job_id>` for manual job dispatch

This keeps the script aligned with the actual runtime surfaces users already have.

## Output Shape

The script output should stay human-readable and compact.

Suggested sections:

- `Preflight`
- `Startup`
- `Health`
- `Source Jobs`
- `Metric Checks`
- `Summary`

Example summary lines:

- `service=up`
- `db=connected`
- `health=healthy`
- `next_run=2026-03-15T14:02:00+08:00`
- `source_health=success`
- `coingecko=success`
- `l2beat=success`
- `mnt_volume=present`
- `total_value_secured=present`

## Testability

Shell scripts are harder to test if every command is hard-coded. The implementation should allow lightweight overrides through environment variables:

- `CURL_BIN`
- `PYTHON_BIN`
- `UVICORN_BIN`
- `TMP_DIR`
- `APP_HOST`
- `APP_PORT`

This makes it possible to test the script with fake command shims and temporary directories.

## Error Handling

- If `DATABASE_URL` is unset, print a single clear message and exit `1`.
- If the port is already bound, print a single clear message and exit `1`.
- If `/api/health` never becomes reachable in `full`, exit `2`.
- If `run source_health`, `run core_coingecko`, or `run core_l2beat` fails, exit `3`.
- If health is reachable but the expected metrics are absent, exit `4`.

The script should not silently retry failed manual jobs more than once. It is a diagnostic tool, not a supervisor.

## Testing Strategy

Use pytest-driven subprocess tests for the script, with command overrides rather than real network or long-running uvicorn processes.

Coverage should include:

- `up` rejects missing `DATABASE_URL`
- `check` fails when the app is unreachable
- `down` only removes the tracked PID
- `list`-style summary behavior through mocked HTTP payloads and scheduler command outputs
- success path that marks both target metrics as present

The final manual smoke test should still run the real script against a local service instance.

## Trade-Offs

### Chosen

One script with subcommands:

- keeps the workflow discoverable
- matches how local operators think
- avoids scattering dev procedures across docs and shell history

### Rejected

Two separate scripts:

- clearer separation but worse ergonomics

Python doctor command only:

- integrates more tightly with the app
- but is slower to iterate on and less natural for local shell workflows

