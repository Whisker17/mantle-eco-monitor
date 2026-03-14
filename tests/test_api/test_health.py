def test_health_endpoint_returns_ok(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["db"] == "connected"


def test_health_endpoint_reports_db_and_source_run_state(client, seeded_source_runs):
    class _Schedule:
        def __init__(self, next_fire_time):
            self.next_fire_time = next_fire_time

    class _Scheduler:
        def get_schedules(self):
            return [_Schedule("2026-03-14T08:00:00+00:00")]

    client.app.state.scheduler = _Scheduler()

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["db"] == "connected"
    assert body["status"] == "degraded"
    assert body["last_source_runs"]["defillama"]["status"] == "success"
    assert body["last_source_runs"]["l2beat"]["status"] == "failed"
    assert body["last_source_runs"]["growthepie"]["status"] == "not_run"
    assert body["next_scheduled_run"] == "2026-03-14T08:00:00+00:00"
