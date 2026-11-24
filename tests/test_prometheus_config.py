from __future__ import annotations

from app.config.loader import ClusterConfig, LocationConfig
from app.database.database import initialize_database, transaction
from app.database.prometheus_config import (
    import_location_configuration,
    list_prometheus_configuration,
)


def sample_locations() -> list[LocationConfig]:
    return [
        LocationConfig(
            id="loc-a",
            name="Location A",
            prometheus_url="https://prom-a.internal:9443",
            clusters=(
                ClusterConfig(
                    id="cluster-a1",
                    name="Cluster A1",
                    prometheus_label_value="cluster-a1",
                ),
                ClusterConfig(
                    id="cluster-a2",
                    name="Cluster A2",
                    prometheus_label_value="cluster-a2",
                ),
            ),
        ),
        LocationConfig(
            id="loc-b",
            name="Location B",
            prometheus_url="http://10.0.0.20:9090",
            clusters=(
                ClusterConfig(
                    id="cluster-b1",
                    name="Cluster B1",
                    prometheus_label_value="cluster-b1",
                ),
            ),
        ),
    ]


def test_database_migration_creates_prometheus_configuration_tables(tmp_path, monkeypatch):
    monkeypatch.setenv("MINIO_ANALYTICS_DB", str(tmp_path / "migration.db"))
    initialize_database()

    with transaction() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        version = connection.execute(
            "SELECT MAX(version) AS version FROM schema_version"
        ).fetchone()["version"]

    assert "prometheus_connections" in tables
    assert "cluster_prometheus_bindings" in tables
    assert version == 13


def test_import_yaml_configuration_preserves_cluster_ids_and_binds_endpoints(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MINIO_ANALYTICS_DB", str(tmp_path / "config.db"))

    result = import_location_configuration(sample_locations())
    configured = list_prometheus_configuration()

    assert result == {
        "locations_imported": 2,
        "clusters_imported": 3,
        "connections_imported": 2,
        "cluster_bindings_imported": 3,
    }
    assert len(configured) == 2

    first = next(item for item in configured if item["location_id"] == "loc-a")
    assert first["protocol"] == "https"
    assert first["hostname"] == "prom-a.internal"
    assert first["port"] == 9443
    assert first["verify_tls"] is True
    assert {item["cluster_id"] for item in first["clusters"]} == {
        "cluster-a1",
        "cluster-a2",
    }
    assert all(
        item["identity_label_name"] == "cluster"
        for item in first["clusters"]
    )


def test_import_is_idempotent_and_updates_endpoint_without_duplicate_rows(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MINIO_ANALYTICS_DB", str(tmp_path / "idempotent.db"))
    locations = sample_locations()

    import_location_configuration(locations)
    import_location_configuration(locations)
    configured = list_prometheus_configuration()

    with transaction() as connection:
        connection_count = connection.execute(
            "SELECT COUNT(*) AS n FROM prometheus_connections"
        ).fetchone()["n"]
        binding_count = connection.execute(
            "SELECT COUNT(*) AS n FROM cluster_prometheus_bindings"
        ).fetchone()["n"]

    assert connection_count == 2
    assert binding_count == 3
    assert len(configured) == 2


def test_existing_cluster_ids_are_not_replaced_by_import(tmp_path, monkeypatch):
    monkeypatch.setenv("MINIO_ANALYTICS_DB", str(tmp_path / "identity.db"))
    import_location_configuration(sample_locations())

    with transaction() as connection:
        ids = {
            row["id"]
            for row in connection.execute("SELECT id FROM clusters")
        }

    assert ids == {"cluster-a1", "cluster-a2", "cluster-b1"}


def test_import_clears_credentials_when_prometheus_endpoint_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("MINIO_ANALYTICS_DB", str(tmp_path / "endpoint-change.db"))
    locations = sample_locations()
    import_location_configuration(locations)

    with transaction() as connection:
        connection.execute(
            """UPDATE prometheus_connections
               SET auth_type='basic', auth_secret_encrypted='encrypted-secret'
               WHERE connection_id='prometheus:loc-a'"""
        )

    changed = [
        LocationConfig(
            id=item.id,
            name=item.name,
            prometheus_url=(
                "https://prom-new.internal:9443" if item.id == "loc-a"
                else item.prometheus_url
            ),
            clusters=item.clusters,
            verify_tls=item.verify_tls,
            auth_header=item.auth_header,
        )
        for item in locations
    ]
    import_location_configuration(changed)

    with transaction() as connection:
        row = connection.execute(
            "SELECT protocol, hostname, port, auth_type, auth_secret_encrypted "
            "FROM prometheus_connections WHERE connection_id='prometheus:loc-a'"
        ).fetchone()

    assert tuple(row) == ("https", "prom-new.internal", 9443, "none", None)
