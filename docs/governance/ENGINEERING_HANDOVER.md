# MINIO Analytics — Engineering Handover

- **Checkpoint date:** 23 November 2026
- **Repository:** [faith-fork/minio-analytics](https://github.com/faith-fork/minio-analytics)
- **Purpose:** Self-contained engineering checkpoint for the next development session
- **Authority:** The Master Engineering Charter governs product and engineering decisions. Live GitHub state supersedes this snapshot whenever it changes.

> This handover records only facts verified during the 23 November 2026 session. It is not evidence of the current VM deployment state.

## 1. Governance and responsibilities

The agreed operating agreement is documented in [MASTER_ENGINEERING_CHARTER.md](MASTER_ENGINEERING_CHARTER.md).

- AI engineering partner: architecture, implementation, GitHub development, branch/PR management, reviews, tests, CI verification, documentation, release preparation and handovers.
- User / Product Owner: product decisions, VM operations, deployment, runtime validation and final acceptance.
- Never ask the user to edit application source, resolve conflicts, cherry-pick or perform development on the VM.
- Never merge or deploy without explicit user approval.
- Never claim tests, CI, runtime validation or deployment succeeded unless verified.
- Use focused feature branches; do not develop directly on the integration branch.

## 2. Verified repository baseline

| Item | Verified value |
|---|---|
| Repository | `faith-fork/minio-analytics` |
| Designated integration branch | `feature/auth-foundation` |
| Integration branch HEAD | `850d6394e61948a11f40e80c0ce4b7cc427466ba` |
| Default branch | `main` |
| `main` HEAD (last verified in session) | `a9acbaf9a4057495b0a55edd4f1e050524f86d43` |

The integration branch designation is from the Charter and was checked against live GitHub. Re-verify branch HEAD and PR ancestry at the beginning of every new session.

## 3. Recent integration and CI

### PR #38 — Atomic SQLite migrations

- **Status:** Merged into `feature/auth-foundation`.
- **Merge commit:** `850d6394e61948a11f40e80c0ce4b7cc427466ba`.
- **Pull request:** https://github.com/faith-fork/minio-analytics/pull/38
- **CI:** Two GitHub Actions test runs on the exact merge commit completed successfully:
  - https://github.com/faith-fork/minio-analytics/actions/runs/45181374376
  - https://github.com/faith-fork/minio-analytics/actions/runs/45181362068
- **Change summary:** Migration execution uses an explicit `BEGIN IMMEDIATE`, executes statements without `executescript()` implicit-commit behaviour, applies base schema and migrations in one transaction, commits only after success and rolls back on failure. Regression tests cover rollback and SQL parsing.
- **Deployment:** Not performed or verified in this session.

## 4. Open pull requests observed

The following open PRs were returned by the live GitHub search during this checkpoint. Re-check their state, head SHA, base SHA, ancestry, changed files and CI before relying on them.

| PR | Title | Base | Scope / notes |
|---|---|---|---|
| [#1](https://github.com/faith-fork/minio-analytics/pull/1) | Add MinIO multi-tenant analytics dashboard and administration | `main` | Foundational application PR; open and not approved for merge |
| [#16](https://github.com/faith-fork/minio-analytics/pull/16) | Refine capacity planning factor controls layout | `feature/auth-foundation` | CSS/UI refinement; open |
| [#21](https://github.com/faith-fork/minio-analytics/pull/21) | Document Prometheus telemetry source architecture | `feature/auth-foundation` | Documentation-only; contains README update and ADR-001 |
| [#22](https://github.com/faith-fork/minio-analytics/pull/22) | Document Phase 0 architecture audit and implementation backlog | `feature/auth-foundation` | Documentation-only; Phase 0 audit, data model and API backlog |

### Documentation already proposed by PRs #21 and #22

Do not create duplicate architecture documents. Their content should be reviewed and integrated through their own PRs:

- PR #21: `docs/architecture/decisions/ADR-001-telemetry-source-and-collection.md` and README changes.
- PR #22: `docs/architecture/phase-0-audit.md`, `docs/architecture/data-model.md`, `docs/architecture/api-inventory-and-backlog.md`.

These PRs were open at checkpoint time. Their current merge status and branch ancestry must be re-verified before implementation depends on them.

## 5. Branch ancestry and integration safety

The following comparisons were verified against `feature/auth-foundation` during the session:

| Branch | Comparison result | Implication |
|---|---|---|
| `feature/cluster-experience-redesign` | Diverged; 2 commits ahead and 127 behind | Not a safe deployment baseline; inspect and integrate changes deliberately |
| `feature/node-infrastructure-experience` | 0 ahead, 67 behind | Stale relative to integration branch |
| `feature/infrastructure-telemetry-workspace` | 0 ahead, 30 behind | Stale relative to integration branch |

The old cluster redesign branch was also observed to lack the atomic migration fix present on the integration branch. Do not deploy it as-is or assume feature branches contain integration work.

## 6. VM and runtime status

<badge>Not verified</badge>

No VM access or deployment validation was performed for this checkpoint.

Previously recorded lab environment details (Rocky Linux 10.0, Python 3.12.9, application path `/opt/minio-analytics`, persistent data under `/data/minio-analytics`, web service `minio-analytics-web`, port 8001) are historical context only. The currently deployed branch, commit SHA, working-tree state, service status, database schema version and browser behaviour are unknown until the user provides current VM evidence.

Do not issue deployment instructions based on this handover alone.

## 7. Current documentation milestone

This checkpoint is being committed through a dedicated documentation branch and PR:

- Branch: `docs/engineering-governance-baseline`
- Pull request: https://github.com/faith-fork/minio-analytics/pull/39
- Base: `feature/auth-foundation` at `850d6394e61948a11f40e80c0ce4b7cc427466ba`
- Intended files:
  - `docs/governance/MASTER_ENGINEERING_CHARTER.md` — faithful copy of the agreed v1.0 Charter.
  - `docs/governance/ENGINEERING_HANDOVER.md` — this living checkpoint.
  - `docs/README.md` — documentation map and session-start procedure.
- Scope: documentation only. No application code, database schema, CI workflow or runtime configuration changes.
- Merge: not performed; explicit user approval is required.
- Deployment: not applicable.

## 8. Decisions and risks to carry forward

1. The Charter is the stable governance and architecture baseline. Change it only when the user agrees to revise a decision; version meaningful revisions.
2. The Handover is a living snapshot. Update it after every substantial engineering session.
3. GitHub live state is authoritative for branch/PR/commit/CI facts; refresh this document when those facts change.
4. VM state is a separate source of truth and must be verified from current runtime evidence.
5. Review PRs #21 and #22 for consistency and integration before implementing work that depends on their architecture decisions.
6. Preserve existing validated application functionality and follow the Charter's regression and release gates.
7. No merge or deployment is authorized by this handover.

## 9. Review of architecture documentation PRs (23 November 2026)

### PR #21 — Telemetry source architecture

- **Status:** Open; mergeable according to GitHub at review time.
- **Head:** `498157fc90e55671bcc999a9b5f2f7539c931b4d`.
- **Ancestry:** 2 commits ahead and 75 behind `feature/auth-foundation`; diverged from merge base `be367d20965899b37c8127df7ef62fd0a5a3a7b4`.
- **CI:** GitHub Actions Tests run 44925049436 completed successfully on that PR head.
- **Review:** ADR-001 is directionally aligned with the Charter: customer-managed Prometheus as the initial provider, Analytics-owned history, no direct MinIO polling, selective/rate-controlled collection, and deferral of VictoriaMetrics and push ingestion.
- **Required correction:** README manual collection example has doubled trailing backslashes on the first two continued lines compared with the current integration branch.
- **Action:** Review findings posted in the PR conversation. Refresh the branch against the current integration branch and re-review the full README diff before merge.

### PR #22 — Phase 0 audit, data model and API backlog

- **Status:** Open; mergeable according to GitHub at review time.
- **Head:** `466f200f436dcc90df98acf24ae7eea948a3734a`.
- **Ancestry:** 3 commits ahead and 75 behind `feature/auth-foundation`; diverged from merge base `be367d20965899b37c8127df7ef62fd0a5a3a7b4`.
- **CI:** GitHub Actions Tests run 44971389842 completed successfully on that PR head.
- **Review:** The evolutionary approach, preservation requirements, Prometheus security priorities, discovery/approval lifecycle, and explicit non-goals are useful.
- **Required corrections:** The audit still treats the `executescript()` SQLite migration transaction issue as an outstanding P0 risk, although merged PR #38 addressed that issue on the current integration branch. The API inventory's node-performance route needs verification against current source and should include the current `/nodes/performance-series` route.
- **Model consistency:** The proposed ERD should represent the `cluster_telemetry_bindings` relationship explicitly; the current diagram instead draws clusters directly to telemetry sources while the text proposes a separate binding entity and leaves source-sharing as an open question.
- **Action:** Review findings posted in the PR conversation. Refresh the audit, data model and API inventory against current integration source before merge.

**Important:** The successful CI runs above apply to the recorded PR head SHAs only. They do not establish that the PRs are current with the integration branch or that their documentation is accurate against current source. Neither PR was merged during this review.

## 10. Next engineering actions

1. Complete review and approval workflow for PR #39; do not merge without explicit user approval.
2. Refresh PRs #21 and #22 against the current integration branch, address the review notes, and verify their complete diffs and CI on the refreshed heads.
3. Obtain explicit user approval before merging any of PRs #21, #22 or #39.
4. Confirm the user's next product objective before application implementation.
5. Establish the actual VM deployment baseline only if the next objective requires deployment or runtime comparison.
6. For the next application change, create a focused feature branch from the verified integration baseline, inspect the complete diff, run tests, verify CI on the exact head SHA, and prepare a precise deployment/validation plan only after the release gates are met.


## 11. Refreshed architecture documentation proposals (23 November 2026)

The stale documentation proposals #21 and #22 were not merged. Replacement documentation branches were created directly from the verified integration baseline `feature/auth-foundation` at `850d6394e61948a11f40e80c0ce4b7cc427466ba`.

### PR #40 — Telemetry source architecture refresh
- URL: https://github.com/faith-fork/minio-analytics/pull/40
- Branch: `docs/telemetry-architecture-refresh`
- Head: `07c27d8bb23467aefd5afa9a0422f8043b471561`
- Base: `feature/auth-foundation` at `850d6394e61948a11f40e80c0ce4b7cc427466ba`
- Compare: 2 commits ahead, 0 behind; merge base equals the integration baseline.
- Files: current integration README addition and ADR-001.
- Review: complete GitHub patch fetched. README change adds the telemetry architecture section without reverting other README content. ADR retains Prometheus-only initial provider, Analytics-owned history, no direct MinIO polling, selective/rate-controlled collection, and deferred VictoriaMetrics/push ingestion.
- CI: no PR workflow runs returned for this exact head; combined status returned no statuses. CI is not verified.
- Application tests/runtime validation: not run; documentation-only.
- State: open, unmerged; no merge or deployment approval.

### PR #41 — Phase 0 audit, data model and API inventory refresh
- URL: https://github.com/faith-fork/minio-analytics/pull/41
- Branch: `docs/phase-0-audit-refresh`
- Head: `e97dc1a8aff4e8d4035771dbb8428c5f13bbc7b7`
- Base: `feature/auth-foundation` at `850d6394e61948a11f40e80c0ce4b7cc427466ba`
- Compare: 3 commits ahead, 0 behind; merge base equals the integration baseline.
- Files: Phase 0 audit, data model, API inventory/backlog.
- Corrections: PR #38's atomic migration transaction fix is recorded as remediated while residual migration governance remains; target ERD now explicitly links clusters and telemetry sources through `cluster_telemetry_bindings`; API inventory includes both node performance and performance-series routes.
- CI: no PR workflow runs returned for this exact head; combined status returned no statuses. CI is not verified.
- Application tests/runtime validation: not run; documentation-only.
- Audit limitations: static source review only; no VM, live Prometheus, load or penetration validation.
- State: open, unmerged; no merge or deployment approval.

### Superseded proposals
- PR #21 remains open and stale (head `498157fc90e55671bcc999a9b5f2f7539c931b4d`, previously 2 ahead / 75 behind); it contains the doubled-backslash README defect. Replacement proposal: PR #40.
- PR #22 remains open and stale (head `466f200f436dcc90df98acf24ae7eea948a3734a`, previously 3 ahead / 75 behind); it contains outdated migration and API inventory claims and inconsistent target ERD relationships. Replacement proposal: PR #41.
- The old PRs have not been closed automatically. No merge or close action has been taken.

### Current engineering boundary
PRs #40 and #41 are prepared for review only. Their CI is not verified, and GitHub initially reported `mergeable=false` at PR creation; re-check mergeability and exact PR heads before any further action. PR #39 remains open and unmerged. The VM deployment state remains not verified. The user has not authorized merging or deployment.


## 12. Merge authorization and quality-gate check (23 November 2026, 20:44 IST)

The user responded "go ahead" after the three documentation PRs were presented as ready for review and explicit merge approval. This is treated as explicit authorization to merge PRs #39, #40 and #41, subject to the Charter's mandatory quality gates.

### Fresh GitHub state
- PR #39: open, mergeable; head `30ede0fb0d1cdd2eecff0115e61507a82cd6fe92`; base `feature/auth-foundation`.
- PR #40: open, mergeable; head `07c27d8bb23467aefd5afa9a0422f8043b471561`; base `feature/auth-foundation`.
- PR #41: open, mergeable; head `e97dc1a8aff4e8d4035771dbb8428c5f13bbc7b7`; base `feature/auth-foundation`.
- The three PR heads and complete patches were re-fetched. Their branch comparisons remain respectively 8/0, 2/0 and 3/0 ahead/behind.

### Blocking quality gate
- The repository's `.github/workflows/tests.yml` defines pull-request tests for base branches `main` and `feature/**`; all three PRs target `feature/auth-foundation`.
- For each exact PR head, the GitHub workflow-run lookup returned no PR-triggered workflow runs.
- The combined commit-status lookup returned no statuses for PR #40 and PR #41; the current #39 head likewise has no recorded CI evidence in this review.
- No alternate manual workflow-dispatch action is available through the connected GitHub interface.
- No tests were run locally in this environment. Documentation-only changes reduce code risk but do not waive the Charter's explicit CI verification requirement.

### Result
User authorization to merge is recorded, but **no PR has been merged** because the mandatory CI evidence is absent. Do not merge until CI is visible and successful on the exact current head SHAs (or the user explicitly changes the Charter's quality-gate requirement). No deployment authorization has been given.


## 13. Documentation PR merge completion (23 November 2026)

The user's explicit approval to merge PRs #39, #40 and #41 was executed after the required CI evidence was located and verified on each exact PR head.

### Pre-merge CI on exact PR heads
- PR #39 head `5dfee7932e7cb207aec58b05729a0c7df6abb6b8`: GitHub Actions run [45203065035](https://github.com/faith-fork/minio-analytics/actions/runs/45203065035) — Python 3.12 regression tests and frontend syntax validation both passed.
- PR #40 head `07c27d8bb23467aefd5afa9a0422f8043b471561`: run [45189686798](https://github.com/faith-fork/minio-analytics/actions/runs/45189686798) — both jobs passed.
- PR #41 head `e97dc1a8aff4e8d4035771dbb8428c5f13bbc7b7`: run [45189693916](https://github.com/faith-fork/minio-analytics/actions/runs/45189693916) — both jobs passed.

### Merges completed
All three PRs are confirmed closed and merged into `feature/auth-foundation`:
- PR #39 — merge commit `d662a6a430a2f93f591f333f4f18a225ea45746f`.
- PR #40 — merge commit `7ce4c4fd88602876f59a9555f1f574a52a2a5d23`.
- PR #41 — merge commit `bf1f3f03631c083a8fa350224cb892a660eab1f7`.

The integration branch was compared against the final PR #41 merge commit and returned `identical` (0 ahead, 0 behind). Therefore the verified integration HEAD at this checkpoint is `bf1f3f03631c083a8fa350224cb892a660eab1f7`.

### Post-merge CI
- PR #39 merge commit run [45209586859](https://github.com/faith-fork/minio-analytics/actions/runs/45209586859): both Python 3.12 tests and frontend syntax validation passed.
- PR #40 merge commit run [45209660296](https://github.com/faith-fork/minio-analytics/actions/runs/45209660296): both Python 3.12 regression tests and frontend syntax validation passed.
- PR #41 merge commit run [45209696955](https://github.com/faith-fork/minio-analytics/actions/runs/45209696955): both Python 3.12 regression tests and frontend syntax validation passed.
- All six post-merge jobs across the three merge commits completed successfully.

### Release boundary
- Scope merged: governance documentation, telemetry-source ADR/README documentation, Phase 0 audit, data model and API inventory/backlog.
- No application code, schema migration, or runtime configuration was changed by these three PRs.
- No VM deployment was performed or authorized. Current deployed branch/SHA, service state and runtime behaviour remain **Not verified**.
- Superseded PRs #21 and #22 remain open; no close action was taken.


## 14. Prometheus outbound security increment — 23 November 2026

### Baseline and branch
- Verified integration branch: `feature/auth-foundation`, HEAD `7edb9223b94df42a6c7b7c951d1d1dd80d6f4923`.
- Feature branch: `feature/prometheus-egress-security`.
- PR #42: https://github.com/faith-fork/minio-analytics/pull/42
- Current PR head: `d554bbf583bbbb97de05b42d9cf5f307e3d3c8d5`.
- Compare: 9 commits ahead, 0 behind; merge base is the verified integration HEAD.

### Scope implemented for review
- Added endpoint validation for RFC1918 IPv4, IPv6 ULA and globally routable addresses; prohibited ranges and unsafe DNS answers are rejected.
- Pins the actual TCP socket to a validated literal IP, while retaining the configured hostname for HTTP Host and HTTPS SNI/certificate verification.
- Rejects redirects and uses no environment-derived proxy configuration.
- Adds a 4 MiB decoded response limit and bounded timeout; TLS verification remains enabled by default.
- Adds address-policy and client-transport regression tests, including direct socket-target assertions.
- Declares urllib3 as an explicit dependency.
- No schema changes, no credential storage, no UI changes and no VM deployment.

### Remaining security items
The transport connects to a validated literal IP and does not perform a second DNS lookup, closing the DNS validation/connection TOCTOU gap for this request path. Redirects are rejected. Prometheus authentication and secret lifecycle remain a separate unresolved security item. Host/network egress controls remain recommended defence in depth.

### Validation and release boundary
- Full PR diff fetched and reviewed; changed files are `app/collectors/prometheus.py`, new `app/collectors/prometheus_security.py`, and new `tests/test_prometheus_security.py`.
- GitHub Actions run [45228980426](https://github.com/faith-fork/minio-analytics/actions/runs/45228980426) on exact PR head `d554bbf583bbbb97de05b42d9cf5f307e3d3c8d5`: Python 3.12 regression tests **passed (128 passed, 1 warning)**; frontend syntax validation **passed**.
- The earlier run [45228712037](https://github.com/faith-fork/minio-analytics/actions/runs/45228712037) exposed a multicast-address policy test failure; this was corrected by explicitly rejecting multicast/reserved/special addresses. Do not treat the earlier failed run as final evidence.
- PR is open and GitHub reports mergeable after refresh.
- No merge authorization or deployment authorization has been given.
- Runtime connectivity against private customer Prometheus endpoints remains unverified.

### Next actions
1. Re-run and verify CI on the final PR head after this handover update; inspect the exact head's run and jobs.
2. Validate private customer-network connectivity and HTTPS certificate/SNI behaviour in the lab before release.
3. Design Prometheus authentication and secret lifecycle separately; never place credentials in endpoint URLs or ordinary configuration rows.
4. Do not merge or deploy until CI, review, lab validation and explicit user approvals are satisfied.

This section supersedes older handover snapshots above where their branch HEAD, open-PR list, next actions or merge/deployment boundary differ. The older sections are retained as historical checkpoints.


## 15. Prometheus outbound security merge and post-merge verification — 23 November 2026

### Integration state
- PR #42: https://github.com/faith-fork/minio-analytics/pull/42
- Title: Harden Prometheus outbound endpoint handling.
- Feature branch: `feature/prometheus-egress-security`.
- Exact reviewed PR head: `37fb667b42bd19bfd37f335e2ac6b52ea841f66c`.
- PR comparison before merge: 10 commits ahead, 0 behind; merge base `7edb9223b94df42a6c7b7c951d1d1dd80d6f4923`.
- Pre-merge PR CI run [45229185521](https://github.com/faith-fork/minio-analytics/actions/runs/45229185521): Python 3.12 regression tests and frontend syntax validation both passed.
- No review submissions or inline review threads were present at the final pre-merge check.
- User explicitly authorized proceeding with merge if all checks were good.
- PR #42 was squash-merged successfully. Merge commit: `50563c749ce0adfb421713c8b09353a005cd7767`.
- Verified integration branch `feature/auth-foundation` now points to `50563c749ce0adfb421713c8b09353a005cd7767`.

### Post-merge CI
- GitHub Actions run [45231779294](https://github.com/faith-fork/minio-analytics/actions/runs/45231779294) on exact merge commit `50563c749ce0adfb421713c8b09353a005cd7767`.
- Python 3.12 regression tests: passed.
- Frontend syntax validation: passed.
- Both post-merge jobs completed successfully.

### Deployment and runtime boundary
- No VM commands were run; no service restart, deployment, or runtime configuration change was performed.
- Lab deployment target remains the documented Rocky Linux 10.0 environment at `/opt/minio-analytics`, with persistent data under `/data/minio-analytics`.
- Runtime validation still required: private customer-network Prometheus connectivity, DNS resolution/address pinning under the target network, HTTPS certificate validation and SNI/hostname behaviour, timeout/error handling.
- Prometheus authentication and secure secret lifecycle remain a separate P0 item. Do not put credentials in endpoint URLs or ordinary configuration rows.
- Deployment must use the verified integration branch and exact merge commit above, not the feature branch or an older checkout.
- User owns VM operations and runtime acceptance. Provide commands and expected checks; do not execute VM deployment without explicit deployment authorization.

### Next actions
1. Prepare the VM deployment procedure for exact commit `50563c749ce0adfb421713c8b09353a005cd7767`, including backup, clean working-tree checks, dependency installation, restart, journal/health checks and rollback.
2. Have the user execute the VM steps and provide runtime evidence.
3. Complete the Prometheus authentication/secret-management design as a separate reviewed increment before production use.

This section supersedes Section 14's PR-open, pre-merge, and pending-CI statements. Historical checkpoints are retained.


## 16. Prometheus private shared-address regression correction — 23 November 2026

### Root cause
- PR #42 accepted RFC1918 IPv4, IPv6 ULA and globally routable addresses.
- The user's previously working Prometheus endpoint is configured as a literal IPv4 address in RFC 6598 Shared Address Space (100.64.0.0/10).
- Python classifies this address as neither RFC1918-private nor globally routable, so validation rejected it before opening the HTTP connection.
- This is an application policy regression introduced by PR #42, not a subnet connectivity failure.

### Corrective implementation under review
- Feature branch: fix/prometheus-shared-address-endpoints.
- Base integration commit: f3487f92bf7540d1c65559f6efe75e80c8eaee5c.
- Permit RFC 6598 only for explicitly configured literal IPv4 endpoints; DNS names resolving into this range remain rejected.
- Preserve metadata-address blocking, loopback/link-local/multicast/unspecified/reserved checks, DNS validation, socket IP pinning, redirect blocking, proxy isolation, response limits and TLS verification.
- Add regression tests for allowed literal endpoints, CIDR boundaries, DNS-resolved shared addresses and metadata protection.
- No database schema, UI, credential, runtime configuration or VM changes.

### Validation and release boundary
- Automated tests and CI: pending on this feature branch; not yet verified.
- Full diff review and branch ancestry: pending.
- PR merge: not authorized.
- VM deployment/runtime validation: not authorized; user owns deployment and acceptance.
- No merge or deployment without separate explicit user approval.

This checkpoint supersedes the prior handover statement that customer private-network Prometheus connectivity was merely unverified: the reported failure is attributed to the new address-policy rejection, while successful post-fix runtime connectivity remains pending.


## 17. Prometheus customer-network endpoint support redesign — 24 November 2026

### Product decision
The user confirmed that Prometheus endpoints may be configured as reachable IP addresses or FQDNs, on the default port 9090 or a customer-selected port. Customer endpoints may reside in the same or a different private subnet. Hostname resolution must support the operating system resolver, including DNS and local hosts-file/NSS entries.

### Corrected scope for PR #43
- Permit RFC1918 IPv4, RFC6598 shared IPv4 (100.64.0.0/10), IPv6 ULA and globally routable addresses for both literal endpoints and validated hostname answers.
- Resolve FQDNs using the system resolver path (socket.getaddrinfo); this naturally follows configured NSS sources such as /etc/hosts and DNS.
- Validate every A/AAAA result. Reject the entire hostname if any answer is prohibited; do not select only the safe answers.
- Pin the TCP connection to a validated IP; retain the configured hostname for HTTP Host and HTTPS SNI/certificate hostname validation.
- Continue blocking loopback, link-local, multicast, unspecified, reserved/special targets and the explicitly listed metadata addresses.
- Permit custom ports; 9090 remains a convention/default at the configuration layer, not a network-policy restriction.
- HTTPS always requires certificate-chain and hostname verification. The legacy verify_tls constructor argument is retained for compatibility but cannot disable verification. HTTP remains supported as explicitly configured, without TLS protection.

### Security and release notes
- This change does not introduce an arbitrary destination port restriction. Reachability is still determined by customer routing/firewall policy; application-level destination validation remains mandatory.
- Mixed safe/unsafe DNS answer sets are rejected. DNS validation and socket IP pinning prevent a second lookup from changing the connection target.
- Prometheus credentials and secret lifecycle remain a separate P0 design item; do not embed credentials in endpoint URLs.
- No schema migration, UI, database mutation, or VM deployment is included in this PR.
- CI and exact-head review must be verified before any merge consideration. No merge or deployment is authorized by this handover.
- The previous Section 16's literal-only RFC6598 exception and claim that DNS-resolved RFC6598 addresses remain blocked are superseded by this section. The asserted specific cause of the original customer failure remains an inference until runtime validation confirms it.

## 18. RFC 6598 boundary validation correction — 24 November 2026

### CI finding
- GitHub Actions run for PR #43 failed in the Python 3.12 regression suite: 142 passed and 2 failed.
- Both failures showed that Python's `ipaddress.is_global` classified addresses immediately outside RFC 6598 Shared Address Space (100.64.0.0/10) as global on the runner's Python version.
- The prior policy checked `is_global` before applying the RFC 6598 boundary, so addresses such as 100.63.255.255 and 100.128.0.1 were accepted unintentionally.

### Correction committed to the PR branch
- Introduce an explicit conservative guard for 100.0.0.0/8 before consulting `is_global`.
- Permit only addresses within 100.64.0.0/10 from that enclosing /8; reject the remainder.
- Retain the explicit metadata block for 100.100.100.200, even though it is inside the permitted RFC 6598 range.
- Expand boundary regression coverage to include 100.0.0.1, 100.63.255.255, 100.128.0.1 and 100.255.255.254.
- This correction is intentionally conservative and avoids Python-version-dependent classification around the shared-address block.

### Validation and release boundary
- Fix commits: 6e2290518f0e93810c88586111a9a85f9cd257e8 (policy) and 4fe6a851ce3842af9658d21ad9ee6a0ab9012c7f (tests).
- CI must rerun against the resulting exact PR head before the fix can be considered validated.
- No merge or deployment is authorized by this checkpoint.


## 19. Master Configuration workspace — 24 November 2026

### Product decision and navigation
- Consolidate the former Master Admin, Prometheus Connections and Historical Backfill entry points into one **Master Configuration** workspace.
- The workspace contains three tabs: **General Configuration**, **Prometheus Configuration** and **Historical Backfill**.
- **User Administration remains a separate sidebar item** and retains its existing admin-role visibility. It is not part of the Master Admin-only workspace.
- Preserve existing validated workflows, role checks, APIs, connection/discovery behaviour, credential lifecycle, backfill jobs and stored history.

### PR #52 — implementation under review
- URL: https://github.com/faith-fork/minio-analytics/pull/52
- Branch: `feature/master-configuration-workspace`
- Base: `feature/prometheus-authentication`
- Base SHA: `12883b12bafd3de5cc34fb7e4937bde324ad56d5` (PR #51 merge commit).
- Current head at initial CI verification: `7c3bb432f2d39cabf33553a70e1bfb6aec56b856`.
- Branch comparison: 6 commits ahead, 0 behind; merge base equals the PR #51 merge commit.
- Changed files: `app/static/index.html`, `app/static/app.js`, `app/static/app.css`, `app/static/prometheus-connections.js`, `app/static/backfill-jobs.js`, and new `tests/test_master_configuration_navigation.py`.
- Scope: frontend navigation/rendering and focused regression tests. No API contract, database schema, collector, scheduler, dependency, credential-storage or VM changes.
- Existing view identifiers are mapped to their corresponding new tabs for compatibility.
- Prometheus and backfill renderers are reused within the shared tab panel; General Configuration reuses the existing settings and backup implementation.

### CI and review
- GitHub Actions run [45420575644](https://github.com/faith-fork/minio-analytics/actions/runs/45420575644) on exact head `7c3bb432f2d39cabf33553a70e1bfb6aec56b856` completed successfully.
- Python 3.12 regression suite: **194 passed, 1 non-blocking Starlette TestClient/httpx deprecation warning**.
- Frontend JavaScript syntax validation: **passed**.
- Complete PR patch reviewed. GitHub reported mergeable; no review submissions or inline review threads were present at the check.
- PR remains Draft/open and unmerged. No merge approval or deployment approval is implied by this handover.
- VM deployment and browser validation have not been performed. User owns runtime validation and acceptance.

### Required next validation
- Verify Master Configuration is visible only to Master Admin.
- Verify the three tabs render and switch correctly.
- Verify General Configuration save and backup history.
- Verify Prometheus connection list, add/test, authentication and cluster discovery workflows.
- Verify Historical Backfill job creation, progress and actions.
- Verify User Administration remains separately visible to Admin users and retains its existing role controls.
- Verify normal navigation, reports, cluster pages and Collection Health remain unaffected.

### Integration note
The Charter designates `feature/auth-foundation` as the integration branch. PR #52 is intentionally based on `feature/prometheus-authentication` because it depends on the newer PR #51 integration containing the Prometheus connection and backfill experiences being reorganized. Do not retarget or merge it to the older integration branch without first reconciling the prerequisite feature stack and verifying the complete ancestry.

This section records the PR #52 checkpoint only. It does not supersede the Charter's merge, deployment or runtime-acceptance gates.


## 20. General Configuration and Historical Backfill UI refinement — 24 November 2026

### Approved design direction
- Balanced enterprise dashboard layout for both General Configuration and Historical Backfill.
- General Configuration: two-column collection settings and telemetry footprint, compact backup management and history, contextual explanations, and password confirmation at save time.
- Historical Backfill: distinct job-creation and execution-monitoring sections, cluster selection, date presets, visible range constraints, summary counters, progress cards, outcome counts and grouped job actions.

### Implementation checkpoint
- Feature branch: feature/configuration-ui-refinement
- Base: current deployed feature/prometheus-authentication head 37065f982040062064a2fb843c4b262f4c83bc19, including merged Master Configuration navigation regression fix PR #53.
- Scope: frontend presentation and focused regression tests only.
- Existing API routes, authorization, settings validation, scheduler behaviour, retention policy, backup integrity verification, backfill lifecycle, 60-day limit and stored history are preserved.
- No schema migration, API contract change, dependency change or VM modification is included.
- Automated tests, exact-head CI, complete patch review and browser validation remain pending.

No merge or deployment is authorized by this checkpoint.


## 21. General Configuration and database backup management — 24 November 2026

### Approved product direction
- Split General Configuration into two secondary workspaces: **Collection Settings** and **Database Backups**.
- Keep the existing top-level Master Configuration tabs: General Configuration, Prometheus Configuration and Historical Backfill.
- Show 10 backup records by default, with page sizes 10, 25, 50 and 100.
- Add administrator-reviewed cleanup of old backups with a preview, password confirmation and an audit trail.
- Preserve the latest configurable number of verified backups (default 5), including when older than the retention window.
- Unverified files must be preserved for investigation; cleanup must never follow symlinks or remove files outside the application-managed backup naming pattern.
- Automatic retention and manual cleanup must apply the same age and minimum-keep safeguards.

### PR #57 — implementation checkpoint
- URL: https://github.com/faith-fork/minio-analytics/pull/57
- Branch: `feature/backup-management-workspace`
- Base: `feature/prometheus-authentication` at `850ff98e80855a0dd2981f26f17292ce6e78a255` (merged PR #55).
- Application/test head reviewed and validated: `d9d5034025f082dfcf5680d9571b99359d0c58bc`. This checkpoint update is documentation-only; verify the live PR head and CI again after it is committed.
- Compare at PR creation: 16 commits ahead, 0 behind; merge base equals the deployed PR #55 commit.
- Changed files at PR creation: `app/api/master_admin.py`, `app/static/app.css`, `app/static/app.js`, `scripts/backup_database.py`, `tests/test_backup_management.py`, and `tests/test_master_configuration_navigation.py`.
- No database schema migration or dependency change is intended.
- Existing settings, backup creation and download routes remain; cleanup preview and execution routes are additive.
- Backup cleanup audit records are written to `/data/minio-analytics/logs/backup-cleanup-audit.jsonl` with restrictive file permissions.
- Draft PR created for review. GitHub Actions run [45453807552](https://github.com/faith-fork/minio-analytics/actions/runs/45453807552) on exact application/test head `d9d5034025f082dfcf5680d9571b99359d0c58bc` passed: **209 Python tests passed, 1 existing Starlette/httpx deprecation warning; frontend syntax validation passed**. Complete diff reviewed; PR is mergeable, with no review comments submitted. Browser/runtime validation remains pending. No merge or deployment approval is given.

### Explicitly deferred navigation-test improvement
- GitHub Issue #56: https://github.com/faith-fork/minio-analytics/issues/56
- Scope: add executable DOM-backed JavaScript navigation tests for `setView`, Master Configuration tab switching, legacy view aliases and selector/DOM assumptions; run them in CI.
- This is intentionally separate from PR #57 to keep backup-management scope focused.

### Release and safety gates
- Verify exact PR head, complete diff, backend tests, frontend syntax and CI before requesting merge approval.
- Review backup retention and cleanup behaviour, including audit failure handling and concurrent operations.
- No VM deployment is authorized. User-owned browser/runtime validation is required after any later approved deployment.


## 22. PR #57 merge checkpoint — 25 November 2026

- PR #57, **Improve General Configuration and database backup management**, was squash-merged after explicit user approval.
- PR: https://github.com/faith-fork/minio-analytics/pull/57
- Source head: `3197bf1481588d6c8ce3053bb98545431c66b25a`
- Merge commit: `9c3544444197d123d1c4f52eabc10bd2120bf137`
- Verified `feature/prometheus-authentication` points exactly to the merge commit; compare result is identical (0 ahead / 0 behind).
- CI on the exact PR head passed: 209 Python tests, 1 existing Starlette/httpx deprecation warning; frontend syntax validation passed.
- PR #57 is closed and merged. No VM deployment has been performed or authorized by this merge approval.
- Deployment gate remains separate: confirm the lab VM's branch, worktree, remote, current commit and service health before any update. Preserve any local modifications; do not reset or overwrite them.
- After a separately approved deployment, the user must validate Collection Settings, Database Backups, pagination, backup creation/download, cleanup preview, password rejection/acceptance, stale-preview conflict handling, minimum-five preservation, unverified-file preservation and responsive layouts.
- JavaScript DOM-backed navigation regression tests remain parked in Issue #56: https://github.com/faith-fork/minio-analytics/issues/56


## 23. PR #59 frontend cache invalidation and DOM navigation tests — 25 November 2026

### Implementation and integration
- PR #59: https://github.com/faith-fork/minio-analytics/pull/59 — **Prevent stale frontend assets and test navigation in a DOM**.
- Feature branch: `feature/frontend-cache-and-navigation-tests`.
- Reviewed PR head: `53a49991faa713f6ae2d09a6342b31b563cd08c8`.
- Squash merge commit: `55d7940ce32e1c76bb80ee7627bbacc2c5ce0feb`.
- Integration branch `feature/prometheus-authentication` was verified to match the merge commit exactly (0 ahead / 0 behind).
- PR #59 addresses the parked navigation-testing follow-up from Issue #56.

### Scope
- Dashboard HTML uses a content-derived fingerprint for the four first-party CSS/JavaScript assets.
- HTML response uses `Cache-Control: no-cache, must-revalidate` so browsers re-check the document and obtain the current fingerprinted URLs.
- CI runs DOM-backed navigation tests using jsdom for sidebar navigation, Master Configuration tab routing and legacy aliases, alongside syntax and Python tests.
- Added regression coverage for root-route registration and asset-version substitution/cache headers.
- No database schema, collector, scheduler, metrics, or persistent data changes.

### CI and review
- Exact PR-head CI passed: **212 Python tests passed**, with one existing non-blocking Starlette/httpx deprecation warning; JavaScript syntax checks and DOM-backed navigation tests passed.
- Complete patch reviewed; the root-route decorator placement regression found during review was corrected and covered by a test before merge.
- PR #59 was merged after explicit user approval. Merge commit: `55d7940ce32e1c76bb80ee7627bbacc2c5ce0feb`.

### Lab deployment evidence — 25 November 2026
- User completed preflight and fast-forward deployment on the lab VM `minio-analytics` at `/opt/minio-analytics`.
- VM branch: `feature/prometheus-authentication`; worktree clean; remote is the expected repository.
- VM HEAD verified at the exact merge commit `55d7940ce32e1c76bb80ee7627bbacc2c5ce0feb`.
- `minio-analytics-web.service` restarted successfully and is `active (running)`.
- `/healthz` returned HTTP 200 with `{"status":"ok","database":"ok"}`.
- Dashboard root returned HTTP 200 and `Cache-Control: no-cache, must-revalidate`.
- All four assets showed the same fingerprint query value: `0958cb659fb2458b`.
- Git worktree remained clean after deployment.

### Browser acceptance — 25 November 2026
- User supplied screenshots confirming the dashboard Overview renders; Master Configuration navigation works; General Configuration / Collection Settings renders; Database Backups renders with pagination and backup integrity status; Prometheus Configuration renders with configured endpoint; and Historical Backfill renders.
- The screenshots also show an authenticated Admin session and the sidebar navigation in the expected state.
- Combined with deployment-stage 1–3 evidence, **browser functional acceptance is passed for the displayed views**.
- Browser Console error status and explicit Network-panel verification of fingerprinted asset requests were not included in the evidence; these remain unverified, but do not block the demonstrated navigation/UI acceptance.
- Deployment/runtime acceptance for PR #59 is therefore recorded as passed for the checks evidenced by terminal output and screenshots. No further deployment is requested by this checkpoint.


## 24. Baseline-preservation incident and recovery checkpoint — 28 November 2026

### Product Owner directive
The Product Owner explicitly approved the addition of a mandatory change-control/baseline-preservation policy and authorized the recovery audit and subsequent feature work. The requirement is to prevent previously approved changes from disappearing because new features are developed or deployed from incomplete/divergent branches.

### Governance document added
- PR #77: https://github.com/faith-fork/minio-analytics/pull/77
- Branch: `docs/baseline-preservation-governance`
- Head: `ec44b2068c530f5240832dba3f8c8cb2df1568e5`
- Base: `feature/auth-foundation` at `50a610f879c97cb008ecc2e9d16a20c66a4bad04`
- New document: `docs/governance/CHANGE_CONTROL_AND_BASELINE_PRESERVATION.md`
- Documentation-only; draft/open; no merge or deployment.
- Policy includes verified baseline checks, branch dependency integrity, Preservation Matrix for every application PR, exact-SHA CI/lab gates, checkpoint ledger, incident-response steps and no accidental downgrade deployments.

### Branch incident evidence
- **PR #71 — Cluster Detail workspace redesign** remains open/draft, not merged. Base: `feature/auth-foundation` at `50a610f879c97cb008ecc2e9d16a20c66a4bad04`; head branch `feature/cluster-detail-workspace`; head `89604dea786438103c7d684d8fcb28e04a2726cb`. PR #71's recorded CI run **46105289555** completed successfully. It includes the approved four workspaces: Infrastructure Status, Capacity & Forecast, Object & Bucket Analysis, and Daily Snapshots. The head commit is based on the PR #71 implementation head `786e71a87a1cef8eb71ded5952446557393b04a2` and adds the object-analysis trend filter. The commit description records prior lab validation/browser acceptance for that filter fix.
- **PR #74 — Consolidated Reports historical analytics** is open, not merged. Head `0cbc27fa1ba9123825ec2752e38819ebbd4c7a52`; base `feature/auth-foundation`.
- **PR #75 — Report history selector UX** is open/draft. Head `25f78b2059f80ceda99877f997e53975474a002a`; stacked on #74.
- **PR #76 — Report history selector alignment** is open/draft. Head `6e1e4206238a0eaf15b5b67c8ce0f7db8c215550`; stacked on #75.
- The PR #74–#76 chain is based on the auth-foundation baseline and does not contain PR #71's Cluster Detail workspace changes. The latest lab deployment reported by the user was branch `lab/report-history-filter-right-alignment-validation` at `6e1e4206238a0eaf15b5b67c8ce0f7db8c215550`. This explains the likely regression: the lab was switched to a Reports feature chain whose baseline omitted the unmerged Cluster Detail redesign. This is a branch/baseline selection problem, not evidence that the PR #71 code was deleted.
- The PR #71 head changed nine files: analytics API, bucket collector, persistence, CSS, JS, design doc, frontend tests, API tests, bucket collector tests. The Report PR chain also modifies overlapping frontend files and report-specific analytics/tests, so integration requires full-file/diff reconciliation—not blind branch switching or cherry-picking.

### Important state distinction
PR #71 is a successful CI feature branch and contains the workspace redesign, but it is **not merged into the designated integration branch**. The reports chain is independently validated, but it also is not merged. No single verified integration baseline currently contains both feature sets. The exact lab-accepted baseline must be confirmed from current VM evidence; this checkpoint records the latest reported lab commit, not a live VM inspection.

### Recovery work authorized; status
1. Reconcile the actual lab branch/commit and working tree from user terminal evidence. **Pending current VM verification.**
2. Audit PR #71 and #74–#76 complete patches, overlapping files, dependency ancestry, and approved capabilities. **Started; detailed integration analysis pending.**
3. Create a dedicated recovery/integration candidate preserving Cluster workspaces plus Reports historical analytics/filter UX. **Not yet created.**
4. Resolve overlapping files, add integration regression tests and a Preservation Matrix, run CI on the exact candidate. **Pending.**
5. Lab deploy only after candidate SHA, complete diff, CI and preservation checklist are verified. **Not authorized yet.**
6. Record user acceptance before marking the candidate as the new lab-accepted baseline. **Pending.**

### Next approved feature work
After recovery/reconciliation, perform a full graph/filter inventory and implement a shared historical-range UX. Approved historical presets: 7, 30, 60, and 90 days; 6 months; 1, 2, and 5 years; 10 years/all available; and Custom. Historical default is 90 days unless a documented metric-specific exception applies. Live telemetry ranges remain semantically distinct but should share the selector's UX pattern. This feature must be based on the reconciled baseline, never on a branch that omits approved capabilities.

### Merge/deployment boundary
PR #77 is documentation only and remains draft. The recovery and time-range feature work is authorized, but no existing PR merge, branch rewrite, or lab deployment is authorized without a separate explicit approval at the appropriate gate.
