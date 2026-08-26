# WhoScored Team Style Shape v1

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
| Build-up | Circulation security | share | Completed passes / pass attempts | 30 passes + 900s |
| Progression & attack | Progressive actions | actions/90 state min | (Progressive passes + derived progressive carries) × 5400 / exposure seconds | 30 actions + 900s |
| Progression & attack | Box-entry rate | entries/90 state min | (Pass box entries + carry box entries) × 5400 / exposure seconds | 30 actions + 900s |
| Progression & attack | Carry progression | share of carries | Progressive derived carries / derived carries | 10 derived carries + 900s |
| Progression & attack | Shot frequency | shots/90 state min | Non-penalty team shots × 5400 / exposure seconds | 5 non-penalty shots + 900s |
| Defence | Defensive-action height | pitch x % | Median qualified defensive event x from the focal-team defending perspective | 30 located defensive events + 900s |
| Defence | Recovery height | pitch x % | Median ball-recovery x from the focal-team defending perspective | 10 located recoveries + 900s |
| Defence | Deep-defending concentration | share | Located non-clearance actions at x < 33.33 / located non-clearance actions | 30 located non-clearance actions + 900s |
| Defence | Settled block height | pitch x % | Median persisted settled defensive average x in opponent possessions | 5 settled block possessions + 900s |
| Transitions | Counter launch | launches/90 state min | Derived possession counter launches × 5400 / exposure seconds | 5 derived launches + 900s |
| Transitions | Counter arrival | share of launches | Derived counter final-third arrivals / derived counter launches | 5 derived launches + 900s |
| Transitions | Counter speed | m/s | Mean persisted counter forward metres / elapsed seconds | 5 counters with speed + 900s |
| Transitions | Counter-shot tendency | share of launches | Derived counter shots / derived counter launches | 5 derived launches + 900s |

Pass direction, length and progressive flags consume the Batch 9 pass-state
contract. Defensive event inclusion and orientation consume the defensive
territory contract. Counter launches and speed consume possession-context v1;
provider-tagged fast-break shots are retained only as a separate raw count.
Settled block height uses only opponent possessions whose event links were
marked settled defensive after the Batch 9 establishment rule. Transition
defence is excluded.

“Higher” means more prevalent for every axis. That does not make a high value
good or a low value bad. In particular, pass completion, shot frequency,
defensive height and counter-shot tendency are all descriptive observations,
not outcome or quality measures.

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
create a confident radial shift. A single-match view keeps its raw evidence and
explicitly withholds season-cohort percentiles because a match reference is
not a common fixture for the other teams.

The distribution exposes sample size, p10/p25/p50/p75/p90, min/max/IQR, sorted
cohort values, and the per-team member rows. This makes a displayed percentile
reconstructable and avoids hiding a thin comparison cohort.

## State comparison and signed shift

The payload always returns `overall` (all eligible state exposure) and
`selected`. When an explicit `baseline_*` lens is supplied it also returns
`baseline` and `comparison.selected_minus_baseline`. A shift has:

- selected and baseline raw values;
- a unit-aware raw delta (`selected - baseline`);
- reliability and eligibility;
- a normalised delta for the radial view, calculated as raw delta divided by
  the same-axis selected-state cohort p90-minus-p10 spread and clipped to
  `[-1, 1]`.

Positive means the selected state contains more prevalent behaviour; negative
means less. If either state is sparse, the raw delta remains visible but the
normalised shift is withheld. This is why the UI uses a diverging radial shift
centred on zero rather than a normal percentile pizza: a signed change is not a
rank and a larger spoke is not a quality signal.

## UI contract

`TeamStyleShapePanel` displays:

1. selected and baseline exposure plus competition-season cohort coverage;
2. a signed, zero-centred radial shift with separate positive/negative legend;
3. overall and selected raw values, prevalence percentile, reliability and
   evidence counts;
4. expandable formulas, raw component values, distributions, and method notes;
5. an accessible axis picker that keeps at least one axis selected.

The panel stacks its radial and evidence table on narrow screens, keeps all
axis data in a semantic table for keyboard and screen-reader users, and uses
the existing Event Map share/export shell. The parent Team Event Maps surface
owns URL state for `axes` and the shared State Lens; the client helper includes
both in the request/cache key so copied links restore the same profile.
