# MinIO Multi-Tenant Analytics

A lightweight analytics dashboard for multi-location, multi-cluster MinIO environments.

## Goals

- Collect daily cluster and bucket metrics from Prometheus.
- Maintain bucket inventory independently of daily metric collection.
- Map buckets to customers/tenants through an administrative UI.
- Preserve historical tenant attribution at snapshot time.
- Present fleet, location, cluster, tenant, bucket, and collection-health analytics.
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

The collector makes at most two attempts per cluster (initial attempt plus one retry). It persists successful metric families even if another family fails, and records each cluster's outcome in `collection_runs` as `success`, `partial`, or `failed`. A non-zero process exit status indicates that at least one cluster did not complete successfully.

The default timestamp is intended for manual validation. The production systemd timer must explicitly calculate and pass the intended midnight-IST snapshot timestamp; do not use the timer's execution time as the snapshot time.

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

## Data and safety principles

- Store measurements in bytes; convert to TiB only for display.
- Identify a bucket by both cluster ID and bucket name.
- Treat missing metrics and failed Prometheus requests as unavailable, never as zero.
- Keep bucket inventory and tenant mappings even when a bucket is temporarily absent from a scrape.
- Store tenant attribution with each daily bucket snapshot so reassignment does not rewrite history.
- Use SQLite WAL mode and take regular database backups.

## Status

Initial database schema, Prometheus client, configuration loader, and cluster collector are in the repository. Lab deployment and collector validation are in progress.
