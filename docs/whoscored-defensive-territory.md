# WhoScored defensive action territory

The team event-map endpoint
`/api/v1/team-seasons/event-profile/{team_id}/defensive-territory` exposes
cached, rebuildable defensive-location evidence for a concrete competition and
season. It accepts the shared State Lens and match query parameters used by the
team event profile.

The normalized defensive family is deliberately fixed: ball recoveries,
tackles, interceptions, blocked passes, clearances, and Aerial or Challenge
events carrying WhoScored's Defensive qualifier. Unqualified Aerial and
Challenge events are excluded and reported in evidence metadata. Deleted
events are also excluded.

Coordinates use the normalized acting-team frame for both home and away teams:
the focal team's own goal is x=0 and the opponent's goal is x=100. The payload
reports recovery height, non-clearance action height, clearance depth, pitch-
third distribution, p10–p90 spread, family composition, located and unlocated
counts, state exposure, episode evidence, per-state-minute rates, and complete
12×8 density bins. When a State Lens baseline is supplied, the response carries
the same shape for selected and baseline scopes so consumers can calculate a
State Delta Map without re-binning observations.

These locations are factual event territory only. They do not demonstrate
pressing intensity or prove that a team used an organised high, mid, or low
block. Possession-aware block classification belongs to the separate possession
context contract.
