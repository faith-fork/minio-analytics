from __future__ import annotations

from datetime import datetime, timezone

from app.collectors import network_metrics
from app.config.loader import ClusterConfig, LocationConfig
from app.collectors.prometheus import MetricSample


class FakePrometheus:
    def __init__(self, *args, **kwargs):
        self.calls = []

    def query(self, query, at=None):
        self.calls.append((query, at))
        metric = next(name for name in network_metrics.METRICS.values() if name in query)
        if metric == "node_network_receive_bytes_total":
            return [
                MetricSample({"instance": "node-a:9100", "device": "eth0"}, 10.0, 1),
                MetricSample({"instance": "node-a:9100", "device": "lo"}, 999.0, 1),
            ]
        if metric == "node_network_transmit_bytes_total":
            return [MetricSample({"instance": "node-a:9100", "device": "eth0"}, 20.0, 1)]
        return [MetricSample({"instance": "node-a:9100", "device": "eth0"}, 1.0, 1)]

    def close(self):
        pass


def _configs():
    cluster = ClusterConfig(id="C", name="Cluster", prometheus_label_value='c"\n')
    location = LocationConfig(id="LOC", name="Location", prometheus_url="http://prom:9090",
                              clusters=(cluster,))
    return location, cluster


def test_collection_uses_common_timestamp_and_excludes_loopback(monkeypatch):
    fake = FakePrometheus()
    monkeypatch.setattr(network_metrics, "PrometheusClient", lambda *a, **kw: fake)
    location, cluster = _configs()
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows, error = network_metrics.collect_network_metrics(location, cluster, ts)
    assert len(rows) == 1
    assert rows[0]["interface_name"] == "eth0"
    assert rows[0]["node_name"] == "node-a"
    assert rows[0]["rx_bytes_per_second"] == 10.0
    assert rows[0]["tx_bytes_per_second"] == 20.0
    assert error is None
    assert all(call[1] == int(ts.timestamp()) for call in fake.calls)
    assert all("[5m]" in call[0] for call in fake.calls)
    assert all('c\\"\\n' in call[0] for call in fake.calls)


def test_empty_metric_families_are_reported_as_partial(monkeypatch):
    class EmptyProm(FakePrometheus):
        def query(self, query, at=None):
            return []
    monkeypatch.setattr(network_metrics, "PrometheusClient", lambda *a, **kw: EmptyProm())
    location, cluster = _configs()
    rows, error = network_metrics.collect_network_metrics(location, cluster,
        datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert rows == []
    assert error and "no interface samples" in error


def test_ipv6_instance_host_is_normalized():
    assert network_metrics._host("[2001:db8::10]:9100") == "2001:db8::10"
    assert network_metrics._host("2001:db8::10") == "2001:db8::10"


def test_client_close_error_is_family_isolated(monkeypatch):
    class CloseErrorProm(FakePrometheus):
        def close(self):
            raise RuntimeError("cleanup failed")

    fake = CloseErrorProm()
    monkeypatch.setattr(network_metrics, "PrometheusClient", lambda *a, **kw: fake)
    location, cluster = _configs()
    rows, error = network_metrics.collect_network_metrics(
        location, cluster, datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    assert rows and rows[0]["rx_bytes_per_second"] == 10.0
    assert error and "Prometheus client close: cleanup failed" in error
