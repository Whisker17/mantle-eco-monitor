# Scheduler Profiles Design

> Design for making scheduler behavior environment-aware while keeping production aligned with upstream data freshness and keeping local testing fast.

**Goal:** Replace the hard-coded schedule table with a TOML-driven profile system so production can poll at a low frequency while development and CI can use alternate behavior.

**Status:** Approved in discussion on 2026-03-15.

---

## Context

The current scheduler is hard-coded in [src/scheduler/jobs.py](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/src/scheduler/jobs.py). Most configured sources currently expose data at daily granularity:

- DefiLlama chain TVL and stablecoin series are daily buckets.
- Growthepie fundamentals are effectively daily and can lag by a day.
- The configured Dune query returns `day`-bucketed results.
- L2Beat and CoinGecko can refresh more frequently, but the application currently stores snapshots with same-day deduplication in [src/db/repositories.py](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/src/db/repositories.py).

This means the existing 4-hour and 6-hour polling cadence creates many `source_runs` without producing additional `metric_snapshots`.

## Problem

We need two different scheduler behaviors:

- Production should poll in a way that matches upstream freshness and the current snapshot model.
- Local testing and QA should not have to wait half a day to exercise scheduler code paths.

The solution should avoid introducing a second configuration system for runtime code and should let us turn individual jobs on, off, or manual per environment.

## Goals

- Move scheduler cadence out of Python constants and into TOML.
- Support multiple scheduler profiles selected by configuration.
- Keep production polling conservative and aligned with daily-style data.
- Keep testing fast without changing the semantics of snapshot storage.
- Allow selected jobs to be `manual` so developers can trigger them on demand.

## Non-Goals

- Changing snapshot deduplication semantics.
- Rewriting alert rules for intraday signal handling.
- Adding a full external scheduler service.

## Recommended Approach

Use a single `config/scheduler.toml` file with named profiles. The active profile is selected via settings.

Each job definition declares:

- a scheduling mode: `cron`, `interval`, `manual`, or `disabled`
- the trigger parameters for that mode
- optional per-profile timezone override

The scheduler builder will:

1. load the active profile
2. map known job ids to existing callables
3. build APScheduler triggers dynamically
4. skip registration for `manual` or `disabled` jobs

This keeps the runtime logic simple and makes behavior observable in one place.

## Profiles

### `prod`

Production keeps the current data model and reduces load:

- daily-ish sources run twice per day for freshness plus retry tolerance
- `source_health` remains hourly
- `watchlist_refresh` remains daily

Recommended cadence:

- `core_defillama`: 10:00, 18:00 Asia/Shanghai
- `core_growthepie`: 10:10, 18:10
- `core_l2beat`: 10:20, 18:20
- `core_dune`: 10:30, 18:30
- `core_coingecko`: 10:40, 18:40
- `eco_aave`: 10:50, 18:50
- `eco_protocols`: 11:00, 19:00
- `watchlist_refresh`: 04:00
- `source_health`: hourly at minute 45

### `dev_live`

Development keeps fast feedback without pretending daily sources are realtime:

- `source_health` runs every few minutes
- `core_coingecko` and `core_l2beat` run on short intervals
- daily sources default to `manual`
- developers trigger specific jobs directly when validating ingestion changes

Recommended behavior:

- `source_health`: every 2 minutes
- `core_coingecko`: every 5 minutes
- `core_l2beat`: every 15 minutes
- `core_defillama`: manual
- `core_growthepie`: manual
- `core_dune`: manual
- `eco_aave`: manual
- `eco_protocols`: manual
- `watchlist_refresh`: manual

### `ci`

CI disables the background scheduler entirely. Tests continue to call job functions directly.

This keeps tests deterministic and avoids time-based flakiness.

## Manual Execution

Testing daily sources should rely on explicit execution, not high-frequency polling. The system should expose a small local entry point that runs a known job id immediately using the same callable registry as the scheduler.

This can be:

- a CLI command such as `python -m src.scheduler.jobs run core_defillama`
- or a small helper function used by tests and local scripts

An HTTP endpoint is not required for the first version.

## Data Flow

The runtime flow stays the same:

1. scheduler or manual trigger selects a job
2. job collects records
3. records attempt to insert into `metric_snapshots`
4. rule engine evaluates only inserted snapshots
5. `source_runs` always records execution outcome

Only job registration changes.

## Configuration Shape

Recommended TOML structure:

```toml
active_profile = "prod"

[profiles.prod]
timezone = "Asia/Shanghai"

[profiles.prod.jobs.core_defillama]
mode = "cron"
hour = "10,18"
minute = 0

[profiles.dev_live]
timezone = "Asia/Shanghai"

[profiles.dev_live.jobs.core_defillama]
mode = "manual"

[profiles.dev_live.jobs.core_coingecko]
mode = "interval"
minutes = 5

[profiles.ci]
scheduler_enabled = false
```

Rules:

- `active_profile` in TOML can be overridden by settings.
- `scheduler_enabled = false` at either settings or profile level short-circuits scheduler startup.
- Unknown job ids fail fast during scheduler construction.

## Error Handling

- Invalid profile name should raise a startup error with the missing profile name.
- Invalid job mode should raise a startup error with the job id and mode.
- Invalid trigger fields should raise a startup error before FastAPI fully starts.
- Manual job execution should reject unknown or non-runnable job ids with a clear error.

## Testing Strategy

Add focused tests for:

- TOML profile loading and override precedence
- dynamic trigger construction for cron and interval jobs
- scheduler registration skipping `manual` and `disabled` jobs
- `lifespan()` honoring profile-disabled scheduling
- manual execution dispatch for a known job id

Existing runtime and ingestion tests stay mostly unchanged because job functions themselves are not being rewritten.

## Trade-Offs

### Chosen

Single TOML file with profiles:

- keeps config discoverable
- avoids hard-coded production logic in Python
- supports future staging profiles cleanly

### Rejected

Faster test-only cron profile without manual mode:

- still wastes requests for daily sources
- does not improve validation of same-day deduplicated metrics

Separate scheduler files per environment:

- easier to drift
- more files to keep aligned

## Rollout

1. Add TOML loader and profile selection.
2. Preserve current behavior behind an initial compatibility profile if needed.
3. Switch the default profile to `prod`.
4. Document `dev_live` and `ci` usage in `.env.example` and project docs.

