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
