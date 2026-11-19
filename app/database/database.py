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
    c.executescript("""
    CREATE TABLE IF NOT EXISTS app_settings(setting_key TEXT PRIMARY KEY,setting_value TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')),updated_by TEXT);
    CREATE TABLE IF NOT EXISTS settings_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,setting_key TEXT NOT NULL,old_value TEXT,new_value TEXT NOT NULL,changed_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')),changed_by TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS scheduler_state(job_key TEXT PRIMARY KEY,last_started_at TEXT,last_completed_at TEXT,last_status TEXT,last_error TEXT);
    CREATE TABLE IF NOT EXISTS node_health_runs(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL UNIQUE,cluster_id TEXT NOT NULL REFERENCES clusters(id),snapshot_ts TEXT NOT NULL,collected_at TEXT NOT NULL,family_errors_json TEXT NOT NULL DEFAULT '{}',node_count INTEGER NOT NULL DEFAULT 0,drive_count INTEGER NOT NULL DEFAULT 0);
    CREATE INDEX IF NOT EXISTS idx_node_health_runs_cluster_ts ON node_health_runs(cluster_id,snapshot_ts DESC);
    CREATE TABLE IF NOT EXISTS node_health_metrics(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL REFERENCES node_health_runs(run_id) ON DELETE CASCADE,cluster_id TEXT NOT NULL REFERENCES clusters(id),node_name TEXT NOT NULL,node_exporter_instance TEXT,minio_instance TEXT,node_exporter_up REAL,minio_scrape_up REAL,cpu_utilization_pct REAL,memory_total_bytes REAL,memory_available_bytes REAL,memory_used_bytes REAL,load1 REAL,drives_online INTEGER,drives_offline INTEGER,UNIQUE(run_id,node_name));
    CREATE TABLE IF NOT EXISTS drive_health_metrics(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL REFERENCES node_health_runs(run_id) ON DELETE CASCADE,cluster_id TEXT NOT NULL REFERENCES clusters(id),node_name TEXT NOT NULL,server TEXT NOT NULL,drive_path TEXT NOT NULL,mountpoint TEXT,total_bytes REAL,used_bytes REAL,free_bytes REAL,availability_errors REAL,io_errors REAL,timeout_errors REAL,filesystem_total_bytes REAL,filesystem_available_bytes REAL,filesystem_free_bytes REAL,filesystem_readonly REAL,filesystem_used_bytes REAL,filesystem_used_pct REAL,UNIQUE(run_id,server,drive_path));
    """)
    for k,v in (("node_interval_hours","4"),("daily_collection_time","00:15")):
        c.execute("INSERT OR IGNORE INTO app_settings(setting_key,setting_value) VALUES(?,?)",(k,v))
    c.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (6)")
def initialize_database() -> None:
    c=get_connection()
    try:
        c.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        c.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (1)")
        _apply_migrations(c); c.commit()
    except Exception:c.rollback(); raise
    finally:c.close()
@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    c=get_connection()
    try:yield c;c.commit()
    except Exception:c.rollback();raise
    finally:c.close()
