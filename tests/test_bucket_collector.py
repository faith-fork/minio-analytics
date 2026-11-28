from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.collectors.bucket_collector import collect_bucket_snapshots
from app.collectors.prometheus import MetricSample
from app.config.loader import ClusterConfig, LocationConfig


class FakePrometheus:
    def __init__(self, values: dict[str, list[MetricSample]]):
        self.values = values
        self.queries: list[str] = []

    def query(self, promql: str, at=None):
        self.queries.append(promql)
        metric = promql.split("{", 1)[0]
        return list(self.values.get(metric, []))

    def close(self):
        pass


def sample(labels: dict[str, str], value: float) -> MetricSample:
    return MetricSample(labels=labels, value=value, timestamp=1)


def _collect(client: FakePrometheus):
    location = LocationConfig(
        id="loc1", name="Test", prometheus_url="http://prometheus:9090",
        clusters=(),
    )
    cluster = ClusterConfig(
        id="cluster1", name="Test Cluster", prometheus_label_value="cluster1"
    )
    return collect_bucket_snapshots(
        location, cluster, datetime(2026, 11, 20, tzinfo=timezone.utc), client=client
    )


def test_bucket_collector_persists_version_and_delete_marker_metric_values():
    client = FakePrometheus({
        "minio_cluster_usage_buckets_total_bytes": [
            sample({"bucket": "bucket-a"}, 1000),
        ],
        "minio_cluster_usage_buckets_objects_count": [
            sample({"bucket": "bucket-a"}, 10),
        ],
        "minio_cluster_usage_buckets_versions_count": [
            sample({"bucket": "bucket-a", "server": "node1"}, 18),
            sample({"bucket": "bucket-a", "server": "node2"}, 18),
        ],
        "minio_cluster_usage_buckets_delete_markers_count": [
            sample({"bucket": "bucket-a", "server": "node1"}, 3),
            sample({"bucket": "bucket-a", "server": "node2"}, 3),
        ],
    })

    result = _collect(client)

    assert len(result) == 1
    assert result[0].version_count == 18
    assert result[0].delete_marker_count == 3
    assert any("minio_cluster_usage_buckets_versions_count" in q for q in client.queries)
    assert any("minio_cluster_usage_buckets_delete_markers_count" in q for q in client.queries)


def test_missing_version_metrics_remain_unavailable_not_zero():
    client = FakePrometheus({
        "minio_cluster_usage_buckets_total_bytes": [
            sample({"bucket": "bucket-a"}, 1000),
        ],
        "minio_cluster_usage_buckets_objects_count": [
            sample({"bucket": "bucket-a"}, 10),
        ],
    })

    result = _collect(client)

    assert result[0].version_count is None
    assert result[0].delete_marker_count is None


def test_bucket_collector_rejects_conflicting_replicated_version_values():
    client = FakePrometheus({
        "minio_cluster_usage_buckets_total_bytes": [
            sample({"bucket": "bucket-a"}, 1000),
        ],
        "minio_cluster_usage_buckets_versions_count": [
            sample({"bucket": "bucket-a", "server": "node1"}, 18),
            sample({"bucket": "bucket-a", "server": "node2"}, 19),
        ],
    })

    with pytest.raises(Exception, match="Conflicting replicated values"):
        _collect(client)
