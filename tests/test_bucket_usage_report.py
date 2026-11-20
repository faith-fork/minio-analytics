from __future__ import annotations

from fastapi.testclient import TestClient

from app.database.database import transaction


def test_bucket_usage_report_returns_latest_active_bucket_inventory(
    viewer_client: TestClient,
) -> None:
    response = viewer_client.get("/api/analytics/bucket-usage-report")

    assert response.status_code == 200
    data = response.json()
    assert data["generated_from"] == "sqlite"
    assert data["active_cluster_count"] == 1
    assert data["active_bucket_count"] == 3
    assert data["buckets_with_snapshots"] == 3
    assert data["buckets_with_metrics"] == 3
    assert data["buckets_without_metrics"] == 0
    assert data["coverage_pct"] == 100
    assert data["totals_bytes"] == {
        "used_bytes": 600,
        "quota_bytes": 3000,
        "object_count": 60,
        "version_count": None,
        "delete_marker_count": None,
    }
    assert len(data["items"]) == 3
    first = data["items"][0]
    assert first["bucket_name"] == "bucket-one"
    assert first["used_bytes"] == 100
    assert first["quota_bytes"] == 1000
    assert first["usage_pct"] == 10
    assert first["tenant_name_at_snapshot"] is None
    assert first["status"] == "Available"
    assert data["data_as_of"] == "2026-01-01T00:00:00Z"


def test_bucket_usage_report_withholds_incomplete_metric_totals_independently(
    viewer_client: TestClient,
) -> None:
    with transaction() as connection:
        connection.execute(
            "UPDATE bucket_daily_metrics SET used_bytes = NULL WHERE bucket_id = 1"
        )
        connection.execute(
            "UPDATE bucket_daily_metrics SET quota_bytes = NULL WHERE bucket_id = 2"
        )

    data = viewer_client.get("/api/analytics/bucket-usage-report").json()
    assert data["totals_bytes"]["used_bytes"] is None
    assert data["totals_bytes"]["quota_bytes"] is None
    assert data["totals_bytes"]["object_count"] == 60
    assert data["items"][0]["usage_pct"] is None


def test_bucket_usage_report_uses_latest_snapshot_date_per_cluster(
    viewer_client: TestClient,
) -> None:
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO bucket_daily_metrics
                (snapshot_date, bucket_id, cluster_id, bucket_name,
                 tenant_id_at_snapshot, snapshot_ts, collected_at,
                 used_bytes, quota_bytes, object_count, metrics_available)
            VALUES ('2026-01-02', 1, 'cluster-1', 'bucket-one', NULL,
                    '2026-01-02T00:00:00Z', '2026-01-02T00:05:00Z',
                    150, 1000, 15, 1)
            """
        )

    data = viewer_client.get("/api/analytics/bucket-usage-report").json()
    assert data["buckets_with_snapshots"] == 1
    assert data["buckets_with_metrics"] == 1
    assert data["totals_bytes"]["used_bytes"] is None
    by_name = {item["bucket_name"]: item for item in data["items"]}
    assert by_name["bucket-one"]["used_bytes"] == 150
    assert by_name["bucket-one"]["bucket_snapshot_date"] == "2026-01-02"
    assert by_name["bucket-two"]["used_bytes"] is None
    assert by_name["bucket-two"]["status"] == "No snapshot"


def test_bucket_usage_report_excludes_inactive_buckets(
    viewer_client: TestClient,
) -> None:
    with transaction() as connection:
        connection.execute("UPDATE buckets SET is_active = 0 WHERE id = 3")

    data = viewer_client.get("/api/analytics/bucket-usage-report").json()
    assert data["active_bucket_count"] == 2
    assert [item["bucket_name"] for item in data["items"]] == [
        "bucket-one", "bucket-two"
    ]
    assert data["totals_bytes"]["used_bytes"] == 300


def test_bucket_usage_report_returns_zero_totals_for_empty_inventory(
    viewer_client: TestClient,
) -> None:
    with transaction() as connection:
        connection.execute("UPDATE buckets SET is_active = 0")

    data = viewer_client.get("/api/analytics/bucket-usage-report").json()
    assert data["active_bucket_count"] == 0
    assert data["totals_bytes"] == {
        "used_bytes": 0,
        "quota_bytes": 0,
        "object_count": 0,
        "version_count": 0,
        "delete_marker_count": 0,
    }


def test_bucket_usage_report_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/analytics/bucket-usage-report").status_code == 401
