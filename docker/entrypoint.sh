#!/usr/bin/env sh
set -eu

echo "Waiting for database to become ready..."

python - <<'PY'
import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.environ["DATABASE_URL"]
RETRIES = 30
SLEEP_SECONDS = 2


async def main() -> None:
    engine = create_async_engine(DATABASE_URL)
    try:
        for attempt in range(1, RETRIES + 1):
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                print(f"Database ready on attempt {attempt}")
                return
            except Exception as exc:
                print(f"Database not ready on attempt {attempt}: {exc}")
                await asyncio.sleep(SLEEP_SECONDS)
        raise SystemExit("database did not become ready in time")
    finally:
        await engine.dispose()


asyncio.run(main())
PY

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec uvicorn src.main:create_app --factory --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
