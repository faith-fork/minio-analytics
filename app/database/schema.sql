PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'viewer')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS locations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS clusters (
    id TEXT PRIMARY KEY,
    location_id TEXT NOT NULL REFERENCES locations(id) ON UPDATE CASCADE,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    labels_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(location_id, name)
);

CREATE TABLE IF NOT EXISTS tenants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Bucket identity is scoped to a cluster: identical names may exist in different clusters.
-- Inventory is retained when a bucket temporarily disappears from Prometheus.
CREATE TABLE IF NOT EXISTS buckets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id TEXT NOT NULL REFERENCES clusters(id) ON UPDATE CASCADE,
    bucket_name TEXT NOT NULL,
    tenant_id INTEGER REFERENCES tenants(id) ON DELETE RESTRICT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    labels_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(cluster_id, bucket_name),
    UNIQUE(id, cluster_id)
);

-- Audit trail for current bucket-to-tenant mapping changes.
CREATE TABLE IF NOT EXISTS bucket_tenant_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket_id INTEGER NOT NULL REFERENCES buckets(id) ON DELETE RESTRICT,
    tenant_id INTEGER REFERENCES tenants(id) ON DELETE RESTRICT,
    changed_at TEXT NOT NULL,
    changed_by TEXT NOT NULL DEFAULT 'system',
    note TEXT
);

CREATE TABLE IF NOT EXISTS cluster_daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    cluster_id TEXT NOT NULL REFERENCES clusters(id) ON DELETE RESTRICT,
    snapshot_ts TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    raw_total_bytes REAL,
    raw_free_bytes REAL,
    usable_total_bytes REAL,
    usable_free_bytes REAL,
    nodes_online INTEGER,
    nodes_offline INTEGER,
    growth_bytes_per_day REAL,
    days_to_full REAL,
    metrics_available INTEGER NOT NULL DEFAULT 1 CHECK (metrics_available IN (0, 1)),
    error_text TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(snapshot_date, cluster_id)
);

CREATE TABLE IF NOT EXISTS bucket_daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    bucket_id INTEGER NOT NULL,
    cluster_id TEXT NOT NULL,
    bucket_name TEXT NOT NULL,
    tenant_id_at_snapshot INTEGER REFERENCES tenants(id) ON DELETE RESTRICT,
    snapshot_ts TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    used_bytes REAL,
    quota_bytes REAL,
    object_count INTEGER,
    version_count INTEGER,
    delete_marker_count INTEGER,
    object_size_distribution_json TEXT NOT NULL DEFAULT '{}',
    version_count_distribution_json TEXT NOT NULL DEFAULT '{}',
    metrics_available INTEGER NOT NULL DEFAULT 1 CHECK (metrics_available IN (0, 1)),
    error_text TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY(bucket_id, cluster_id) REFERENCES buckets(id, cluster_id) ON DELETE RESTRICT,
    UNIQUE(snapshot_date, bucket_id)
);

CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    location_id TEXT REFERENCES locations(id) ON DELETE RESTRICT,
    cluster_id TEXT REFERENCES clusters(id) ON DELETE RESTRICT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'partial', 'failed')),
    attempt INTEGER NOT NULL DEFAULT 1,
    metrics_collected INTEGER NOT NULL DEFAULT 0,
    error_text TEXT,
    details_json TEXT NOT NULL DEFAULT '{}'
);



-- Daily infrastructure topology and health snapshots. Identity is cluster-scoped.
CREATE TABLE IF NOT EXISTS node_daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    cluster_id TEXT NOT NULL REFERENCES clusters(id) ON DELETE RESTRICT,
    node_name TEXT NOT NULL,
    node_exporter_instance TEXT,
    minio_instance TEXT,
    node_exporter_up REAL,
    minio_scrape_up REAL,
    cpu_utilization_pct REAL,
    memory_total_bytes REAL,
    memory_available_bytes REAL,
    memory_used_bytes REAL,
    load1 REAL,
    drives_online INTEGER,
    drives_offline INTEGER,
    snapshot_ts TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    UNIQUE(snapshot_date, cluster_id, node_name)
);

CREATE TABLE IF NOT EXISTS drive_daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    cluster_id TEXT NOT NULL REFERENCES clusters(id) ON DELETE RESTRICT,
    node_name TEXT NOT NULL,
    server TEXT NOT NULL,
    drive_path TEXT NOT NULL,
    mountpoint TEXT,
    total_bytes REAL,
    used_bytes REAL,
    free_bytes REAL,
    availability_errors REAL,
    io_errors REAL,
    timeout_errors REAL,
    filesystem_total_bytes REAL,
    filesystem_available_bytes REAL,
    filesystem_free_bytes REAL,
    filesystem_readonly REAL,
    filesystem_used_bytes REAL,
    filesystem_used_pct REAL,
    snapshot_ts TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    UNIQUE(snapshot_date, cluster_id, server, drive_path)
);

CREATE TABLE IF NOT EXISTS pool_daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    cluster_id TEXT NOT NULL REFERENCES clusters(id) ON DELETE RESTRICT,
    pool_id TEXT NOT NULL,
    erasure_set_count INTEGER,
    online_drives REAL,
    healing_drives REAL,
    snapshot_ts TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    UNIQUE(snapshot_date, cluster_id, pool_id)
);

CREATE TABLE IF NOT EXISTS erasure_set_daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    cluster_id TEXT NOT NULL REFERENCES clusters(id) ON DELETE RESTRICT,
    pool_id TEXT NOT NULL,
    set_id TEXT NOT NULL,
    status_value REAL,
    online_drives REAL,
    healing_drives REAL,
    read_quorum REAL,
    write_quorum REAL,
    snapshot_ts TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    UNIQUE(snapshot_date, cluster_id, pool_id, set_id)
);

CREATE TABLE IF NOT EXISTS topology_daily_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    cluster_id TEXT NOT NULL REFERENCES clusters(id) ON DELETE RESTRICT,
    snapshot_ts TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    family_errors_json TEXT NOT NULL DEFAULT '{}',
    node_count INTEGER NOT NULL DEFAULT 0,
    drive_count INTEGER NOT NULL DEFAULT 0,
    pool_count INTEGER NOT NULL DEFAULT 0,
    erasure_set_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(snapshot_date, cluster_id)
);

CREATE INDEX IF NOT EXISTS idx_node_metrics_date
    ON node_daily_metrics(snapshot_date, cluster_id);
CREATE INDEX IF NOT EXISTS idx_drive_metrics_date
    ON drive_daily_metrics(snapshot_date, cluster_id, node_name);
CREATE INDEX IF NOT EXISTS idx_pool_metrics_date
    ON pool_daily_metrics(snapshot_date, cluster_id);
CREATE INDEX IF NOT EXISTS idx_erasure_set_metrics_date
    ON erasure_set_daily_metrics(snapshot_date, cluster_id, pool_id);

CREATE INDEX IF NOT EXISTS idx_users_active_role ON users(is_active, role);
CREATE INDEX IF NOT EXISTS idx_clusters_location ON clusters(location_id);
CREATE INDEX IF NOT EXISTS idx_buckets_cluster ON buckets(cluster_id);
CREATE INDEX IF NOT EXISTS idx_buckets_tenant ON buckets(tenant_id);
CREATE INDEX IF NOT EXISTS idx_buckets_last_seen ON buckets(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_bucket_tenant_history_bucket_time
    ON bucket_tenant_history(bucket_id, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_cluster_metrics_date
    ON cluster_daily_metrics(snapshot_date, cluster_id);
CREATE INDEX IF NOT EXISTS idx_bucket_metrics_date
    ON bucket_daily_metrics(snapshot_date, cluster_id, bucket_name);
CREATE INDEX IF NOT EXISTS idx_bucket_metrics_tenant_date
    ON bucket_daily_metrics(tenant_id_at_snapshot, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_collection_runs_date
    ON collection_runs(snapshot_date, status);
CREATE INDEX IF NOT EXISTS idx_collection_runs_cluster
    ON collection_runs(cluster_id, started_at DESC);
