from __future__ import annotations

import pytest

from app.database.database import initialize_database, transaction
from app.database.prometheus_config import load_database_locations
from scripts.scheduler_tick import _load_locations


def _seed_config(db_path, monkeypatch):
    monkeypatch.setenv("MINIO_ANALYTICS_DB", str(db_path))
    initialize_database()
    with transaction() as connection:
        connection.execute(
            "INSERT INTO locations (id, name, enabled) VALUES ('lab', 'LAB', 1)"
        )
        connection.execute(
            """
            INSERT INTO clusters (id, location_id, name, enabled)
            VALUES ('cluster-a', 'lab', 'Cluster A', 1)
            """
        )
        connection.execute(
            """
            INSERT INTO prometheus_connections (
                connection_id, location_id, protocol, hostname, port,
                verify_tls, enabled
            ) VALUES ('prom-a', 'lab', 'https', 'prometheus.example.net',
                     9443, 1, 1)
            """
        )
        connection.execute(
            """
            INSERT INTO cluster_prometheus_bindings (
                cluster_id, connection_id, identity_label_name,
                identity_label_value
            ) VALUES ('cluster-a', 'prom-a', 'site', 'site-a')
            """
        )


def test_load_database_locations_includes_endpoint_tls_and_identity(tmp_path, monkeypatch):
    _seed_config(tmp_path / "collection.db", monkeypatch)

    locations = load_database_locations()

    assert len(locations) == 1
    location = locations[0]
    assert location.id == "lab"
    assert location.prometheus_url == "https://prometheus.example.net:9443"
    assert location.verify_tls is True
    assert len(location.clusters) == 1
    assert location.clusters[0].id == "cluster-a"
    assert location.clusters[0].prometheus_label_value == "site-a"
    assert location.clusters[0].identity_label_name == "site"


def test_load_database_locations_excludes_disabled_records(tmp_path, monkeypatch):
    _seed_config(tmp_path / "disabled.db", monkeypatch)
    with transaction() as connection:
        connection.execute(
            "UPDATE prometheus_connections SET enabled = 0 WHERE connection_id = 'prom-a'"
        )

    with pytest.raises(ValueError, match="No enabled Prometheus connections"):
        load_database_locations()


def test_load_database_locations_supports_multiple_connections_per_location(
    tmp_path, monkeypatch
):
    _seed_config(tmp_path / "multiple.db", monkeypatch)
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO clusters (id, location_id, name, enabled)
            VALUES ('cluster-b', 'lab', 'Cluster B', 1)
            """
        )
        connection.execute(
            """
            INSERT INTO prometheus_connections (
                connection_id, location_id, protocol, hostname, port,
                verify_tls, enabled
            ) VALUES ('prom-b', 'lab', 'http', '10.0.0.2', 9090, 1, 1)
            """
        )
        connection.execute(
            """
            INSERT INTO cluster_prometheus_bindings (
                cluster_id, connection_id, identity_label_name,
                identity_label_value
            ) VALUES ('cluster-b', 'prom-b', 'cluster', 'cluster-b')
            """
        )

    locations = load_database_locations()

    assert len(locations) == 2
    assert {location.id for location in locations} == {"lab"}
    assert {
        location.prometheus_url for location in locations
    } == {
        "https://prometheus.example.net:9443",
        "http://10.0.0.2:9090",
    }
    assert {
        location.clusters[0].id for location in locations
    } == {"cluster-a", "cluster-b"}


def test_load_database_locations_fails_when_no_bindings_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("MINIO_ANALYTICS_DB", str(tmp_path / "empty.db"))
    initialize_database()

    with pytest.raises(ValueError, match="No enabled Prometheus connections"):
        load_database_locations()



def test_scheduler_defaults_to_database_configuration(tmp_path, monkeypatch):
    _seed_config(tmp_path / "scheduler.db", monkeypatch)
    monkeypatch.delenv("MINIO_ANALYTICS_CONFIG_SOURCE", raising=False)

    locations = _load_locations()

    assert [cluster.id for location in locations for cluster in location.clusters] == [
        "cluster-a"
    ]


def test_scheduler_can_explicitly_fall_back_to_yaml(tmp_path, monkeypatch):
    _seed_config(tmp_path / "scheduler-yaml.db", monkeypatch)
    config_path = tmp_path / "locations.yaml"
    config_path.write_text(
        """
locations:
  - id: yaml-lab
    name: YAML Lab
    prometheus:
      host: prometheus-yaml.example.net
      scheme: https
      port: 9443
    clusters:
      - id: yaml-cluster
        name: YAML Cluster
        prometheus_label_value: yaml-cluster
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("MINIO_ANALYTICS_CONFIG_SOURCE", "yaml")
    monkeypatch.setenv("MINIO_ANALYTICS_CONFIG", str(config_path))

    locations = _load_locations()

    assert [location.id for location in locations] == ["yaml-lab"]


def test_scheduler_rejects_unknown_configuration_source(monkeypatch):
    monkeypatch.setenv("MINIO_ANALYTICS_CONFIG_SOURCE", "remote")

    with pytest.raises(ValueError, match="must be 'database' or 'yaml'"):
        _load_locations()
