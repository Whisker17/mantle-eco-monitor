# Docker VPS Deployment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Docker-based deployment path that runs the app and PostgreSQL on a VPS, keeps the database private to the compose network, and exposes the API externally on port `8000`.

**Architecture:** Add a repository-built app image, a small container entrypoint that waits for PostgreSQL and runs Alembic, and a two-service `docker-compose.yml` that starts `app` plus `db`. Keep HTTP API and scheduler in the same app container so runtime behavior stays aligned with the current FastAPI lifespan model.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, SQLAlchemy async engine, Alembic, PostgreSQL 16, Docker, Docker Compose, POSIX shell

---

### Task 1: Make environment examples Docker-aware

**Files:**
- Modify: `.env.example`

**Step 1: Confirm the current example does not document Docker Compose DB wiring**

Run: `rg -n "POSTGRES_DB|POSTGRES_USER|POSTGRES_PASSWORD|@db:5432" .env.example`
Expected: no matches, which confirms the compose-specific database wiring is still undocumented.

**Step 2: Add the minimal Docker-specific environment guidance**

Update `.env.example` to add:

- `POSTGRES_DB=mantle_monitor`
- `POSTGRES_USER=monitor`
- `POSTGRES_PASSWORD=password`
- a comment explaining that local non-Docker runs keep using `DATABASE_URL=...@localhost:5432/...`
- a comment explaining that Docker Compose will inject the container-internal `DATABASE_URL=...@db:5432/...`

Keep all existing app settings and feature flags unchanged.

Suggested shape:

```env
# --- Docker Compose Postgres ---
POSTGRES_DB=mantle_monitor
POSTGRES_USER=monitor
POSTGRES_PASSWORD=password

# --- Database ---
# Local Poetry/systemd example:
DATABASE_URL=postgresql+asyncpg://monitor:password@localhost:5432/mantle_monitor
# Docker Compose injects the app container DATABASE_URL with host "db".
```

**Step 3: Re-run the validation**

Run: `rg -n "POSTGRES_DB|POSTGRES_USER|POSTGRES_PASSWORD|@localhost:5432" .env.example`
Expected: PASS with matching lines for the new Docker guidance and the existing local database example.

**Step 4: Commit**

```bash
git add .env.example
git commit -m "docs: add docker compose env guidance"
```

### Task 2: Add the app container entrypoint

**Files:**
- Create: `docker/entrypoint.sh`

**Step 1: Verify the script is missing**

Run: `sh -n docker/entrypoint.sh`
Expected: FAIL because `docker/entrypoint.sh` does not exist yet.

**Step 2: Write the minimal entrypoint**

Create `docker/entrypoint.sh` with:

- `#!/usr/bin/env sh`
- `set -eu`
- an inline Python readiness loop that:
  - reads `DATABASE_URL`
  - creates an async SQLAlchemy engine
  - retries `SELECT 1` until PostgreSQL is reachable
  - exits non-zero after a bounded retry count
- `alembic upgrade head`
- `exec uvicorn src.main:create_app --factory --host 0.0.0.0 --port 8000`

Keep the script thin; do not move scheduler logic out of the app.

Suggested core structure:

```sh
#!/usr/bin/env sh
set -eu

python - <<'PY'
import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.environ["DATABASE_URL"]

async def main() -> None:
    engine = create_async_engine(DATABASE_URL)
    try:
        for attempt in range(30):
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                return
            except Exception:
                await asyncio.sleep(2)
        raise SystemExit("database did not become ready in time")
    finally:
        await engine.dispose()

asyncio.run(main())
PY

alembic upgrade head
exec uvicorn src.main:create_app --factory --host 0.0.0.0 --port 8000
```

Make the script executable.

**Step 3: Validate shell syntax**

Run: `sh -n docker/entrypoint.sh`
Expected: PASS

**Step 4: Commit**

```bash
git add docker/entrypoint.sh
git commit -m "feat: add docker app entrypoint"
```

### Task 3: Add the application image build

**Files:**
- Create: `Dockerfile`

**Step 1: Verify image build currently fails**

Run: `docker build -t mantle-eco-monitor:test .`
Expected: FAIL because `Dockerfile` does not exist yet.

**Step 2: Write the minimal Dockerfile**

Create `Dockerfile` using `python:3.12-slim` and:

- set `PYTHONDONTWRITEBYTECODE=1`
- set `PYTHONUNBUFFERED=1`
- set `WORKDIR /app`
- copy the repository into `/app`
- install the package with `pip install --no-cache-dir .`
- copy and use `docker/entrypoint.sh`

Suggested shape:

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

RUN chmod +x /app/docker/entrypoint.sh

ENTRYPOINT ["/app/docker/entrypoint.sh"]
```

Do not introduce Poetry into the runtime image.

**Step 3: Validate the image build**

Run: `docker build -t mantle-eco-monitor:test .`
Expected: PASS

**Step 4: Commit**

```bash
git add Dockerfile
git commit -m "feat: add docker image build"
```

### Task 4: Add Compose orchestration for app and PostgreSQL

**Files:**
- Create: `docker-compose.yml`

**Step 1: Verify compose config fails before the file exists**

Run: `docker compose config`
Expected: FAIL because `docker-compose.yml` does not exist yet.

**Step 2: Write the minimal compose topology**

Create `docker-compose.yml` with:

- `db` service:
  - `image: postgres:16-alpine`
  - environment from `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
  - named volume for `/var/lib/postgresql/data`
  - `healthcheck` using `pg_isready`
  - no `ports:` entry
- `app` service:
  - `build: .`
  - `env_file: .env`
  - `environment:` override for `DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}`
  - `ports: ["8000:8000"]`
  - `depends_on` with `db` health condition
  - `restart: unless-stopped`
- top-level named volume such as `pgdata`

Suggested core shape:

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-mantle_monitor}
      POSTGRES_USER: ${POSTGRES_USER:-monitor}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-password}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 5s
      retries: 12
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped

  app:
    build: .
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-monitor}:${POSTGRES_PASSWORD:-password}@db:5432/${POSTGRES_DB:-mantle_monitor}
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "8000:8000"
    restart: unless-stopped

volumes:
  pgdata:
```

**Step 3: Validate Compose parsing**

Run: `docker compose config`
Expected: PASS with resolved service definitions for `app` and `db`

**Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add docker compose deployment"
```

### Task 5: Document VPS deployment and verification

**Files:**
- Create: `docs/docker-vps-deployment.md`

**Step 1: Write the deployment guide**

Create a focused document that covers:

- required `.env` values for Docker deployment
- opening inbound TCP `8000` on the VPS
- `docker compose up -d --build`
- `docker compose ps`
- `docker compose logs app --tail=100`
- `curl http://127.0.0.1:8000/api/health`
- external `curl http://<vps-ip>:8000/api/health`
- initial data-loading commands:
  - `docker compose exec app python -m src.scheduler run source_health`
  - `docker compose exec app python -m src.scheduler run core_l2beat`
  - `docker compose exec app python -m src.scheduler run core_coingecko`
- `docker compose down`

Keep this doc separate from the currently untracked runbook files so the change stays isolated.

**Step 2: Validate the guide contains the required commands**

Run: `rg -n "docker compose up -d --build|docker compose logs app --tail=100|http://<vps-ip>:8000/api/health|docker compose exec app python -m src.scheduler run source_health" docs/docker-vps-deployment.md`
Expected: PASS with matches for each required deployment and verification command.

**Step 3: Run regression and deployment verification**

Run:

```bash
pytest tests/test_main.py tests/test_config/test_settings.py -q
docker compose build
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:8000/api/health
docker compose logs app --tail=100
docker compose down
```

Expected:

- pytest PASS
- compose build PASS
- `app` and `db` containers reach running/healthy state
- health endpoint returns JSON
- logs show Alembic upgrade followed by Uvicorn startup without traceback

**Step 4: Commit**

```bash
git add docs/docker-vps-deployment.md
git commit -m "docs: add docker vps deployment guide"
```
