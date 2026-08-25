# WhoScored state-conditioned passing

The team pass-state endpoint is:

`GET /api/v1/team-seasons/event-profile/{team_id}/pass-state`

It requires the same `competition`, `season`, and optional `match` parameters as
the team event profile. It also accepts the shared State Lens parameters:
`state`, `goal_difference`, `phase`, `draw_provenance`,
`minimum_state_age_seconds`, and `maximum_state_age_seconds`. Prefix every one
with `baseline_` to request a comparison cohort. State age is half-open:
`minimum <= age < maximum`.

## Evidence and interpretation

The response keeps pass choice and execution separate. `attempt_share` describes
which direction, length band, or origin zone the team selected. `completion_rate`
describes execution within that same cohort. `attempts_per_state_minute` uses
canonical eligible game-state exposure rather than match minutes. The response
contains the selected cohort in full and, when requested, the full baseline plus
a compact null-safe delta.

Every normalized pass enters overall volume, completion, and progressive totals.
Only passes with an origin and destination enter spatial, direction, and length
analysis. The endpoint does not infer a receiver, possession, pressure, or pass
value. Missing-coordinate counts, eligible and excluded matches, empty/sparse
status, row limits, and truncation are disclosed in the payload.

All normalized events are oriented with the acting team attacking left to right.
For coordinates in the stored 0..10000 range, physical displacement is:

`hypot((end_x - x) * 105 / 10000, (end_y - y) * 68 / 10000)`

Direction is forward above 1 metre of forward displacement, backward below -1
metre, and lateral between those thresholds. Length bands are short `[0,15)`,
medium `[15,30)`, and long `[30,+inf)` metres.

The flow field is bounded to the established 6×4 origin grid. Each occupied bin
returns attempted volume and state-minute rate, attempted share, completions and
completion rate, plus mean origin, mean vector, destination, and physical length.
`origin_conditioned` repeats directional choice and execution inside each origin
bin so territorial relocation is not mistaken for a change in passing choice.

Overall pass totals are database aggregates. At most 50,000 pass events are
processed for spatial evidence per cohort. The response always reports the source
and located counts and whether this cap truncated spatial evidence; aggregate arrays
remain fixed at 24 origin bins, three direction rows, and three length rows.
