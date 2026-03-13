from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes.health import health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from config.settings import Settings

    settings = Settings()

    if settings.scheduler_enabled:
        from src.scheduler.jobs import build_scheduler

        scheduler = build_scheduler()
        scheduler.start_in_background()
        app.state.scheduler = scheduler

    yield

    if hasattr(app.state, "scheduler"):
        app.state.scheduler.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="Mantle Monitor", lifespan=lifespan)
    app.include_router(health_router)
    return app
