from __future__ import annotations
import os, sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
DEFAULT_DB_PATH=Path("/data/minio-analytics/database/minio_analytics.db")
SCHEMA_PATH=Path(__file__).with_name("schema.sql")
def database_path() -> Path:
    configured=os.getenv("MINIO_ANALYTICS_DB","").strip()
    return Path(configured).expanduser() if configured else DEFAULT_DB_PATH
def get_connection() -> sqlite3.Connection:
    path=database_path(); path.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(path,timeout=30); c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA busy_timeout=30000")
    return c
def _execute_sql_script(c: sqlite3.Connection, script: str) -> None:
    """Execute SQL statements without implicitly committing the active transaction.

    sqlite3.complete_statement() handles semicolons inside quoted strings and
    multi-line SQL statements, while each complete statement remains inside
    the caller's transaction.
    """
    pending = ""
    for line in script.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            statement = pending.strip()
            if statement:
                c.execute(statement)
            pending = ""

    if pending.strip():
        raise sqlite3.OperationalError("Incomplete SQL statement in schema/migration script")


def _apply_migrations(c: sqlite3.Connection) -> None:
    cols={r["name"] for r in c.execute("PRAGMA table_info(bucket_daily_metrics)")}
    for n,d in {"object_size_distribution_json":"TEXT NOT NULL DEFAULT '{}'","version_count_distribution_json":"TEXT NOT NULL DEFAULT '{}'"} .items():
        if n not in cols:c.execute(f"ALTER TABLE bucket_daily_metrics ADD COLUMN {n} {d}")
    c.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (2)")
    c.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (3)")
    cols={r["name"] for r in c.execute("PRAGMA table_info(node_daily_metrics)")}
    for n in ("drives_online","drives_offline"):
        if n not in cols:c.execute(f"ALTER TABLE node_daily_metrics ADD COLUMN {n} INTEGER")
    c.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (4)")
    c.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (5)")
    cols={r["name"] for r in c.execute("PRAGMA table_info(users)")}
    if "is_master_admin" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN is_master_admin INTEGER NOT NULL DEFAULT 0 CHECK(is_master_admin IN (0,1))")
    _execute_sql_script(c, """
    CREATE TABLE IF NOT EXISTS app_settings(setting_key TEXT PRIMARY KEY,setting_value TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')),updated_by TEXT);
    CREATE TABLE IF NOT EXISTS settings_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,setting_key TEXT NOT NULL,old_value TEXT,new_value TEXT NOT NULL,changed_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')),changed_by TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS scheduler_state(job_key TEXT PRIMARY KEY,last_started_at TEXT,last_completed_at TEXT,last_status TEXT,last_error TEXT);
    CREATE TABLE IF NOT EXISTS node_health_runs(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL UNIQUE,cluster_id TEXT NOT NULL REFERENCES clusters(id),snapshot_ts TEXT NOT NULL,collected_at TEXT NOT NULL,family_errors_json TEXT NOT NULL DEFAULT '{}',node_count INTEGER NOT NULL DEFAULT 0,drive_count INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'success' CHECK(status IN ('success','partial','failed')),error_text TEXT);
    CREATE INDEX IF NOT EXISTS idx_node_health_runs_cluster_ts ON node_health_runs(cluster_id,snapshot_ts DESC);
    CREATE INDEX IF NOT EXISTS idx_node_health_runs_snapshot_ts ON node_health_runs(snapshot_ts);
    CREATE TABLE IF NOT EXISTS node_health_metrics(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL REFERENCES node_health_runs(run_id) ON DELETE CASCADE,cluster_id TEXT NOT NULL REFERENCES clusters(id),node_name TEXT NOT NULL,node_exporter_instance TEXT,minio_instance TEXT,node_exporter_up REAL,minio_scrape_up REAL,cpu_utilization_pct REAL,memory_total_bytes REAL,memory_available_bytes REAL,memory_used_bytes REAL,load1 REAL,drives_online INTEGER,drives_offline INTEGER,UNIQUE(run_id,node_name));
    CREATE TABLE IF NOT EXISTS drive_health_metrics(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL REFERENCES node_health_runs(run_id) ON DELETE CASCADE,cluster_id TEXT NOT NULL REFERENCES clusters(id),node_name TEXT NOT NULL,server TEXT NOT NULL,drive_path TEXT NOT NULL,mountpoint TEXT,total_bytes REAL,used_bytes REAL,free_bytes REAL,availability_errors REAL,io_errors REAL,timeout_errors REAL,filesystem_total_bytes REAL,filesystem_available_bytes REAL,filesystem_free_bytes REAL,filesystem_readonly REAL,filesystem_used_bytes REAL,filesystem_used_pct REAL,UNIQUE(run_id,server,drive_path));
    """)
    legacy_interval = c.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key='node_interval_hours'"
    ).fetchone()
    existing_interval = c.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key='node_interval_minutes'"
    ).fetchone()
    migration_v10 = c.execute(
        "SELECT 1 FROM schema_version WHERE version=10"
    ).fetchone()
    for k,v in (("node_interval_hours","4"),("node_interval_minutes","5"),("telemetry_retention_days","3"),("daily_collection_time","00:15"),
                ("capacity_dp","1.33"),("capacity_rf","0.85"),("capacity_eff","0.99")):
        c.execute("INSERT OR IGNORE INTO app_settings(setting_key,setting_value) VALUES(?,?)",(k,v))
    # The previous hourly collector setting must not be silently replaced by the
    # new five-minute default. Also repair databases where the earlier telemetry
    # migration already inserted its default 5-minute value but did not record v10.
    if not migration_v10 and legacy_interval is not None and (
        existing_interval is None or existing_interval["setting_value"] == "5"
    ):
        try:
            legacy_hours = max(1, int(legacy_interval["setting_value"]))
        except (TypeError, ValueError):
            legacy_hours = 1
        migrated_minutes = str(min(60, legacy_hours * 60))
        c.execute(
            """UPDATE app_settings SET setting_value=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
               updated_by='system-migration-v10' WHERE setting_key='node_interval_minutes'""",
            (migrated_minutes,),
        )
        c.execute(
            """INSERT INTO settings_audit(setting_key,old_value,new_value,changed_by)
               VALUES('node_interval_minutes',?,?,?)""",
            (f"{legacy_hours} hours (legacy)", migrated_minutes, "system-migration-v10"),
        )
    _execute_sql_script(c, """
    CREATE TABLE IF NOT EXISTS prometheus_connections (
        connection_id TEXT PRIMARY KEY,
        location_id TEXT NOT NULL REFERENCES locations(id) ON UPDATE CASCADE ON DELETE RESTRICT,
        protocol TEXT NOT NULL CHECK (protocol IN ('http', 'https')),
        hostname TEXT NOT NULL,
        port INTEGER NOT NULL CHECK (port BETWEEN 1 AND 65535),
        verify_tls INTEGER NOT NULL DEFAULT 1 CHECK (verify_tls IN (0, 1)),
        enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        UNIQUE(location_id, protocol, hostname, port)
    );
    CREATE INDEX IF NOT EXISTS idx_prometheus_connections_location
        ON prometheus_connections(location_id, enabled);
    CREATE TABLE IF NOT EXISTS cluster_prometheus_bindings (
        cluster_id TEXT PRIMARY KEY REFERENCES clusters(id) ON UPDATE CASCADE ON DELETE RESTRICT,
        connection_id TEXT NOT NULL REFERENCES prometheus_connections(connection_id) ON UPDATE CASCADE ON DELETE RESTRICT,
        identity_label_name TEXT NOT NULL DEFAULT 'cluster'
            CHECK (identity_label_name IN ('cluster', 'site', 'environment')),
        identity_label_value TEXT NOT NULL CHECK (length(trim(identity_label_value)) > 0),
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    );
    CREATE INDEX IF NOT EXISTS idx_cluster_prometheus_bindings_connection
        ON cluster_prometheus_bindings(connection_id);
    """)
    c.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (7)")
    c.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (8)")
    _execute_sql_script(c, """
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        preference_key TEXT NOT NULL,
        preference_value TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        PRIMARY KEY (user_id, preference_key)
    );
    """)
    c.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (9)")
    c.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (10)")
    migration_v11 = c.execute(
        "SELECT 1 FROM schema_version WHERE version=11"
    ).fetchone()
    if not migration_v11:
        run_cols = {r["name"] for r in c.execute("PRAGMA table_info(node_health_runs)")}
        if "status" not in run_cols:
            c.execute(
                "ALTER TABLE node_health_runs ADD COLUMN status TEXT NOT NULL DEFAULT 'success' "
                "CHECK(status IN ('success','partial','failed'))"
            )
        if "error_text" not in run_cols:
            c.execute("ALTER TABLE node_health_runs ADD COLUMN error_text TEXT")
        # Preserve historical partial outcomes from the pre-v11 family-error record.
        c.execute(
            """UPDATE node_health_runs SET status='partial'
               WHERE status='success' AND family_errors_json NOT IN ('{}', '')"""
        )
        c.execute("INSERT INTO schema_version(version) VALUES (11)")

    migration_v12 = c.execute("SELECT 1 FROM schema_version WHERE version=12").fetchone()
    if not migration_v12:
        _execute_sql_script(c, """
        CREATE TABLE IF NOT EXISTS backfill_jobs (
            job_id TEXT PRIMARY KEY,
            location_id TEXT NOT NULL REFERENCES locations(id) ON DELETE RESTRICT,
            cluster_id TEXT NOT NULL REFERENCES clusters(id) ON DELETE RESTRICT,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            next_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('queued','running','paused','failed','completed','cancelled')),
            total_days INTEGER NOT NULL CHECK(total_days BETWEEN 1 AND 60),
            completed_days INTEGER NOT NULL DEFAULT 0,
            successful_days INTEGER NOT NULL DEFAULT 0,
            partial_days INTEGER NOT NULL DEFAULT 0,
            failed_days INTEGER NOT NULL DEFAULT 0,
            requested_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            last_error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_backfill_jobs_status_created
            ON backfill_jobs(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_backfill_jobs_cluster_status
            ON backfill_jobs(cluster_id, status);
        CREATE TABLE IF NOT EXISTS backfill_job_days (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES backfill_jobs(job_id) ON DELETE CASCADE,
            snapshot_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('success','partial','failed')),
            error_text TEXT,
            completed_at TEXT NOT NULL,
            UNIQUE(job_id, snapshot_date)
        );
        CREATE INDEX IF NOT EXISTS idx_backfill_job_days_job_date
            ON backfill_job_days(job_id, snapshot_date);
        """)
        c.execute("INSERT INTO schema_version(version) VALUES (12)")


    migration_v13 = c.execute("SELECT 1 FROM schema_version WHERE version=13").fetchone()
    if not migration_v13:
        connection_cols = {
            row["name"] for row in c.execute("PRAGMA table_info(prometheus_connections)")
        }
        if "auth_type" not in connection_cols:
            c.execute(
                "ALTER TABLE prometheus_connections ADD COLUMN auth_type TEXT NOT NULL DEFAULT 'none' "
                "CHECK(auth_type IN ('none','basic','bearer'))"
            )
        if "auth_secret_encrypted" not in connection_cols:
            c.execute("ALTER TABLE prometheus_connections ADD COLUMN auth_secret_encrypted TEXT")
        c.execute("INSERT INTO schema_version(version) VALUES (13)")

    migration_v14 = c.execute("SELECT 1 FROM schema_version WHERE version=14").fetchone()
    if not migration_v14:
        _execute_sql_script(c, """
        CREATE TABLE IF NOT EXISTS network_health_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES node_health_runs(run_id) ON DELETE CASCADE,
            cluster_id TEXT NOT NULL REFERENCES clusters(id) ON DELETE RESTRICT,
            node_name TEXT NOT NULL,
            instance TEXT NOT NULL,
            interface_name TEXT NOT NULL,
            rx_bytes_per_second REAL,
            tx_bytes_per_second REAL,
            rx_packets_per_second REAL,
            tx_packets_per_second REAL,
            rx_errors_per_second REAL,
            tx_errors_per_second REAL,
            rx_drops_per_second REAL,
            tx_drops_per_second REAL,
            UNIQUE(run_id, instance, interface_name)
        );
        CREATE INDEX IF NOT EXISTS idx_network_metrics_cluster_run
            ON network_health_metrics(cluster_id, run_id);
        CREATE INDEX IF NOT EXISTS idx_network_metrics_node_interface
            ON network_health_metrics(cluster_id, node_name, interface_name);
        """)
        c.execute("INSERT INTO schema_version(version) VALUES (14)")

def initialize_database() -> None:
    c=get_connection()
    try:
        c.execute("BEGIN IMMEDIATE")
        _execute_sql_script(c, SCHEMA_PATH.read_text(encoding="utf-8"))
        c.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (1)")
        _apply_migrations(c)
        c.commit()
    except Exception:c.rollback(); raise
    finally:c.close()
@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    c=get_connection()
    try:yield c;c.commit()
    except Exception:c.rollback();raise
    finally:c.close()
