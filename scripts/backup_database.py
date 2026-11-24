from __future__ import annotations

import argparse
import fcntl
import json
import os
import sqlite3
import stat
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.database.database import database_path

DEFAULT_BACKUP_DIR = Path("/data/minio-analytics/backups")
DEFAULT_MINIMUM_BACKUPS = 5
MANAGED_BACKUP_GLOB = "minio_analytics_*.db"


@contextmanager
def backup_management_lock(backup_dir: Path) -> Iterator[None]:
    """Serialize backup creation and cleanup across API and scheduler processes."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    if backup_dir.is_symlink():
        raise RuntimeError("Backup directory must not be a symbolic link")
    lock_path = backup_dir / ".backup-management.lock"
    if lock_path.is_symlink():
        raise RuntimeError("Backup management lock must not be a symbolic link")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(descriptor, "r+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except Exception:
        raise


def _backup_files(backup_dir: Path) -> list[tuple[Path, os.stat_result]]:
    if backup_dir.is_symlink():
        raise RuntimeError("Backup directory must not be a symbolic link")
    backup_dir.mkdir(parents=True, exist_ok=True)
    files: list[tuple[Path, os.stat_result]] = []
    for path in backup_dir.glob(MANAGED_BACKUP_GLOB):
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(metadata.st_mode) and not path.is_symlink():
            files.append((path, metadata))
    return sorted(files, key=lambda item: (item[1].st_mtime, item[0].name), reverse=True)


def verify_backup(path: Path) -> tuple[bool, str | None]:
    """Verify a regular, non-symlink SQLite backup without modifying it."""
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
            return False, "Not a regular backup file"
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()
        finally:
            connection.close()
        if result and result[0] == "ok":
            return True, None
        return False, str(result[0] if result else "No integrity result")
    except (OSError, sqlite3.Error, ValueError) as exc:
        return False, str(exc)


def inspect_backup_retention(
    backup_dir: Path,
    retention_days: int = 14,
    minimum_keep: int = DEFAULT_MINIMUM_BACKUPS,
    now: datetime | None = None,
) -> dict:
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")
    if minimum_keep < 1:
        raise ValueError("minimum_keep must be at least 1")

    now = now or datetime.now(timezone.utc)
    cutoff = now.timestamp() - retention_days * 86400
    files = _backup_files(backup_dir)
    verified: list[dict] = []
    unverified: list[dict] = []
    for path, metadata in files:
        ok, error = verify_backup(path)
        item = {
            "filename": path.name,
            "size_bytes": metadata.st_size,
            "created_at": datetime.fromtimestamp(metadata.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
            "modified_at": metadata.st_mtime,
        }
        if ok:
            verified.append(item)
        else:
            item["verification_error"] = error
            unverified.append(item)

    preserved_names = {item["filename"] for item in verified[:minimum_keep]}
    candidates = [
        item for item in verified
        if item["modified_at"] < cutoff and item["filename"] not in preserved_names
    ]
    preserved = [
        item for item in verified
        if item["filename"] in preserved_names or item["modified_at"] >= cutoff
    ]
    return {
        "retention_days": retention_days,
        "minimum_keep": minimum_keep,
        "total_count": len(files),
        "verified_count": len(verified),
        "unverified_count": len(unverified),
        "eligible_count": len(candidates),
        "eligible_size_bytes": sum(item["size_bytes"] for item in candidates),
        "candidates": [{k: v for k, v in item.items() if k != "modified_at"} for item in candidates],
        "preserved": [{k: v for k, v in item.items() if k != "modified_at"} for item in preserved],
        "unverified": [{k: v for k, v in item.items() if k != "modified_at"} for item in unverified],
    }


def cleanup_expired_backups(
    backup_dir: Path,
    retention_days: int = 14,
    minimum_keep: int = DEFAULT_MINIMUM_BACKUPS,
) -> dict:
    with backup_management_lock(backup_dir):
        preview = inspect_backup_retention(backup_dir, retention_days, minimum_keep)
        candidates = preview["candidates"]
        if candidates:
            _append_retention_audit({
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "event": "automatic_backup_retention_started",
                "actor": "system",
                "retention_days": retention_days,
                "minimum_keep": minimum_keep,
                "candidate_filenames": [item["filename"] for item in candidates],
                "candidate_size_bytes": sum(item["size_bytes"] for item in candidates),
            }, backup_dir)
        deleted = []
        for item in candidates:
            path = backup_dir / item["filename"]
            try:
                metadata = path.lstat()
                if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
                    continue
                path.unlink()
                deleted.append({"filename": path.name, "size_bytes": metadata.st_size})
            except FileNotFoundError:
                continue
        preview["deleted"] = deleted
        preview["deleted_count"] = len(deleted)
        preview["deleted_size_bytes"] = sum(item["size_bytes"] for item in deleted)
        if deleted:
            _append_retention_audit({
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "event": "automatic_backup_retention_completed",
                "actor": "system",
                "deleted": deleted,
                "deleted_count": len(deleted),
                "deleted_size_bytes": preview["deleted_size_bytes"],
                "retention_days": retention_days,
                "minimum_keep": minimum_keep,
            }, backup_dir)
        return preview


def _append_retention_audit(record: dict, backup_dir: Path) -> None:
    audit_dir = backup_dir.parent / "logs"
    audit_file = audit_dir / "backup-cleanup-audit.jsonl"
    audit_dir.mkdir(parents=True, exist_ok=True)
    if audit_dir.is_symlink() or audit_file.is_symlink():
        raise RuntimeError("Backup audit path must not contain symbolic links")
    payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(audit_file, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def backup_database(
    backup_dir: Path,
    retention_days: int = 14,
    minimum_keep: int = DEFAULT_MINIMUM_BACKUPS,
) -> Path:
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")
    if minimum_keep < 1:
        raise ValueError("minimum_keep must be at least 1")

    source_path = database_path()
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {source_path}")

    with backup_management_lock(backup_dir):
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

        preview = inspect_backup_retention(backup_dir, retention_days, minimum_keep)
        candidates = preview["candidates"]
        if candidates:
            _append_retention_audit({
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "event": "automatic_backup_retention_started",
                "actor": "system",
                "retention_days": retention_days,
                "minimum_keep": minimum_keep,
                "candidate_filenames": [item["filename"] for item in candidates],
                "candidate_size_bytes": sum(item["size_bytes"] for item in candidates),
            }, backup_dir)
        deleted = []
        for item in candidates:
            path = backup_dir / item["filename"]
            try:
                metadata = path.lstat()
                if stat.S_ISREG(metadata.st_mode) and not path.is_symlink():
                    path.unlink()
                    deleted.append({"filename": path.name, "size_bytes": metadata.st_size})
            except FileNotFoundError:
                pass
        if deleted:
            _append_retention_audit({
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "event": "automatic_backup_retention_completed",
                "actor": "system",
                "deleted": deleted,
                "deleted_count": len(deleted),
                "deleted_size_bytes": sum(item["size_bytes"] for item in deleted),
                "retention_days": retention_days,
                "minimum_keep": minimum_keep,
            }, backup_dir)

    return destination


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a consistent SQLite backup and prune eligible old verified backups."
    )
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--retention-days", type=int, default=14)
    parser.add_argument("--minimum-keep", type=int, default=DEFAULT_MINIMUM_BACKUPS)
    args = parser.parse_args()

    path = backup_database(args.backup_dir, args.retention_days, args.minimum_keep)
    print(f"Backup created and integrity-checked: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
