# WhoScored Transition Leverage v1

Transition Leverage is an evidence view over the materialized WhoScored
possession contract. It is deliberately not a goal-proximity score and does
not make a causal claim about any action.

## Public endpoint

`GET /api/v1/team-seasons/transition-leverage/<canonical_team_id>`

The request uses the normal concrete `competition` and `season` parameters.
It accepts the shared State Lens parameters (`state`, `goal_difference`,
`phase`, `draw_provenance`, `minimum_state_age_seconds`,
`maximum_state_age_seconds`) and their `baseline_` equivalents. `match` is the
stable zero-based reference in the returned `matches` list.

The route is intentionally cached through `MaterializedApiPayload`. The
`X-Materialized-Payload` response header reports `hit` or `miss`; the cache
source version includes the normalized events, game-state episodes,
possessions, and verified participation rows.

## Outcome ladder

Each included possession carries all of these booleans and the first event
that reached each tier:

1. `territorial_entry` — a documented final-third entry;
2. `box_entry` — a documented penalty-area entry;
3. `shot` — a shot event;
4. `big_chance` — a shot marked as a big chance; and
5. `goal` — a valid normal or own-goal score event.

Team rates are counts divided by the displayed possession opportunity
denominator. The ladder components remain available even when a goal sample is
sparse; `coverage.sparse` and `coverage.sparse_threshold` make that limitation
visible. No weighted or hand-assigned composite is emitted.

`attacking` uses focal-team possessions. `concession` uses opponent
possessions, plus a focal-team possession that terminates in a focal own goal;
the latter is called out in `opportunity_basis` so it cannot be mistaken for a
standard opponent-possession denominator.

## State transitions and boundaries

The terminal action carries the focal-team state immediately before it. A
goal-ending possession uses the pre-goal half-open episode, so it cannot leak
into the following state. Score changes retain exact goal difference and are
classified into reusable strings such as:

* `losing_to_drawing`;
* `drawing_to_winning`;
* `winning_to_drawing`; and
* `one_goal_to_multi_goal_lead`.

The response also includes before/after state, goal difference, scoring
perspective (`for` or `against`), phase, draw provenance, and state age. A
same-coarse-state score change remains visible through exact goal differences.
Own goals and penalty goals use the same score replay semantics as #105.

## Sequence roles

Every linked action in a trace receives one transparent stage/role:

* `origin_recovery` — first control anchor, including a recovery or
  acquisition;
* `escape` — a successful take-on;
* `advancement` — a progressive pass or documented entry;
* `destabilisation` — key, through, or other unlocking action;
* `creation` — documented shot-assist or intentional-assist evidence;
* `contest` — tackle, interception, aerial, challenge, or blocked-pass event;
* `terminal` — the final shot/own-goal action; and
* `support` — another event linked to the same possession.

The trace exposes event order, minute/second, focal/opponent perspective,
canonical player identity where resolved, coordinates, completion, flags,
state, role evidence, and terminal status. Provider IDs and source payload
qualifiers are not public.

Turnover/recovery launches retain the #112 rapid-transition evidence in
`rapid_transition`: launch status, the documented forward-progress threshold,
elapsed seconds, forward metres, speed, and outcome. Restart launches remain
labelled as restarts rather than being silently merged with a turnover.

## Player involvement and reliability

Only `ProviderMatchPlayerParticipation` rows with `status=verified` and
`confidence=verified`, canonical team/player identity, and a positive verified
interval are eligible. An event is attributed only when its timestamp is in
that player's half-open on-pitch interval. A player opportunity is a focal
team possession with at least one focal-team event during that same interval;
it is not a whole-match or team-volume denominator. The payload reports
opportunities, involved possessions, rates, stage counts, verified minutes,
excluded matches/reasons, and inspectable evidence traces.

The response keeps `selected.observations` (and any baseline observations) as
the bounded shared trace set, currently at 100 complete chains per scope.
Player evidence carries an `observation_ref`, state/outcome summary, stages,
and the player's action indexes; clients resolve that reference to the shared
trace instead of receiving a duplicated chain. Counts and rates still use the
full eligible observation set, while `evidence_truncated` makes the display
cap explicit.

Substitutions, withdrawals, dismissals, added time, transfers/team spells,
unmatched participation, missing timestamps, ambiguous possessions, and
unverified game-state matches remain excluded or explicitly marked. No
fallback to 90 minutes is made.
