# MINIO Analytics — Engineering Documentation

This directory contains the project's controlled engineering records.

## Governance

- [Master Engineering Charter v1.0](governance/MASTER_ENGINEERING_CHARTER.md) — agreed product direction, architecture baseline, roles, branch governance, regression prevention, quality gates and release process.
- [Engineering Handover](governance/ENGINEERING_HANDOVER.md) — latest verified engineering checkpoint. Treat it as a snapshot, not as a substitute for live GitHub or VM verification.

## Architecture records

The following architecture documents are already proposed in separate open pull requests. Review and integrate those PRs rather than creating duplicate copies:

- [ADR-001: Telemetry Sources and Collection Architecture — PR #21](https://github.com/faith-fork/minio-analytics/pull/21)
- [Phase 0 Architecture Audit, Data Model and API Backlog — PR #22](https://github.com/faith-fork/minio-analytics/pull/22)

## Source-of-truth rules

1. The Charter governs stable product and engineering decisions.
2. The Handover records the last verified project checkpoint and must be updated after every substantial engineering session.
3. Live GitHub is authoritative for branch heads, commits, pull request state, ancestry and CI results. Re-check these at the start of each session.
4. The deployed VM is authoritative for runtime state. Never infer its deployed branch or commit from GitHub; request or obtain current runtime evidence when needed.
5. If the Handover conflicts with live GitHub or current VM evidence, update the Handover after recording the verified facts.
6. Never merge or deploy without the user's explicit approval.

## Starting a new engineering session

1. Read the Charter and the latest Handover.
2. Verify the repository, designated integration branch and current HEAD directly in GitHub.
3. Review open PRs, complete diffs, ancestry, required prerequisites and CI.
4. Confirm the user's next product objective before implementation.
5. If runtime or deployment matters, establish the actual VM state separately.
6. Work on a focused feature branch and follow the Charter's review, test, CI, approval and release gates.

## Updating these records

- Keep the Charter stable; create a new version only when an agreed product or governance decision changes.
- Update the Handover after substantial work, recording exact SHAs, PRs, test/CI evidence, runtime status, decisions, risks, approvals and next actions.
- Do not write an unverified state as fact. Use **Not verified** where evidence is unavailable.
