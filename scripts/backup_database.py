from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.database.database import database_path

DEFAULT_BACKUP_DIR = Path("/data/minio-analytics/backups")


def backup_database(backup_dir: Path, retention_days: int) -> Path:
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")

    source_path = database_path()
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {source_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = backup_dir / f"minio_analytics_{timestamp}.db"
    temporary = destination.with_suffix(".db.tmp")

    source = sqlite3.connect(source_path, timeout=30)
    target = sqlite3.connect(temporary)
    try:
        source.backup(target)
        result = target.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(f"Backup integrity check failed: {result}")
        target.commit()
    finally:
        target.close()
        source.close()

    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)

    cutoff = datetime.now(timezone.utc).timestamp() - retention_days * 86400
    for old_backup in backup_dir.glob("minio_analytics_*.db"):
        if old_backup == destination:
            continue
        try:
            if old_backup.stat().st_mtime < cutoff:
                old_backup.unlink()
        except FileNotFoundError:
            pass

    return destination


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a consistent SQLite backup and prune old backups."
    )
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--retention-days", type=int, default=14)
    args = parser.parse_args()

    path = backup_database(args.backup_dir, args.retention_days)
    print(f"Backup created and integrity-checked: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
