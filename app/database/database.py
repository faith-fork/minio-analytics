from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB_PATH = Path("/data/minio-analytics/database/minio_analytics.db")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def database_path() -> Path:
    """Return the configured database path, defaulting to the dedicated data disk."""
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


def _apply_migrations(connection: sqlite3.Connection) -> None:
    """Apply additive, idempotent migrations without rebuilding existing tables."""
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(bucket_daily_metrics)")
    }
    additions = {
        "object_size_distribution_json": (
            "TEXT NOT NULL DEFAULT '{}'"
        ),
        "version_count_distribution_json": (
            "TEXT NOT NULL DEFAULT '{}'"
        ),
    }
    for name, definition in additions.items():
        if name not in columns:
            connection.execute(
                f"ALTER TABLE bucket_daily_metrics ADD COLUMN {name} {definition}"
            )

    connection.execute(
        "INSERT OR IGNORE INTO schema_version(version) VALUES (?)", (2,)
    )


def initialize_database() -> None:
    """Create the schema and apply safe additive migrations; safe to call repeatedly."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    connection = get_connection()
    try:
        connection.executescript(schema)
        connection.execute(
            "INSERT OR IGNORE INTO schema_version(version) VALUES (?)", (1,)
        )
        _apply_migrations(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection and commit on success or roll back on failure."""
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
