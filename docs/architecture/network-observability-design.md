# Network Observability — Data-Source Audit and Design Proposal

**Status:** Design proposal  
**Branch:** `design/network-observability-audit`  
**Base:** `feature/auth-foundation`  
**Baseline reviewed:** 26 November 2026  
**Scope:** Historical network telemetry and dashboard design; no application implementation.

## 1. Executive recommendation

Implement network observability as a separate increment under **Node Infrastructure**, backed initially by customer-managed Prometheus and node_exporter. Extend the existing high-frequency infrastructure telemetry collection and persisted-history architecture; do not add direct node polling or a second telemetry provider.

Start with interface-level counters and derived throughput/error/drop trends. Add interface role classification and aggregation only after the product can safely distinguish physical interfaces, logical interfaces, bonds and their slaves. Never infer client/internal traffic separation from interface names or counters alone.

## 2. Source audit — current integration branch

Reviewed source files on `feature/auth-foundation`:

- `app/collectors/topology_collector.py`
- `app/collectors/node_health.py`
- `app/collectors/prometheus.py`
- `app/database/schema.sql`
- `app/database/persistence.py`
- `app/api/analytics.py`
- `tests/test_infrastructure_telemetry.py`

### Current historical infrastructure collection

The current node-health collector persists timestamped per-cluster collection runs and node/drive records. The topology collector queries Prometheus at the run timestamp, correlates Node Exporter and MinIO instances, and records family-level errors/partial outcomes.

Currently collected historical families include:

- Node Exporter and MinIO scrape availability.
- CPU utilization.
- Memory total, available and used.
- Load average 1 minute.
- MinIO node drive online/offline counts.
- MinIO drive capacity and drive error counters.
- Data-filesystem capacity, availability, read-only state and utilization.

The current performance-series API advertises CPU, memory, load and filesystem utilization. **Network samples are not currently persisted or exposed as historical series.**

## 3. Product placement

Network performance belongs under:

**Node Infrastructure → Network**

It must not be placed under Collection Health. Collection Health remains responsible for collector/scheduler execution, scrape reliability, freshness, collection duration and collection errors.

Recommended navigation/UX:

- Node Infrastructure overview: fleet-level network summary and availability.
- Network tab/workspace: historical network charts and interface inventory.
- Node drill-down: per-interface trends and details.
- Interface detail: RX/TX throughput, packets, errors and drops.

## 4. Phase 1 metric scope

Collect from node_exporter, subject to validation against the deployed exporter version and actual series/labels:

### Primary counters

- Receive bytes: `node_network_receive_bytes_total`
- Transmit bytes: `node_network_transmit_bytes_total`
- Receive packets: `node_network_receive_packets_total`
- Transmit packets: `node_network_transmit_packets_total`
- Receive errors: `node_network_receive_errs_total`
- Transmit errors: `node_network_transmit_errs_total`
- Receive drops: `node_network_receive_drop_total`
- Transmit drops: `node_network_transmit_drop_total`

### Optional metadata, after compatibility audit

- Interface speed.
- Interface information/labels.
- Operational state.
- Duplex.
- Bond/slave relationship.

Do not assume all node_exporter versions expose every metadata metric. Missing metrics should be represented as unsupported/unavailable, not zero.

## 5. Derived metrics and semantics

Prometheus counters must be converted using rate semantics over a bounded window; do not subtract counters across persisted snapshots.

Recommended derived series:

- RX bytes/sec.
- TX bytes/sec.
- RX bits/sec and TX bits/sec (presentation units derived from byte rates).
- RX packets/sec.
- TX packets/sec.
- RX error rate.
- TX error rate.
- RX drop rate.
- TX drop rate.

Use a documented rate window consistent with collection cadence. Handle counter resets and absent samples using Prometheus `rate()` semantics. Persist only finite, valid values.

Do not calculate interface utilization percentage until speed is known and trustworthy. If link speed is unknown, show throughput without utilization percentage.

## 6. Interface identity and filtering

Persist stable cluster/node/interface identity. The display name alone must not be treated as globally unique.

Initial exclusions should be conservative and explicit:

- Loopback should be excluded from default aggregate views.
- Interfaces with no usable counters should be shown as unavailable or excluded from charts with an explanation.
- Do not automatically exclude interfaces based on name patterns such as `ens`, `eth`, `bond`, `vlan`, or `enp`.

Avoid double counting:

- Physical NICs and logical bonds may both expose counters.
- Bond slaves and the bond master must not be aggregated together.
- VLANs may represent a subset of parent traffic.
- Bridge interfaces may overlap with physical-device traffic.

Phase 1 should provide **per-interface series** and a conservative node-level view only where the selected interface set is explicitly defined and non-overlapping.

## 7. Role classification — separate follow-up

The Charter requires configurable roles such as:

- Client/public.
- Cluster/internal.
- Shared client and cluster.
- Other.
- Excluded.

Classification must be administrator-controlled, per cluster, with node overrides available if necessary. Interface names are not reliable role indicators.

For shared interfaces, show total traffic only. Do not manufacture client/internal split values.

Discovery and classification must follow the approved lifecycle: Discover → Review → Approve → Monitor. Newly discovered interfaces must not silently enter approved aggregates.

## 8. Persistence proposal

Prefer an additive schema migration and a dedicated interface telemetry table rather than widening the existing node or drive metric tables.

Proposed logical fields:

- run_id
- cluster_id
- node_name
- interface_name
- interface_type/metadata (nullable and only when supported)
- sample timestamp
- RX/TX byte rate
- RX/TX packet rate
- RX/TX error rate
- RX/TX drop rate
- optional link speed/state
- metric availability/quality indicators

Keep raw Prometheus counters out of the historical table unless a concrete troubleshooting requirement justifies them. The analytics layer should persist derived rates with their timestamp and collection quality.

This is a proposal only; the exact schema, indexes, cardinality and migration need design review before implementation.

## 9. Collection and retention

- Reuse the existing configurable high-frequency telemetry cadence.
- Reuse existing cluster connection/binding and authentication paths.
- Collect network telemetry as an independently reported metric family so network failure does not invalidate unrelated node/drive families.
- Respect existing detailed telemetry retention.
- Do not add a separate scheduler or direct polling service.
- Keep collection bounded: avoid querying every interface with an unbounded label set.
- Validate the number of interfaces and sample volume across representative clusters before setting limits.

## 10. API proposal

Extend the existing cluster node-performance API family with a network series endpoint, subject to the API inventory review.

Possible shape:

`GET /api/analytics/clusters/{cluster_id}/network/performance-series`

Parameters should follow existing series API conventions:

- hours or start/end timestamps.
- optional node filter.
- optional interface filter.
- bounded range within configured telemetry retention.

Response should include:

- selected time range.
- sample/coverage information.
- available nodes/interfaces.
- per-interface time series.
- aggregate statistics where aggregation is safe.
- supported metric list.
- data-quality/coverage warnings.

API details and naming must be checked against the current API inventory before implementation.

## 11. Dashboard proposal

### Network overview

- Fleet RX/TX throughput trend.
- Node comparison (only when interface selection is consistent).
- Interface availability/coverage.
- Top interfaces by RX and TX.
- Error/drop trend summary.

### Node/interface drill-down

- RX throughput.
- TX throughput.
- RX/TX packets/sec.
- RX/TX error rate.
- RX/TX drop rate.
- Link speed/utilization only when reliable metadata is available.

Chart behavior:

- Consistent time-range controls with existing infrastructure graphs.
- Clear units (bytes/sec, bits/sec, packets/sec).
- Gaps remain gaps; do not interpolate missing telemetry as zero.
- Clearly distinguish unavailable metrics from actual zero.
- Preserve existing filters and navigation.

## 12. Regression and quality gates

Required before implementation PR:

- Verify integration branch and exact base SHA.
- Confirm existing node performance-series APIs and collection behavior.
- Confirm schema migration version and migration discipline.
- Confirm existing Node Infrastructure and Collection Health separation.
- Review query cardinality and bounded response sizes.
- Test counter resets, missing interfaces, duplicate/overlapping interfaces and partial family failures.
- Test retention cleanup.
- Test node/interface filters and range limits.
- Test API authorization.
- Test frontend navigation and empty/error/loading states.
- CI on exact feature PR head.
- No deployment until explicit user approval.

## 13. Suggested incremental delivery

**Increment N1 — Interface telemetry collection and persistence**
- Collect and persist rates/counters per node/interface.
- Add independent family error/coverage reporting.
- Add schema migration and tests.
- No dashboard yet.

**Increment N2 — API and historical charts**
- Add bounded network series API.
- Add Network workspace and node/interface drill-down.
- Add filters and chart states.
- Regression-test existing infrastructure pages.

**Increment N3 — Interface inventory and classification**
- Discovery/review/approval.
- Role assignment and node overrides.
- Safe non-overlapping aggregation.
- Client/internal/shared views only when classifications support them.

## 14. Decisions required before coding

1. Approve Network Observability as the next feature.
2. Confirm whether Phase N1/N2 should initially be per-interface only, with role classification deferred to N3 (recommended).
3. Confirm whether node-level aggregate charts should be limited to explicitly approved interfaces or omitted initially (recommended: omit unsafe aggregates; offer per-interface and top-interface views first).

## 15. Acceptance criteria for Phase N1

- Network metrics are collected through the configured Prometheus connection.
- Samples are associated with correct cluster, node and interface.
- Derived rates handle counter resets and missing samples correctly.
- Network collection failures are isolated and reported independently.
- Existing CPU/memory/load/drive/filesystem collection remains unaffected.
- Schema migration is additive and tested for rollback/upgrade safety.
- Retention removes expired network samples consistently.
- Regression suite and CI pass on the exact PR head.
- No VM deployment or merge without explicit approval.
