# Lead Control contract

The team-facing Lead Control surface keeps two questions separate:

- **Lead Gravity** describes how a team's observed behaviour changes after it
  takes a lead.  Its decomposable components are touch and pass origin height,
  defensive-action height, pass direction, own box entries, own shots,
  clearances, and opponent territorial height/final-third share.
- **Lead Ownership** describes process evidence while the team is ahead.  It
  reports opponent box entries, shots and big chances; own territorial exits,
  counters and shots; and time from lead entry to the opponent's first
  meaningful attack.

## Matching rule

The API uses verified half-open game-state episodes.  Lead observations are
winning episodes only (`goal_difference = +1` for one-goal leads and `>= +2`
for multi-goal leads).  Every lead episode is split into 15-minute match-clock
segments.  Its drawing baseline must be:

1. a verified drawing episode (`goal_difference = 0`),
2. in the same match phase, and
3. in the same or adjacent 15-minute clock bucket, with its midpoint no more
   than 15 minutes from the lead segment midpoint.

The baseline keeps its original event times.  Unmatched drawing time is not
added to the denominator and is visible through `matched_baseline_windows` and
the coverage object.  State Lens phase, goal-difference and state-age filters
are applied before this matching step.  A non-drawing State Lens baseline is
forced back to the explicit drawing control, so a UI selection cannot turn
this into an unmatched season-wide comparison.

## Rates and reliability

Count components expose raw `count`, `exposure_seconds`, `per_state_minute`
and `per_90` values.  Height components expose the mean observed x coordinate
as a percentage of pitch length, with located sample counts.  Pass direction
components are shares of located pass attempts.  Time to first meaningful
opponent attack is the median (with mean and raw values) across lead episodes.

The descriptive axes are transparent averages of fixed-scale signed component
deltas.  A higher behavioural-retreat axis means more observed retreat versus
the matched drawing baseline.  A higher process-control axis means more
opposition restriction and viable outlets versus that baseline.  These are
display axes, not team-strength scores.  At least three lead episodes, 15
minutes of lead exposure, and matched baseline exposure are required before a
quadrant label is emitted.  Sparse samples retain raw evidence but receive no
confident label.

## Outcomes and limitations

Episode drill-down includes lead margin, phase, clock buckets, matched
baseline exposure, first meaningful opponent attack, and lead survival/final
result.  Survival and final result are secondary outcomes; winning a match is
never sufficient to call a team a strong lead owner.

Opponent strength, venue, line-ups, substitutions and tactical context are
not controlled in v1.  The quadrant labels (`assertive controllers`,
`controlled deep defenders`, `vulnerable high teams`, and `retreat and
suffer`) are descriptive placements from component deltas.  They must not be
read as causal explanations or rankings.

The public endpoint is:

`GET /api/v1/team-seasons/lead-control/:canonicalTeamId?competition=...&season=...`

It is cached using the materialized payload cache and includes the formula,
State Lens, matching thresholds, coverage, limitations, raw components, and
episode evidence in the response.

