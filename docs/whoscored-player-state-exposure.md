# Verified player participation and state exposure

Status: implementation contract

## Purpose

Player state metrics use only the seconds in which a player is verified to be
on the pitch for the focal team. Existing merged season minutes and existing
non-state per-90 rates are not changed by this feature.

The persisted models are provider-neutral. Full lineup objects, source event
identifiers, relation identifiers, and reconstruction diagnostics remain
private backend evidence.

## Clock and boundary contract

All participation intervals, team-state episodes, and their intersections use
the shared continuous expanded-match clock. Played-period boundaries come from
`ProviderMatchPlayedPeriod`; no consumer assumes 45, 90, 105, or 120 minutes.

Intervals are half-open: `[start_second, end_second)`. A goal changes state at
its event timestamp, so the timestamp belongs to the post-goal episode. At a
simultaneous substitution and goal, the incoming player receives post-goal
exposure and the outgoing player does not.

## Evidence hierarchy

- A normalized lineup marks starters and substitutes.
- A starter begins at the verified match start.
- Substitution-on, player-on, and player-return events begin an interval.
- Substitution-off, player-off, player-retired, verified dismissal, and match
  end close an interval.
- Substitution relations use the raw provider `eventId` namespace represented
  by `provider_event_sequence_id`; raw `id` is a different namespace. Sequence
  identifiers are scoped to the team because both teams can reuse the same value.
- Reciprocal event relation is preferred, then related-player evidence, then a
  unique same-team/same-time on/off pair.
- Equivalent duplicate evidence is collapsed. Conflicting duplicates exclude
  the affected player.
- Red and second-yellow cards with an identified active player close that
  player's interval. A dismissal without a reliable player identity excludes
  affected active players rather than assuming eleven players remained.
- Goalkeeper substitutions follow the same interval rules. A goalkeeper or
  outfield position change alone is not a participation boundary.
- Players introduced by valid event evidence but absent from the lineup are
  retained with roster role `added`; they are never inferred to be starters.

Missing lineup, match end, identity, timestamp, substitution partner, or other
required evidence never produces a default 90-minute interval.

## Public eligibility

A player-match contributes public state exposure only when:

1. canonical player and team identities are present;
2. participation status and every interval are `verified`;
3. shared team-state episodes exist for the entire verified interval; and
4. summed episode intersections exactly equal verified on-pitch seconds.

An otherwise verified interval with missing episode seconds is publicly
excluded as `state_episode_coverage_mismatch`. Unused substitutes are reported
separately and are neither included participation nor an ambiguous exclusion.

The public API returns canonical match references, included/excluded counts and
reason codes, verified seconds, confidence, formula versions, and exposure
grouped by coarse state, exact goal difference, phase, draw provenance, and
state age. It never returns provider IDs, lineup details, event relations, or
private diagnostics.

## State-age grouping

Exact state age is retained on every intersection. Public v1 groupings are:

- `0_5_minutes`: `[0, 300)` seconds since state entry
- `5_15_minutes`: `[300, 900)`
- `15_plus_minutes`: `[900, infinity)`

An interval crossing a boundary is split so every stored exposure row belongs
to exactly one bucket.

## Rebuild behavior

For a locked match, participation builds, participants, intervals, and player
state exposures are replaced transactionally from current normalized evidence.
Exposure rows are intersections of verified player intervals and the focal
team's current game-state episodes. Rebuilding unchanged source data produces
the same derived content apart from audit timestamps.

Formula versions:

- `player_participation_v1`
- `player_state_exposure_v1`
