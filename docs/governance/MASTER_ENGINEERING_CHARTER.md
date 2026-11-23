# MINIO ANALYTICS
## Master Engineering Charter & Architecture Baseline
**Version:** 1.0  
**Date:** 21 November 2026  
**Repository:** `faith-fork/minio-analytics`  
**Document status:** Agreed product direction and engineering operating baseline  
**Architecture status:** Target architecture — implementation to be delivered incrementally

---

# PART I — PROJECT CHARTER

## 1. Product vision

MinIO Analytics is intended to become an enterprise-grade MinIO observability, storage analytics and operational intelligence platform.

It must provide a unified view of multiple independent MinIO clusters, their infrastructure, storage topology, capacity, performance, replication, logs, events and operational health.

The product should evolve beyond a conventional monitoring dashboard.

Its purpose is to help storage administrators answer five questions:

1. What infrastructure and storage resources do I have?
2. Are my MinIO clusters and their underlying infrastructure healthy?
3. How are my storage systems performing?
4. What happened, why did it happen and what is affected?
5. What action should I take to prevent or resolve an operational problem?

The long-term objective is to provide an AI-accessible storage observability platform with REST APIs and MCP integration, while maintaining accurate engineering, security and operational controls.

## 2. Confirmed product decisions

These are agreed architectural decisions and should not be repeatedly reconsidered without a material technical reason.

| Area | Decision |
|---|---|
| Storage platform | MinIO only |
| Cluster support | Multiple independent MinIO clusters from day one |
| Deployment models | Customer-managed and hosted multi-tenant |
| Metrics | Integrated infrastructure and MinIO analytics |
| Logs | Integrated server and audit log observability |
| Events | Central operational event timeline |
| API | Full REST API, designed API-first |
| AI integration | MCP support |
| MCP initial scope | Read-only observability |
| Future AI operations | Controlled operational tools with explicit authorization and approval |
| Infrastructure discovery | Automatic discovery followed by administrator review and approval |
| Network classification | Configurable per cluster, with optional node overrides |
| Filesystem classification | Administrator-approved monitoring inventory |
| Pool monitoring | First-class storage monitoring capability |
| External storage platforms | Out of scope; MinIO-specific product |

## 3. Product principles

The following principles guide all product and engineering decisions.

1. MinIO-native functionality takes priority over generic S3 abstractions.
2. Multi-cluster capability must be part of the foundational architecture.
3. Existing validated functionality must be preserved.
4. Infrastructure discovery must not silently change approved monitoring configuration.
5. Missing or unsupported metrics must be reported honestly.
6. Metrics, logs and events must have a common correlation model.
7. The application must remain fully functional without an AI/MCP connection.
8. The REST API is the authoritative application interface.
9. MCP is an integration layer, not the application core.
10. Customer-managed and hosted deployments should share the same product capabilities wherever possible.
11. Security, data integrity and operational reliability take priority over feature delivery speed.

---

# PART II — FUNCTIONAL PRODUCT ARCHITECTURE

## 4. Product modules

MinIO Analytics will be organized into six functional domains.

### 4.1 Infrastructure Observability

- Cluster health and availability.
- Node health and availability.
- CPU utilization.
- Memory utilization.
- System load averages.
- Filesystem capacity and utilization.
- Disk health and performance.
- Network interface performance.
- Storage pools.
- Erasure sets.
- Infrastructure inventory and topology.
- Historical infrastructure telemetry.

### 4.2 Storage Analytics

- Cluster raw and logical capacity.
- Provisioned and usable capacity.
- Bucket capacity and object counts.
- Object versions and delete markers.
- Bucket versioning status.
- Tenant and bucket mappings.
- Quotas and quota utilization.
- Storage classes, including configured MinIO storage classes.
- S3 API request rates, errors and latency.
- Historical capacity and bucket growth.

### 4.3 Replication and Resiliency

- Native MinIO site replication.
- Bucket replication.
- Source and destination cluster health.
- Replication status.
- Replication backlog and pending objects.
- Replication backlog bytes, where exposed.
- Replication failures and error details.
- Replication lag and latency.
- Destination availability.
- Versioning prerequisites.
- Disaster recovery readiness.

Native MinIO replication and external replication solutions must be represented as distinct mechanisms. The application must not imply that their semantics or capabilities are identical.

### 4.4 Operations Intelligence

- Prometheus metrics.
- MinIO server logs.
- MinIO audit logs.
- Operational events.
- Alerts and notifications.
- Historical trends.
- Reports.
- Capacity forecasting.
- Anomaly detection.
- Incident timeline.
- Metrics/log correlation.
- Operational recommendations.

### 4.5 Administration and Governance

- Organization and user administration.
- Role-based access control.
- Cluster onboarding.
- Prometheus connection management.
- Infrastructure discovery.
- Administrator approval of discovered resources.
- Configuration management.
- Collection policies.
- Retention policies.
- Audit trail.
- Backup and restore.
- Application health and scheduler management.

### 4.6 API and AI Integration

- Versioned REST APIs.
- OpenAPI documentation.
- External integrations.
- Webhooks.
- MCP server.
- MCP resources.
- MCP tools.
- MCP prompts.
- AI-assisted operational analysis.

---

## 5. Multi-cluster architecture

Multi-cluster support is foundational.

The platform must not be designed around a single MinIO cluster with multiple dashboards.

### Logical hierarchy

Organization  
→ Deployment  
→ Site / Location  
→ MinIO Cluster  
→ Pools  
→ Erasure Sets  
→ Drives

A cluster also has its own:

- Nodes.
- Buckets.
- Tenants and quotas.
- Prometheus connection.
- Infrastructure configuration.
- Collection configuration.
- Replication relationships.
- Logs and events.
- Historical analytics.

### Required behaviour

1. A global dashboard must consolidate information across authorized clusters.
2. Administrators must be able to drill down into an individual cluster.
3. Every observation must have an unambiguous cluster identity.
4. Cluster-specific configurations must be independent.
5. Different clusters may have different node counts, pool layouts, drive counts and network designs.
6. Historical records must remain associated with the correct cluster.
7. Replication relationships must support source and destination clusters across sites.
8. The architecture must support customer and organization isolation in hosted deployments.

A cluster's stable internal identity must not depend solely on its hostname, display name or Prometheus label.

---

## 6. Infrastructure discovery and administrator approval

This is a central architectural feature.

The application should automatically discover infrastructure but must not automatically assume that every discovered resource belongs to MinIO storage or should be monitored.

### Discovery lifecycle

Discover → Classify → Review → Approve → Monitor → Rediscover

### 6.1 Filesystem discovery

Discover:

- Mountpoint.
- Source device.
- Filesystem type.
- Mount status.
- Node association.
- Underlying block-device relationship, where available.

Suggested classifications:

- MinIO data filesystem.
- OS filesystem.
- Other filesystem.
- Excluded filesystem.

The administrator must be able to approve or reject the suggested classification.

### 6.2 Block-device discovery

Discover:

- Device name.
- Device type.
- Parent device.
- Model.
- Capacity.
- Rotational status.
- Filesystem and mount relationships.
- Device-mapper and LVM relationships, where available through metrics or supplementary discovery.

Suggested classifications:

- MinIO data disk.
- OS disk.
- Other device.
- Excluded device.

The application must prevent double-counting logical and underlying physical devices.

### 6.3 Network interface discovery

Discover:

- Interface name.
- Operational status.
- Interface counters.
- Link speed where available.
- Bond relationships.
- VLAN relationships where available.
- Node association.

Suggested classifications:

- Client/public.
- Cluster/internal.
- Shared client and cluster.
- Other.
- Excluded.

Network roles must never be inferred solely from interface names.

### 6.4 Approval states

Every discovered resource should have a distinct state:

- Discovered: detected automatically.
- Pending review: awaiting administrator classification.
- Approved: accepted for a monitoring purpose.
- Monitored: actively included in collection.
- Missing: previously approved but no longer discovered.
- Excluded: explicitly excluded by an administrator.

### 6.5 Change detection

Periodic rediscovery must compare current inventory with approved configuration.

For newly discovered resources:

- Mark them as pending review.
- Continue monitoring previously approved resources.
- Notify administrators.
- Do not silently add new resources to approved capacity reporting.

For missing resources:

- Mark them as missing.
- Preserve historical data.
- Do not silently delete configuration or historical records.

### 6.6 Configuration hierarchy

Use three configuration levels:

1. Cluster defaults.
2. Node-specific overrides.
3. Discovered resource inventory.

This supports different hardware and network configurations across nodes within a cluster.

---

## 7. Network monitoring design

The network model must support multiple deployment patterns.

### Supported patterns

**A. Dedicated interfaces**

- Separate client/public network.
- Separate cluster/internal network.

**B. Single shared interface**

- One interface carries both client and internal traffic.
- Display total interface throughput.
- Do not invent separate client and cluster traffic measurements.

**C. Multiple interfaces per role**

- Multiple client interfaces.
- Multiple internal interfaces.
- Per-interface details and role-level aggregation.

**D. Bonded interfaces**

- Support logical bond interfaces.
- Avoid counting the bond and its physical slaves together.
- Preserve physical interface visibility where useful.

### Current lab environment reference

The representative cluster has:

- `ens3`: client/public-facing network.
- `ens4`: cluster/internal network.
- `lo`: loopback, excluded from performance reporting.

These are example classifications, not global application defaults.

### Network metrics

- Receive throughput.
- Transmit throughput.
- Historical throughput.
- Peak throughput.
- Per-node comparison.
- Per-interface performance.
- Role-based aggregation.
- Link status and speed where available.

Traffic separation must only be claimed when actual telemetry supports it. A shared interface's counters cannot independently identify client and internal traffic.

---

## 8. Filesystem and disk monitoring

Filesystem capacity and block-device performance must remain separate concepts.

### Filesystem metrics

- Total capacity.
- Used capacity.
- Available capacity.
- Utilization percentage.
- Historical utilization.
- Mount availability.
- Filesystem type.
- Growth trends.

### Disk performance metrics

- Read bytes per second.
- Write bytes per second.
- Read IOPS.
- Write IOPS.
- Average read latency.
- Average write latency.
- Disk utilization/busy time where supported.
- Historical trends.

All derived values must be calculated using correct counter-rate and aggregation semantics.

Device-mapper and underlying devices must not be blindly aggregated together.

### Current lab reference

The representative node has:

- 24 independently mounted XFS data filesystems.
- `/mnt/datadisk1` through `/mnt/datadisk24`.
- 24 individual 10 GB QEMU virtual disks.
- OS disk `sda`.
- LVM root and swap devices `dm-0` and `dm-1`.
- OS filesystems `/`, `/boot` and `/boot/efi`.

These values are environmental evidence, not hardcoded product assumptions.

The collector must discover resources dynamically.

---

## 9. Node infrastructure monitoring

Node Infrastructure must be separate from Collection Health.

### Node Infrastructure

- CPU utilization.
- Memory utilization.
- Load averages: 1, 5 and 15 minutes.
- Filesystem capacity.
- Disk performance.
- Network performance.
- Node availability.
- Historical performance.
- Hardware inventory where available.

### Collection Health

- Collector execution status.
- Scheduler health.
- Last successful collection.
- Collection failures.
- Prometheus scrape availability.
- Data freshness.
- Collection duration.
- Collection errors.

Do not mix infrastructure performance metrics into Collection Health.

### Historical telemetry policy

Current high-frequency telemetry design reference:

- Default collection cadence: 5 minutes.
- Configurable cadence: 1–60 minutes.
- Default detailed telemetry retention: 3 days.
- Configurable retention: 1–90 days.

These are initial defaults and must be reviewed against actual scale, storage cost and workload.

Daily capacity, bucket and topology history must remain separate from high-frequency node/drive retention.

---

## 10. Pool monitoring — first-class capability

Pools must be treated as a first-class monitoring entity, not merely a topology table.

### Pool overview

- Pool identity.
- Pool availability.
- Raw capacity.
- Used capacity.
- Available capacity.
- Utilization percentage.
- Growth trends.
- Number of nodes.
- Number of erasure sets.
- Number of drives.
- Online/offline drives.
- Health state.

### Pool drill-down

1. Overview.
2. Erasure sets.
3. Drives.
4. Nodes.
5. Performance.
6. Capacity history.
7. Health history.

### Pool performance

Where reliable pool attribution is available:

- Read/write throughput.
- IOPS.
- Latency.
- Performance trends.

Never blindly aggregate node or drive performance to produce pool metrics without validating membership and aggregation semantics.

### Pool alerts

- Capacity thresholds.
- Growth and exhaustion forecasts.
- Availability degradation.
- Drive failures.
- Erasure-set degradation.
- Missing or stale pool telemetry.

The topology collector should obtain pool membership from authoritative MinIO topology information wherever possible.

---

## 11. Erasure-set and drive monitoring

### Erasure sets

- Set identity.
- Pool relationship.
- Drive membership.
- Online/offline status.
- Degraded state.
- Protection status where reliably exposed.
- Historical health.

### Drives

- Drive identity.
- Node and pool relationship.
- Drive availability.
- SMART/health information where exposed.
- Capacity.
- IOPS.
- Throughput.
- Latency.
- Error trends.
- Historical health.

Drive identity must be stable enough to preserve historical data across application restarts and display-name changes.

---

## 12. MinIO service and storage analytics

Include:

- MinIO process/service health.
- Service uptime and restarts.
- Host and process memory.
- S3 API request rates.
- S3 API latency.
- Request errors.
- Bucket capacity.
- Object counts.
- Object versions.
- Delete markers.
- Versioning status.
- Tenant-to-bucket mapping.
- Quotas.
- Storage class usage.
- Logical versus raw capacity.
- Healing activity where supported.

All metric support must be verified against the actual MinIO version and available metric labels.

---

## 13. Replication and disaster recovery

Support monitoring of:

- Site replication.
- Bucket replication.
- Source and destination health.
- Replication configuration.
- Backlog.
- Pending objects.
- Pending bytes.
- Failures.
- Replication lag.
- Error details.
- Versioning prerequisites.
- Destination readiness.

Distinguish actual replication metrics from estimates or inferred indicators.

Do not claim recovery readiness merely because a replication relationship exists.

---

## 14. Logs, metrics and operational events

Use separate storage systems appropriate to each data type.

| Data | Purpose | Initial technology direction |
|---|---|---|
| Metrics | Numeric historical time series | Prometheus integration |
| Logs | Server and audit records | VictoriaLogs or equivalent |
| Events | Operational state transitions | Relational event store |
| Configuration | Product and cluster state | Relational database |

### Operational timeline

Correlate events such as:

- Node becomes unavailable.
- Drive fails.
- Erasure set becomes degraded.
- Pool availability changes.
- S3 API errors increase.
- Replication falls behind.
- Collector fails.

Correlation must use real cluster, node, resource and timestamp relationships.

### Log capabilities

- MinIO server logs.
- MinIO audit logs.
- Search and filtering.
- Time-based queries.
- Cluster/node association.
- Severity filtering where available.
- Event correlation.
- Configurable retention.

Do not store high-volume logs in the application's relational configuration database.

---

# PART III — API, AI AND DEPLOYMENT ARCHITECTURE

## 15. REST API-first design

The REST API is the authoritative interface for the application.

The frontend must consume application APIs rather than implement business logic independently.

Suggested API domains:

| Domain | Example |
|---|---|
| Organizations | `/api/v1/organizations` |
| Sites | `/api/v1/sites` |
| Clusters | `/api/v1/clusters` |
| Discovery | `/api/v1/discovery` |
| Nodes | `/api/v1/clusters/{id}/nodes` |
| Drives | `/api/v1/clusters/{id}/drives` |
| Pools | `/api/v1/clusters/{id}/pools` |
| Storage | `/api/v1/clusters/{id}/buckets` |
| Replication | `/api/v1/clusters/{id}/replication` |
| Metrics | `/api/v1/metrics` |
| Logs | `/api/v1/logs` |
| Events | `/api/v1/events` |
| Alerts | `/api/v1/alerts` |
| Reports | `/api/v1/reports` |
| Administration | `/api/v1/admin` |

### API standards

- OpenAPI documentation.
- Versioned endpoints.
- Consistent pagination.
- Filtering and sorting.
- Standard error responses.
- Input validation.
- Authentication and authorization.
- Rate limiting.
- Audit logging.
- Backward-compatibility policy.
- Idempotency for appropriate write operations.

No unrestricted SQL or arbitrary backend execution through the API.

## 16. MCP and AI integration

MCP is an approved architectural capability.

The MCP server must sit above the REST API and reuse the same application services, authorization and audit mechanisms.

### MCP capabilities

**Tools — initial read-only scope**

- `list_clusters`
- `get_cluster_health`
- `get_cluster_capacity`
- `get_pool_health`
- `get_erasure_set_status`
- `get_node_performance`
- `get_drive_health`
- `get_network_performance`
- `get_bucket_analytics`
- `get_replication_status`
- `search_minio_logs`
- `get_recent_events`
- `generate_cluster_health_report`

**Resources**

- Cluster inventory.
- Cluster health.
- Pool inventory.
- Node inventory.
- Replication status.
- Recent events.
- Reports.

**Prompts**

- Daily infrastructure health review.
- Pool capacity risk assessment.
- Replication health investigation.
- Drive degradation investigation.
- MinIO performance troubleshooting.
- DR readiness assessment.

### MCP security

- Authentication for every request.
- Server-side organization and cluster authorization.
- No credential disclosure.
- No arbitrary shell execution.
- No unrestricted SQL execution.
- No arbitrary Prometheus query execution.
- Audit every tool invocation.
- Rate and query limits.
- Read/write permission separation.
- Explicit approval for mutating operations.

The product must remain fully operational without MCP or an AI assistant.

## 17. Deployment models

### Customer-managed edition

- Runs in customer-controlled infrastructure.
- Supports restricted and disconnected environments.
- Customer controls credentials, retention and backups.
- Supports native Linux deployment.
- Same core capabilities as the hosted edition.

### Hosted multi-tenant edition

- Shared application platform.
- Organization-level data isolation.
- Tenant-scoped authentication and authorization.
- Tenant-specific retention and configuration.
- Centralized upgrades and backups.
- Secure connectivity to customer MinIO environments.

The architecture must not require customer-managed installations to depend on public cloud services for normal operations.

---

## 18. Technology direction

These are initial architecture recommendations. Existing working components should not be replaced without evidence and a migration plan.

| Component | Proposed direction |
|---|---|
| Backend | Python / FastAPI |
| Frontend | Existing application UI, progressively API-driven |
| Relational database | PostgreSQL for hosted multi-tenant scale; SQLite may remain for appropriate standalone deployments |
| Metrics | Prometheus |
| Logs | VictoriaLogs or equivalent |
| Events | Relational event store |
| Scheduler | Reliable background scheduler/workers |
| API documentation | OpenAPI |
| Authentication | Existing authentication extended with RBAC and tenant scope |
| Customer-managed deployment | Native RPM/DEB |
| Hosted deployment | Containerized deployment where appropriate |
| AI integration | MCP server |

Do not migrate from SQLite simply because PostgreSQL is more scalable. Assess concurrency, database size, retention, workload and deployment needs first.

---

# PART IV — ENGINEERING STANDARDS AND DELIVERY ROADMAP

## 19. Architecture and software engineering standards

Use established industry practices appropriate to the product's scale and deployment requirements.

### Code quality

- Modular architecture.
- Separation of concerns.
- Reusable services.
- Clear naming conventions.
- Avoid unnecessary dependencies.
- Strong input validation.
- Explicit error handling.
- Structured logging.
- No secrets in logs.
- No hardcoded environment-specific values.

### Backend

- API contracts.
- Service/repository separation where appropriate.
- Authentication and authorization.
- Timeouts and retry policies.
- Rate limiting.
- Efficient database access.
- Safe background jobs.
- Observability of application internals.

### Frontend

- Consistent visual language.
- Responsive layouts.
- Reusable components.
- Loading, empty, error and success states.
- Large-dataset usability.
- Correct filters and exports.
- Accessibility and keyboard usability.
- Functional testing, not screenshots alone.

### Database

- Versioned migrations.
- Additive and backward-compatible changes where possible.
- Transactions.
- Appropriate indexes.
- Data retention policies.
- No destructive production migrations without explicit approval.
- Backup and recovery procedures.
- Historical data preservation.

### Performance and scalability

Design for large MinIO deployments:

- Multiple clusters.
- Large node counts.
- Large drive counts.
- Large bucket inventories.
- High-cardinality Prometheus metrics.
- Large log volumes.
- Concurrent API consumers.

Avoid unbounded queries, excessive frontend payloads and uncontrolled telemetry cardinality.

### Security

- Least privilege.
- TLS.
- Secure credential storage.
- SSRF protection.
- Safe outbound connection validation.
- Authentication and authorization.
- Tenant isolation.
- Audit logging.
- Dependency security checks.
- Secure secret rotation.
- No arbitrary command execution.

### Reliability

- Collection retry and recovery.
- Scheduler health.
- Stale-data detection.
- Database backup.
- Application health endpoints.
- Failure isolation.
- Graceful degradation.
- Upgrade and rollback procedures.

---

## 20. Development and integration responsibilities

This is the formal operating agreement between the AI engineering partner and the user.

### 20.1 AI engineering partner — Lead/Principal Engineer responsibilities

The AI engineering partner owns:

- Product and technical architecture.
- Detailed design.
- Backend implementation.
- Frontend implementation.
- Database schema and migrations.
- API implementation.
- MCP implementation.
- Security design.
- GitHub development.
- Branch management.
- Commits.
- Pull requests.
- Code reviews.
- Regression analysis.
- Automated tests.
- CI/CD verification.
- Documentation.
- Release notes.
- Integration planning.
- Merge recommendations.
- Release readiness.
- Rollback planning.
- Engineering handovers.

Development must be performed through available GitHub/repository development tools.

The AI engineering partner must not ask the user to manually edit application source code, resolve Git conflicts, cherry-pick commits or perform development tasks on the VM.

If tooling does not permit an operation, the limitation must be stated honestly and the safest alternative proposed.

### 20.2 User — Product Owner / Platform Engineering / Deployment and Validation responsibilities

The user owns:

- Product priorities and architectural decisions.
- Business and operational requirements.
- Access to relevant infrastructure and test environments.
- Running commands on the lab VM.
- Deploying explicitly approved releases.
- Restarting services.
- Browser-based functional validation.
- Verifying actual MinIO connectivity.
- Validating live metrics and logs.
- Providing terminal output and screenshots.
- Reporting runtime issues.
- Approving merges.
- Approving deployments.
- Final release acceptance.

The user must not be asked to develop or debug application source code on the VM.

### 20.3 Joint responsibilities

Both parties collaborate on:

- Architecture decisions.
- Feature acceptance criteria.
- Prioritization.
- Risk assessment.
- Release planning.
- Production readiness.
- Acceptance and sign-off.

The AI engineering partner must challenge unsafe or technically weak requirements and recommend better alternatives, explaining trade-offs.

The user retains final approval authority over scope, merges and deployments.

---

## 21. GitHub and branch management rules

Repository:

`faith-fork/minio-analytics`

The current designated integration branch is:

`feature/auth-foundation`

This must be verified against GitHub at the start of each development session. It may be changed only through an agreed integration strategy.

### Mandatory rules

1. Never develop directly on the integration branch.
2. Create focused feature branches.
3. Use descriptive commits.
4. Review complete diffs.
5. Avoid unrelated changes.
6. Never force-push or rewrite shared history without explicit approval.
7. Verify branch ancestry.
8. Verify prerequisite PR integration.
9. Never assume two branches contain the same features.
10. Never deploy an incomplete feature branch.
11. Never merge without explicit approval.
12. Never deploy without explicit approval.

### Mandatory pre-deployment verification

Before asking the user to deploy:

- Verify integration branch HEAD.
- Verify feature branch HEAD.
- Verify required ancestry.
- Verify complete diff.
- Check for accidental file deletion or reversion.
- Confirm prerequisite features.
- Run automated tests.
- Verify CI.
- Review security and database implications.
- Identify the exact deployment commit.
- Obtain explicit deployment approval.

A successful CI run does not prove that a branch includes all required prior features.

### Post-merge verification
After an approved merge:

- Confirm GitHub reports merged.
- Record actual merge commit SHA.
- Verify integration branch HEAD.
- Confirm merged code exists.
- Verify CI.
- Update the engineering handover.

A closed PR is not necessarily a merged PR.

---

## 22. Regression prevention

Regression prevention is mandatory.

The application must retain previously validated functionality when new features are implemented.

The regression checklist must be specific to the affected modules.

Existing functionality to protect includes:

- Authentication and authorization.
- Cluster overview.
- Navigation.
- Consolidated Provisioned report.
- Consolidated Bucket Usage report.
- Consolidated RAW Capacity report.
- Report column visibility preferences.
- CSV exports respecting visibility.
- Bucket Usage filters.
- Capacity planning calculations.
- Table layout and column sizing.
- Node Infrastructure.
- Collection Health.
- Storage Topology.
- Node and drive historical trends.
- Existing APIs.
- Existing collection and scheduling behaviour.
- Existing retention behaviour.

A new feature passing its own tests does not establish that it integrates safely.

Test the combined implementation against the integration branch.

---

## 23. Testing and quality gates

The AI engineering partner owns automated validation.

Use, as applicable:

- Unit tests.
- Integration tests.
- API tests.
- Frontend tests.
- Database migration tests.
- Regression tests.
- Static analysis.
- Linting.
- Dependency and security checks.
- CI pipeline validation.
- Performance tests for important high-volume paths.

Never claim a test passed unless it was actually executed and the result is available.

Always distinguish:

- Executed and passed.
- Executed and failed.
- Not executed.
- Requires user VM validation.

CI does not replace real VM validation.

### Deployment gate

Deployment instructions must not be issued until:

1. Required integration prerequisites are present.
2. Exact commit SHA is identified.
3. Automated tests pass.
4. CI passes.
5. Complete diff is reviewed.
6. No known blocking regression remains.
7. User explicitly approves deployment.

---

## 24. Deployment and release process

The release sequence is:

1. Complete implementation.
2. Review implementation.
3. Integrate required changes.
4. Run tests.
5. Verify CI.
6. Review complete PR.
7. Obtain user approval to merge.
8. Merge.
9. Verify merge commit and integration branch.
10. Obtain user approval to deploy.
11. Provide exact VM deployment commands.
12. User deploys.
13. User performs runtime validation.
14. Review runtime evidence.
15. Resolve defects.
16. Complete release validation.
17. Update engineering handover.

### Deployment instructions must include

- Exact branch.
- Exact commit SHA.
- Confirmation of required integration history.
- Working-tree safety check.
- Fetch/pull or exact commit procedure.
- Service restart commands.
- Service status verification.
- Relevant journal commands.
- Specific UI validation steps.
- Expected results.
- Rollback procedure.
- Evidence requested from the user.

Never assume the VM is on the expected branch or has a clean working tree.

Never use destructive commands such as `git reset --hard`, force operations or database deletion without explaining the consequences and obtaining approval.

---

# PART V — IMPLEMENTATION ROADMAP

## 25. Phased delivery plan

The implementation must be incremental, with independently testable milestones.

| Phase | Work