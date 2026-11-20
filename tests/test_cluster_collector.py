from __future__ import annotations

from datetime import datetime, timezone

from app.collectors.cluster_collector import collect_cluster_snapshot
from app.collectors.prometheus import MetricSample
from app.config.loader import ClusterConfig, LocationConfig


class FakePrometheus:
    def __init__(self, days_to_full: float | None):
        self.days_to_full = days_to_full
        self.queries: list[str] = []

    def query(self, promql: str, at=None):
        self.queries.append(promql)
        if "count_over_time" in promql:
            return [] if self.days_to_full is None else [
                MetricSample(labels={}, value=self.days_to_full, timestamp=1)
            ]
        if "minio_cluster_capacity_raw_total_bytes" in promql and "deriv(" in promql:
            value = 10.0
        elif "minio_cluster_capacity_raw_total_bytes" in promql:
            value = 1000.0
        elif "minio_cluster_capacity_raw_free_bytes" in promql:
            value = 500.0
        elif "minio_cluster_capacity_usable_total_bytes" in promql:
            value = 900.0
        elif "minio_cluster_capacity_usable_free_bytes" in promql:
            value = 450.0
        elif "minio_cluster_nodes_online_total" in promql:
            value = 4.0
        elif "minio_cluster_nodes_offline_total" in promql:
            value = 0.0
        else:
            value = 100.0
        return [MetricSample(labels={}, value=value, timestamp=1)]

    def close(self):
        pass


def _collect(client: FakePrometheus):
    location = LocationConfig(
        id="loc1", name="Test", prometheus_url="http://prometheus:9090",
        clusters=(),
    )
    cluster = ClusterConfig(
        id="cluster1", name="Test Cluster", prometheus_label_value="cluster1"
    )
    return collect_cluster_snapshot(
        location, cluster, datetime(2026, 11, 20, tzinfo=timezone.utc), client=client
    )


def test_days_to_full_requires_minimum_daily_observations():
    client = FakePrometheus(days_to_full=None)
    snapshot = _collect(client)

    assert snapshot.metrics_available is True
    assert snapshot.days_to_full is None
    forecast_query = next(q for q in client.queries if "count_over_time" in q)
    assert ">= 14" in forecast_query
    assert "deriv(" in forecast_query
    assert "< 0" in forecast_query


def test_days_to_full_is_retained_when_forecast_quality_checks_pass():
    client = FakePrometheus(days_to_full=365.0)
    snapshot = _collect(client)

    assert snapshot.metrics_available is True
    assert snapshot.days_to_full == 365.0
