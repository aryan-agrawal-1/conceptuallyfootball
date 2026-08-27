# WhoScored Team Style Shape v2

Team Style Shape is a descriptive team profile. It answers “which behaviours
are more or less prevalent in this sample?” It does not rank teams by quality,
assign result credit, estimate causality, or combine outcome metrics into a
score. Percentiles are therefore labelled **style prevalence**, never “better”.

The public endpoint is:

```text
GET /api/v1/team-seasons/style-shape/{canonical_team_id}
```

It requires the same concrete `competition` + `season` (or
`competition_season`) scope as the Event Map APIs. `BIG5` and `ALL` are not
valid event-profile scopes. It accepts the shared State Lens parameters from
`state_lens.py`, `match`, and an optional comma-separated `axes` selection. The
selection is part of the cache key and can be persisted by the Team Event Maps
URL.

## Axes

Every axis is calculated once in
`backend/ingestion/services/team_style_shape.py`. The API returns the
definition, formula version, unit, minimum evidence, direction, raw component
counts, value, reliability, and percentile eligibility alongside the value.
The comparison cohort is the current canonical teams with data in the same
competition-season and eligible WhoScored state evidence.

| Group | Axis | Unit | Formula | Minimum evidence |
| --- | --- | --- | --- | --- |
| Build-up | Pass length | m/pass | Mean physical pass length using the Batch 9 105m × 68m `physical_vector` formula | 30 located passes + 900s |
| Build-up | Pass directness | share | Forward located attempts / located attempts; forward is >1m | 30 located passes + 900s |
| Build-up | Forward intent | share | Progressive pass attempts / pass attempts | 30 passes + 900s |
| Build-up | Pass completion | share | Completed passes / pass attempts | 30 passes + 900s |
| Progression & attack | Progressive actions | actions/90 state min | (Progressive passes + derived progressive carries) × 5400 / exposure seconds | 30 actions + 900s |
| Progression & attack | Box-entry rate | entries/90 state min | (Pass box entries + carry box entries) × 5400 / exposure seconds | 30 actions + 900s |
| Progression & attack | Carry progression | share of carries | Progressive derived carries / derived carries | 10 derived carries + 900s |
| Progression & attack | Shot frequency | shots/90 state min | Non-penalty team shots × 5400 / exposure seconds | 5 non-penalty shots + 900s |
| Defence | Defensive-action height | pitch x % | Median every qualified located defensive event x from the focal-team defending perspective, including transition defending | 30 located defensive events + 900s |
| Defence | Recovery height | pitch x % | Median ball-recovery x from the focal-team defending perspective | 10 located recoveries + 900s |
| Defence | Deep-defending concentration | share | Located non-clearance actions at x < 33.33 / located non-clearance actions | 30 located non-clearance actions + 900s |
| Defence | Settled block height | pitch x % | Median of the per-possession average defensive x after opponent possession establishment; transition defence excluded | 5 settled block possessions + 900s |
| Transitions | Counter starts | launches/90 state min | Derived counter starts × 5400 / exposure seconds | 5 derived launches + 900s |
| Transitions | Counters reaching final third | share of starts | Derived counter final-third arrivals / derived counter starts | 5 derived launches + 900s |
| Transitions | Counter speed | m/s | Mean persisted counter forward metres / elapsed seconds | 5 counters with speed + 900s |
| Transitions | Counters leading to shots | share of starts | Derived counter shots / derived counter starts | 5 derived launches + 900s |

Pass direction, length and progressive flags consume the Batch 9 pass-state
contract. Defensive event inclusion and orientation consume the defensive
territory contract. Counter starts and speed consume possession-context v1;
provider-tagged fast-break shots are retained only as a separate raw count.
Settled block height uses only opponent possessions whose event links were
marked settled defensive after the Batch 9 establishment rule. Transition
defence is excluded.

“Higher” means more prevalent for every axis. That does not make a high value
good or a low value bad. In particular, pass completion, shot frequency,
defensive height and counters leading to shots are all descriptive
observations, not outcome or quality measures.

### Definitions users see in the panel

- **State exposure:** verified seconds spent in the selected state. Per-90
  rates use `count × 5400 / verified state exposure seconds`; selecting all
  states therefore uses all verified state minutes.
- **Defensive-action height:** the median x location of every qualified,
  located defensive action, including transitions, measured from the team's
  own goal.
- **Settled block height:** after an opponent possession is established by its
  third control action or 10 seconds, calculate that possession's average
  defensive x and take the median across possessions. Transition defending is
  excluded.
- **Counter starts:** a non-restart recovery or control change at or behind
  x=60. The next 12 seconds are inspected; final-third and shot outcomes
  require at least 21 metres of forward progress. Provider `FastBreak` is a
  separate observation and does not create a derived counter.

## Cohorts, percentiles and reliability

Each overall, selected-state, and baseline cohort includes exposure seconds and
minutes, episodes, matches, excluded matches, raw event-family counts, and a
per-axis reliability state:

- `verified`: minimum evidence and exposure are met;
- `partial`: minimum evidence is met but one or more source matches were
  excluded;
- `sparse`: raw evidence is retained but the axis is below its family-specific
  minimum;
- `unavailable`: no valid source value or no verified exposure exists.

The percentile is a deterministic mid-rank percentile:

```text
100 × (number of cohort values below x + 0.5 × number equal to x) / cohort size
```

One-value cohorts are reported as P50. Only axes meeting their minimum
evidence contribute to a distribution. Sparse rows remain in the `members`
list with raw values and reliability, but receive no percentile and cannot
create a confident state position. A single-match view keeps its raw evidence and
explicitly withholds season-cohort percentiles because a match reference is
not a common fixture for the other teams.

The distribution exposes sample size, p10/p25/p50/p75/p90, min/max/IQR, sorted
cohort values, and the per-team member rows. This makes a displayed percentile
reconstructable and avoids hiding a thin comparison cohort.

## State comparison and chart scale

The payload always returns `overall` (all eligible state exposure) and
`selected`. When an explicit `baseline_*` lens is supplied it also returns
`baseline` and `comparison.selected_minus_baseline`. The raw selected-minus-
baseline change remains available for audit in the table; it is not used as a
quality score.

When requested with `include_game_states=1`, the endpoint adds one compact
`game_states` object containing the target team's winning, drawing and losing
cohorts. This is assembled in the existing bulk source load, so the client
does not need three requests. It is optional because it is not needed for the
default profile view.

The **By game state** chart positions each state against the metric's all-state
competition-season P10–P90 range:

```text
100 × (state value − all-state P10) / (all-state P90 − all-state P10)
```

The result is clipped to 0–100 for display, with an edge marker when the raw
value falls outside the typical range. It is a linear location, not a
percentile or quality score. Thin connectors join only supported state points;
sparse points remain hollow and faded. The all-state value is a quieter
diamond reference. With an explicit comparison context the same component
shows selected and comparison dots plus that reference.

## UI contract

`TeamStyleShapePanel` displays:

1. selected and baseline exposure plus competition-season cohort coverage;
2. a profile radar by default, or a connected state dot/range chart on the
   **By game state** view;
3. overall and selected raw values, prevalence percentile, reliability and
   evidence counts;
4. expandable calculation definitions without repeating live values;
5. an accessible axis picker that keeps at least one axis selected.

The panel stacks its chart and evidence table on narrow screens, keeps all
axis data in a semantic table for keyboard and screen-reader users, and uses
the existing Event Map share/export shell. The parent Team Event Maps surface
owns URL state for `axes`, the shared State Lens, and whether
`include_game_states=1` is needed; the client helper includes all three in the
request/cache key so copied links restore the same profile.
