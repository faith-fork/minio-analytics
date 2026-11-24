from pathlib import Path


def test_all_prometheus_database_services_load_the_credentials_environment():
    root = Path(__file__).resolve().parents[1]
    for service in (
        "minio-analytics-web.service",
        "minio-analytics-collect.service",
        "minio-analytics-scheduler.service",
    ):
        content = (root / "systemd" / service).read_text(encoding="utf-8")
        assert "EnvironmentFile=/etc/minio-analytics/web.env" in content
