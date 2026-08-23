# WhoScored possession context v1

`possession_context_v1` is a rebuildable, provider-neutral interpretation of
the ordered normalized event stream. It does not create synthetic raw events.
Every included event has one `ProviderMatchPossessionEvent` row at most; events
that cannot safely be assigned are listed by index and reason in the match
build diagnostics.

## Continuity and boundaries

- A pass, touch, take-on, shot, recovery, successful tackle/interception/save,
  or other documented control action anchors team control. A failed opponent
  duel or defensive action is evidence within the current possession, not a
  control change.
- An opponent control anchor changes possession. Period changes, restarts,
  shots/goals, fouls, offsides, and unsuccessful passes end the current
  possession. Set pieces, corners, free kicks, and throw-ins start a fresh
  restart possession even when the same team retains the ball.
- Cards, substitutions, deleted events, and administrative events are excluded
  as non-play. Unknown events are excluded as `ambiguous_control` and mark an
  intersecting possession ambiguous. Public aggregates exclude ambiguous rows.
- Identity is a stable SHA-256 digest of calculation version, match, period,
  first event index, and controlling team. Match replacement deletes and
  atomically recreates that match's build, possessions, membership, and
  participants, so corrected ingestion cannot accumulate duplicates.

## Counters and settled defending

A counter launch begins with a non-restart recovery/control change at or behind
x=60. It must move at least 21 metres forward within 12 seconds to count an
arrival or shot. Final-third arrival begins at x=66.67. Box arrival uses
x>=83.50 and y=21.18..78.82. Elapsed time, furthest forward distance, speed,
outcome, and canonical participant IDs remain independently reproducible.

WhoScored's `FastBreak` shot qualifier is persisted and returned only under the
separate `provider_observed.fast_break_shots` label. It never substitutes for a
derived launch, arrival, or shot.

A possession becomes settled at the earlier of its third control action or 10
elapsed seconds. Defensive locations before that boundary are transition
actions and never enter block-height measures. Settled defensive action x is
classified low below 33.33, mid from 33.33 to below 66.67, and high from 66.67.
Payloads expose evidence counts and all thresholds rather than an opaque score.

## Canonical game-state intersection

Possessions intersect the focal team's canonical half-open state episodes.
Segments expose state, goal difference, and seconds. A possession ending in a
goal stops at the goal timestamp and uses the event's `game_state_before` for a
zero-duration boundary case; it cannot inherit the post-goal state.

## Public endpoint and performance gate

`GET /api/v1/team-seasons/possession-context/{team_id}` accepts the standard
`competition_season` or `competition` plus `season` scope. It returns derived
aggregates, capped evidence, thresholds, settled block distribution, and the
separately provider-tagged observed count. Provider IDs, qualifiers, and source
payload details are not returned.

The test suite includes a 20-match pilot-shaped derivation benchmark (30,000
events) with a one-second local ceiling. Production backfill should record the
same elapsed time and possession/event counts before expanding beyond a pilot.
Use `manage.py backfill_possession_context --competition ENG1 --season 2025-26`
or add one or more `--match-id` values for a deterministic affected-match rebuild.
