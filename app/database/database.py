from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "minio_analytics.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def database_path() -> Path:
    """Return the configured database path, defaulting to the project data directory."""
    configured = os.getenv("MINIO_ANALYTICS_DB", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_DB_PATH


def get_connection() -> sqlite3.Connection:
    """Open a SQLite connection with row access, foreign keys, WAL and a busy timeout."""
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def initialize_database() -> None:
    """Create the initial schema. Safe to call repeatedly during application startup."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    connection = get_connection()
    try:
        connection.executescript(schema)
        connection.execute(
            "INSERT OR IGNORE INTO schema_version(version) VALUES (?)",
            (1,),
        )
        connection.commit()
    finally:
        connection.close()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Yield a connection and commit on success or roll back on failure."""
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
