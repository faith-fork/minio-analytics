# Change Control and Baseline Preservation

**Status:** Approved engineering governance addition  
**Approved:** 28 November 2026  
**Applies to:** All MINIO Analytics feature, bug-fix, refactor, design, integration, and lab-validation work  
**Authority:** Master Engineering Charter v1.0 and Engineering Handover

## 1. Non-negotiable preservation rule

Previously approved, implemented, or lab-validated functionality must not disappear, regress, be silently reverted, or be replaced because work is performed on a new feature branch.

A new feature is additive by default. Any intentional behavior removal, redesign, replacement, or incompatibility must be explicitly identified, explained, reviewed, and approved by the Product Owner **before implementation**.

## 2. Establish a verified baseline before every change

Before creating or updating a development branch:

1. Inspect the current repository branches, open PRs, relevant commits, and their ancestry.
2. Identify the current **verified integration baseline** and the latest **lab-accepted application commit**.
3. Record the baseline commit SHA(s) and the approved capabilities present in that baseline.
4. Identify prerequisite PRs/features and determine whether the proposed branch is based on the correct dependency.
5. Review the target branch's full application diff against the verified baseline—not only the new feature's files.
6. Do not assume a branch contains another feature because it was discussed, tested, or deployed in a different branch/session.

The repository is the source of truth for code. The lab's currently deployed commit is a separate source of truth for runtime acceptance and must be recorded independently.

## 3. Branch and PR dependency policy

- Feature branches must be based on the verified integration baseline or explicitly stack on their prerequisite feature branch/PR.
- UI-only or documentation-only branches must not accidentally become a replacement application baseline.
- Stacked PRs must state their dependency order and target the immediate prerequisite branch.
- Before changing a PR base, rebasing, merging, or reconciling branches, inspect and document the resulting ancestry and complete diff.
- Never use a branch that lacks approved functionality as the deployment candidate merely because it contains the newest feature.
- Do not merge, rebase, squash, close, or otherwise rewrite approved feature history without the appropriate explicit authorization.
- Integration must preserve approved features; when branches diverge, reconcile deliberately and verify—not blindly merge or cherry-pick.

## 4. Required regression-preservation review for every application PR

Every application PR must include a **Preservation Matrix** identifying:

| Approved capability | Baseline evidence | Expected after change | Validation evidence |
|---|---|---|---|
| Existing feature/workspace | PR, commit, or lab acceptance reference | Preserved / intentionally changed with approval | Automated test, diff review, and/or lab check |

The matrix must cover all affected areas and any shared navigation, layout, routing, API, frontend state, CSS, data model, or common components that could create collateral impact.

PR review must explicitly check for:
- Removed or hidden routes, tabs, workspaces, cards, panels, controls, and navigation.
- Replaced legacy pages or rendering paths.
- Shared JavaScript/CSS changes that affect other screens.
- API contract or database changes that affect existing features.
- Missing/changed filters, date ranges, graph controls, exports, or user preferences.
- Data correctness and unavailable-vs-zero semantics.
- Regressions outside the nominal PR scope.

A statement such as “only UI changed” is not sufficient evidence of safety.

## 5. Deployment candidate and lab protection

Before issuing lab deployment commands:

1. State the exact candidate branch and commit SHA.
2. State the lab's recorded current commit/baseline.
3. Verify the candidate includes the required approved features and prerequisite changes.
4. Compare the complete candidate diff against the lab baseline and identify any removals.
5. Confirm CI passed on the exact candidate SHA.
6. Provide the expected feature-preservation checklist and rollback SHA/branch.
7. Deploy only to the intended isolated validation branch/environment.

The lab must not be switched to an older or incomplete branch without an explicit warning and Product Owner approval. A feature validation deployment must not be mistaken for the new canonical lab baseline.

After validation, record:
- Exact deployed commit SHA and branch.
- Service/runtime status.
- Screenshots and tested workflows.
- Pass/fail and outstanding issues.
- Whether the commit becomes a lab-accepted baseline (only after explicit acceptance).

## 6. Baseline ledger

Maintain a baseline ledger/checkpoint in the Engineering Handover. Each checkpoint records:

- Checkpoint date.
- Verified integration baseline commit.
- Lab-accepted commit (if different).
- Approved feature PRs and commits included.
- Pending/staged PRs and dependency order.
- Known regressions, exclusions, and unresolved validation.
- Candidate feature branch/commit currently under test.
- Deployment/rollback instructions.

Never overwrite a prior checkpoint. Add a new dated checkpoint so historical state remains auditable.

## 7. Integration and release gates

No PR may be considered integration-ready solely because its own tests pass.

Required gates:
1. Correct dependency/base branch.
2. Full diff and ancestry review.
3. Preservation Matrix completed.
4. Regression tests for impacted existing functionality.
5. CI green on exact PR head.
6. Lab validation when UI/runtime behavior or operational changes are involved.
7. Product Owner acceptance.
8. Explicit merge authorization, where required.

A PR that introduces a regression to an approved feature must be blocked, even if its new feature works.

## 8. Incident response when approved functionality disappears

When a regression or missing feature is discovered:

1. Stop further feature work and deployments on the affected candidate.
2. Record the exact branch, commit, and lab commit.
3. Reproduce and identify the commit/branch boundary that lost the capability.
4. Inspect branch ancestry and full diffs to establish root cause.
5. Restore the approved capability through deliberate integration/reconciliation.
6. Add a regression test or preservation check where feasible.
7. Update the baseline ledger and handover.
8. Resume feature work only from the reconciled baseline.

Do not apply an ad-hoc fix on an unrelated feature branch or deploy another branch until its preservation status is established.

## 9. Current incident and next engineering sequence (28 Nov 2026)

The Cluster Detail workspace redesign was observed missing from the lab after deploying the Reports historical-filter branch.

Relevant open PRs and known heads at investigation time:

- **PR #71 — Cluster Detail workspace redesign**
  - Head branch: `feature/cluster-detail-workspace`
  - Head SHA: `89604dea786438103c7d684d8fcb28e04a2726cb`
  - Base: `feature/auth-foundation`
  - Draft/open; not merged.
  - Intended four workspaces: Infrastructure Status, Capacity & Forecast, Object & Bucket Analysis, Daily Snapshots.
- **PR #74 — Consolidated Reports historical analytics**
  - Head: `0cbc27fa1ba9123825ec2752e38819ebbd4c7a52`
  - Base: `feature/auth-foundation`
- **PR #75 — Reports historical range selector UX**
  - Head: `25f78b2059f80ceda99877f997e53975474a002a`
  - Stacked on PR #74.
- **PR #76 — Reports historical selector alignment**
  - Head: `6e1e4206238a0eaf15b5b67c8ce0f7db8c215550`
  - Stacked on PR #75.

These feature branches are not yet established as a single reconciled integration baseline. The Reports branch chain is based on `feature/auth-foundation`; PR #71 is also based on that branch. Deploying the Reports chain therefore does not guarantee it includes PR #71. This is the likely branch/baseline cause of the observed disappearance, pending complete ancestry and diff reconciliation.

**No PR in this incident is authorized to be merged or rewritten by this document.**

### Immediate recovery plan

1. Audit PR #71, PR #74–#76, their full diffs, ancestry, and lab-deployed SHA.
2. Identify the latest lab-accepted Cluster workspace commit and all approved changes that must be preserved.
3. Produce a capability-preservation inventory and a verified integration plan.
4. Reconcile branches on a dedicated integration/recovery branch; review the complete resulting diff.
5. Test the recovered Cluster workspaces and Reports changes together in CI.
6. Deploy the exact integration candidate to the lab only after checks and provide a clear validation checklist.
7. Record Product Owner acceptance before declaring it the new lab-accepted baseline.

## 10. Approved historical graph range standardization — planned scope

Historical graph range presets should be consistent across historical analytics:

- 7 days
- 30 days
- 60 days
- 90 days
- 6 months
- 1 year
- 2 years
- 5 years
- 10 years / all available
- Custom inclusive date range

Historical analytics default: **90 days**, unless a documented metric-specific reason requires a different default.

Live telemetry ranges (minutes/hours/days) are semantically distinct from historical snapshot ranges. They should share the common selector design, alignment, interaction, custom-range behavior, and visual language, but must retain appropriate live presets and metric semantics.

The graph inventory and implementation must include, at minimum, Cluster, Node Infrastructure, Drives & Filesystems, Network, Collection Health, Performance Reports, and Consolidated Reports. Each graph's API parameters, retention limits, timezone handling, data availability, default, refresh behavior, zoom/reset, custom-date validation, and missing-data semantics must be audited.

This work must be implemented only on top of the reconciled, verified baseline described in the immediate recovery plan.

## 11. Engineering commitment

The governing principle is:

> **New work must build on the product we have approved—not on a convenient branch that happens to contain the new code.**

Feature delivery speed must never be prioritized over preserving the validated product. Branch integrity, dependency correctness, complete diff review, regression testing, and baseline tracking are mandatory engineering activities.
