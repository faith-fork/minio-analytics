from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.database import database as database_module


def test_initialize_database_rolls_back_all_schema_changes_on_migration_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db_path = tmp_path / "atomic-migration.db"
    monkeypatch.setenv("MINIO_ANALYTICS_DB", str(db_path))

    apply_migrations = database_module._apply_migrations

    def fail_after_migrations(connection: sqlite3.Connection) -> None:
        apply_migrations(connection)
        connection.execute(
            "CREATE TABLE migration_failure_probe (id INTEGER PRIMARY KEY)"
        )
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(
        database_module, "_apply_migrations", fail_after_migrations
    )

    with pytest.raises(RuntimeError, match="simulated migration failure"):
        database_module.initialize_database()

    connection = sqlite3.connect(db_path)
    try:
        tables = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    finally:
        connection.close()

    # Neither the base schema nor any migration DDL may survive a failed
    # initialization. This catches implicit commits between schema scripts.
    assert tables == []


def test_execute_sql_script_preserves_transaction_and_quoted_semicolons(
    tmp_path: Path,
):
    db_path = tmp_path / "sql-script-transaction.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        database_module._execute_sql_script(
            connection,
            """
            CREATE TABLE script_probe (
                id INTEGER PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT INTO script_probe (value)
            VALUES ('first;second');
            """,
        )

        assert connection.in_transaction
        assert connection.execute(
            "SELECT value FROM script_probe"
        ).fetchone()[0] == "first;second"

        connection.rollback()
        tables = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'script_probe'
            """
        ).fetchall()
        assert tables == []
    finally:
        connection.close()
