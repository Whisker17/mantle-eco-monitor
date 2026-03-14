# Project Status

Last updated: 2026-03-14

## Overview

- Current product stage: Phase 1 implementation is functionally complete on the working branch.
- Current integration status:
  - `main` is behind the latest runtime work.
  - `codex/phase1-runtime` contains the runtime collection pipeline and readiness upgrades.
  - `codex/status-handoff` adds project-management docs on top of `codex/phase1-runtime`.
- Most important current objective: merge the runtime branch and deploy with a real database.

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
- [x] Scheduler shutdown no longer throws the APScheduler context cleanup error in lifespan tests.
- [x] Full automated test suite passes on the runtime branch.
- [ ] Runtime branch merged back to `main`.
- [ ] Production deployment completed on server.
- [ ] Production migrations run against the deployment database.
- [ ] First production scheduler cycle observed and validated.

### Todo

- [ ] Merge `codex/phase1-runtime` into `main`.
- [ ] Provision PostgreSQL for deployment.
- [ ] Run `alembic upgrade head` in the deployment environment.
- [ ] Set `DATABASE_URL` in deployment.
- [ ] Decide whether to enable Dune-backed `stablecoin_transfer_volume`.
- [ ] If enabling Dune, set `DUNE_API_KEY` and `DUNE_STABLECOIN_VOLUME_QUERY_ID`.
- [ ] Start the service and confirm `/api/health` returns `healthy` or expected `degraded`.
- [ ] Observe `/api/health/sources` after the first scheduler runs.
- [ ] Verify the first watchlist refresh and first persisted snapshots in production.

### Risks

- [ ] `eco_aave` and `eco_protocols` depend on many public upstream calls and may be slow on first run.
- [ ] Without Dune configuration, source health will report Dune as failed, which is expected.
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
