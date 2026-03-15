# Project Status

Last updated: 2026-03-15

## Overview

- Current product stage: Phase 1 runtime implementation is functionally complete.
- Current integration status:
  - `main` includes the runtime collection pipeline, scheduler profiles, stablecoin transfer breakdown snapshots, manual scheduler dispatch, and local `dev_live` smoke-check tooling.
  - `main` is currently the only local branch; there is no outstanding feature branch waiting to be merged.
  - Local development can validate source reachability and key metric ingestion with `./scripts/dev_live_check.sh`.
  - Production deployment and production observation are still pending.
- Most important current objective: deploy against PostgreSQL and validate the first real scheduler cycles.

## Current Implementation

- FastAPI service bootstraps with profile-aware scheduler startup and shutdown.
- Runtime jobs collect from DefiLlama, Growthepie, L2Beat, CoinGecko, and Dune, then persist:
  - `metric_snapshots`
  - `source_runs`
  - `alert_events`
- Scheduler supports environment profiles:
  - `prod`
  - `dev_live`
  - `ci`
- Manual local job dispatch is available through:
  - `python -m src.scheduler list`
  - `python -m src.scheduler run <job_id>`
- Local `dev_live` verification is available through:
  - `./scripts/dev_live_check.sh up`
  - `./scripts/dev_live_check.sh check`
  - `./scripts/dev_live_check.sh full`
  - `./scripts/dev_live_check.sh down`
- Health and readiness surfaces currently available:
  - `GET /api/health`
  - `GET /api/health/sources`
  - `GET /api/metrics/latest`
- Dynamic watchlist refresh and ecosystem protocol routing are implemented.

## Phase 1

### Milestones

- [x] Core backend service boots and exposes internal review APIs.
- [x] Database schema, repositories, and rule engine are implemented.
- [x] Public-source-first data strategy replaced the original Dune-first assumption.
- [x] Core public collectors are aligned to current public endpoints.
- [x] Live public-source coverage test exists and passes when explicitly enabled.
- [x] Runtime collection pipeline writes `metric_snapshots`, `source_runs`, and `alert_events`.
- [x] Scheduler jobs are wired to real collection functions instead of placeholder logs.
- [x] Dynamic watchlist refresh fetches Mantle protocols and persists the watchlist.
- [x] Ecosystem protocol collection distinguishes Aave, DEX, and non-DEX protocols.
- [x] `/api/health` reports DB connectivity, source status, and next scheduled run.
- [x] Scheduler supports `prod`, `dev_live`, and `ci` profiles.
- [x] Local manual scheduler dispatch exists for targeted job execution.
- [x] Scheduler shutdown no longer throws the APScheduler context cleanup error in lifespan tests.
- [x] Full automated test suite passes on `main` (`141 passed, 2 skipped` in the latest local verification).
- [x] Local `dev_live` smoke check script exists for startup and availability verification.
- [x] Runtime work merged back to `main`.
- [ ] Production deployment completed on server.
- [ ] Production migrations run against the deployment database.
- [ ] First production scheduler cycle observed and validated.

### Todo

- [ ] Provision PostgreSQL for deployment.
- [ ] Run `alembic upgrade head` in the deployment environment.
- [ ] Set `DATABASE_URL` in deployment.
- [ ] Decide whether to enable Dune-backed `stablecoin_transfer_volume`.
- [ ] If enabling Dune, set `DUNE_API_KEY` and `DUNE_STABLECOIN_VOLUME_QUERY_ID`.
- [ ] Start the service and confirm `/api/health` returns `healthy` or expected `degraded`.
- [ ] Observe `/api/health/sources` after the first scheduler runs.
- [ ] Verify the first watchlist refresh and first persisted snapshots in production.
- [ ] Run `./scripts/dev_live_check.sh full` when validating local `dev_live` behavior.

### Risks

- [ ] `eco_aave` and `eco_protocols` depend on many public upstream calls and may be slow on first run.
- [ ] Without Dune configuration, source health will report Dune as failed, which is expected.
- [ ] The local `dev_live` script validates app health and selected key metrics, but it is not a substitute for production validation on PostgreSQL.
- [ ] Public APIs can rate limit or transiently fail; `source_runs` is the operational truth for these events.

## Phase 2

### Milestones

- [ ] AI enrichment layer added for alert explanation and packaging.
- [ ] Draft social copy generation implemented.
- [ ] Better alert grouping / narrative bundling implemented.
- [ ] Lark delivery design finalized.

### Todo

- [ ] Define the exact AI enrichment prompt contract.
- [ ] Decide whether to enrich all alerts or only high-signal alerts.
- [ ] Add storage for AI outputs if persistence is required.
- [ ] Prototype Lark delivery payload format.

## Phase 3

### Milestones

- [ ] Automatic fallback routing between sources implemented.
- [ ] Source-specific stale/failure recovery rules implemented.
- [ ] Higher-level operational observability and dashboards implemented.
- [ ] More advanced ecosystem ranking and protocol-specific alerting added.

### Todo

- [ ] Design fallback policy by metric.
- [ ] Add automated stale-source suppression and operator alerts.
- [ ] Revisit methodology reconciliation for TVL / TVS / ecosystem TVL differences.
- [ ] Reassess whether more paid sources are justified.
