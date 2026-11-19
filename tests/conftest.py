from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "MINIO_ANALYTICS_SESSION_SECRET",
    "test-only-session-secret-that-is-long-enough-for-tests",
)
os.environ.setdefault("MINIO_ANALYTICS_COOKIE_SECURE", "true")

from app.auth.security import hash_password
from app.database.database import initialize_database, transaction
from app.main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Give every test an isolated SQLite database and a seeded lab inventory."""
    db_path = tmp_path / "test-analytics.db"
    monkeypatch.setenv("MINIO_ANALYTICS_DB", str(db_path))
    initialize_database()

    with transaction() as connection:
        connection.execute(
            "INSERT INTO locations (id, name) VALUES ('LOC1', 'Test Location')"
        )
        connection.execute(
            """
            INSERT INTO clusters (id, location_id, name)
            VALUES ('cluster-1', 'LOC1', 'Test Cluster')
            """
        )
        for bucket_id, bucket_name in (
            (1, "bucket-one"),
            (2, "bucket-two"),
            (3, "bucket-three"),
        ):
            connection.execute(
                """
                INSERT INTO buckets
                    (id, cluster_id, bucket_name, first_seen_at, last_seen_at)
                VALUES (?, 'cluster-1', ?, '2026-01-01T00:00:00Z',
                        '2026-01-01T00:00:00Z')
                """,
                (bucket_id, bucket_name),
            )
            connection.execute(
                """
                INSERT INTO bucket_daily_metrics
                    (snapshot_date, bucket_id, cluster_id, bucket_name,
                     tenant_id_at_snapshot, snapshot_ts, collected_at,
                     used_bytes, quota_bytes, object_count, metrics_available)
                VALUES ('2026-01-01', ?, 'cluster-1', ?, NULL,
                        '2026-01-01T00:00:00Z', '2026-01-01T00:05:00Z',
                        ?, 1000, ?, 1)
                """,
                (bucket_id, bucket_name, bucket_id * 100, bucket_id * 10),
            )

        connection.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES ('admin-test', ?, 'admin')
            """,
            (hash_password("Admin-Test-Password-123!"),),
        )
        connection.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES ('viewer-test', ?, 'viewer')
            """,
            (hash_password("Viewer-Test-Password-123!"),),
        )

    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture
def admin_client(client: TestClient) -> TestClient:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin-test", "password": "Admin-Test-Password-123!"},
    )
    assert response.status_code == 200
    return client


@pytest.fixture
def viewer_client(client: TestClient) -> TestClient:
    response = client.post(
        "/api/auth/login",
        json={"username": "viewer-test", "password": "Viewer-Test-Password-123!"},
    )
    assert response.status_code == 200
    return client
