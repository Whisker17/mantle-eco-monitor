import threading

import src.api.deps as api_deps


def test_get_session_factory_scopes_cache_per_thread(monkeypatch):
    class FakeSettings:
        database_url = "sqlite+aiosqlite:///tmp/test.db"

    created_engines = []

    def fake_create_async_engine(url, echo=False):
        engine = {"url": url, "thread": threading.get_ident(), "index": len(created_engines)}
        created_engines.append(engine)
        return engine

    def fake_async_sessionmaker(engine, expire_on_commit=False):
        return {"engine": engine, "thread": threading.get_ident()}

    monkeypatch.setattr(api_deps, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(api_deps, "async_sessionmaker", fake_async_sessionmaker)
    monkeypatch.setattr(api_deps, "_session_factory", None, raising=False)
    monkeypatch.setattr(api_deps, "_session_factories", {}, raising=False)

    results = [api_deps.get_session_factory(FakeSettings())]

    def build_factory():
        results.append(api_deps.get_session_factory(FakeSettings()))

    worker = threading.Thread(target=build_factory)
    worker.start()
    worker.join()

    assert len(created_engines) == 2
    assert results[0] is not results[1]
