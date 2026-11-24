from __future__ import annotations

from urllib.parse import urlsplit
import sqlite3

from app.config.loader import ClusterConfig, LocationConfig
from app.database.database import database_path, initialize_database, transaction
from app.collectors.prometheus_credentials import build_authorization_header


def _endpoint_parts(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Invalid Prometheus endpoint: {url!r}")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Prometheus endpoint must not contain credentials, query, or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("Prometheus endpoint must be a base URL without a path")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 9090)
    except ValueError as exc:
        raise ValueError(f"Invalid Prometheus port in endpoint: {url!r}") from exc
    if not 1 <= port <= 65535:
        raise ValueError("Prometheus port must be between 1 and 65535")
    return parsed.scheme, parsed.hostname, port


def import_location_configuration(
    locations: list[LocationConfig],
    *,
    verify_tls: bool = True,
) -> dict[str, int]:
    """Idempotently import YAML endpoints and cluster bindings into SQLite.

    Existing location/cluster rows are only created when absent. Their enabled
    state, display names, IDs, and historical relationships are not overwritten.
    YAML remains the collector's source until a later validated runtime cutover.
    """
    initialize_database()
    endpoints = {
        location.id: _endpoint_parts(location.prometheus_url)
        for location in locations
    }
    connections = 0
    bindings = 0
    location_count = 0
    cluster_count = 0

    with transaction() as connection:
        for location in locations:
            connection.execute(
                """
                INSERT INTO locations (id, name, enabled)
                VALUES (?, ?, 1)
                ON CONFLICT(id) DO NOTHING
                """,
                (location.id, location.name),
            )
            location_count += 1
            protocol, hostname, port = endpoints[location.id]
            connection_id = f"prometheus:{location.id}"
            connection.execute(
                """
                INSERT INTO prometheus_connections (
                    connection_id, location_id, protocol, hostname, port,
                    verify_tls, enabled
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(connection_id) DO UPDATE SET
                    location_id = excluded.location_id,
                    protocol = excluded.protocol,
                    hostname = excluded.hostname,
                    port = excluded.port,
                    verify_tls = excluded.verify_tls,
                    auth_type = CASE
                        WHEN prometheus_connections.protocol != excluded.protocol
                          OR prometheus_connections.hostname != excluded.hostname
                          OR prometheus_connections.port != excluded.port
                        THEN 'none' ELSE prometheus_connections.auth_type END,
                    auth_secret_encrypted = CASE
                        WHEN prometheus_connections.protocol != excluded.protocol
                          OR prometheus_connections.hostname != excluded.hostname
                          OR prometheus_connections.port != excluded.port
                        THEN NULL ELSE prometheus_connections.auth_secret_encrypted END,
                    enabled = 1,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                """,
                (connection_id, location.id, protocol, hostname, port, int(verify_tls)),
            )
            connections += 1

            for cluster in location.clusters:
                connection.execute(
                    """
                    INSERT INTO clusters (id, location_id, name, enabled, labels_json)
                    VALUES (?, ?, ?, 1, '{}')
                    ON CONFLICT(id) DO NOTHING
                    """,
                    (cluster.id, location.id, cluster.name),
                )
                cluster_count += 1
                connection.execute(
                    """
                    INSERT INTO cluster_prometheus_bindings (
                        cluster_id, connection_id, identity_label_name,
                        identity_label_value
                    ) VALUES (?, ?, 'cluster', ?)
                    ON CONFLICT(cluster_id) DO UPDATE SET
                        connection_id = excluded.connection_id,
                        identity_label_name = excluded.identity_label_name,
                        identity_label_value = excluded.identity_label_value,
                        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    """,
                    (cluster.id, connection_id, cluster.prometheus_label_value),
                )
                bindings += 1

    return {
        "locations_imported": location_count,
        "clusters_imported": cluster_count,
        "connections_imported": connections,
        "cluster_bindings_imported": bindings,
    }


def list_prometheus_configuration() -> list[dict[str, object]]:
    """Return stored Prometheus endpoints with their bound MinIO clusters."""
    initialize_database()
    with transaction() as connection:
        rows = connection.execute(
            """
            SELECT pc.connection_id, pc.location_id, l.name AS location_name,
                   pc.protocol, pc.hostname, pc.port, pc.verify_tls, pc.enabled,
                   cpb.cluster_id, c.name AS cluster_name,
                   cpb.identity_label_name, cpb.identity_label_value
            FROM prometheus_connections pc
            JOIN locations l ON l.id = pc.location_id
            LEFT JOIN cluster_prometheus_bindings cpb
                ON cpb.connection_id = pc.connection_id
            LEFT JOIN clusters c ON c.id = cpb.cluster_id
            ORDER BY pc.location_id, pc.connection_id, cpb.cluster_id
            """
        ).fetchall()

    result: dict[str, dict[str, object]] = {}
    for row in rows:
        item = result.setdefault(
            row["connection_id"],
            {
                "connection_id": row["connection_id"],
                "location_id": row["location_id"],
                "location_name": row["location_name"],
                "protocol": row["protocol"],
                "hostname": row["hostname"],
                "port": row["port"],
                "verify_tls": bool(row["verify_tls"]),
                "enabled": bool(row["enabled"]),
                "clusters": [],
            },
        )
        if row["cluster_id"] is not None:
            item["clusters"].append(
                {
                    "cluster_id": row["cluster_id"],
                    "cluster_name": row["cluster_name"],
                    "identity_label_name": row["identity_label_name"],
                    "identity_label_value": row["identity_label_value"],
                }
            )
    return list(result.values())



def load_database_locations(*, read_only: bool = False) -> list[LocationConfig]:
    """Build collector configurations from enabled SQLite connections/bindings.

    In read-only mode, no migrations, directory creation, WAL changes, or
    other database writes are attempted.
    """
    query = """
        SELECT pc.connection_id, pc.location_id, l.name AS location_name,
               pc.protocol, pc.hostname, pc.port, pc.verify_tls,
               pc.auth_type, pc.auth_secret_encrypted,
               cpb.cluster_id, cpb.identity_label_name,
               cpb.identity_label_value, c.name AS cluster_name
        FROM prometheus_connections pc
        JOIN locations l ON l.id = pc.location_id
        JOIN cluster_prometheus_bindings cpb
            ON cpb.connection_id = pc.connection_id
        JOIN clusters c ON c.id = cpb.cluster_id
        WHERE pc.enabled = 1 AND l.enabled = 1 AND c.enabled = 1
        ORDER BY pc.location_id, pc.connection_id, cpb.cluster_id
    """
    if read_only:
        path = database_path().expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Analytics database does not exist: {path}")
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(query).fetchall()
        finally:
            connection.close()
    else:
        initialize_database()
        with transaction() as connection:
            rows = connection.execute(query).fetchall()

    if not rows:
        raise ValueError(
            "No enabled Prometheus connections with enabled cluster bindings "
            "were found in SQLite. Import or enable a Prometheus connection "
            "and at least one cluster binding before collection."
        )

    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        connection_id = row["connection_id"]
        item = grouped.setdefault(
            connection_id,
            {
                "location_id": row["location_id"],
                "location_name": row["location_name"],
                "protocol": row["protocol"],
                "hostname": row["hostname"],
                "port": row["port"],
                "verify_tls": bool(row["verify_tls"]),
                "auth_type": row["auth_type"],
                "auth_secret_encrypted": row["auth_secret_encrypted"],
                "clusters": [],
            },
        )
        item["clusters"].append(
            ClusterConfig(
                id=row["cluster_id"],
                name=row["cluster_name"],
                prometheus_label_value=row["identity_label_value"],
                identity_label_name=row["identity_label_name"],
            )
        )

    locations: list[LocationConfig] = []
    for item in grouped.values():
        hostname = str(item["hostname"])
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        endpoint = f'{item["protocol"]}://{hostname}:{item["port"]}'
        locations.append(
            LocationConfig(
                id=str(item["location_id"]),
                name=str(item["location_name"]),
                prometheus_url=endpoint,
                clusters=tuple(item["clusters"]),
                verify_tls=bool(item["verify_tls"]),
                auth_header=build_authorization_header(
                    str(item["auth_type"]), item["auth_secret_encrypted"]
                ),
            )
        )
    return locations
