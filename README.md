# MinIO Multi-Tenant Analytics

A lightweight analytics dashboard for multi-location, multi-cluster MinIO environments.

## Goals

- Collect daily cluster, bucket, node, drive, pool, and erasure-set metrics from Prometheus.
- Maintain bucket inventory independently of daily metric collection.
- Map buckets to customers/tenants through an administrator-only UI, including bulk assignment.
- Preserve historical tenant attribution at snapshot time and audit every ownership change.
- Provide authenticated administrator and read-only viewer experiences.
- Present fleet, cluster topology/health, tenant, bucket, and collection-health analytics.
- Keep Prometheus queries out of the interactive dashboard path; the UI reads historical data from SQLite.

## Initial technology choices

- Python 3.12.9 (lab baseline; system Python is not modified)
- FastAPI
- SQLite (WAL mode)
- HTML, CSS, and vanilla JavaScript
- Chart.js
- Prometheus HTTP API
- systemd service/timer for scheduled collection

## Deployment paths

- Application and virtual environment: `/opt/minio-analytics`
- Persistent application data root: `/data/minio-analytics`
- SQLite database: `/data/minio-analytics/database/minio_analytics.db`
- Database backups: `/data/minio-analytics/backups`
- Application/collector logs: `/data/minio-analytics/logs`
- Exports: `/data/minio-analytics/exports`

The database location can be overridden with the `MINIO_ANALYTICS_DB` environment variable.

## Project layout

```text
app/
  api/             API route modules
  collectors/      Prometheus and snapshot collection
  config/          Configuration loading and validation
  database/        SQLite schema and database access
  services/        Analytics and capacity calculations
  static/          Frontend assets
scripts/           Daily, manual, and backfill collection commands
config/            Safe example configuration
```

Runtime data, logs, virtual environments, secrets, live endpoints, and customer data must not be committed to Git.

## Lab environment

- OS: Rocky Linux 10.0 (Red Quartz)
- Python: 3.12.9
- CPU: 8 vCPUs
- RAM: 7.5 GiB
- Swap: 5 GiB
- Root filesystem: 44 GB
- Dedicated data filesystem: 50 GB mounted at `/data`

## Development setup

From `/opt/minio-analytics`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy `config/locations.example.yaml` to a local configuration file and add environment-specific Prometheus endpoints only on the VM. Do not commit the populated configuration.

Start the API during development with:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

## Manual daily collection

The collector can be run manually from the application root after creating the local `config/locations.yaml` file:

```bash
source .venv/bin/activate
python -m scripts.collect_daily --config config/locations.yaml
```

By default, the snapshot timestamp is the current UTC time. To backfill or test a specific snapshot, pass an explicit timezone-aware timestamp:

```bash
python -m scripts.collect_daily \
  --config config/locations.yaml \
  --snapshot-at 2026-11-19T18:30:00Z
```

The default collection source is SQLite: enabled Prometheus connections, locations, clusters, TLS verification settings, and identity-label bindings are read from the database. An explicit `--config` path selects the legacy YAML source for manual rollback/testing. The collector makes at most two attempts per cluster (initial attempt plus one retry). It persists successful metric families even if another family fails, and records each cluster's outcome in `collection_runs` as `success`, `partial`, or `failed`. A non-zero process exit status indicates that at least one cluster did not complete successfully.

The default timestamp is intended for manual validation. The production systemd timer must explicitly calculate and pass the intended midnight-IST snapshot timestamp; do not use the timer's execution time as the snapshot time.

## Prometheus connection configuration migration

Prometheus connection metadata can be imported from the existing location YAML into SQLite without changing the daily collector's configuration source.

Preview the import first:

```bash
source .venv/bin/activate
python -m scripts.import_prometheus_config --config config/locations.yaml
```

Apply the import only after reviewing the preview:

```bash
python -m scripts.import_prometheus_config --config config/locations.yaml --apply
```

The import is idempotent and preserves existing location and cluster IDs. It stores each location's Prometheus endpoint and associates its clusters with the discovered identity label/value. Daily collection and scheduled node-health collection now read enabled connections and cluster bindings from SQLite. An explicit `--config` argument to `scripts.collect_daily` retains the YAML-based path for controlled rollback. Historical backfill remains explicitly YAML-driven. No live endpoint, credential, or populated configuration file should be committed.

SQLite schema version 7 adds `prometheus_connections` and `cluster_prometheus_bindings`. TLS verification is enabled by default for imported endpoints. Use `--no-verify-tls` only for a deliberately configured lab endpoint with a certificate that cannot be validated.

## Historical Prometheus backfill

Prometheus history can be imported into SQLite using the dedicated backfill command. The default imports the previous 60 completed IST dates (ending yesterday), oldest first:

```bash
source .venv/bin/activate
python -m scripts.backfill_history --config config/locations.yaml --days 60 --dry-run
```

Start with `--dry-run` to validate Prometheus coverage without changing SQLite. If the result is healthy, create a database backup and run the same command without `--dry-run`:

```bash
python -m scripts.backup_database
python -m scripts.backfill_history --config config/locations.yaml --days 60
```

Use `--days 30` for a 30-day import, or specify an inclusive end date with `--end-date YYYY-MM-DD`. The default end date is yesterday in Asia/Kolkata, avoiding interference with the current day's scheduled snapshot. Re-running the backfill is safe: existing daily metric rows are not overwritten. Historical bucket inventory updates preserve current tenant assignments and active status; buckets found only in historical data are added as inactive inventory. Historical tenant attribution is left NULL because current ownership must not be projected backwards. Missing historical quota metrics remain NULL, not zero. Each cluster/date result is recorded in `collection_runs` with mode `historical_backfill`.

Prometheus retention must cover the requested dates. The cluster growth calculations also use a 30-day lookback, so the oldest dates may have unavailable growth estimates if the required lookback is outside retention.

## Scheduled collection and SQLite backups

Systemd unit files are provided under `systemd/`:

- `minio-analytics-collect.timer`: daily at 00:15 Asia/Kolkata; collection queries Prometheus at midnight IST for the current local date.
- `minio-analytics-backup.timer`: daily at 00:45 Asia/Kolkata; creates a consistent SQLite online backup and retains the latest 14 days by age.

Install on the lab VM after pulling the repository:

```bash
install -d -m 0750 /data/minio-analytics/{database,backups,logs,exports}
install -m 0600 systemd/minio-analytics-collect.service /etc/systemd/system/
install -m 0644 systemd/minio-analytics-collect.timer /etc/systemd/system/
install -m 0600 systemd/minio-analytics-backup.service /etc/systemd/system/
install -m 0644 systemd/minio-analytics-backup.timer /etc/systemd/system/
systemctl daemon-reload
```

Validate the units before enabling timers:

```bash
systemd-analyze verify /etc/systemd/system/minio-analytics-collect.service /etc/systemd/system/minio-analytics-collect.timer /etc/systemd/system/minio-analytics-backup.service /etc/systemd/system/minio-analytics-backup.timer
```

Enable both schedules only after a successful manual run and backup test:

```bash
systemctl enable --now minio-analytics-collect.timer minio-analytics-backup.timer
systemctl list-timers --all | grep minio-analytics
```

Inspect executions with `journalctl -u minio-analytics-collect.service` and `journalctl -u minio-analytics-backup.service`. The collection service runs as root because the current lab deployment and protected local configuration are root-owned; adjust `User`, `Group`, file ownership, and directory permissions together if a dedicated service account is introduced.


## Web API authentication foundation

The FastAPI application uses SQLite-backed users and signed, HTTP-only session cookies.

- Roles are `admin` and `viewer`.
- Passwords are hashed with PBKDF2-HMAC-SHA256; plaintext passwords are never stored.
- Sessions expire after 8 hours.
- Inactive users are rejected on every authenticated request.
- The initial user is created explicitly with the CLI; there is no default username or password.
- The browser-facing application must use HTTPS. The secure-cookie flag defaults to enabled.

### Configure the session secret

Generate a unique secret on the VM and keep it outside Git:

```bash
umask 077
openssl rand -hex 32
```

Set the generated value in the application service environment as `MINIO_ANALYTICS_SESSION_SECRET`. Do not paste it into source code, README files, or shell history.

For an isolated HTTP-only lab test, set `MINIO_ANALYTICS_COOKIE_SECURE=false` in the current shell. Leave it unset (secure cookies enabled) when serving the app through HTTPS.

### Create the first administrator

From `/opt/minio-analytics`:

```bash
source .venv/bin/activate
python -m scripts.create_user --username admin --role admin
```

The script prompts twice for a password of at least 12 characters. It does not accept passwords as command-line arguments.

Create additional read-only users with:

```bash
python -m scripts.create_user --username analyst1 --role viewer
```

### Run the web application with systemd (lab deployment)

A systemd unit is provided at `systemd/minio-analytics-web.service`. It loads the persistent session secret from `/etc/minio-analytics/web.env`, starts Uvicorn on TCP port 8001, restarts after unexpected failures, and keeps application data writable only under `/data/minio-analytics`.

Install and validate the unit:

```bash
install -m 0600 systemd/minio-analytics-web.service /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/minio-analytics-web.service
systemctl daemon-reload
```

Before enabling it, confirm `/etc/minio-analytics/web.env` exists, is owned by root, has mode 0600, contains the persistent `MINIO_ANALYTICS_SESSION_SECRET`, and has `MINIO_ANALYTICS_COOKIE_SECURE=false` only for the current HTTP lab deployment. Do not regenerate the secret on restart.

Start and inspect:

```bash
systemctl enable --now minio-analytics-web.service
systemctl status minio-analytics-web.service
journalctl -u minio-analytics-web.service -n 50 --no-pager
curl -s http://127.0.0.1:8001/health
```

The supplied unit runs as root to match the current root-owned lab installation, protected environment file, and data directories. This is a lab convenience, not the recommended production identity. Before production, create a dedicated service account, grant only required read access to application/configuration files and write access to the database/backup paths, bind Uvicorn to loopback behind an HTTPS reverse proxy, and set secure cookies. The unit currently binds to all interfaces for the existing lab access pattern; keep TCP 8001 restricted to trusted networks.

### Run the API

For a temporary lab session, export the secret and start Uvicorn:

```bash
export MINIO_ANALYTICS_SESSION_SECRET="$(openssl rand -hex 32)"
export MINIO_ANALYTICS_COOKIE_SECURE=false
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Use a persistent, root-readable environment file or systemd credential for a long-running deployment; do not generate a new secret on every restart, because that invalidates existing sessions.


### Cluster topology and health

The daily collector also records infrastructure topology from MinIO metrics and Node Exporter:

- Nodes: MinIO metrics-target scrape availability, Node Exporter scrape availability, CPU utilization (five-minute rate), memory, and one-minute load.
- Drives: per-drive MinIO total/used/free bytes and availability/I/O/timeout error counters.
- Filesystems: per-mount total, available, free bytes, read-only state, and utilization for MinIO data mounts.
- Pools and erasure sets: pool inventory derived from discovered sets; set status is retained as the raw metric value, with online/healing drives and read/write quorum.
- Drive identity is cluster + MinIO server + drive path. Filesystem mounts are correlated from `/mnt/datadiskN` to the MinIO path `/mnt/datadiskN/minio`.
- Replicated MinIO gauges are deduplicated by their logical identity and conflicting replicas are treated as a collection error. Missing metrics remain NULL.
- Node Exporter reachability and MinIO metrics-target reachability are shown separately; neither is presented as a substitute for MinIO's own node/erasure health.
- Topology snapshots are stored in dedicated SQLite daily tables and served by `GET /api/analytics/clusters/{cluster_id}/topology`.

### Tenant and bucket management

- `GET /api/tenants` — list active tenants; administrators can include inactive tenants.
- `POST /api/tenants` — create a tenant (administrator).
- `PATCH /api/tenants/{tenant_id}` — update tenant details or status (administrator).
- `GET /api/buckets` — list bucket inventory with optional cluster/tenant filters.
- `PUT /api/buckets/{bucket_id}/tenant` — assign or unassign one bucket (administrator).
- `PUT /api/buckets/bulk-tenant` — assign or unassign up to 500 buckets atomically (administrator).
- `GET /api/buckets/{bucket_id}/history` — read the audit history for a bucket.

Bulk assignment validates the active tenant and every selected active bucket before making changes. The transaction updates current ownership and inserts one audit event per changed bucket. Unchanged assignments do not create duplicate history events. Existing daily snapshot attribution is never rewritten.

### User administration

Administrators can manage local dashboard accounts from the **User administration** section:

- Create users with a unique username, an initial password (minimum 12 characters), and either the `admin` or `viewer` role.
- List accounts and their active status.
- Change a user's role.
- Activate or deactivate accounts.
- Reset a user's password.

Only administrators can access these endpoints and the UI. The last active administrator cannot be demoted or deactivated, and an administrator cannot deactivate their own account. Deactivated users are rejected on their next request because the session identity is checked against SQLite on every authenticated request.

Local accounts are the initial identity provider for the PoC. OIDC federation is a planned future enhancement; do not treat the current local login as an OIDC implementation.

### Browser dashboard

Open `http://<server>:8001/` from a trusted internal network during lab validation. The dashboard provides overview, cluster, tenant, bucket, and collection-health views. Administrators can create tenants and assign buckets; viewers have read-only access.

Chart.js is currently loaded from a CDN, so charts require the browser to reach that CDN. The API and non-chart dashboard data remain served locally.

### Authentication endpoints

- `POST /api/auth/login` — JSON body: `{"username":"admin","password":"..."}`; sets the session cookie.
- `GET /api/auth/me` — returns the current authenticated user and role.
- `POST /api/auth/logout` — clears the session.
- `GET /health` — database health check.
- `GET /docs` — interactive API documentation (keep internal; do not expose publicly).

Login failures return a generic error. User records and role checks are read from SQLite. Analytics and read-only inventory endpoints require authentication; tenant creation, tenant updates, and bucket assignment require the administrator role.

## Data and safety principles

- Store measurements in bytes; convert to TiB only for display.
- Identify a bucket by both cluster ID and bucket name.
- Treat missing metrics and failed Prometheus requests as unavailable, never as zero.
- Keep bucket inventory and tenant mappings even when a bucket is temporarily absent from a scrape.
- Store tenant attribution with each daily bucket snapshot so reassignment does not rewrite history.
- Use SQLite WAL mode and take regular database backups.

## Automated tests

Install the development dependencies into the project virtual environment:

```bash
pip install -r requirements-dev.txt
```

Run the API regression suite:

```bash
pytest -q
```

The tests use a fresh temporary SQLite database per test. They do not connect to Prometheus or modify the configured lab database. Coverage includes authentication, role enforcement, user creation/password reset/deactivation, last-administrator safeguards, tenant and bucket assignment, bulk assignment atomicity/idempotency, assignment history, current tenant aggregation, and preservation of snapshot-time attribution.

## Current implementation status

The lab has validated daily cluster and bucket collection, SQLite persistence and backups, systemd scheduling, authentication and role enforcement, tenant/bucket management (including bulk assignment), all analytics APIs, and the browser dashboard for viewer and administrator workflows. Production hardening, automated regression tests, HTTPS/reverse-proxy deployment, and broader multi-location validation remain before production use.
