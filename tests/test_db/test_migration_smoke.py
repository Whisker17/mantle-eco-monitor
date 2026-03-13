def test_initial_migration_creates_all_phase1_tables(db_inspector):
    tables = db_inspector.get_table_names()
    assert "metric_snapshots" in tables
    assert "alert_events" in tables
    assert "watchlist_protocols" in tables
    assert "source_runs" in tables
