# HANDOFF

## Project Snapshot

- Repository: `mantle-eco-monitor`
- Current branch in this worktree: `codex/status-handoff`
- Base for this worktree: `codex/phase1-runtime`
- Important reality:
  - `main` does **not** yet include the latest runtime collection pipeline
  - `codex/phase1-runtime` is the branch that currently reflects the best Phase 1 runtime state
- Most important runtime commit right now: `1fd1ec4 feat: wire phase1 runtime collection pipeline`

## Verified State

Fresh verification on `codex/status-handoff`:

- `pytest`
  - Result: `105 passed, 1 skipped`
- `RUN_LIVE_SOURCE_TESTS=1 pytest tests/test_ingestion/test_public_source_coverage_live.py -m live -v`
  - Result: `1 passed`

These results were obtained before writing this handoff file.

## What Is Done

- Public-source-first strategy is documented and implemented.
- Growthepie, DefiLlama, L2Beat, CoinGecko, and Dune collectors are aligned to the current source strategy.
- Runtime collection jobs are no longer placeholders.
- Scheduler jobs now call real collectors and persist:
  - `metric_snapshots`
  - `source_runs`
  - `alert_events`
- Dynamic watchlist refresh now pulls Mantle protocols instead of only seeding static entries.
- `/api/health` now checks DB, reports latest source runs, and exposes next scheduled run.
- A generic ecosystem protocol adapter exists so non-DEX protocols do not get forced through DEX volume endpoints.
- Scheduler lifespan shutdown has been fixed so APScheduler no longer throws the previous context cleanup error in the tested startup/shutdown path.

## Important Commits

- `0e479e0` docs: redefine mantle data sources around public endpoints
- `8c83690` feat: shift ingestion to public-first sources
- `541f3ba` fix: ignore legacy dune env keys
- `1fd1ec4` feat: wire phase1 runtime collection pipeline

## What Worked

- Using public sources first works for the majority of Phase 1 metrics.
- `api.growthepie.com` works; the old `.xyz` domain does not.
- L2Beat current useful endpoints:
  - `/api/scaling/tvs/mantle`
  - `/api/scaling/activity/mantle`
- DefiLlama current useful protocol endpoint is:
  - `/protocol/{slug}`
  - not `/api/protocol/{slug}`
- Treating DEX volume as optional for DEX-like protocols prevents a hard failure when DefiLlama has protocol TVL but no `summary/dexs/{slug}` entry.
- Ignoring legacy removed env keys in `Settings` is necessary because old local `.env` files may still contain removed Dune keys.
- Evaluating alerts only from the latest inserted snapshot per metric prevents a first-run historical import from generating a huge alert storm.

## What Did Not Work

- Assuming `stablecoincharts` returns integer timestamps:
  - real payload uses string timestamps
  - fixed in `src/ingestion/defillama.py`
- Treating Dune health as `status_code < 500`:
  - this incorrectly marks `401` and other bad auth states as healthy
  - fixed to require 2xx
- Forcing all non-Aave protocols through `DexAdapter`:
  - non-DEX protocols like Ondo or Beefy do not belong on DEX volume endpoints
  - fixed with `GenericAdapter`
- Using `Scheduler.start_in_background()` without explicit context management in app lifespan:
  - caused APScheduler `ContextVar` cleanup errors on shutdown
  - fixed by explicitly entering and exiting the scheduler context in `src/main.py`
- Refreshing watchlist from seed only:
  - that never exercises the intended dynamic protocol discovery
  - fixed in `src/api/routes/watchlist.py` and scheduler runtime

## What Was Tried

1. Public-source coverage investigation across DefiLlama, Growthepie, and L2Beat
   - worked
   - produced the current public-first strategy

2. Full local dry-run against a temporary SQLite database using real job functions
   - partially worked
   - exposed runtime-only issues not caught by unit tests:
     - DefiLlama stablecoin timestamp type mismatch
     - DEX volume endpoint failures for pseudo-DEX entries
     - first-run alert overproduction

3. Lifespan startup/shutdown test using `TestClient(create_app())`
   - worked as a bug finder
   - exposed the APScheduler shutdown problem

4. Full multi-job dry-run with a 60-second wrapper per job
   - showed that `eco_aave` / `eco_protocols` can be slow in a local dev network environment
   - this did not prove a code bug by itself, but it is an operational risk to watch in deployment

## Known Remaining Risks

- `eco_aave` and especially `eco_protocols` make many public HTTP calls. On a slow or unstable network, first-run execution can be slow.
- Dune remains expected-failed unless you configure:
  - `DUNE_API_KEY`
  - `DUNE_STABLECOIN_VOLUME_QUERY_ID`
- Public APIs may transiently fail or rate limit. The system now records this in `source_runs`, but it does not yet implement sophisticated retries/fallback routing.
- Dynamic watchlist categorization comes from current protocol metadata. Some protocols may still be imperfectly classified by category, even though runtime now tolerates missing DEX volume better.

## Current Deployment Readiness

Branch `codex/phase1-runtime` is the branch I would currently treat as deployable for Phase 1, with these caveats:

- You must have a real database.
- You must run migrations first.
- You should expect Dune to show `failed` in health until configured.
- You should observe the first scheduler cycles after deployment rather than assuming public APIs will all behave the same as local tests.

## Deployment Prereqs

- Set `DATABASE_URL`
- Run `alembic upgrade head`
- Optionally set `COINGECKO_API_KEY`
- Optionally set Dune credentials if you want `stablecoin_transfer_volume`
- Start the service, for example:
  - `uvicorn src.main:create_app --factory --host 0.0.0.0 --port 8000`

## First Checks After Deploy

1. `GET /api/health`
2. `GET /api/health/sources`
3. Confirm `watchlist_protocols` has rows
4. Confirm `metric_snapshots` is increasing after scheduler cycles
5. Confirm `source_runs` reflects expected success/failure patterns

## Important Files

- Runtime orchestration:
  - `src/scheduler/runtime.py`
  - `src/scheduler/jobs.py`
- App startup/shutdown:
  - `src/main.py`
- Health/readiness:
  - `src/api/routes/health.py`
- Dynamic watchlist:
  - `src/api/routes/watchlist.py`
  - `src/protocols/watchlist.py`
- Ecosystem adapter routing:
  - `src/protocols/registry.py`
  - `src/protocols/generic.py`
  - `src/protocols/dex.py`
  - `src/protocols/aave.py`
- Public-source strategy docs:
  - `specs/DESIGN.md`
  - `docs/plans/2026-03-14-public-source-first-design.md`
  - `docs/plans/2026-03-14-public-source-first-implementation.md`
- New project management docs:
  - `docs/project-status.md`
  - `HANDOFF.md`

## Recommended Next Steps

1. Merge `codex/phase1-runtime` into `main`.
2. If desired, merge `codex/status-handoff` after that or fold these docs into the runtime branch.
3. Deploy to a server with PostgreSQL and migrations applied.
4. Watch the first full scheduler cycle through `/api/health/sources`.
5. If ecosystem jobs are too slow in production, reduce watchlist breadth or split `eco_protocols` into smaller jobs.
