# Consolidated Reports — Historical Analytics Design Proposal

**Status:** Proposed / design review  
**Owner:** Product Owner + Engineering  
**Scope:** Add historical charts beneath the existing data table in each Consolidated Reports tab. This document does not authorize implementation, merge, or deployment.  
**Target integration baseline:** `feature/auth-foundation`

## 1. Objective

Evolve Reports from a latest-snapshot reporting view into a fleet-level historical analytics experience, while retaining the current KPI cards, filters, tables, column visibility, and CSV exports.

The user should be able to answer:

- What is the fleet's current state? — existing KPI cards and table.
- How has it changed over time? — new historical charts.
- Is the historical view trustworthy? — explicit coverage, freshness, and missing-data handling.

## 2. UX principles and placement

Each report tab retains its existing layout and receives an additive section below its table:

1. Existing report title and metadata.
2. Existing KPI summary cards.
3. Existing table, column controls, and CSV export.
4. **Historical Trends** section (new).

The current KPI cards and table always represent the latest available snapshot. Selecting a historical period changes **only** the charts.

### Shared controls

One time-range selector per report tab controls every chart in that tab:

- 7 days
- 30 days
- 90 days (initial default)
- 6 months
- 1 year
- 2 years
- 5 years
- 10 years / all available (bounded by retained history)
- Custom start and end dates

Use the same visual/control behavior as the existing Cluster historical trend filters. Custom ranges are inclusive, use the application's business date convention (IST), and are validated server-side.

All graphs use daily snapshots. No sub-daily aggregation is proposed in this feature.

Chart cards should reuse existing MinIO Analytics styling, chart library, legend, tooltip, zoom, reset, and fullscreen conventions where available. Keep a two-column layout for the first two charts and a full-width third chart on desktop; stack responsively on narrower screens.

## 3. Consolidated Provisioned Report

### Questions answered

- How is usable capacity consumed over time?
- Is fleet utilization increasing?
- How does bucket consumption and provisioned quota evolve?

### Charts

#### P1 — Fleet Capacity Composition (primary)

**Chart type:** Stacked area (or stacked line if area rendering obscures gaps).

Series:
- Used usable capacity
- Usable free capacity

Optional overlay:
- Installed capacity as a line, clearly distinguished from usable capacity.

Definition based on daily cluster snapshots:
- Used capacity = usable total − usable free
- Free capacity = usable free
- Usable capacity = usable total
- Installed capacity = raw total × the installed-capacity factor used by the current report

The current report service calculates installed capacity with the persisted factors: `Eff × (RF / DP)`. The historical chart must use the same formula and must not apply raw-efficiency adjustments a second time.

**Factor semantics:** If the user changes DP/RF/Eff, historical calculated installed-capacity series will be recalculated using the currently selected factors for the entire displayed period. Show a small explanatory note and the factors in effect. This is a planning scenario, not a claim that those factors were historically configured.

Do not combine installed and usable values into a misleading stacked series because they represent different capacity concepts.

#### P2 — Fleet Utilization Trend

**Chart type:** Line chart.

Series:
- Fleet used-capacity percentage, using the same definition as the existing report: used usable capacity ÷ installed capacity × 100.
- Reference thresholds at 70% and 80%.

Fleet aggregation should be calculated from summed numerator and denominator only when coverage permits. Do not average cluster percentages for the fleet line unless explicitly labeled as an average-of-clusters measure.

#### P3 — Bucket Consumption and Provisioned Quota

**Chart type:** Multi-series line chart.

Series:
- Bucket used bytes (logical bucket usage)
- Provisioned quota bytes
- Remaining quota, derived only when both used and quota totals are complete and valid

Use historical bucket snapshots. The historical cohort and coverage rules in Section 7 apply.

### Provisioned-report chart layout

- Row 1: P1 Fleet Capacity Composition | P2 Fleet Utilization
- Row 2: P3 Bucket Consumption and Provisioned Quota (full width)

## 4. Consolidated Bucket Usage Report

### Questions answered

- Is logical bucket consumption growing?
- How much quota is allocated compared with consumption?
- Is quota coverage complete enough to make utilization meaningful?

### Charts

#### B1 — Fleet Bucket Consumption Trend

**Chart type:** Line chart.

Series:
- Total bucket used bytes, only when historical coverage is valid.

Optional future breakdown:
- Cluster contribution (stacked area or selectable cluster series), but not part of the first implementation unless the API and data volume make it straightforward and clear.

#### B2 — Quota vs Consumption

**Chart type:** Line chart.

Series:
- Bucket used bytes
- Allocated quota bytes

Quota totals must be withheld if quota coverage is incomplete. Never fill missing quota with zero.

#### B3 — Quota Utilization

**Chart type:** Line chart (%).

Formula:
- Used bucket bytes ÷ quota bytes × 100

Only emit a value for dates where both totals have valid complete coverage and quota is greater than zero. Values with zero or invalid denominator are unavailable, not zero.

### Coverage indicator

Display a compact coverage strip/metadata line near the charts, for example:

> Bucket snapshot coverage: 10/10 buckets · Quota coverage: 8/10 · Trend value withheld for incomplete dates

Coverage should be date-specific when historical coverage varies. Do not represent coverage as an additional large chart in Phase 1; a compact coverage visualization is sufficient.

### Bucket-report chart layout

- Row 1: B1 Bucket Consumption | B2 Quota vs Consumption
- Row 2: B3 Quota Utilization (full width)
- Coverage note associated with the historical section and relevant chart dates.

## 5. Consolidated RAW Capacity Report

### Questions answered

- How much raw capacity exists across the fleet?
- How much is consumed and free?
- Is raw utilization increasing?
- Are changes caused by consumption or capacity expansion?

### Charts

#### R1 — Fleet RAW Capacity Composition (primary)

**Chart type:** Stacked area.

Series:
- Raw used bytes
- Raw free bytes

Overlay:
- Raw total capacity line

Current raw-capacity collector/service semantics must be retained. The service documentation states that the collector already applies the raw-efficiency adjustment to `raw_total_bytes`; do not apply it again.

#### R2 — RAW Utilization Trend

**Chart type:** Line chart (%).

Formula:
- Raw used ÷ raw total × 100

Calculate fleet percentage from aggregated raw-used and raw-total values, not from a simple average of cluster percentages. Missing cluster metrics must follow strict coverage rules.

#### R3 — Raw Consumption and Capacity Change

**Chart type:** Line chart.

Series:
- Raw used capacity
- Raw total capacity

The purpose is to distinguish usage growth from capacity additions/removals. A capacity change should be visible as a change in total-capacity series. Do not infer or annotate expansion events in Phase 1.

### RAW-report chart layout

- Row 1: R1 Raw Capacity Composition | R2 Raw Utilization
- Row 2: R3 Raw Consumption and Capacity Change (full width)

## 6. Data sources and architecture

Use the existing SQLite daily snapshot history as the source of truth. Do not add a new collection job, telemetry store, or separate historical-report database for this feature.

Existing API/report services reviewed on the integration baseline:

- `GET /api/analytics/capacity-report` → `get_consolidated_capacity_report()`
- `GET /api/analytics/bucket-usage-report` → `get_consolidated_bucket_usage_report()`
- `GET /api/analytics/raw-capacity-report` → `get_consolidated_raw_capacity_report()`

The provisioned and bucket-usage report services currently produce latest-snapshot data. The raw-capacity report service already reads daily historical cluster snapshots and currently applies a 30-day trend lookback. The new feature should extend the report history API/service layer consistently rather than making the frontend perform report calculations.

### Proposed API direction

Use report-specific historical endpoints, keeping current endpoints backward-compatible. Candidate shape:

- `GET /api/analytics/capacity-report/history?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
- `GET /api/analytics/bucket-usage-report/history?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
- `GET /api/analytics/raw-capacity-report/history?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`

This is a proposal; final route naming should be confirmed during implementation.

Each response should include:

- report key
- requested and effective date range
- available snapshot dates / data range
- generated-from/source indicator
- series points keyed by date
- coverage metadata
- per-series availability/status where needed
- capacity factors used for derived provisioned metrics
- clear unavailable reasons where applicable

Use authenticated API access consistent with existing report endpoints. Avoid returning the full raw table payload when only chart data is required.

### Query/performance requirements

- Query only the requested date window.
- Aggregate in SQL/service layer, not browser-side from a large table.
- Use appropriate existing indexes or add reviewed indexes if necessary.
- Avoid N+1 queries per date or per cluster.
- Return a bounded daily data set.
- Validate date ranges and prevent future dates.
- Maintain timezone/date consistency (daily snapshot business dates are IST).

## 7. Historical data coverage and correctness (release-critical)

### Missing snapshots

- Missing dates must be gaps/nulls, not zeros.
- Do not silently interpolate.
- Do not forward-fill values.
- Tooltip/empty-state should indicate no snapshot for that date.

### Fleet completeness

A fleet total must not be presented as complete when required enabled-cluster metrics are missing. Follow existing strict-coverage principles. If partial totals are useful in a future iteration, they must be explicitly labeled partial; Phase 1 should prefer withheld totals to misleading totals.

### Bucket-history completeness

Historical bucket cohort membership is a key design constraint. Current active-bucket membership cannot automatically be used as the denominator for past dates because bucket membership may change.

Before implementation, confirm what the daily bucket snapshots and collection metadata can prove about expected bucket membership for each historical date. Where completeness cannot be established:
- show coverage metadata;
- withhold quota/usage totals or percentages that require completeness;
- do not treat missing bucket records or metrics as zero;
- do not use current bucket membership to silently rewrite historical coverage.

If the existing schema cannot reliably establish historical expected-bucket coverage, implement the safest available behavior and document the limitation. A schema enhancement to persist snapshot cohort counts may be considered separately, but it must not be introduced without migration review.

### Different snapshot dates

Cluster capacity snapshots and bucket snapshots may have different dates. Charts must not pretend they are synchronized. Where a chart combines these metric families:
- retain each metric's snapshot date;
- disclose freshness/as-of information;
- avoid joining different dates into a single misleading point;
- either align on common dates or show series with independently available dates and clear coverage.

## 8. Empty, partial, and stale states

Each historical section must handle:

- No history: explanatory empty state, no empty axes pretending to contain data.
- One snapshot: show a point, explain that a trend requires multiple snapshots.
- Sparse history: visible gaps.
- Partial coverage: show coverage metadata and withhold invalid totals.
- Different data-as-of dates: disclose freshness.
- API failure: error state with retry; do not hide the failure or replace it with zero.
- Long-range selector with less history available: bound to actual available history and show the effective range.

## 9. Interaction requirements

- Time-range selector updates every chart in that report tab.
- Switching report tabs does not accidentally carry an incompatible date selection; each tab may retain its selection during the session.
- Custom date inputs are inclusive and validate start ≤ end.
- Reset returns to the default range.
- Zoom/reset/fullscreen behaviors follow existing chart conventions.
- Hover tooltips show date, series name, exact value, unit, and coverage/freshness context when relevant.
- Units are consistent and human-readable (Bytes/TiB/GiB; percentage).
- The chart legend can hide/show series without changing the underlying report.
- The table, table filters, column preferences, and CSV export remain independent of the historical chart selector.

## 10. Acceptance criteria

### Common

- [ ] Historical Trends section appears below the existing table on all three report tabs.
- [ ] Latest KPI cards and table remain unchanged when historical range changes.
- [ ] All charts in a tab respond to one shared time-range control.
- [ ] Presets and custom date ranges work.
- [ ] Data uses stored historical snapshots; no new collector is introduced.
- [ ] Missing data is represented as gaps/unavailable, never zero or interpolated.
- [ ] Chart units, tooltips, legends, zoom/reset/fullscreen, and empty/error states are correct.
- [ ] Responsive layout is verified.
- [ ] Existing table filters, column visibility, and CSV exports remain functional.
- [ ] API is authenticated and range validation is covered by tests.
- [ ] SQL/query performance is reviewed for multi-cluster history.
- [ ] Tests verify complete, incomplete, missing, and mismatched-date coverage.

### Provisioned

- [ ] Capacity composition correctly derives used/free from usable snapshots.
- [ ] Installed capacity uses the existing service formula and selected factors, without double-applying efficiency.
- [ ] Historical factor semantics are clearly explained.
- [ ] Utilization percentage uses correct fleet aggregation.
- [ ] Bucket used/quota series follow historical coverage rules.

### Bucket Usage

- [ ] Bucket used trend is withheld when coverage is incomplete.
- [ ] Quota trend is withheld when quota coverage is incomplete.
- [ ] Utilization is calculated only with complete, valid numerator and denominator and quota > 0.
- [ ] Date-specific coverage is shown.

### RAW Capacity

- [ ] Raw used/free/total are consistent with existing collector/service semantics.
- [ ] Raw-efficiency adjustment is not applied a second time.
- [ ] Fleet utilization uses aggregate numerator and denominator.
- [ ] Capacity changes are visible without implying expansion-event detection.

## 11. Test plan

Automated tests should include:

- Preset date window mapping and inclusive custom range.
- Invalid date order and future date validation.
- Empty history.
- Single snapshot.
- Sparse dates.
- Complete multi-cluster history.
- One cluster missing a date.
- Cluster metric unavailable/null.
- Bucket metric unavailable/null.
- Incomplete historical bucket cohort.
- Different cluster and bucket snapshot dates.
- Quota = 0 and missing quota.
- Capacity factors changed after historical snapshots.
- Raw capacity efficiency adjustment not double-applied.
- API authorization.
- SQL/API response shape and bounded data volume.
- Frontend selector changes all charts but not KPI/table.
- Regression of existing reports, filters, preferences, and CSV exports.

CI must pass, and lab/browser acceptance is required. CI alone is not release acceptance.

## 12. Delivery phases

### Phase 1 — Historical chart foundation

- Shared range control for report historical sections.
- Three report-specific historical APIs/services.
- Three charts per report (nine charts total).
- Coverage, freshness, empty/error states.
- Automated tests and lab acceptance.

### Phase 2 — Comparison and deeper analysis (not included in Phase 1)

Potential later features:
- Cluster contribution/stacking controls.
- Compare selected clusters.
- Month-over-month/period-over-period change.
- Growth rate and peak usage indicators.
- Capacity expansion annotations.
- Export chart data.
- Historical event annotations.

### Phase 3 — Forecasting/intelligence (separate scope)

Potential later features:
- Forecasts and confidence intervals.
- Days-to-capacity thresholds.
- Growth anomaly detection.
- Capacity recommendations.
- AI-generated historical insights.

Forecasting and anomaly detection are explicitly out of scope for this proposal's Phase 1.

## 13. Governance

This is a design proposal only. It does not authorize implementation, merge, or deployment.

After Product Owner review and acceptance:
1. Create a focused feature branch from the verified integration baseline.
2. Implement the historical APIs/services and frontend charts incrementally.
3. Preserve existing report behavior.
4. Review the complete diff.
5. Run automated tests and CI.
6. Prepare a lab deployment checkpoint with exact commit and rollback instructions.
7. User performs deployment and browser/data acceptance.
8. Merge only after explicit Product Owner approval.

---

## 14. Design decision summary

**Recommended Phase 1:** Nine historical charts—three per report tab—with a shared date-range control per tab. Charts are additive and below the current table. Current KPIs and table remain latest-snapshot views. Existing SQLite daily snapshots remain the data source. Strict coverage, missing-data honesty, and date/freshness transparency are release-critical.
