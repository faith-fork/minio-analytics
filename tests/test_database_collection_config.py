from __future__ import annotations

import pytest

from app.database.database import initialize_database, transaction
from app.database.prometheus_config import load_database_locations


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
