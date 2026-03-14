from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes.alerts import alerts_router
from src.api.routes.health import health_router
from src.api.routes.metrics import metrics_router
from src.api.routes.watchlist import watchlist_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from config.settings import Settings

    settings = Settings()

    if settings.scheduler_enabled:
        from src.scheduler.jobs import build_scheduler

        scheduler = build_scheduler()
        scheduler.__enter__()
        scheduler.start_in_background()
        app.state.scheduler = scheduler

    yield

    if hasattr(app.state, "scheduler"):
        app.state.scheduler.stop()
        app.state.scheduler.wait_until_stopped()
        app.state.scheduler.__exit__(None, None, None)


def create_app() -> FastAPI:
    app = FastAPI(title="Mantle Monitor", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(alerts_router)
    app.include_router(metrics_router)
    app.include_router(watchlist_router)
    return app
