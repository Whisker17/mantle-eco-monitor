# Docker VPS Deployment

This guide starts the Mantle Eco Monitor on a VPS with Docker Compose and exposes the API directly on port `8000`.

## 1. Prepare `.env`

Copy the example and fill in real values:

```bash
cp .env.example .env
```

Required points for Docker deployment:

- set `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`
- keep `HOST=0.0.0.0`
- keep `PORT=8000`
- set your Lark and LLM values if you need those features

You do not need to set `DATABASE_URL` to the Docker host manually. `docker compose` injects the app container database URL with host `db`.

## 2. Open The VPS Port

Allow inbound TCP `8000` in the VPS firewall or cloud security group.

Do not expose PostgreSQL port `5432` publicly.

## 3. Start The Stack

Build and start both services:

```bash
docker compose up -d --build
```

Check container state:

```bash
docker compose ps
```

Check recent app logs:

```bash
docker compose logs app --tail=100
```

Expected app startup sequence:

1. wait for PostgreSQL
2. run `alembic upgrade head`
3. start `uvicorn`

## 4. Verify The API

From the VPS itself:

```bash
curl http://127.0.0.1:8000/api/health
```

From outside the VPS:

```bash
curl http://<vps-ip>:8000/api/health
```

Both should return JSON from the health endpoint.

## 5. Seed Initial Runtime Data

On first deploy, run a few jobs manually so the API and bot have data to read:

```bash
docker compose exec app python -m src.scheduler run source_health
docker compose exec app python -m src.scheduler run core_l2beat
docker compose exec app python -m src.scheduler run core_coingecko
```

Then re-check:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/health/sources
```

## 6. Admin CLI

For inspection, manual collection, and seed scenarios, use:

```bash
docker compose exec app python -m src.admin inspect overview
docker compose exec app python -m src.admin inspect snapshots --entity mantle --metric tvl --limit 10
docker compose exec app python -m src.admin inspect alerts --entity mantle --metric tvl --limit 10
docker compose exec app python -m src.admin inspect runs --source defillama --limit 10
docker compose exec app python -m src.admin collect job core_defillama
docker compose exec app python -m src.admin collect job core_defillama --dry-run
docker compose exec app python -m src.admin seed alert-spike --entity mantle --metric tvl --previous 1000000000 --current 1500000000
docker compose exec app python -m src.admin seed alert-spike --entity mantle --metric tvl --previous 1000000000 --current 1500000000 --no-evaluate-rules
```

`seed alert-spike` inserts snapshots by default and evaluates rules to persist matching alerts. Use `--no-evaluate-rules` if you only want test snapshots without creating `alert_events`.

## 7. Stop The Stack

```bash
docker compose down
```

To also remove the database volume:

```bash
docker compose down -v
```

## 8. Troubleshooting

If startup fails:

```bash
docker compose ps
docker compose logs app --tail=100
docker compose logs db --tail=100
```

Common causes:

- `.env` missing or incomplete
- port `8000` blocked by firewall
- PostgreSQL credentials in `.env` do not match the compose defaults
- migration failure during `alembic upgrade head`
