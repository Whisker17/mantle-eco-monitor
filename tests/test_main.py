from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI

from src.main import lifespan


class FakeScheduler:
    def __init__(self):
        self.entered = False
        self.exited = False
        self.started = False
        self.stopped = False
        self.waited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exited = True

    def start_in_background(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def wait_until_stopped(self):
        self.waited = True


class FakeTask:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def done(self):
        return False


@pytest.mark.asyncio
async def test_lifespan_waits_for_scheduler_shutdown(monkeypatch):
    fake_scheduler = FakeScheduler()

    class FakeSettings:
        scheduler_enabled = True

    monkeypatch.setattr("config.settings.Settings", lambda: FakeSettings())
    monkeypatch.setattr("src.scheduler.jobs.is_scheduler_enabled", lambda settings: True)
    monkeypatch.setattr("src.scheduler.jobs.build_scheduler", lambda settings: fake_scheduler)

    app = FastAPI()

    async with lifespan(app):
        assert fake_scheduler.entered is True
        assert fake_scheduler.started is True

    assert fake_scheduler.stopped is True
    assert fake_scheduler.waited is True
    assert fake_scheduler.exited is True


@pytest.mark.asyncio
async def test_lifespan_skips_scheduler_when_profile_disables_it(monkeypatch):
    class FakeSettings:
        scheduler_enabled = True

    monkeypatch.setattr("config.settings.Settings", lambda: FakeSettings())
    monkeypatch.setattr("src.scheduler.jobs.is_scheduler_enabled", lambda settings: False)

    def fail_build_scheduler():
        raise AssertionError("build_scheduler should not be called when profile disables scheduling")

    monkeypatch.setattr("src.scheduler.jobs.build_scheduler", fail_build_scheduler)

    app = FastAPI()

    async with lifespan(app):
        assert hasattr(app.state, "scheduler") is False


@pytest.mark.asyncio
async def test_lifespan_does_not_start_background_dune_sync_task(monkeypatch):
    fake_scheduler = FakeScheduler()

    class FakeSettings:
        scheduler_enabled = True

    monkeypatch.setattr("config.settings.Settings", lambda: FakeSettings())
    monkeypatch.setattr("src.scheduler.jobs.is_scheduler_enabled", lambda settings: True)
    monkeypatch.setattr("src.scheduler.jobs.build_scheduler", lambda settings: fake_scheduler)

    app = FastAPI()

    async with lifespan(app):
        assert fake_scheduler.started is True
        assert hasattr(app.state, "dune_sync_task") is False
