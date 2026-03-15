# Docker VPS Deployment Design

> Design for running the Mantle Eco Monitor on a VPS with Docker Compose, a bundled PostgreSQL container, and direct external access over port `8000`.

**Goal:** Add a simple, repeatable Docker-based deployment path so the full service can run on a VPS and be called externally via `http://<vps-ip>:8000`.

**Status:** Approved in discussion on 2026-03-15.

---

## Context

The current application already supports production-style runtime behavior:

- [src/main.py](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/src/main.py) starts a FastAPI app and bootstraps the in-process scheduler inside the application lifespan.
- [config/settings.py](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/config/settings.py) already defaults to `HOST=0.0.0.0` and `PORT=8000`.
- [docs/vps-deployment-and-lark-e2e-guide.md](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/docs/vps-deployment-and-lark-e2e-guide.md) documents a manual Poetry-based VPS deployment flow.
- [specs/DESIGN.md](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/specs/DESIGN.md) already calls out Docker Compose as the intended containerization target.

What is missing is the actual containerization layer: image build instructions, compose orchestration, database boot ordering, and an external-call-ready deployment path for a VPS.

## Problem

The service can currently be started manually with Poetry and `uvicorn`, but that creates several deployment gaps:

- no checked-in container image definition
- no checked-in compose topology for app plus PostgreSQL
- no automatic migration step during container startup
- no single-command deployment path for a VPS
- no repository-level Docker deployment guide for external callers

## Goals

- Run the full service stack on a VPS with `docker compose`.
- Include PostgreSQL in the same compose project.
- Keep API and scheduler in the same application container.
- Expose the service externally on port `8000`.
- Keep the database private to the compose network.
- Ensure application startup waits for PostgreSQL and runs Alembic migrations before serving traffic.
- Document the exact VPS deployment and verification steps.

## Non-Goals

- Adding Nginx, Traefik, or HTTPS termination in this change.
- Splitting scheduler into a separate container.
- Supporting multiple deployment topologies in the first Dockerized version.
- Exposing PostgreSQL on a public host port.
- Reworking application runtime behavior beyond what Docker startup requires.

## Approaches Considered

### Recommended: `app + db` in one Compose project

Use a single `docker-compose.yml` with:

- `db`: `postgres:16-alpine` with a persistent named volume
- `app`: repository-built image that waits for DB, runs `alembic upgrade head`, then starts Uvicorn

Why this is recommended:

- smallest change from the current runtime architecture
- one deployment command for the whole stack
- lowest operational complexity for the requested VPS setup

Trade-off:

- the application container runs migrations on every startup, which is acceptable here because Alembic upgrades are idempotent at steady state

### Rejected: separate one-shot migration service

This separates concerns more cleanly, but it adds extra deployment steps and is not necessary for the initial VPS target.

### Rejected: split API and scheduler into separate services

This is a better long-term scale-out shape, but current application startup intentionally couples them. Splitting now would increase code changes and deployment complexity without helping the immediate requirement.

## Recommended Architecture

Add three deployment assets:

- [Dockerfile](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/Dockerfile)
- [docker-compose.yml](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/docker-compose.yml)
- [docker/entrypoint.sh](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/docker/entrypoint.sh)

Runtime flow:

1. `docker compose up -d --build` starts `db` and `app`
2. PostgreSQL initializes using a named volume
3. the `app` entrypoint waits for `db:5432` to accept connections
4. the `app` entrypoint runs `alembic upgrade head`
5. the `app` entrypoint launches `uvicorn src.main:create_app --factory --host 0.0.0.0 --port 8000`
6. FastAPI starts, then the in-process scheduler starts during lifespan if enabled

This preserves the current behavior where one application process serves HTTP traffic and owns scheduler execution.

## Compose Topology

### `db`

- image: `postgres:16-alpine`
- persistent volume mounted at `/var/lib/postgresql/data`
- environment:
  - `POSTGRES_DB=mantle_monitor`
  - `POSTGRES_USER=monitor`
  - `POSTGRES_PASSWORD=<from env>`
- healthcheck enabled
- no host port published

### `app`

- built from the repository root
- loads runtime settings from `.env`
- publishes `8000:8000`
- depends on `db`
- restart policy: `unless-stopped`

## Environment Model

The root `.env` remains the single configuration entry point for both local and VPS Docker deployments.

In Docker mode the important change is the database host:

```env
DATABASE_URL=postgresql+asyncpg://monitor:<password>@db:5432/mantle_monitor
```

Other settings remain unchanged, including:

- `HOST=0.0.0.0`
- `PORT=8000`
- `SCHEDULER_ENABLED=true`
- `SCHEDULER_PROFILE=prod`

`.env.example` should explicitly document the compose-network database hostname so deployment users do not leave `localhost` in place by mistake.

## External Access And Security Boundary

The intended external call path is:

```text
client -> http://<vps-ip>:8000 -> app container
```

Boundary rules:

- expose host port `8000` for API traffic
- do not expose PostgreSQL on host port `5432`
- allow only Docker-internal access from `app` to `db`
- document that the VPS firewall or security group must allow inbound TCP `8000`

This is intentionally HTTP-only for the first version. HTTPS and reverse proxying can be layered later without changing the application container contract.

## Error Handling

- If PostgreSQL is not ready, the entrypoint keeps retrying instead of starting Uvicorn prematurely.
- If Alembic migration fails, the `app` container exits non-zero so deployment does not look healthy by accident.
- If the application process fails after startup, Docker restart policy brings it back.
- If external requests fail, the first diagnostics should be:
  - `docker compose ps`
  - `docker compose logs app --tail=100`
  - VPS firewall and security-group inspection for port `8000`

## Testing And Verification Strategy

Keep verification focused on configuration and deployment behavior rather than adding heavy Docker-specific unit tests.

### Repository-side validation

- `docker compose config`
- shell syntax validation for `docker/entrypoint.sh`
- existing Python tests that cover application lifespan behavior, especially [tests/test_main.py](/Users/whisker/Work/src/Whisker17/mantle-eco-monitor/tests/test_main.py)

### Runtime validation on the VPS

1. `docker compose up -d --build`
2. `docker compose ps`
3. `docker compose logs app --tail=100`
4. `curl http://127.0.0.1:8000/api/health`
5. external `curl http://<vps-ip>:8000/api/health`

### Initial data validation

After the stack is up, manually run a few key jobs so the service has usable data:

- `docker compose exec app python -m src.scheduler run source_health`
- `docker compose exec app python -m src.scheduler run core_l2beat`
- `docker compose exec app python -m src.scheduler run core_coingecko`

## Rollout

1. Add Docker image build and entrypoint assets.
2. Add compose orchestration for `app` and `db`.
3. Update `.env.example` for Docker/VPS usage.
4. Update runbook-style documentation with deployment and troubleshooting commands.
5. Verify config parsing and deployment commands locally.
6. Deploy to VPS and verify external access on port `8000`.
