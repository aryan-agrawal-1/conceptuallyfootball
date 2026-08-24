# Event-map pass-flow design

## Research reviewed

Reviewed 20 August 2026:

- [StatsBomb, “Explaining xGChain Passing Networks”](https://statsbomb.com/articles/soccer/explaining-xgchain-passing-networks/) describes the established network grammar: locations act as nodes, connections represent passes, and line thickness represents pass volume. It also warns that averages can imply a position where the underlying actions did not occur and that dense networks quickly become difficult to read.
- [mplsoccer's pass-network example](https://mplsoccer.readthedocs.io/en/latest/gallery/pitch_plots/plot_pass_network.html) scales line width and opacity relative to the largest connection, keeping low-volume routes visible without giving them the same visual weight as dominant routes.
- [StatsBomb's positional-tracker note](https://statsbomb.com/articles/soccer/new-development-introduction-to-player-positional-tracker/) again uses thicker connections for more frequent completed-pass combinations and cautions that small samples make average positions unstable.

Those products usually show player-to-player networks. Statballer's provider-neutral event stream does not reliably expose recipient identities, so copying a player network would imply information the data does not contain. The redesign adopts the established volume grammar while remaining a spatial flow field.

## Chosen approach

- Assign each successful pass to one deterministic 6-by-4 origin bin using its real start coordinate.
- Materialize only occupied bins. Each bin stores completed-pass volume/share, mean origin, mean destination, and mean physical pass length; it never infers a receiver or possession sequence.
- Draw one arrow per occupied bin from the mean origin toward the mean destination. Cap its display length within the local field while retaining the materialized mean length for inspection.
- Encode relative completed-pass volume only in the origin-bin shade, using a square-root scale to compress the long tail. Keep every arrow at one visual weight so volume has a single, unambiguous channel.
- Use completed passes only. Mixing completion quality into the same colour channel would overload a compact card.

The result is deterministic for a given event set, performs in a single canvas pass, and makes a team's typical direction and length from each occupied area legible without suggesting player identities.

## Representative sanity checks

- A dominant build-up origin produces the strongest origin density; lower-volume bins remain subordinate while their arrows retain the same weight.
- Backward, lateral, and forward mean destinations produce visibly different field vectors.
- A bin with no successful passes is omitted rather than rendered as a zero-information mark.
- Player pass maps retain individual event start/end coordinates and default to **All**, so unsuccessful passes are not silently excluded from the overall total.

Future work can add possession/value weighting, or recipient-aware networks, if those fields are introduced to the provider-neutral contract. The frontend should continue to render only materialized evidence rather than infer either concept.

## State-conditioned shot pressure

Team Event Maps requests `/api/v1/team-seasons/shot-pressure/:teamId` with the
shared State Lens parameters. The cached provider-neutral response divides shot
counts by canonical half-open episode exposure, not by match count or an assumed
90 minutes. It reports evidence minutes, episodes, matches, zero-shot episodes,
and exclusions beside every view.

The tactical default is `penalty_mode=exclude`; `include` and `only` are explicit
controls. WhoScored/Opta normalization stores `FAST_BREAK` as a mutually exclusive
shot situation, so those shots contribute to the broad open-play count and also
appear in the narrower **provider-tagged fast break** row. That row is never
described as a complete counter-attack count.

The 6×4 pitch surface publishes shot frequency per 90 minutes of state exposure,
location share, and observed conversion separately. Comparison mode subtracts
aligned zone rates and never subtracts individual shot dots. Existing single-state
shot maps retain individual inspection. No event-level xG, pseudo-xG, or blended
quality score is created.

## Coordinate orientation

Opta/WhoScored event coordinates use a bottom-left origin: `x` increases toward
the opponent goal (the acting team always attacks toward x=100 after
normalization) and `y` increases toward the far touchline. Our SVG/canvas
surfaces render y top-down, so `lib/eventMaps/api.ts` flips y once at the API
mapping layer (`toDisplay`) and inverts grid row indices (24×16 action grid,
6×4 flow bins). Everything downstream of that file works in display space;
the database keeps native Opta coordinates.

Goal-mouth zones follow the shooter's perspective: the shooter's left is the
high-y side of the goal, so ascending pitch-y columns read right-to-left.
WhoScored text descriptions ("low to the right") were used to confirm the
handedness — e.g. Haaland's 94' goal vs Bournemouth (match 1903442) has
goalMouthY 48.1 and is described as low to the right.
