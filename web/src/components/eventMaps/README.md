# Event-map pass-flow design

## Research reviewed

Reviewed 20 August 2026:

- [StatsBomb, “Explaining xGChain Passing Networks”](https://statsbomb.com/articles/soccer/explaining-xgchain-passing-networks/) describes the established network grammar: locations act as nodes, connections represent passes, and line thickness represents pass volume. It also warns that averages can imply a position where the underlying actions did not occur and that dense networks quickly become difficult to read.
- [mplsoccer's pass-network example](https://mplsoccer.readthedocs.io/en/latest/gallery/pitch_plots/plot_pass_network.html) scales line width and opacity relative to the largest connection, keeping low-volume routes visible without giving them the same visual weight as dominant routes.
- [StatsBomb's positional-tracker note](https://statsbomb.com/articles/soccer/new-development-introduction-to-player-positional-tracker/) again uses thicker connections for more frequent completed-pass combinations and cautions that small samples make average positions unstable.

Those products usually show player-to-player networks. Statballer's provider-neutral team contract exposes completed-pass counts between deterministic pitch zones, not recipient identities, so copying a player network would imply information the API does not contain. The redesign adopts the established visual grammar while remaining a spatial flow map.

## Chosen approach

- Preserve the deterministic 5-by-3 origin/destination matrix and provider-neutral API shape.
- Keep only routes above a relative visibility floor by default (at least eight completions and at least 12% of the largest route); retain a **Show all** control for auditability.
- Render nodes at zone centres, sized by aggregate outgoing completed-pass volume.
- Inset route endpoints from node centres, curve reciprocal routes to opposite sides, and explicitly draw arrowheads so direction is readable.
- Scale route width by the square root of relative completed-pass volume. This compresses the long tail, avoiding one dominant route making every other route hairline-thin.
- Scale opacity from 0.18 to 0.88 with the same relative volume and include a visible legend. Self-zone circulation is drawn as a loop rather than a zero-length mark.
- Use completed passes only. Attempts and completion rate remain available in the matrix, but mixing completion quality into the same colour channel would overload a compact card.

The result is deterministic for a given matrix, performs in a single canvas pass, and makes forward, backward, lateral, reciprocal, and same-zone movement visually distinct without suggesting player identities or inferred possession sequences.

## Representative sanity checks

- A dominant build-up route produces the widest and darkest arrow; lower-volume routes remain subordinate.
- Reversing origin and destination produces an opposite arrowhead and a curve on the other side of the node pair.
- A same-zone route produces a local loop rather than disappearing.
- The focused view prevents a complete 225-edge matrix from becoming an opaque block; **Show all** exposes every non-zero route when exact completeness matters.
- Player pass maps retain individual event start/end coordinates and default to **All**, so unsuccessful passes are not silently excluded from the overall total.

Future work can replace zone centres with pass-endpoint centroids or add possession/value weighting if those fields are introduced to the provider-neutral contract. It should not infer them in the frontend.
