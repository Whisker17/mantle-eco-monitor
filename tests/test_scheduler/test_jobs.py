from src.scheduler.jobs import build_scheduler


def test_scheduler_registers_phase1_jobs():
    scheduler = build_scheduler()
    schedules = scheduler.get_schedules()
    schedule_ids = {s.id for s in schedules}

    expected_ids = {
        "core_defillama",
        "core_dune",
        "core_l2beat",
        "core_coingecko",
        "eco_protocols",
        "eco_aave",
        "watchlist_refresh",
        "source_health",
    }
    assert schedule_ids >= expected_ids


def test_scheduler_has_correct_count():
    scheduler = build_scheduler()
    schedules = scheduler.get_schedules()
    assert len(schedules) >= 8
