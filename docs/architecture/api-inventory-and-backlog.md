# MINIO Analytics — API Inventory and Prioritized Engineering Backlog

- **Baseline:** `feature/auth-foundation`
- **Status:** Initial source inventory; OpenAPI/runtime verification still required
- **Prepared:** 2026-11-22

## 1. API design principles

- REST API is the authoritative application interface.
- The frontend must use the same application services as API clients.
- Preserve existing endpoints while introducing a versioned surface deliberately.
- Use consistent authentication, authorization, validation, pagination, filtering and error shapes.
- Enforce cluster and organization scope server-side; never trust a client-supplied cluster ID as authorization.
- Add request IDs/correlation IDs and audit security-relevant mutations.
- Do not expose arbitrary PromQL, SQL or shell execution to ordinary users or MCP clients.

## 2. Existing route inventory

The following is a source-level inventory from the inspected router modules. It is not a complete generated OpenAPI export.

| Router/module | Observed route(s) | Purpose |
|---|---|---|
| `app/api/auth.py` | `/api/auth/*` | Login, logout, current user and user administration |
| `app/api/clusters.py` | `POST /api/clusters/discover` | Admin-only, read-only Prometheus discovery |
| `app/api/tenants.py` | `GET/POST /api/tenants`, `PATCH /api/tenants/{tenant_id}` | Tenant inventory and management |
| `app/api/tenants.py` | `GET /api/buckets`, `PUT /api/buckets/{bucket_id}/tenant`, `PUT /api/buckets/bulk-tenant` | Bucket inventory and tenant assignment |
| `app/api/tenants.py` | `GET /api/buckets/{bucket_id}/history` | Bucket assignment history |
| `app/api/analytics.py` | `GET /api/analytics/overview` | Consolidated overview |
| `app/api/analytics.py` | `GET /api/analytics/capacity-report` | Capacity report |
| `app/api/analytics.py` | `GET /api/analytics/raw-capacity-report` | RAW capacity report |
| `app/api/analytics.py` | `GET /api/analytics/bucket-usage-report` | Bucket usage report |
| `app/api/analytics.py` | `GET/PUT /api/analytics/report-column-preferences` | User report preferences |
| `app/api/analytics.py` | `GET/PUT /api/analytics/capacity-factors` | Capacity calculation factors |
| `app/api/analytics.py` | `GET /api/analytics/clusters`, `GET /api/analytics/clusters/{cluster_id}` | Cluster analytics |
| `app/api/analytics.py` | `GET /api/analytics/tenants`, `GET /api/analytics/tenants/{tenant_id}` | Tenant analytics |
| `app/api/analytics.py` | `GET /api/analytics/buckets/{bucket_id}` | Bucket analytics |
| `app/api/analytics.py` | `GET /api/analytics/object-size-distribution/{scope}/{entity_id}` | Object size distribution |
| `app/api/analytics.py` | `GET /api/analytics/collection-health` | Collection and scheduler health |
| `app/api/analytics.py` | `GET /api/analytics/clusters/{cluster_id}/topology/trends` | Infrastructure history |
| `app/api/analytics.py` | `GET /api/analytics/clusters/{cluster_id}/topology` | Current topology view |
| `app/api/analytics.py` | `GET /api/analytics/clusters/{cluster_id}/nodes/performance` | Short-window node performance (PR #20 branch addition; confirm integration state) |
| `app/api/master_admin.py` | `GET/PUT /api/master-admin/settings` | Master Admin scheduler settings |
| `app/api/master_admin.py` | `GET/POST /api/master-admin/backups` | Backup listing and creation |
| `app/api/master_admin.py` | `GET /api/master-admin/backups/{filename}/download` | Backup download |

Before publishing an API contract, generate the OpenAPI schema from the actual integration branch and compare it with this inventory. Branch-only endpoints must not be represented as deployed capabilities.

## 3. Target API domains

| Domain | Target capabilities | Priority |
|---|---|---|
| Organizations/deployments | Organization and deployment lifecycle, membership and RBAC | P1 |
| Sites/clusters | Inventory, enablement, labels and cluster details | P1 |
| Telemetry sources | Prometheus connection test, credentials reference, binding and health | P0 |
| Discovery | Scan, list pending resources, classify, approve, exclude, rediscover | P0 |
| Nodes | Node inventory, status, CPU, memory, load and history | P1 |
| Filesystems/devices | Inventory, approval, capacity, I/O and history | P1 |
| Network | Interface inventory, roles, counters, rates and history | P1 |
| Pools/erasure sets | Membership, availability, quorum, healing and trends | P1 |
| Buckets/tenants | Existing inventory, quota, assignment, versions and analytics | Preserve |
| Collection health | Category freshness, duration, coverage, failures and scheduler status | P0 |
| Reports/events/alerts | Existing reports plus event correlation and alerts | P2 |
| Administration | Retention, policies, audit, backup/restore and system health | P1 |

## 4. Proposed versioned resource map

The following is a target naming proposal, not a set of implemented endpoints.

| Resource | Proposed route |
|---|---|
| Organizations | `/api/v1/organizations` |
| Deployments | `/api/v1/deployments` |
| Sites | `/api/v1/sites` |
| Clusters | `/api/v1/clusters` |
| Telemetry sources | `/api/v1/telemetry-sources` |
| Cluster source binding | `/api/v1/clusters/{cluster_id}/telemetry-source` |
| Discovery jobs | `/api/v1/clusters/{cluster_id}/discovery` |
| Discovered resources | `/api/v1/clusters/{cluster_id}/discovered-resources` |
| Resource approval | `/api/v1/discovered-resources/{resource_id}/approval` |
| Nodes | `/api/v1/clusters/{cluster_id}/nodes` |
| Filesystems | `/api/v1/clusters/{cluster_id}/filesystems` |
| Block devices | `/api/v1/clusters/{cluster_id}/block-devices` |
| Network interfaces | `/api/v1/clusters/{cluster_id}/network-interfaces` |
| Pools | `/api/v1/clusters/{cluster_id}/pools` |
| Erasure sets | `/api/v1/clusters/{cluster_id}/erasure-sets` |
| Buckets | `/api/v1/clusters/{cluster_id}/buckets` |
| Collection policies | `/api/v1/clusters/{cluster_id}/collection-policies` |
| Collection runs | `/api/v1/clusters/{cluster_id}/collection-runs` |
| Events | `/api/v1/events` |
| Alerts | `/api/v1/alerts` |
| Reports | `/api/v1/reports` |
| Audit | `/api/v1/audit-events` |

## 5. API contract requirements

### Request and response behavior
- Use Pydantic request/response models.
- Define consistent error codes and structured error bodies.
- Validate identifiers, ranges, time windows, sort fields and filter values.
- Use pagination for potentially large inventories and history.
- Bound time-series query windows and maximum returned samples.
- Use UTC ISO-8601 timestamps.
- Make mutating operations idempotent where appropriate.
- Return explicit freshness and availability metadata with telemetry results.

### Security
- Authenticate every non-public endpoint.
- Enforce role, organization, deployment and cluster authorization at the service layer.
- Apply CSRF protection appropriate to cookie-authenticated browser requests.
- Rate-limit login, discovery, report generation and expensive queries.
- Audit connection changes, credential rotation, resource approval and administrative actions.
- Never expose Prometheus credentials or raw authorization headers.

### Compatibility
- Keep current routes working while the frontend and integrations migrate.
- Document deprecation windows.
- Add contract tests for current routes and versioned routes.
- Keep OpenAPI output under CI review.

## 6. Prioritized implementation backlog

### EPIC 0 — Integration and regression baseline
- [ ] Reconcile PR #19 and PR #20 ancestry and complete diffs.
- [ ] Confirm the integration candidate contains all required prior features.
- [ ] Run full CI on the exact integration candidate.
- [ ] Maintain a UI/API regression checklist.
- [ ] Obtain lab runtime validation before merge approval.

### EPIC 1 — Migration governance
- [ ] Inventory deployed schema versions and migration-created tables.
- [ ] Implement ordered additive migration units.
- [ ] Add fresh-database migration tests.
- [ ] Add upgrade tests from supported previous database fixtures.
- [ ] Verify data preservation, foreign keys and SQLite integrity.
- [ ] Document backup, upgrade and restore steps.

### EPIC 2 — Prometheus security
- [ ] Document supported authentication modes.
- [ ] Implement secure credential references and redaction.
- [ ] Add SSRF-safe endpoint validation and outbound policy.
- [ ] Validate DNS resolution and redirects.
- [ ] Add response-size, timeout, concurrency and query limits.
- [ ] Add tests for TLS failure, authentication failure and unsafe destinations.

### EPIC 3 — Discovery and approval
- [ ] Define stable resource identity/fingerprint rules.
- [ ] Discover filesystems, block devices and network interfaces.
- [ ] Record node and parent-child relationships.
- [ ] Add pending-review, approved, excluded and missing states.
- [ ] Add approval history and audit actor.
- [ ] Add cluster defaults and node overrides.
- [ ] Verify no resource is silently included in MinIO totals.

### EPIC 4 — Collection policy and Collection Health
- [ ] Define collection categories and dependencies.
- [ ] Add category enablement and cadence.
- [ ] Add bounded concurrency, jitter and retry budgets.
- [ ] Avoid re-running successful families on sibling-family failure.
- [ ] Persist category-level run duration and freshness.
- [ ] Report expected versus observed coverage.
- [ ] Test scheduler restart and missed-run recovery.

### EPIC 5 — Network observability
- [ ] Add interface inventory.
- [ ] Add role configuration and node overrides.
- [ ] Add receive/transmit rates and error/drop counters.
- [ ] Model bonds and VLANs without double counting.
- [ ] Add trends and node comparisons.
- [ ] Add tests using the user's lab inventory.

### EPIC 6 — Organization isolation and hosted readiness
- [ ] Define organization/deployment ownership.
- [ ] Map current standalone deployment to a default organization safely.
- [ ] Enforce organization scope in API and background collection.
- [ ] Add cross-organization denial tests for every resource family.
- [ ] Add organization-scoped audit and RBAC.
- [ ] Complete hosted security review before rollout.

### EPIC 7 — Scale, retention and API evolution
- [ ] Establish synthetic multi-cluster benchmark data.
- [ ] Measure collector query load, DB writes, storage growth and API latency.
- [ ] Validate retention and cleanup behavior.
- [ ] Generate and review OpenAPI contract.
- [ ] Introduce versioned routes with compatibility tests.
- [ ] Reassess persistence architecture using measured thresholds.

## 7. Definition of done for each epic

An epic is complete only when:
1. The implementation is committed on a dedicated branch.
2. The complete diff is reviewed for correctness and regressions.
3. Unit, integration and migration tests are executed and their outcomes reported.
4. CI passes on the exact head SHA.
5. Existing feature regression checks pass.
6. Security and data-preservation implications are reviewed.
7. Documentation and operational notes are updated.
8. User-facing runtime validation is identified where required.
9. No merge or deployment occurs without explicit approval.

## 8. Out of scope for the immediate foundation increment

- VictoriaMetrics provider.
- Push/remote ingestion.
- Direct MinIO metrics polling.
- MCP write operations.
- Automatic infrastructure approval.
- Forced database-engine migration.
- Unbounded live Prometheus queries from the dashboard.
