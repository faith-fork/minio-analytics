# Network Observability — N1 Lab Validation & N2 Design Checkpoint

**Date:** 27 November 2026  
**Integration branch:** `feature/auth-foundation`  
**N1 implementation:** PR #67 — merged  
**N1 lab validation:** Confirmed by user-provided SQLite output  
**Status:** N1 accepted for lab validation; N2 design proposed

## 1. N1 lab validation evidence

The lab deployment is running the merged N1 implementation. The user verified the following against `/data/minio-analytics/database/minio_analytics.db`.

### Migration
The `schema_version` table reports versions 14, 13, 12, 11 and 10, confirming migration v14 is applied.

### Schema
The `network_health_metrics` table exists with:
- `run_id` linked to `node_health_runs` with ON DELETE CASCADE.
- `cluster_id` linked to `clusters`.
- Node and Prometheus instance identity.
- Interface name.
- RX/TX bytes/sec, packets/sec, errors/sec and drops/sec.
- Unique constraint on `(run_id, instance, interface_name)`.
- Indexes on `(cluster_id, run_id)` and `(cluster_id, node_name, interface_name)`.

### Persisted telemetry
The lab query returned **8 records** in one collection run:
- Cluster: `miniotestcl02`
- Four nodes: `minioTestNode01CL2` through `minioTestNode04CL2`
- Two interfaces per node: `ens3` and `ens4`
- No loopback interface
- RX/TX rates populated; zero values were observed for some directional metrics and for error/drop counters.

This validates schema creation, collector execution, per-node/per-interface persistence, run association, and metric-field population. It does **not yet** validate longer-term history, retention cascade, API behavior, chart rendering, or network-role semantics.

## 2. N1 acceptance status

- [x] Migration v14 applied in lab
- [x] Table and expected columns present
- [x] Expected indexes present
- [x] Collection samples persisted
- [x] Four nodes represented
- [x] Two interfaces represented per node
- [x] Loopback absent
- [x] RX/TX rate fields populated
- [x] Errors and drops persisted (observed zero values)
- [x] Samples associated with a node-health run
- [ ] Retention cascade explicitly tested in lab (automated test remains the primary gate)
- [ ] Longer-duration sampling validated

**N1 status: PASS for functional lab collection and persistence.** Remaining items are follow-up confidence checks, not blockers to designing N2.

## 3. Product placement

Network observability belongs under **Node Infrastructure**, not Collection Health.

The existing Node Infrastructure workspace has these primary sections:
- Overview
- Node Health & Performance
- Drives & Filesystems

N2 should add **Network** as a peer section/tab in this workspace. Collection Health remains focused on collection execution, scrape reliability, freshness, duration, and errors.

N2 must not implement interface role classification, discovery approval, or traffic-role aggregation. Those remain N3.

## 4. N2 scope — API and historical UI

### API

Proposed endpoint:

`GET /api/analytics/clusters/{cluster_id}/network/performance-series`

Follow established cluster analytics API authentication, authorization, range, response, and error conventions.

Supported filters:
- Time range: existing preset convention and/or bounded start/end timestamps.
- Optional node name.
- Optional interface name.
- Optional combination of node and interface filters.

The API must enforce a maximum query window compatible with detailed telemetry retention and avoid unbounded result payloads. Return explicit time-range and coverage metadata.

Suggested response model:
- `cluster_id`
- `range_start`, `range_end`
- `sample_interval_minutes` (if known)
- `sample_count` / coverage information
- available nodes and interfaces for the selected range
- series grouped by node and interface
- per-series samples with timestamp and the eight persisted metrics
- summary statistics for the selected series/range
- metric availability and data-quality warnings

Do not invent missing samples as zero. Preserve SQL NULL as unavailable. Gaps must remain gaps.

### UI

Add a **Network** section within Node Infrastructure.

Initial layout:
1. Shared time-range controls, matching existing infrastructure trend UX.
2. Filters for node and interface.
3. Per-interface historical charts:
   - RX and TX throughput (bytes/sec; optionally display bits/sec through presentation conversion)
   - RX and TX packets/sec
   - RX and TX errors/sec
   - RX and TX drops/sec
4. Interface table showing node, interface, selected-range RX/TX summaries, packet summaries, error/drop summaries, and sample coverage.
5. Empty, loading, partial-data, and API-error states.

Avoid rendering an unbounded number of chart canvases. Prefer a filterable interface table with a selected-interface detail chart, and optionally a small number of clearly labeled top-interface views only when selection semantics are explicit and bounded.

## 5. Aggregation and semantic guardrails

N2 is **per-interface telemetry only**.

Do not:
- Sum all interfaces into a cluster-wide RX/TX value by default.
- Sum bond masters and their physical slaves.
- Sum VLAN and parent-interface counters.
- Infer client/public vs cluster/internal roles from interface names.
- Present role-level traffic splits.
- Calculate link utilization without validated speed metadata.
- Convert missing/unsupported metrics to zero.

Any aggregate view must be deferred until N3 inventory classification can define approved, non-overlapping interface sets. If N2 offers comparison, label it as a comparison of individual interfaces, not a cluster total.

## 6. N2 implementation sequence

1. Audit current API route conventions, node performance-series implementation, range validation, telemetry retention, and frontend chart/filter patterns on the integration branch.
2. Write/confirm endpoint contract and query strategy.
3. Implement bounded API query with node/interface filters and coverage metadata.
4. Add API tests for authorization, range limits, filtering, NULL handling, empty ranges, and payload bounds.
5. Add the Node Infrastructure Network section and UI states.
6. Add frontend tests for navigation, filter changes, chart/table state, and empty/partial/error cases.
7. Run the full regression suite and CI on the exact PR head.
8. Review the complete diff, migration impact (N2 should require no schema change), and branch ancestry.
9. Provide exact commit and lab validation instructions. No deployment or merge without explicit user approval.

## 7. N2 acceptance criteria

- Network appears as a peer section under Node Infrastructure.
- Network is not mixed into Collection Health.
- API returns bounded historical series from `network_health_metrics`.
- Node and interface filters work individually and together.
- Time-range controls follow existing infrastructure conventions.
- Per-interface RX/TX throughput, packet, error and drop trends are available.
- Summary table has clear units and coverage.
- Missing metrics remain unavailable; missing samples are not zero-filled.
- No unsafe cross-interface aggregation or inferred roles.
- Authentication/authorization and range limits are enforced.
- Empty, loading, partial and error states are handled.
- Existing Node Infrastructure, Collection Health, Drives & Filesystems, Storage Topology, cluster overview, and existing APIs regressions pass.
- Exact PR-head CI passes.
- Lab deployment and browser validation remain user-owned and require explicit release approval.

## 8. N3 boundary

N3 remains a separate feature increment for interface inventory and classification:
- Discover interface metadata and relationships where supported.
- Administrator review and approval lifecycle.
- Cluster defaults and optional node overrides.
- Roles: client/public, cluster/internal, shared, other, excluded.
- Bond/VLAN/bridge/physical relationship awareness.
- Safe aggregation using approved, non-overlapping interfaces only.
- Preserve historical records when an interface is missing or excluded.

No N3 behavior is part of the N2 implementation.
