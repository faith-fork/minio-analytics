from datetime import date, datetime, timezone

from app.collectors.cluster_collector import ClusterSnapshot
from app.collectors.topology_collector import TopologySnapshot
from app.config.loader import ClusterConfig, LocationConfig
from scripts import backfill_history as backfill


def _configs():
    cluster = ClusterConfig(
        id="cluster-a", name="Cluster A",
        prometheus_label_value="cluster-a",
    )
    location = LocationConfig(
        id="site-a", name="Site A", prometheus_url="http://127.0.0.1:9090",
        clusters=(cluster,),
    )
    return location, cluster


def test_snapshot_timestamp_uses_midnight_ist():
    timestamp = backfill._snapshot_timestamp(date(2026, 11, 24))
    assert timestamp == datetime(2026, 11, 23, 18, 30, tzinfo=timezone.utc)


def test_collect_day_persists_all_historical_families_idempotently(monkeypatch):
    location, cluster = _configs()
    day = date(2026, 11, 24)
    timestamp = backfill._snapshot_timestamp(day)
    cluster_snapshot = ClusterSnapshot(
        location_id=location.id, location_name=location.name,
        cluster_id=cluster.id, cluster_name=cluster.name,
        snapshot_ts=timestamp, collected_at=datetime.now(timezone.utc),
        raw_total_bytes=1000, raw_free_bytes=500,
        usable_total_bytes=800, usable_free_bytes=400,
        nodes_online=4, nodes_offline=0,
        growth_bytes_per_day=None, days_to_full=None,
        metrics_available=True,
    )
    bucket = object()
    topology = TopologySnapshot(
        location_id=location.id, cluster_id=cluster.id,
        snapshot_ts=timestamp, collected_at=datetime.now(timezone.utc),
        nodes=[{"node_name": "node-a"}],
    )
    persisted = []

    monkeypatch.setattr(backfill, "collect_cluster_snapshot", lambda *a: cluster_snapshot)
    monkeypatch.setattr(backfill, "collect_bucket_snapshots", lambda *a: [bucket])
    monkeypatch.setattr(backfill, "collect_topology_snapshot", lambda *a: topology)
    monkeypatch.setattr(backfill, "persist_cluster_snapshot", lambda *a, **k: persisted.append("cluster"))
    monkeypatch.setattr(backfill, "persist_bucket_snapshots", lambda *a, **k: {"metrics_upserts": 1})
    monkeypatch.setattr(backfill, "persist_topology_snapshot", lambda *a, **k: {"nodes": 1})
    monkeypatch.setattr(backfill, "_record_run", lambda *a, **k: persisted.append("run"))

    result = backfill._collect_day(location, cluster, day, 2, False)

    assert result["status"] == "success"
    assert result["cluster_snapshot"] is True
    assert result["bucket_snapshots"] == 1
    assert result["topology"] == {"nodes": 1}
    assert persisted == ["cluster", "run"]


def test_collect_day_reports_partial_when_prometheus_has_no_historical_samples(monkeypatch):
    location, cluster = _configs()
    monkeypatch.setattr(
        backfill, "collect_cluster_snapshot",
        lambda *a: type("Failed", (), {"metrics_available": False, "error_text": "no samples"})(),
    )
    monkeypatch.setattr(backfill, "collect_bucket_snapshots", lambda *a: [])
    monkeypatch.setattr(
        backfill, "collect_topology_snapshot",
        lambda *a: TopologySnapshot(
            location_id=location.id, cluster_id=cluster.id,
            snapshot_ts=backfill._snapshot_timestamp(date(2026, 11, 24)),
            collected_at=datetime.now(timezone.utc),
            family_errors={"nodes": "no samples"},
        ),
    )
    result = backfill._collect_day(location, cluster, date(2026, 11, 24), 1, True)
    assert result["status"] == "failed"
    assert result["errors"]



def test_database_configuration_dry_run_does_not_initialize_or_write_sqlite(client, monkeypatch):
    from app.database import prometheus_config
    from app.database.database import transaction

    with transaction() as connection:
        connection.execute(
            """INSERT INTO prometheus_connections
               (connection_id, location_id, protocol, hostname, port, enabled)
               VALUES ('prom-loc1', 'LOC1', 'http', '10.20.30.40', 9090, 1)"""
        )
        connection.execute(
            """INSERT INTO cluster_prometheus_bindings
               (cluster_id, connection_id, identity_label_name, identity_label_value)
               VALUES ('cluster-1', 'prom-loc1', 'cluster', 'cluster-1')"""
        )

    def fail_if_initialized():
        raise AssertionError("read-only configuration loading must not initialize or migrate SQLite")

    monkeypatch.setattr(prometheus_config, "initialize_database", fail_if_initialized)
    locations = prometheus_config.load_database_locations(read_only=True)

    assert len(locations) == 1
    assert locations[0].id == "LOC1"
    assert locations[0].clusters[0].id == "cluster-1"
