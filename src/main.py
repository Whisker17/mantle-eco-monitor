from fastapi import FastAPI

from src.api.routes.health import health_router


def create_app() -> FastAPI:
    app = FastAPI(title="Mantle Monitor")
    app.include_router(health_router)
    return app
