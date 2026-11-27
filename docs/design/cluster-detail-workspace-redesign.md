# Cluster Detail Workspace Redesign

- **Branch:** `feature/cluster-detail-workspace`
- **Base:** `feature/auth-foundation`
- **Baseline commit:** `50a610f879c97cb008ecc2e9d16a20c66a4bad04`
- **Status:** Approved scope; implementation in progress
- **Date:** 27 November 2026

## 1. Goal

Refactor the Cluster Detail experience into four clearly separated workspaces, reducing the current long mixed dashboard and improving operational scanability.

1. **Infrastructure Status** — current cluster state and entry points to Node Infrastructure and Storage Topology.
2. **Capacity & Forecast** — capacity, quota, growth and time-to-full history.
3. **Object & Bucket Analysis** — object, version and delete-marker trends plus date-selectable object-size distribution.
4. **Daily Snapshots** — dedicated snapshot history and inspection.

Use the compact global time-range toolbar standard established by D1 for applicable historical graphs. Snapshot selection is a separate date-based control because it selects a stored daily record, not a telemetry time window.

## 2. Current implementation findings

- Cluster detail currently renders all sections in a single page in `showCluster()` in `app/static/app.js`.
- Current sections are Infrastructure status, Capacity & forecast, Object & bucket analytics, and a Daily snapshots link.
- Infrastructure status currently contains a small Cluster health panel showing online/offline nodes, estimated growth, snapshot date and metric availability; the requested KPI dashboard can replace this panel.
- The existing Node Infrastructure and Storage Topology navigation cards must be preserved.
- Capacity & Forecast has existing daily series for raw capacity, quota, growth and days-to-full.
- Object analytics currently includes object trend and a latest-snapshot object-size histogram.
- `bucket_daily_metrics` already has `version_count`, `delete_marker_count`, `object_size_distribution_json` and `version_count_distribution_json`; version/delete-marker totals are currently persisted as NULL by the collector.
- The existing object-size distribution API aggregates the latest available snapshot only. The underlying per-day histogram is already stored in `bucket_daily_metrics`, enabling a date-specific API without re-collecting historical data.
- Current bucket collector queries object count and size/version distributions, but not total version or delete-marker counts.
- Prometheus supports bucket-level total versions (including delete markers) and delete-marker counts; implement using supported metric families and deduplicate replicated series carefully. Missing metrics must remain unavailable, never zero.
- Current UI and API data is daily snapshot-based. Trends must explicitly communicate daily granularity and data coverage.

## 3. Proposed Infrastructure Status KPIs

### Cluster & inventory
- Cluster status
- Backend
- Buckets
- Objects

### Storage capacity
- Total usage
- EC data/parity
- Disks online
- Disks offline
- Total capacity
- Used
- Available
- Usage percentage

### Versioning & replication
- Total versions (definition: includes delete markers)
- Total delete markers
- Buckets with replication rules configured

### Availability & growth
- Online nodes
- Offline nodes
- 30-day estimated growth

Avoid an unstructured wall of cards. Group compactly into visually subtle KPI groups and use responsive grid layout. Remove the old Cluster Health card because its useful information is represented by KPIs. Keep Node Infrastructure and Storage Topology entry cards beneath the KPI groups.

Use honest missing-data states. Metric unavailability must not be represented as zero or as a healthy state.

## 4. Replication-enabled bucket count — technical limitation

Prometheus replication activity metrics are not equivalent to proof that a bucket has a configured replication rule. A zero-activity bucket may still have replication configured.

Accurate rule detection requires inspecting each bucket's replication configuration through an authorized MinIO/S3 API (for example, GetBucketReplication). The current integration baseline has Prometheus connection/auth configuration but no cluster S3 credential/configuration integration for this read operation.

**Do not use activity metrics as a misleading proxy.** The KPI should display an explicit unavailable/not configured state until a secure read-only credential/API capability is implemented or verified. This feature must not introduce plaintext credentials or bypass the Charter's secure credential handling.

## 5. Capacity & Forecast workspace

Preserve existing charts and calculations:
- Capacity trend (used/free/total)
- Bucket quota trend
- Growth trend
- Days-to-full forecast

Move the current top-of-page raw capacity/raw free/days-to-full cards into this workspace or consolidate them with its chart context so capacity data is not duplicated in Infrastructure Status. Do not change forecasting semantics or existing retention/coverage constraints without a separate design review.

## 6. Object & Bucket Analysis workspace

Provide:
- Object count trend
- Version count trend (including delete markers)
- Delete-marker trend
- Object-size distribution for a selected daily snapshot date

Historical trend data uses daily snapshots. Reuse the global time-range control where supported, bounded by actual stored data and retention.

### Historical object-size distribution

- Date picker selects a date with an available bucket snapshot/distribution.
- Default to the latest available date.
- Display snapshot date/time.
- Graph/Table toggle remains.
- Preserve bucket coverage and partial/unavailable semantics.
- Do not compute percentages or totals when coverage is incomplete.
- API should accept a date and return data for that exact date; never silently fall back to latest if the requested date is missing.

## 7. Daily Snapshots workspace

Replace the bottom-of-dashboard link/card with a dedicated workspace tab/section. Preserve existing snapshot history filtering, pagination and collection-status semantics. Provide a route/action to inspect a selected snapshot if supported by existing APIs; do not invent snapshot details or present daily rows as fully available when collection was partial.

## 8. API/data implementation

- Add collector support for total bucket versions and delete markers using the verified metric names supported by the current collector's Prometheus source.
- Persist values in the existing nullable columns; avoid redundant schema unless the audit demonstrates a requirement.
- Extend cluster analytics daily series with complete-coverage-aware aggregate versions/delete markers.
- Extend the object-size-distribution endpoint with an optional snapshot date and exact-date behavior.
- Add/extend tests for metric deduplication, missing metrics, aggregate coverage, date selection, no silent fallback, and API authorization.
- KPI current values must derive from a clearly defined latest successful snapshot/collection and report freshness.

## 9. UX standards

- Four tabs/workspaces with clear names and consistent navigation.
- Keep compact, modern, responsive layouts.
- Historical charts use the D1 global time-range control.
- Date-specific snapshot distribution uses a compact contextual date picker.
- Avoid unnecessary vertical rows and duplicated metrics.
- Provide loading, empty, partial and error states.
- Keep accessible control labels and keyboard behavior.

## 10. Acceptance criteria

- [ ] Cluster detail is organized into four workspaces.
- [ ] Infrastructure Status replaces Cluster Health with grouped KPI cards.
- [ ] Node Infrastructure and Storage Topology links remain functional.
- [ ] Capacity/forecast charts and calculations remain unchanged in meaning.
- [ ] Object trend remains and versions/delete-marker trends are added.
- [ ] Version/delete-marker metrics are persisted, aggregated with coverage and charted daily.
- [ ] Object-size distribution can be requested for a selected historical snapshot date.
- [ ] Exact-date requests never silently show a different snapshot.
- [ ] Daily Snapshots has a dedicated workspace and preserves existing capabilities.
- [ ] Replication-enabled bucket count is not fabricated; it remains explicitly unavailable until configuration can be safely inspected.
- [ ] Responsive, loading, empty, partial and error states are covered.
- [ ] Regression tests preserve cluster navigation, reports, Node Infrastructure, Storage Topology, capacity charts, histogram graph/table toggle, and snapshots.
- [ ] CI passes, complete diff is reviewed, and lab validation is completed before merge.
- [ ] No deployment or merge occurs without explicit user approval.

## 11. Delivery approach

Implement on this feature branch, starting from the verified integration commit. Keep schema changes additive and migration-safe. Review the complete diff and test on CI. Provide exact lab deployment instructions only after implementation, review and CI gates pass. The user performs VM deployment and browser/runtime validation.
