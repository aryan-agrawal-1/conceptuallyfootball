# WhoScored Response Half-Life v1

Response Half-Life is a descriptive, team-level measure of how observed
behaviour moves after a valid concession. It does not claim that an event
caused a goal and it does not grade tactical quality.

## Window contract

Each valid opponent-scored goal creates a post-concession episode. Windows are
five minutes (`300` played seconds) wide, begin at the concession timestamp,
and start again every minute (`60` seconds). Consecutive windows therefore
overlap by four minutes. Intervals are half-open `[start, end)`, so an event at
the right boundary belongs to the next window.

The response horizon is fifteen minutes. A window must fit wholly inside one
persisted played period. A concession with less than five minutes remaining in
that period is censored as `period_boundary`; later windows stop at the period
boundary. Regulation added time and periods 3/4 of extra time use the same
played-time rules and expose `is_added_time`. A window is never silently
carried across half-time, extra-time breaks, or a period boundary.

A subsequent score-changing goal inside the first five-minute window censors
the episode. A gap of 120 seconds or less is specifically labelled
`rapid_subsequent_goal`. When the subsequent goal is later than five minutes,
windows that cross it are censored as `subsequent_goal`; earlier complete
windows remain inspectable. Red and second-yellow dismissal events censor a
window containing the card. Normalized substitution, retirement, or an
explicitly excluded participation build is labelled
`participation_uncertainty`.

## Expected destination

The destination is the team's established behaviour for the new state. A
source episode contributes only after 600 seconds of state age. Destination
priority is:

1. resulting coarse state + phase + exact goal difference;
2. resulting coarse state + phase when the exact goal-difference cell has
   fewer than 900 stable seconds.

The second case is labelled `match_basis=state_phase` and reliability is
`partial`. A destination requires at least 900 stable seconds, 10 observed
events, and 5 pass attempts. Otherwise the concession is `no_destination` and
does not receive a confident aggregate value. Destination exposure and match
basis are included on every episode trace.

## Signals and half-life

The attacking signal is the equal-weight mean of normalized absolute
deviations for:

- non-penalty shots per minute;
- box entries per minute from normalized passes and derived carries;
- progressive passes plus progressive carries per minute; and
- attacking action height in the acting-team frame.

The structural signal is a separate equal-weight mean for:

- forward pass share;
- physical pass length in metres;
- pass completion rate;
- team action territory height; and
- defensive-action height.

Fixed component scales are returned by the API: `1` for the three attacking
rate components, `50` for attacking height, `0.5` for forward share, `15m` for
pass length, `0.25` for completion, and `50` for both structural heights. The
signal is the mean of supported components, so a missing coordinate is visible
and does not become a zero value.

Initial deviation is the offset-zero signal. The half threshold is half that
value. The half-life is the first later supported rolling window whose signal
is at or below the threshold. A zero initial deviation has a zero half-life;
if no later window reaches the threshold, the episode reports
`status=no_recovery` and no half-life. Team aggregates expose median and mean
seconds separately for attacking and structural signals, along with the
qualifying concessions, windows, matches, censored episodes, and reliability.

## API and inspection

The public endpoint is:

```
GET /api/v1/team-seasons/response-half-life/<canonical_team_id>
    ?competition=...
    &season=...
```

It accepts the shared State Lens parameters and `match=<match reference>`.
The selected result is cached using the event, game-state, episode, carry,
period, profile, and formula versions. `selected.episodes[].windows[]` keeps
the complete trace beside each destination and half-life calculation. The
`definitions` object is emitted in the response so consumers can inspect the
window, boundary, destination, signal, and censor rules without relying on
presentation copy.

