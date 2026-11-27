# D1 — Global Time Range & Interface Selection Standardization

**Status:** Design checkpoint / audit completed; implementation not started  
**Base branch:** `feature/auth-foundation`  
**Design branch:** `design/global-time-range-d1`  
**Scope:** Cross-workspace historical time controls and Network interface selection

## Goals

1. Standardize historical time-range selection across dashboard workspaces and chart groups.
2. Provide common quick ranges: 5m, 15m, 30m, 1h, 3h, 6h, 12h, 24h, 2d, 7d, 30d.
3. Support custom absolute start/end time and timezone-aware display.
4. Make the selected time context consistent for all charts in the current dashboard context.
5. Add **All interfaces** to Network's interface selector for the selected node.
6. Keep interface series distinct; do not sum or aggregate across interfaces.
7. Preserve honest handling of data gaps, sampling cadence, retention, and unavailable metrics.

## User experience

### Global time picker

A shared time-picker component should be located in the dashboard-level header/context, not independently duplicated in each workspace. It should expose:

- Quick ranges: Last 5 minutes, 15 minutes, 30 minutes, 1 hour, 3 hours, 6 hours, 12 hours, 24 hours, 2 days, 7 days, and 30 days.
- Custom absolute range (start/end date-time).
- Relative range support where practical (e.g. now-6h, now-24h, now-7d).
- Explicit timezone indication (browser timezone by default; preserve existing IST display conventions where applicable).
- Apply/cancel behavior for custom range.
- A clear selected-range label and resolved start/end timestamps.

Previous/next time-window navigation and auto-refresh are **not included** in D1 unless separately approved.

### Shared time context

A single selected time context should be consumed by every historical chart on a workspace/page. Switching workspaces should preserve the selected range where the data and workspace support it. A chart with no data at the selected range must display a clear empty/insufficient-data state, not silently change the range.

The global picker should not affect snapshot/report date filters that represent a different semantic (daily snapshots, date-based reports) unless the audit confirms they are truly time-series charts.

### Network interface selector

For a selected node, the selector should include:

- **All interfaces** (default option)
- Each available interface as a distinct option

Behavior:
- All interfaces: show distinct per-interface series; never sum RX/TX values across interfaces.
- Single interface: filter charts and summary to that interface.
- Interface inventory and selector options are scoped to the selected node.
- Node changes reset interface selection to All interfaces.
- Missing metrics remain unavailable/null; do not turn them into zero.
- Keep interface identity labels readable. Exporter identity may be secondary detail if needed.

## Current-state audit (source review)

The current implementation contains independent range state and controls:

- Network state: `networkHours` (default 6); current quick options are 2, 6, 12, 24, 48, 72 hours, constrained by configured retention.
- Node health/performance state: `nodePerformanceHours` (default 6), used for the node-performance endpoint.
- Historical performance series state: `performanceRangeHours` (default 2), with quick ranges 2, 6, 12, 24, 48, 72 hours and a custom date/time range.
- Existing API calls use hours-based parameters for network and performance series, while custom performance series uses start/end parameters.

This confirms that D1 requires a shared time-range contract and coordinated endpoint/API handling—not just replacing button markup.

## Proposed time-range contract

Represent the selection as a normalized object:

- `mode`: relative or absolute
- `relative`: supported preset identifier (when relative)
- `start`: ISO-8601 timestamp (when absolute or resolved)
- `end`: ISO-8601 timestamp (when absolute or resolved)
- `timezone`: IANA timezone identifier
- `label`: user-facing label

Use a shared client-side source of truth. APIs should receive a consistent range representation, preferably explicit start/end timestamps or a well-defined relative duration. Backend validation must enforce retention and reasonable maximum query windows. Existing endpoints should remain backward-compatible during migration where feasible.

## Data-resolution and retention rules

- Do not promise sub-collection-interval resolution. Current lab telemetry collection interval is 5 minutes.
- Short ranges may contain few or no samples; show a clear explanation of collection cadence and available sample count.
- Do not interpolate or fabricate samples.
- Apply configured retention limits. If a requested range exceeds retention, either constrain the available range with an explicit notice or return a clear validation response; never silently imply full coverage.
- Use a consistent timezone for range boundaries, labels, and chart tooltips.
- Keep missing values distinct from zero.

## Cross-workspace audit checklist

Before implementation, inventory all historical/time-series charts and classify them:

1. Cluster/node performance and health trends
2. Drives and filesystem historical trends
3. Network telemetry
4. Collection/scraper health trends
5. Any other time-series charts

Exclude semantic date filters for daily snapshots, report periods, and static inventory views unless they are chart time contexts.

## Acceptance criteria

- One shared time picker is used for applicable historical chart workspaces.
- Selecting a range updates all applicable charts in the active workspace consistently.
- Workspace navigation preserves selected range where supported.
- Custom range validates start <= end and clearly displays timezone.
- Every chart reports/handles no-data and insufficient-resolution cases honestly.
- Retention boundaries are respected and communicated.
- Network selector has All interfaces and per-interface choices scoped to selected node.
- All interfaces mode displays distinct series and does not aggregate/sum traffic.
- Selecting one interface filters the chart and summary table to that interface.
- Changing node resets interface to All interfaces.
- Existing daily snapshot/report date filters are not unintentionally coupled to global time.
- Regression tests cover shared state, range conversion, timezone boundaries, retention, interface filtering, and no-aggregation behavior.

## Implementation sequencing

1. Complete chart inventory and classify existing controls.
2. Define shared range object and API contract.
3. Implement reusable picker and shared dashboard time state.
4. Migrate workspace/chart APIs and UI incrementally.
5. Implement Network All interfaces behavior.
6. Add tests and regression checks.
7. User lab deployment and visual/runtime validation.

## Out of scope

- Auto-refresh
- Previous/next time-window navigation
- Interface classification (physical, bond, VLAN, bridge, virtual)
- Network aggregation or traffic attribution
- New telemetry collection frequencies
- Changes to daily snapshot/report semantics

