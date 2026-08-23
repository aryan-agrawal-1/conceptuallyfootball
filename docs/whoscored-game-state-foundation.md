# Provider-neutral game-state foundation

Status: implemented foundation  
Formula version: `team_game_state_v1`  
Clock version: `match_clock_v1`

## Contract

Game state is materialized once per eligible normalized match for both canonical
teams. Downstream team and player features consume these rows; they must not
replay provider events independently or interpret an opponent event's acting-team
state as the focal team's state.

The canonical clock is continuous played time in integer seconds. Normalization
reconciles the source's expanded-minute metadata with exact per-period Start/End
event seconds and supplies an immutable provider-neutral structure. Expanded
display clocks can contain a few seconds between one period's End and the next
period's Start; those breaks are compressed out. Period intervals and state
episodes are half-open: `[start_second, end_second)`. Breaks consume no played
seconds. A valid goal changes state at its exact timestamp, so the post-goal
episode starts at that timestamp. Team and opponent events at that instant
therefore resolve to the same post-goal focal state.

`periodMinuteLimits` or equivalent nominal limits classify added time only. They
never determine played exposure. The current source corpus supplies expanded
period ends and an expanded match end; absent, inconsistent, gapped, overlapping,
or reversed clock metadata excludes a match rather than falling back to the last
event or a nominal 90/120 minutes. `ProviderMatchEvent.match_seconds` retains its
legacy meaning; state consumers use `timeline_seconds`.

Supported play consists of the first half, second half, and, when played, both
extra-time periods. Shootouts and post-game events never contribute exposure.

## Replay and eligibility

A goal is accepted only when it belongs to one of the match teams, has a valid
supported-period timeline timestamp, and is neither disallowed nor referenced by
a deleted-event correction. Source event-sequence identifiers are scoped to the
team because the same value can occur once for each team. Deleted-event references
are collected before replay, so their order in the feed does not matter. Own goals
score for the opponent.
Shootout goals are counted for reconciliation diagnostics but do not alter the
regulation/extra-time score timeline.

Public episodes require all of the following:

- a completed match and final payload;
- two distinct resolved canonical teams;
- paired final scores;
- valid expanded played-time boundaries;
- successful event-score reconciliation.

Invalid, incomplete, unverified, or mismatched matches produce no episodes or
exposure rows. Their audit row retains a stable public-safe exclusion reason and
private detailed diagnostics.

## Episode semantics

Each focal-team episode records period/phase, exact start/end/duration, added-time
classification, focal and opponent scores, exact goal difference, coarse
winning/drawing/losing state, previous coarse state, draw provenance, and state
entry lineage.

Draw provenance has three meanings:

- `neutral`: the initial scoreless draw;
- `restored`: the focal team scored the equalizer;
- `surrendered`: the focal team conceded the equalizer.

Goals that change exact goal difference without changing coarse state create a
new score episode but do not reset coarse-state age. Period boundaries split the
timeline while carrying `previous_state`, `state_entry_second`, and `entry_event`
forward. Added-time thresholds may also split storage intervals so exposure is
classified exactly; they do not reset state age.

For each focal team, episodes are gap-free and non-overlapping from zero through
the supported match end. Their durations, and the grouped exposure rows derived
from them, reconcile exactly to supported played seconds. Home and away focal
scores/differences are inverse views of the same transition stream.

## Shared helpers and public metadata

`state_context_for_event` resolves an event through the focal episode and returns
coarse state, exact goal difference, phase, draw provenance, state age, and
episode index. `scope_events_to_focal_state` applies the same focal lookup to both
team and opponent events. `game_state_exposure` supplies denominators from
materialized exposure rather than event counts or whole-match minutes.

`public_game_state_metadata` returns formula version, exposure seconds, episode
and match counts, included/excluded match counts, stable exclusion-reason counts,
and a reliability description. It does not expose provider identifiers, raw
payload fields, deleted-event references, or private diagnostics. Existing event
maps are unchanged unless a state scope is explicitly requested.

Player participation issue #104 must use the persisted played-period boundaries
and intersect verified participation with these team episodes. It must not define
a second clock or replay score state independently.
