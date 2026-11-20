from __future__ import annotations

import argparse
import json

from app.config.loader import load_locations
from app.database.prometheus_config import import_location_configuration


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import existing Prometheus endpoints and cluster identities from YAML into SQLite."
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Location YAML path (defaults to MINIO_ANALYTICS_CONFIG).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the imported configuration to SQLite. Without this flag, perform a read-only preview.",
    )
    parser.add_argument(
        "--no-verify-tls",
        action="store_true",
        help="Disable TLS certificate verification for imported HTTPS endpoints.",
    )
    args = parser.parse_args()

    locations = load_locations(args.config)
    preview = []
    for location in locations:
        preview.append(
            {
                "location_id": location.id,
                "location_name": location.name,
                "prometheus_url": location.prometheus_url,
                "clusters": [
                    {
                        "cluster_id": cluster.id,
                        "cluster_name": cluster.name,
                        "identity_label_name": "cluster",
                        "identity_label_value": cluster.prometheus_label_value,
                    }
                    for cluster in location.clusters
                ],
            }
        )

    if not args.apply:
        print(json.dumps({"mode": "dry_run", "locations": preview}, indent=2))
        print("\nNo database changes made. Re-run with --apply to import.")
        return 0

    result = import_location_configuration(
        locations,
        verify_tls=not args.no_verify_tls,
    )
    print(json.dumps({"mode": "applied", "result": result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
