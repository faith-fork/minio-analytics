# N1 Implementation Specification — Network Telemetry Collection

**Status:** Implementation-ready proposal (subject to design review)  
**Parent design:** `docs/architecture/network-observability-design.md`  
**Integration baseline:** `feature/auth-foundation` at `ec9e60393dc09aadfecf688875f8e4a3822a98c8`  
**No implementation/deployment included in this document.**

## 1. Implementation approach

Extend the existing high-frequency node-health collection run. Do not introduce a new scheduler job, Prometheus connection path, or service.

The existing topology snapshot collector already creates/reuses a Prometheus client, evaluates all metric families at a common timestamp, isolates family errors, and returns nodes/drives/topology. Network will be another independent family in this snapshot.

N1 must not alter daily topology collection or the daily capacity/bucket collectors.

## 2. Integration points

### Collector
`app/collectors/topology_collector.py`

Add a network-interface data collection family to `TopologySnapshot`. Network collection must be independently error-isolated under `family_errors["network"]`.

Keep the current node-health call using `include_pool_health=False`; network must still be collected for high-frequency telemetry.

### Persistence
`app/collectors/node_health.py`

Persist per-interface samples in the same transaction as the node-health run and node/drive records. Family errors from network must make the run partial, but must not suppress successful CPU, memory, drive or filesystem samples.

### Database
`app/database/database.py`

Add additive schema migration **version 14**. Do not alter existing telemetry tables destructively.

Proposed table: `network_health_metrics`

- `id` primary key.
- `run_id` foreign key to `node_health_runs(run_id)`, cascade delete.
- `cluster_id` foreign key to clusters.
- `node_name`.
- `instance` (full Prometheus instance label).
- `interface_name` (device label).
- `rx_bytes_per_second`.
- `tx_bytes_per_second`.
- `rx_packets_per_second`.
- `tx_packets_per_second`.
- `rx_errors_per_second`.
- `tx_errors_per_second`.
- `rx_drops_per_second`.
- `tx_drops_per_second`.
- Unique constraint on `(run_id, instance, interface_name)`.

Indexes:
- `(cluster_id, run_id)`
- `(cluster_id, node_name, interface_name)`

No link speed, utilization percentage, role, bond/VLAN relationship or interface approval state in N1. Those require inventory discovery and classification.

## 3. Prometheus metrics and PromQL

Use node_exporter network counters, scoped to the configured cluster identity and `job="node_exporter"`.

Metric families:

| Stored field | Prometheus counter |
|---|---|
| RX bytes/s | `node_network_receive_bytes_total` |
| TX bytes/s | `node_network_transmit_bytes_total` |
| RX packets/s | `node_network_receive_packets_total` |
| TX packets/s | `node_network_transmit_packets_total` |
| RX errors/s | `node_network_receive_errs_total` |
| TX errors/s | `node_network_transmit_errs_total` |
| RX drops/s | `node_network_receive_drop_total` |
| TX drops/s | `node_network_transmit_drop_total` |

Each query uses a rate window of **5 minutes** and evaluates at the collector's common snapshot timestamp. The rate window is a fixed initial design choice and should be validated against configurable collection cadence; if cadence is later changed to 1 minute, the 5-minute rate remains intentionally smoothing across several collection intervals.

Conceptual query form:

`rate(node_network_receive_bytes_total{<cluster-selector>,job="node_exporter",device!="lo"}[5m])`

Use the actual configured cluster label name/value. The collector must escape label values consistently with existing query code.

Exclude loopback `lo` from N1 records. Do not exclude interfaces based on naming prefixes.

### Label/identity rules

- Require both `instance` and `device` labels.
- Interface key is cluster + node + full instance + device.
- Map node identity using the existing instance hostname normalization helper.
- Do not infer interface role from `device`.
- Keep individual interface records; do not aggregate interfaces in N1.

## 4. Metric completeness and partial outcomes

Network is one family.

- Query each metric independently, so one unsupported/missing metric does not discard the other network measurements.
- If no network metric family yields samples, report a network family error.
- If metric coverage differs between interfaces, report incomplete coverage in the family error/warning metadata.
- Missing metric values are SQL NULL, not zero.
- A valid observed zero rate remains zero.
- Reject non-finite values.
- Do not turn query errors into empty-success results.
- Network failure must not fail the entire node-health run if other families succeeded.
- Existing run status logic must reflect family errors as partial.

## 5. Schema and retention

- Migration v14 is additive.
- Network records reference the existing run identifier.
- Existing telemetry retention deletes expired `node_health_runs`; the foreign-key cascade should delete network child records.
- Add a regression test proving cascade retention cleanup removes network rows.
- Preserve existing historical records and migration behavior.

## 6. Test plan

### PromQL and collector tests
- Cluster selector label/value escaping.
- Rate queries evaluated at supplied snapshot timestamp.
- Loopback exclusion.
- Correct interface labels.
- Node hostname normalization.
- All metric families present.
- Partial metric availability.
- Entire network family absent.
- Individual Prometheus query failure.
- Non-finite sample rejection.
- Conflicting duplicate samples rejected/handled according to existing collector deduplication policy.
- Counter reset behavior is covered by Prometheus rate semantics; test collector stores rate outputs, not raw counter subtraction.

### Persistence tests
- Persist network rows.
- Cluster/node/interface/run identity correct.
- NULL for missing metric.
- Transaction rollback on persistence failure.
- Foreign-key cascade.
- Migration from an existing v13 database to v14.
- Fresh database schema initialization.
- Existing v1–v13 migration suite remains green.

### Integration regression
- Node health run success with network family present.
- Partial node-health run when network family fails.
- CPU/memory/drive/filesystem families still persist when network fails.
- Daily collection path unaffected.
- Network rows are not created by daily topology collection.

## 7. N1 exclusions

Do not implement in N1:

- API endpoint.
- UI/dashboard.
- Interface inventory discovery workflow.
- Role classification.
- Node overrides.
- Link speed or link state.
- Bond/VLAN relationship discovery.
- Utilization percentage.
- Client/internal traffic separation.
- Aggregate throughput charts.
- Alerting.

These belong in later increments.

## 8. N1 acceptance gate

N1 is ready for PR review when:

1. Additive v14 migration is implemented and tested.
2. Network family collection uses the existing Prometheus client and common snapshot timestamp.
3. Per-interface rates are persisted without aggregation.
4. Missing metrics are NULL and collection errors are isolated.
5. Network failures yield partial collection status, not a failure of unrelated families.
6. Retention cascades network data.
7. All regression tests pass.
8. CI passes on the exact PR head.
9. Complete diff review confirms no unrelated source changes.
10. No merge or deployment occurs without explicit approval.
