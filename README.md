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

- Python 3.11+
- FastAPI
- SQLite (WAL mode)
- HTML, CSS, and vanilla JavaScript
- Chart.js
- Prometheus HTTP API
- systemd service/timer for scheduled collection

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
data/              Local SQLite database (not committed)
logs/              Local application and collector logs (not committed)
```

## Development setup

1. Install Python 3.11 or newer.
2. Create and activate a virtual environment.
3. Install dependencies with `pip install -r requirements.txt`.
4. Copy `config/locations.example.yaml` to a local configuration file and fill in your environment-specific Prometheus endpoints.
5. Start the API with `uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload`.

The initial scaffold is intentionally small. Collector queries, database schema, authentication, APIs, and dashboard modules will be added incrementally and validated against the lab environment.

## Data and safety principles

- Store measurements in bytes; convert to TiB only for display.
- Identify a bucket by both cluster ID and bucket name.
- Treat missing metrics and failed Prometheus requests as unavailable, never as zero.
- Keep bucket inventory and tenant mappings even when a bucket is temporarily absent from a scrape.
- Store tenant attribution with each daily bucket snapshot so reassignment does not rewrite history.
- Keep secrets, live endpoints, customer data, database files, logs, and virtual environments out of Git.

## Status

Project scaffold initialised. The next milestone is the SQLite schema and validated Prometheus collectors.
