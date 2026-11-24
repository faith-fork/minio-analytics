from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from app.api import master_admin
from scripts.backup_database import backup_database, inspect_backup_retention


PASSWORD = "Admin-Test-Password-123!"


def make_sqlite_backup(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE backup_probe (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO backup_probe DEFAULT VALUES")
        connection.commit()
    finally:
        connection.close()


def make_old_backups(directory: Path, count: int, days_old: int = 30) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    created = []
    old_time = time.time() - days_old * 86400
    for index in range(count):
        path = directory / f"minio_analytics_202611{index + 1:02d}T000000Z.db"
        make_sqlite_backup(path)
        timestamp = old_time + index
        os.utime(path, (timestamp, timestamp))
        created.append(path)
    return created


def configure_backup_paths(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    backup_dir = tmp_path / "backups"
    audit_dir = tmp_path / "logs"
    monkeypatch.setattr(master_admin, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(master_admin, "BACKUP_AUDIT_DIR", audit_dir)
    monkeypatch.setattr(master_admin, "BACKUP_AUDIT_FILE", audit_dir / "backup-cleanup-audit.jsonl")
    return backup_dir, audit_dir


def test_retention_preview_preserves_minimum_verified_backups_and_unverified_files(tmp_path):
    backup_dir = tmp_path / "backups"
    old_files = make_old_backups(backup_dir, 7)
    corrupt = backup_dir / "minio_analytics_corrupt.db"
    corrupt.write_bytes(b"not a sqlite database")
    old_time = time.time() - 30 * 86400
    os.utime(corrupt, (old_time - 1, old_time - 1))

    preview = inspect_backup_retention(backup_dir, retention_days=14, minimum_keep=5)

    assert preview["total_count"] == 8
    assert preview["verified_count"] == 7
    assert preview["unverified_count"] == 1
    assert preview["eligible_count"] == 2
    assert {item["filename"] for item in preview["candidates"]} == {
        old_files[0].name,
        old_files[1].name,
    }
    assert corrupt.name in {item["filename"] for item in preview["unverified"]}
    assert len(preview["preserved"]) == 5


def test_backup_creation_applies_same_minimum_keep_retention(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    make_sqlite_backup(source)
    monkeypatch.setenv("MINIO_ANALYTICS_DB", str(source))
    backup_dir = tmp_path / "backups"
    make_old_backups(backup_dir, 7)

    created = backup_database(backup_dir, retention_days=14, minimum_keep=5)

    remaining = sorted(backup_dir.glob("minio_analytics_*.db"))
    assert created.exists()
    assert len(remaining) == 5
    assert created in remaining
    assert all(inspect_backup_retention(backup_dir, 14, 5)["verified_count"] == 5 for _ in [0])


def test_backup_list_is_paginated_and_reports_actual_integrity(admin_client, monkeypatch, tmp_path):
    backup_dir, _ = configure_backup_paths(monkeypatch, tmp_path)
    backup_dir.mkdir(parents=True, exist_ok=True)
    for index in range(12):
        make_sqlite_backup(backup_dir / f"minio_analytics_page_{index:02d}.db")

    first = admin_client.get("/api/master-admin/backups")
    assert first.status_code == 200, first.text
    assert first.json()["total_count"] == 12
    assert first.json()["limit"] == 10
    assert len(first.json()["items"]) == 10
    assert all(item["integrity"] == "verified" for item in first.json()["items"])

    second = admin_client.get("/api/master-admin/backups?limit=5&offset=5")
    assert second.status_code == 200
    assert len(second.json()["items"]) == 5
    assert second.json()["offset"] == 5


def test_cleanup_preview_and_password_confirmed_cleanup_are_audited(
    admin_client, monkeypatch, tmp_path
):
    backup_dir, audit_dir = configure_backup_paths(monkeypatch, tmp_path)
    old_files = make_old_backups(backup_dir, 7)
    corrupt = backup_dir / "minio_analytics_corrupt.db"
    corrupt.write_bytes(b"corrupt")
    old_time = time.time() - 30 * 86400
    os.utime(corrupt, (old_time - 1, old_time - 1))

    preview = admin_client.post(
        "/api/master-admin/backups/cleanup/preview",
        json={"retention_days": 14, "minimum_keep": 5},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["eligible_count"] == 2
    assert preview.json()["unverified_count"] == 1

    denied = admin_client.post(
        "/api/master-admin/backups/cleanup",
        json={
            "retention_days": 14,
            "minimum_keep": 5,
            "current_password": "incorrect-password",
        },
    )
    assert denied.status_code == 403
    assert all(path.exists() for path in old_files)

    completed = admin_client.post(
        "/api/master-admin/backups/cleanup",
        json={
            "retention_days": 14,
            "minimum_keep": 5,
            "current_password": PASSWORD,
        },
    )
    assert completed.status_code == 200, completed.text
    result = completed.json()
    assert result["deleted_count"] == 2
    assert result["minimum_keep"] == 5
    assert len(result["preserved"]) == 5
    assert corrupt.exists()
    assert sum(path.exists() for path in old_files) == 5

    audit = [json.loads(line) for line in (audit_dir / "backup-cleanup-audit.jsonl").read_text().splitlines()]
    assert [entry["event"] for entry in audit] == [
        "backup_cleanup_started",
        "backup_cleanup_completed",
    ]
    assert all(entry["actor"] == "admin-test" for entry in audit)


def test_cleanup_does_not_follow_symlinks_or_delete_unmanaged_files(tmp_path):
    backup_dir = tmp_path / "backups"
    make_old_backups(backup_dir, 7)
    outside = tmp_path / "outside.db"
    make_sqlite_backup(outside)
    link = backup_dir / "minio_analytics_link.db"
    link.symlink_to(outside)
    unmanaged = backup_dir / "pre_migration_backup.db"
    make_sqlite_backup(unmanaged)

    preview = inspect_backup_retention(backup_dir, retention_days=14, minimum_keep=5)

    assert link.name not in {item["filename"] for item in preview["candidates"]}
    assert unmanaged.name not in {item["filename"] for item in preview["candidates"]}
    assert outside.exists()
    assert unmanaged.exists()
