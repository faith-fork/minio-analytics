from __future__ import annotations

from fastapi.testclient import TestClient


def test_unauthenticated_requests_are_rejected(client: TestClient) -> None:
    assert client.get("/api/tenants").status_code == 401
    assert client.get("/api/analytics/overview").status_code == 401


def test_viewer_role_cannot_perform_administrative_actions(
    viewer_client: TestClient,
) -> None:
    assert viewer_client.get("/api/tenants").status_code == 200
    assert viewer_client.post(
        "/api/tenants", json={"name": "Blocked Tenant"}
    ).status_code == 403
    assert viewer_client.get("/api/auth/users").status_code == 403
    assert viewer_client.put(
        "/api/buckets/bulk-tenant",
        json={"bucket_ids": [1], "tenant_id": None},
    ).status_code == 403


def test_admin_can_create_user_reset_password_and_deactivate(
    admin_client: TestClient,
) -> None:
    created = admin_client.post(
        "/api/auth/users",
        json={
            "username": "new-viewer",
            "password": "Initial-Password-123!",
            "role": "viewer",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]

    duplicate = admin_client.post(
        "/api/auth/users",
        json={
            "username": "NEW-VIEWER",
            "password": "Initial-Password-123!",
            "role": "viewer",
        },
    )
    assert duplicate.status_code == 409

    reset = admin_client.post(
        f"/api/auth/users/{user_id}/reset-password",
        json={"password": "Changed-Password-456!"},
    )
    assert reset.status_code == 200

    login = admin_client.post(
        "/api/auth/login",
        json={"username": "new-viewer", "password": "Changed-Password-456!"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "viewer"

    # The previous login changed this client session to the new viewer.
    admin_login = admin_client.post(
        "/api/auth/login",
        json={"username": "admin-test", "password": "Admin-Test-Password-123!"},
    )
    assert admin_login.status_code == 200

    deactivate = admin_client.post(
        f"/api/auth/users/{user_id}/active", json={"is_active": False}
    )
    assert deactivate.status_code == 200
    assert admin_client.get("/api/auth/users").status_code == 200


def test_last_active_admin_cannot_be_demoted_or_deactivated(
    admin_client: TestClient,
) -> None:
    users = admin_client.get("/api/auth/users").json()["items"]
    admin_id = next(user["id"] for user in users if user["username"] == "admin-test")

    demote = admin_client.patch(
        f"/api/auth/users/{admin_id}", json={"role": "viewer"}
    )
    assert demote.status_code == 409

    deactivate = admin_client.post(
        f"/api/auth/users/{admin_id}/active", json={"is_active": False}
    )
    assert deactivate.status_code == 409


def test_bulk_assignment_is_atomic_and_audited(admin_client: TestClient) -> None:
    tenant = admin_client.post(
        "/api/tenants", json={"name": "Bulk Tenant"}
    )
    assert tenant.status_code == 201
    tenant_id = tenant.json()["id"]

    invalid = admin_client.put(
        "/api/buckets/bulk-tenant",
        json={"bucket_ids": [1, 999], "tenant_id": tenant_id},
    )
    assert invalid.status_code == 404
    buckets_after_failure = admin_client.get("/api/buckets").json()["items"]
    assert all(bucket["tenant_id"] is None for bucket in buckets_after_failure)

    assigned = admin_client.put(
        "/api/buckets/bulk-tenant",
        json={
            "bucket_ids": [1, 2],
            "tenant_id": tenant_id,
            "note": "Automated bulk assignment test",
        },
    )
    assert assigned.status_code == 200
    assert assigned.json()["changed_count"] == 2
    assert assigned.json()["unchanged_count"] == 0

    replay = admin_client.put(
        "/api/buckets/bulk-tenant",
        json={"bucket_ids": [1, 2], "tenant_id": tenant_id},
    )
    assert replay.status_code == 200
    assert replay.json()["changed_count"] == 0
    assert replay.json()["unchanged_count"] == 2

    for bucket_id in (1, 2):
        history = admin_client.get(
            f"/api/buckets/{bucket_id}/history"
        ).json()
        assert history["count"] == 1
        assert history["items"][0]["tenant_id"] == tenant_id
        assert history["items"][0]["changed_by"] == "admin-test"


def test_single_assignment_and_snapshot_attribution_are_separate(
    admin_client: TestClient,
) -> None:
    tenant = admin_client.post(
        "/api/tenants", json={"name": "Current Owner"}
    ).json()
    tenant_id = tenant["id"]

    assigned = admin_client.put(
        "/api/buckets/1/tenant",
        json={"tenant_id": tenant_id, "note": "Ownership change"},
    )
    assert assigned.status_code == 200

    summary = admin_client.get("/api/analytics/tenants").json()
    current_owner = next(
        item for item in summary["items"] if item["tenant_id"] == tenant_id
    )
    assert current_owner["bucket_count"] == 1
    assert current_owner["used_bytes"] == 100

    bucket_history = admin_client.get("/api/analytics/buckets/1?days=3650").json()
    assert bucket_history["bucket"]["current_tenant_id"] == tenant_id
    assert bucket_history["series"][0]["tenant_id_at_snapshot"] is None

    current_trend = admin_client.get(
        "/api/analytics/tenants/" + str(tenant_id) + "?days=3650"
    ).json()
    assert current_trend["attribution"] == "current"
    assert current_trend["series"][0]["used_bytes"] == 100
    assert current_trend["series"][0]["bucket_count"] == 1
    assert current_trend["series"][0]["quota_bytes"] == 1000
    assert current_trend["series"][0]["object_count"] == 10

    historical_trend = admin_client.get(
        "/api/analytics/tenants/" + str(tenant_id) + "?days=3650&attribution=historical"
    ).json()
    assert historical_trend["attribution"] == "historical"
    assert historical_trend["series"] == []

    invalid_mode = admin_client.get(
        "/api/analytics/tenants/" + str(tenant_id) + "?attribution=unknown"
    )
    assert invalid_mode.status_code == 422

def test_viewer_can_read_analytics_but_not_manage_users(
    viewer_client: TestClient,
) -> None:
    assert viewer_client.get("/api/analytics/overview").status_code == 200
    assert viewer_client.get("/api/analytics/tenants").status_code == 200
    assert viewer_client.get("/api/auth/users").status_code == 403


def test_cluster_topology_api_returns_latest_persisted_inventory(
    viewer_client: TestClient,
) -> None:
    from app.database.database import transaction

    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO topology_daily_runs (
                snapshot_date, cluster_id, snapshot_ts, collected_at,
                family_errors_json, node_count, drive_count, pool_count, erasure_set_count
            ) VALUES (
                '2026-11-19', 'cluster-1', '2026-11-18T18:30:00Z',
                '2026-11-19T00:16:00Z', '{}', 1, 1, 1, 1
            )
            """
        )
        connection.execute(
            """
            INSERT INTO node_daily_metrics (
                snapshot_date, cluster_id, node_name, node_exporter_up,
                minio_scrape_up, cpu_utilization_pct, memory_total_bytes,
                memory_available_bytes, memory_used_bytes, load1,
                snapshot_ts, collected_at
            ) VALUES (
                '2026-11-19', 'cluster-1', 'node01', 1, 1, 12.5,
                16000, 4000, 12000, 0.5,
                '2026-11-18T18:30:00Z', '2026-11-19T00:16:00Z'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO drive_daily_metrics (
                snapshot_date, cluster_id, node_name, server, drive_path,
                mountpoint, total_bytes, used_bytes, free_bytes,
                availability_errors, io_errors, timeout_errors,
                filesystem_total_bytes, filesystem_available_bytes,
                filesystem_free_bytes, filesystem_readonly,
                filesystem_used_bytes, filesystem_used_pct,
                snapshot_ts, collected_at
            ) VALUES (
                '2026-11-19', 'cluster-1', 'node01', 'node01:9000',
                '/mnt/datadisk1/minio', '/mnt/datadisk1',
                1000, 400, 600, 0, 0, 0, 1000, 600, 600, 0,
                400, 40, '2026-11-18T18:30:00Z', '2026-11-19T00:16:00Z'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO pool_daily_metrics (
                snapshot_date, cluster_id, pool_id, erasure_set_count,
                online_drives, healing_drives, snapshot_ts, collected_at
            ) VALUES (
                '2026-11-19', 'cluster-1', '0', 1, 16, 0,
                '2026-11-18T18:30:00Z', '2026-11-19T00:16:00Z'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO erasure_set_daily_metrics (
                snapshot_date, cluster_id, pool_id, set_id, status_value,
                online_drives, healing_drives, read_quorum, write_quorum,
                snapshot_ts, collected_at
            ) VALUES (
                '2026-11-19', 'cluster-1', '0', '0', 1, 16, 0, 12, 12,
                '2026-11-18T18:30:00Z', '2026-11-19T00:16:00Z'
            )
            """
        )

    response = viewer_client.get("/api/analytics/clusters/cluster-1/topology")
    assert response.status_code == 200
    data = response.json()
    assert data["snapshot_date"] == "2026-11-19"
    assert data["counts"] == {
        "nodes": 1, "drives": 1, "pools": 1, "erasure_sets": 1
    }
    assert data["nodes"][0]["cpu_utilization_pct"] == 12.5
    assert data["drives"][0]["mountpoint"] == "/mnt/datadisk1"
    assert data["pools"][0]["pool_id"] == "0"
    assert data["erasure_sets"][0]["read_quorum"] == 12


def test_cluster_topology_api_returns_empty_state_before_first_collection(
    viewer_client: TestClient,
) -> None:
    response = viewer_client.get("/api/analytics/clusters/cluster-1/topology")
    assert response.status_code == 200
    data = response.json()
    assert data["snapshot_date"] is None
    assert data["nodes"] == []
    assert data["drives"] == []
    assert data["pools"] == []
    assert data["erasure_sets"] == []


def test_master_admin_settings_require_privilege_and_password(admin_client, viewer_client):
    # Both fixtures share one TestClient session; explicitly select the admin first.
    admin_login = admin_client.post("/api/auth/login", json={"username": "admin-test", "password": "Admin-Test-Password-123!"})
    assert admin_login.status_code == 200
    settings = admin_client.get("/api/master-admin/settings")
    assert settings.status_code == 200
    assert settings.json()["settings"] == {
        "node_interval_minutes": 5,
        "node_interval_hours": None,
        "telemetry_retention_days": 3,
        "daily_collection_time": "00:15",
    }
    viewer_login = viewer_client.post("/api/auth/login", json={"username": "viewer-test", "password": "Viewer-Test-Password-123!"})
    assert viewer_login.status_code == 200
    denied = viewer_client.get("/api/master-admin/settings")
    assert denied.status_code == 403
    admin_login = admin_client.post("/api/auth/login", json={"username": "admin-test", "password": "Admin-Test-Password-123!"})
    assert admin_login.status_code == 200
    bad_password = admin_client.put(
        "/api/master-admin/settings",
        json={"node_interval_minutes": 10, "telemetry_retention_days": 7, "daily_collection_time": "00:30",
              "current_password": "Wrong-Password-123!"},
    )
    assert bad_password.status_code == 403
    updated = admin_client.put(
        "/api/master-admin/settings",
        json={"node_interval_minutes": 10, "telemetry_retention_days": 7, "daily_collection_time": "00:30",
              "current_password": "Admin-Test-Password-123!"},
    )
    assert updated.status_code == 200
    assert updated.json()["effective_within_seconds"] == 60
    assert admin_client.get("/api/master-admin/settings").json()["settings"] == {
        "node_interval_minutes": 10,
        "node_interval_hours": None,
        "telemetry_retention_days": 7,
        "daily_collection_time": "00:30",
    }


def test_normal_admin_cannot_access_master_admin_settings(client):
    from app.auth.security import hash_password
    from app.database.database import transaction
    with transaction() as connection:
        connection.execute(
            "INSERT INTO users(username,password_hash,role) VALUES('regular-admin',?,'admin')",
            (hash_password("Regular-Admin-Password-123!"),),
        )
    response = client.post(
        "/api/auth/login",
        json={"username": "regular-admin", "password": "Regular-Admin-Password-123!"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["is_master_admin"] is False
    assert client.get("/api/master-admin/settings").status_code == 403


def test_master_admin_can_create_list_and_download_verified_backup(
    admin_client: TestClient, viewer_client: TestClient, tmp_path, monkeypatch
) -> None:
    import sqlite3
    from app.api import master_admin

    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(master_admin, "BACKUP_DIR", backup_dir)

    assert viewer_client.get("/api/master-admin/backups").status_code == 403
    assert viewer_client.post("/api/master-admin/backups").status_code == 403

    # Both fixtures share one TestClient session; restore the Master Admin login.
    relogin = admin_client.post(
        "/api/auth/login",
        json={"username": "admin-test", "password": "Admin-Test-Password-123!"},
    )
    assert relogin.status_code == 200

    created = admin_client.post("/api/master-admin/backups")
    assert created.status_code == 201
    payload = created.json()
    assert payload["integrity"] == "ok"
    assert payload["filename"].endswith(".db")

    backup_path = backup_dir / payload["filename"]
    assert backup_path.is_file()
    with sqlite3.connect(backup_path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute(
            "SELECT username FROM users WHERE username='admin-test'"
        ).fetchone()[0] == "admin-test"

    listed = admin_client.get("/api/master-admin/backups")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["items"][0]["filename"] == payload["filename"]

    downloaded = admin_client.get(payload["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.content[:16] == b"SQLite format 3\x00"

    invalid = admin_client.get("/api/master-admin/backups/..%2Fsecret.db/download")
    assert invalid.status_code in (400, 404)


def test_object_size_distribution_aggregates_bucket_tenant_and_cluster(
    admin_client: TestClient,
) -> None:
    import json
    from app.database.database import transaction

    tenant = admin_client.post("/api/tenants", json={"name": "Histogram Tenant"})
    assert tenant.status_code == 201
    tenant_id = tenant.json()["id"]

    with transaction() as connection:
        connection.execute(
            "UPDATE buckets SET tenant_id = ? WHERE id IN (1, 2)",
            (tenant_id,),
        )
        connection.execute(
            """UPDATE bucket_daily_metrics
               SET tenant_id_at_snapshot = ?,
                   object_size_distribution_json = ?
               WHERE bucket_id = 1""",
            (tenant_id, json.dumps({"LESS_THAN_1KB": 10, "BETWEEN_1KB_AND_64KB": 20})),
        )
        connection.execute(
            """UPDATE bucket_daily_metrics
               SET tenant_id_at_snapshot = ?,
                   object_size_distribution_json = ?
               WHERE bucket_id = 2""",
            (tenant_id, json.dumps({"LESS_THAN_1KB": 5, "BETWEEN_1KB_AND_64KB": 15})),
        )
        connection.execute(
            """UPDATE bucket_daily_metrics
               SET object_size_distribution_json = ?
               WHERE bucket_id = 3""",
            (json.dumps({"LESS_THAN_1KB": 2, "BETWEEN_1KB_AND_64KB": 8}),),
        )

    bucket = admin_client.get("/api/analytics/object-size-distribution/bucket/1")
    assert bucket.status_code == 200
    assert bucket.json()["total_objects"] == 30
    assert bucket.json()["status"] == "available"

    current = admin_client.get(
        f"/api/analytics/object-size-distribution/tenant/{tenant_id}?attribution=current"
    )
    assert current.status_code == 200
    assert current.json()["total_objects"] == 50
    assert current.json()["buckets_available"] == 2

    historical = admin_client.get(
        f"/api/analytics/object-size-distribution/tenant/{tenant_id}?attribution=historical"
    )
    assert historical.status_code == 200
    assert historical.json()["total_objects"] == 50

    cluster = admin_client.get(
        "/api/analytics/object-size-distribution/cluster/cluster-1"
    )
    assert cluster.status_code == 200
    assert cluster.json()["total_objects"] == 60


def test_object_size_distribution_does_not_report_partial_totals(
    admin_client: TestClient,
) -> None:
    import json
    from app.database.database import transaction

    with transaction() as connection:
        connection.execute(
            """UPDATE bucket_daily_metrics
               SET object_size_distribution_json = ?
               WHERE bucket_id = 1""",
            (json.dumps({"LESS_THAN_1KB": 10}),),
        )
        connection.execute(
            """UPDATE bucket_daily_metrics
               SET object_size_distribution_json = '{}'
               WHERE bucket_id IN (2, 3)"""
        )

    response = admin_client.get(
        "/api/analytics/object-size-distribution/cluster/cluster-1"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["total_objects"] is None
    assert response.json()["buckets_missing"] == 2
    assert response.json()["distribution"][0]["percentage"] is None

def test_cluster_analytics_reports_quota_metric_coverage(viewer_client: TestClient) -> None:
    from app.database.database import transaction

    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO cluster_daily_metrics (
                snapshot_date, cluster_id, snapshot_ts, collected_at,
                metrics_available
            ) VALUES (
                '2026-01-01', 'cluster-1', '2026-01-01T00:00:00Z',
                '2026-01-01T00:05:00Z', 1
            )
            """
        )

    complete = viewer_client.get("/api/analytics/clusters/cluster-1?days=3650")
    assert complete.status_code == 200
    row = complete.json()["series"][0]
    assert row["active_bucket_count"] == 3
    assert row["quota_bucket_count"] == 3
    assert row["bucket_quota_bytes"] == 3000

    with transaction() as connection:
        connection.execute(
            "UPDATE bucket_daily_metrics SET quota_bytes = NULL WHERE bucket_id = 3"
        )

    partial = viewer_client.get("/api/analytics/clusters/cluster-1?days=3650")
    assert partial.status_code == 200
    row = partial.json()["series"][0]
    assert row["active_bucket_count"] == 3
    assert row["quota_bucket_count"] == 2
    assert row["bucket_quota_bytes"] is None


def test_master_admin_settings_reject_legacy_interval_above_policy_limit(admin_client):
    response = admin_client.put(
        "/api/master-admin/settings",
        json={"node_interval_hours": 2, "daily_collection_time": "00:45",
              "current_password": "Admin-Test-Password-123!"},
    )
    assert response.status_code == 422
    assert "cannot exceed 60 minutes" in response.json()["detail"]

    one_hour = admin_client.put(
        "/api/master-admin/settings",
        json={"node_interval_hours": 1, "daily_collection_time": "00:45",
              "current_password": "Admin-Test-Password-123!"},
    )
    assert one_hour.status_code == 200
    settings = admin_client.get("/api/master-admin/settings").json()["settings"]
    assert settings["node_interval_minutes"] == 60
    assert settings["node_interval_hours"] == 1
    assert settings["telemetry_retention_days"] == 3


def test_cluster_analytics_exposes_complete_version_and_delete_marker_trends(
    viewer_client: TestClient,
) -> None:
    from app.database.database import transaction

    with transaction() as connection:
        connection.execute(
            "UPDATE bucket_daily_metrics SET version_count=?, delete_marker_count=? WHERE bucket_id=1",
            (12, 2),
        )
        connection.execute(
            "UPDATE bucket_daily_metrics SET version_count=?, delete_marker_count=? WHERE bucket_id=2",
            (18, 3),
        )
        connection.execute(
            "UPDATE bucket_daily_metrics SET version_count=?, delete_marker_count=? WHERE bucket_id=3",
            (24, 4),
        )

    response = viewer_client.get(
        "/api/analytics/clusters/cluster-1?start_date=2026-01-01&end_date=2026-01-01"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_bucket_summary"]["versions"] == 54
    assert payload["latest_bucket_summary"]["delete_markers"] == 9
    assert payload["series"][0]["bucket_version_count"] == 54
    assert payload["series"][0]["bucket_delete_marker_count"] == 9
    assert payload["series"][0]["version_bucket_count"] == 3
    assert payload["series"][0]["delete_marker_bucket_count"] == 3


def test_cluster_analytics_withholds_incomplete_version_totals(
    viewer_client: TestClient,
) -> None:
    from app.database.database import transaction

    with transaction() as connection:
        connection.execute(
            "UPDATE bucket_daily_metrics SET version_count=7, delete_marker_count=1 WHERE bucket_id=1"
        )
        connection.execute(
            "UPDATE bucket_daily_metrics SET version_count=NULL, delete_marker_count=2 WHERE bucket_id=2"
        )
        connection.execute(
            "UPDATE bucket_daily_metrics SET version_count=9, delete_marker_count=NULL WHERE bucket_id=3"
        )

    response = viewer_client.get(
        "/api/analytics/clusters/cluster-1?start_date=2026-01-01&end_date=2026-01-01"
    )
    payload = response.json()
    assert payload["series"][0]["bucket_version_count"] is None
    assert payload["series"][0]["bucket_delete_marker_count"] is None
    assert payload["series"][0]["version_bucket_count"] == 2
    assert payload["series"][0]["delete_marker_bucket_count"] == 2


def test_object_size_distribution_honors_exact_snapshot_date(
    admin_client: TestClient,
) -> None:
    import json
    from app.database.database import transaction

    with transaction() as connection:
        for bucket_id, name, count in ((1, "bucket-one", 10), (2, "bucket-two", 20), (3, "bucket-three", 30)):
            connection.execute(
                """INSERT INTO bucket_daily_metrics
                   (snapshot_date,bucket_id,cluster_id,bucket_name,tenant_id_at_snapshot,
                    snapshot_ts,collected_at,used_bytes,quota_bytes,object_count,
                    object_size_distribution_json,metrics_available)
                   VALUES ('2026-01-02',?,?,?,NULL,'2026-01-02T00:00:00Z',
                           '2026-01-02T00:05:00Z',100,1000,?,?,1)""",
                (bucket_id,"cluster-1",name,count,json.dumps({"LESS_THAN_1KB":count})),
            )
        connection.execute(
            "UPDATE bucket_daily_metrics SET object_size_distribution_json=? WHERE snapshot_date='2026-01-01'",
            (json.dumps({"LESS_THAN_1KB":10}),),
        )

    latest = admin_client.get("/api/analytics/object-size-distribution/cluster/cluster-1")
    assert latest.status_code == 200
    assert latest.json()["snapshot_date"] == "2026-01-02"
    assert latest.json()["total_objects"] == 60

    selected = admin_client.get(
        "/api/analytics/object-size-distribution/cluster/cluster-1?snapshot_date=2026-01-01"
    )
    assert selected.status_code == 200
    assert selected.json()["snapshot_date"] == "2026-01-01"
    assert selected.json()["total_objects"] == 30
    assert "2026-01-02" in selected.json()["available_dates"]

    missing = admin_client.get(
        "/api/analytics/object-size-distribution/cluster/cluster-1?snapshot_date=2025-12-31"
    )
    assert missing.status_code == 200
    assert missing.json()["snapshot_date"] == "2025-12-31"
    assert missing.json()["status"] == "unavailable"
    assert missing.json()["total_objects"] is None
