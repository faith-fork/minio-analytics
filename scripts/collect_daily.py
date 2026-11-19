from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone

from app.collectors.orchestrator import collect_all
from app.config.loader import load_locations


def _parse_snapshot(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Snapshot time must be ISO-8601, for example 2026-11-19T18:30:00Z"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError(
            "Snapshot time must include a timezone, such as Z or +05:30"
        )
    return parsed.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect and persist MinIO cluster and bucket daily metrics."
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Location YAML path (defaults to MINIO_ANALYTICS_CONFIG).",
    )
    parser.add_argument(
        "--snapshot-at",
        type=_parse_snapshot,
        default=None,
        help="Timezone-aware ISO-8601 snapshot timestamp; defaults to current UTC.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=2,
        help="Attempts per cluster, including the initial attempt (default: 2).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    args = parser.parse_args()

    if args.max_attempts < 1 or args.max_attempts > 2:
        parser.error("--max-attempts must be 1 or 2; the default is one retry")

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    locations = load_locations(args.config)
    snapshot_ts = args.snapshot_at or datetime.now(timezone.utc)
    results = collect_all(
        locations=locations,
        snapshot_ts=snapshot_ts,
        max_attempts=args.max_attempts,
    )
    print(json.dumps({
        "snapshot_ts": snapshot_ts.isoformat(),
        "results": results,
        "clusters_total": len(results),
        "clusters_success": sum(r["status"] == "success" for r in results),
        "clusters_partial": sum(r["status"] == "partial" for r in results),
        "clusters_failed": sum(r["status"] == "failed" for r in results),
    }, indent=2, sort_keys=True))

    return 0 if all(r["status"] == "success" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
