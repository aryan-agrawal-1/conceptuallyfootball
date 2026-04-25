## Problem Statement

As the product owner of a Premier League analytics platform, I need a reliable way to ingest, normalize, match, store, and expose player season data from multiple football data providers before I can build meaningful product features on top of it. Right now, the platform concept depends on Understat for attacking/general data, Sofascore for defensive/passing/goalkeeping data, and `reep` for identity resolution, but there is no stable ingestion layer that turns those sources into one trustworthy backend dataset.

From my perspective, the problem is not just fetching data. I need the backend to own canonical players, teams, competitions, and seasons; reconcile mismatched provider identities safely; preserve enough provenance to debug problems; and expose merged season-level data through a clean internal API. I also need this pipeline to work against the current Premier League season, tolerate real-world provider imperfections, and provide enough admin visibility that I can inspect runs, repair unmatched records, and trust the data before building user-facing analytics.

## Solution

Build a backend-first data ingestion foundation that fetches season-aggregate data from Understat and Sofascore, resolves player and team identities using an offline locally synced `reep` reference dataset, stores normalized provider-owned rows in PostgreSQL, materializes a canonical merged player-season dataset, and exposes minimal internal read APIs for that merged data.

From the user's perspective, the solution should make the platform "data ready." I should be able to run the ingestion flow for Premier League 2025-26, inspect the results in admin, manually resolve identity edge cases, reprocess affected rows, and query a stable merged dataset without touching provider APIs directly. The system should be designed for multiple seasons and competitions, but the first proven slice should be the current Premier League season. The goal is not analytics computation yet; the goal is to produce a trustworthy canonical season data layer that future matrix, profile, and similarity features can build on.

## User Stories

1. As a product owner, I want the backend to ingest Premier League 2025-26 season data from Understat, so that attacking and general player statistics are available in our system.
2. As a product owner, I want the backend to ingest Premier League 2025-26 season data from Sofascore, so that defensive, passing, and goalkeeping statistics are available in our system.
3. As a product owner, I want the ingestion architecture to support multiple seasons from the start, so that expanding beyond the current season does not require redesigning the data model.
4. As a product owner, I want the ingestion architecture to be competition-aware from the start, so that adding new leagues later does not require hardcoded Premier League assumptions.
5. As a data consumer, I want the system to create canonical player records independent of provider IDs, so that the rest of the platform can rely on stable internal identities.
6. As a data consumer, I want the system to create canonical team records independent of provider IDs, so that filtering, joins, and future team-based features are consistent.
7. As a data consumer, I want canonical competition and season records in the database, so that all ingested data can be scoped and queried cleanly by competition and season.
8. As a product owner, I want `reep` to be used as a local reference dataset rather than a live runtime dependency, so that ingestion runs are more deterministic and less fragile.
9. As a data operator, I want a separate `reep` sync flow, so that identity reference data can be refreshed independently from daily stats ingestion.
10. As a data operator, I want the system to import only the relevant subset of `reep` data, so that the database contains useful identity reference data without unnecessary noise.
11. As a data operator, I want provider-specific player identity mappings to be stored explicitly, so that I can understand how an Understat or Sofascore player was attached to a canonical player.
12. As a data operator, I want provider-specific team identity mappings to be stored explicitly, so that I can understand how provider team records map to canonical teams.
13. As a platform owner, I want season-varying facts like team, position, and minutes stored separately from the base player record, so that player identity and season context do not get mixed together.
14. As a platform owner, I want player-season records to exist even when only one provider has data for a player, so that valid partial coverage is still usable.
15. As a platform owner, I want Understat to be the preferred metadata authority when available, so that season metadata is promoted consistently.
16. As a platform owner, I want Sofascore metadata to be used as a fallback when Understat is missing for a valid matched player-season, so that players are not dropped unnecessarily.
17. As a frontend developer, I want a single merged player-season dataset, so that I do not have to understand multiple provider schemas to build product features.
18. As a frontend developer, I want provider-owned fields to have clear source ownership, so that I know exactly what each merged stat means.
19. As a frontend developer, I want attacking and general fields to come from Understat, so that those numbers are consistent across the app.
20. As a frontend developer, I want defensive, passing, and goalkeeping fields to come from Sofascore, so that those categories come from one consistent provider.
21. As a product owner, I want the system to avoid silent cross-provider fallback for similar-looking stats, so that merged data remains semantically consistent.
22. As a data consumer, I want missing stat values to remain `NULL` rather than being converted to zero, so that the system can distinguish missing data from true zero values.
23. As a data operator, I want source-specific stats to be stored in provider-owned normalized tables, so that ingestion truth remains separated from the product-facing merged contract.
24. As a data operator, I want the Sofascore ingestion flow to fetch multiple stat groups but normalize them into one provider season row per player, so that provider data is easier to validate and merge.
25. As a product owner, I want the merged player-season dataset to be materialized as a table, so that it is stable, indexable, and easy to expose through APIs.
26. As a product owner, I want the merged dataset to refresh only after both provider ingestions succeed for the same slice, so that the canonical season layer reflects a coherent cross-provider snapshot.
27. As a data operator, I want provider-specific slice refreshes to be full refreshes for a competition-season slice, so that ingestion is easier to reason about and rerun safely.
28. As a data operator, I want merged rows to be soft-retired rather than silently disappearing, so that stale or superseded rows remain explainable and auditable.
29. As a data operator, I want row-level provider identifiers preserved on normalized source rows, so that I can trace each stored record back to the original provider entity.
30. As a data operator, I want every source row linked to an ingestion run, so that I can diagnose which batch produced a problem.
31. As a data operator, I want merged rows linked to the source runs that created them, so that I can explain freshness and provenance clearly.
32. As a data operator, I want ingestion runs recorded explicitly, so that I can inspect run status, timing, scope, and failure details.
33. As a data operator, I want balanced validation gates on ingestion, so that systemic provider issues fail the run while a few edge-case records do not break the pipeline.
34. As a data operator, I want the system to detect suspicious anomalies such as low match rates or unexpectedly low row counts, so that bad data does not silently enter the merged layer.
35. As a product owner, I want unmatched player identities to be quarantined rather than auto-merged, so that duplicate or incorrect canonical players are not created accidentally.
36. As a product owner, I want unmatched team identities to be quarantined rather than auto-merged, so that club identity remains clean and trustworthy.
37. As a data operator, I want Django admin visibility into unmatched identities, so that I can review and resolve edge cases without direct database edits.
38. As a data operator, I want to manually resolve an unmatched provider player to an existing canonical player, so that I can fix identity gaps without changing code.
39. As a data operator, I want to manually resolve an unmatched provider team to an existing canonical team, so that I can fix affiliation gaps without changing code.
40. As a data operator, I want manual identity overrides to preserve whether a match was automatic or manual, so that I can understand how a mapping was created.
41. As a data operator, I want manual overrides to trigger targeted reprocessing for the affected rows, so that fixes become visible immediately without rerunning an entire season.
42. As a platform owner, I want goalkeeper records included in the ingestion model, so that the platform has full player coverage even before goalkeeper-specific analytics exist.
43. As a platform owner, I want canonical position groups normalized into stable buckets such as GK, DEF, MID, and FWD, so that filters and future analytics operate on consistent categories.
44. As a data operator, I want provider-native positions preserved alongside normalized position groups, so that I can debug mapping decisions and refine them later.
45. As a platform owner, I want player-season rows to exist at one row per player-season grain, so that the canonical contract stays simple for future consumers.
46. As a platform owner, I want multi-club player histories preserved separately from the main player-season row, so that transfers can be represented without duplicating players in the canonical season layer.
47. As a frontend developer, I want each merged player-season row to expose one canonical display team, so that table and profile UIs have one stable team value to show.
48. As a frontend developer, I want the canonical display team for a player-season to use the provider-reported current season team from the preferred metadata source, so that the displayed club aligns with the player's current club context.
49. As a frontend developer, I want a minimal internal list API for merged player-season data, so that I can begin building against the canonical backend contract.
50. As a frontend developer, I want a minimal internal detail API for merged player-season data, so that I can inspect one canonical player-season record cleanly.
51. As a frontend developer, I want list APIs to support filtering by season and competition, so that I can query relevant slices of the dataset.
52. As a frontend developer, I want list APIs to support team and position filters, so that future table and profile screens can be built on top of the ingestion contract.
53. As a frontend developer, I want merged APIs to expose canonical identity data together with merged stats, so that the UI does not need to stitch multiple resources together just to render a player row.
54. As a product owner, I want the Phase 1 read APIs to expose only canonical merged data, so that consumers depend on the stable product contract rather than provider-specific internals.
55. As a product owner, I want the bootstrap read APIs to be unauthenticated for now, so that I can iterate on the ingestion layer without introducing unrelated auth complexity.
56. As a developer, I want management commands for `reep` sync, provider ingestion, and merge execution, so that the pipeline can be run and debugged manually.
57. As a developer, I want the same ingestion logic callable from Celery tasks, so that asynchronous processing is available without duplicating business logic.
58. As a platform owner, I want Celery and Redis used for background execution from the start, so that the architecture matches the intended production shape.
59. As a developer, I want local development to require PostgreSQL and Redis from the start, so that local behavior matches the architecture the ingestion system is designed for.
60. As a developer, I want the first validated implementation to target the live Premier League 2025-26 season, so that I can test both the stable ingestion path and how the system behaves as provider data changes over time.
61. As a product owner, I want Phase 1 to be considered complete only when end-to-end ingestion, matching, merge, admin inspection, and minimal read APIs all work for the configured slice, so that the milestone represents a proven data foundation rather than just scaffolding.
62. As a future feature developer, I want the ingestion layer to stop at merged provider data and not compute analytics yet, so that future percentile, custom score, and similarity work can be built on a clean base.
63. As a future analytics developer, I want the merged layer to preserve provenance and clean null semantics, so that later per-90, percentile, and similarity computation can be done accurately.
64. As a product owner, I want the system to serve stored data from our database rather than calling providers from the frontend, so that reliability, rate limiting, and API fragility are handled server-side.
65. As a data operator, I want enough admin visibility to inspect runs, source rows, canonical records, mappings, unmatched records, and merged rows, so that I can operate the ingestion pipeline confidently.

## Implementation Decisions

- The feature will be implemented as a backend ingestion foundation, not a user-facing analytics feature.
- The architecture is multi-season and competition-aware from the start, even though the first operational slice is Premier League 2025-26.
- The first validated target is the current Premier League season, not a historical frozen season.
- Canonical entities will exist for players, teams, competitions, and seasons.
- All canonical entities will use internal database primary keys.
- `reep_id` will be stored as an external canonical reference where applicable, but it will not become the database primary key.
- `reep` will be consumed as an offline local reference dataset, not as a live runtime API dependency during ingestion.
- `reep` sync will run on its own lifecycle, separate from provider stats ingestion.
- The application will import a scoped subset of `reep` reference data rather than mirroring the entire public register.
- The data model will include provider identity mappings for players and teams.
- Identity resolution will rely on `reep` first, with manual override capability in admin for unresolved edge cases.
- Unmatched player identities will be quarantined rather than auto-created or silently merged.
- Unmatched team identities will be quarantined rather than auto-created or silently merged.
- Manual identity overrides will trigger targeted reprocessing for affected entities and season slices.
- Season-varying attributes will be stored separately from base identity records.
- A dedicated player-season model will hold canonical season context such as team, position group, and metadata provenance.
- Provider-native position values will be preserved alongside a normalized canonical position group.
- Canonical position grouping will use stable broad buckets suitable for filtering and future analytics.
- Multi-club season history will be modeled separately from the main player-season row.
- The main merged season contract will remain one row per player-season rather than duplicating players by club spell.
- The canonical display club for a player-season will be the provider-reported current season team from the preferred metadata source.
- Understat is the preferred metadata authority when both providers exist for a valid player-season.
- Sofascore metadata may be used as fallback when Understat is absent for a matched player-season.
- A player-season row may exist even if only one provider contributes data for that player.
- Source-specific data will be stored in provider-owned normalized season tables.
- Understat source tables will hold attacking and general season-aggregate data.
- Sofascore source tables will hold defensive, passing, and goalkeeping season-aggregate data.
- Sofascore transport-level stat groups will be fetched separately but consolidated into one normalized Sofascore player-season source row.
- A single materialized merged player-season table will represent the canonical app-facing season dataset.
- The merged table will contain only merged provider data and canonical identity metadata, not downstream analytics computation.
- Field ownership in the merged table will be strict and explicit.
- Attacking and general fields are sourced from Understat.
- Defensive, passing, and goalkeeping fields are sourced from Sofascore.
- No silent cross-provider fallback will be used for field values that appear similar across providers.
- Missing values will be stored as `NULL` rather than coerced to zero unless the provider explicitly reports zero.
- Provider ingestion will use full refresh behavior for each provider, competition, and season slice.
- The merged table will be rebuilt only after both provider ingestions for the same slice complete successfully.
- Merged rows can be partial at the row level, meaning a player-season may have some fields populated and other provider-owned fields left `NULL`.
- Retired or superseded merged rows will be soft-retired rather than simply disappearing without trace.
- Ingestion provenance will be captured at both run level and row level.
- Source rows will store their original provider identifiers and link back to the ingestion run that created them.
- Merged rows will store enough provenance to identify which provider runs produced them.
- Balanced validation gates will be applied during ingestion to catch systemic anomalies such as abnormally low row counts, suspicious field completeness, or poor identity match rates.
- Provider-specific configuration for competition and season resolution will live in database-backed configuration records rather than scattered hardcoded values.
- Local development will require PostgreSQL and Redis from the start.
- Postgres and Redis will be installed and run manually rather than via Docker.
- Celery tasks will exist for background execution, but the first milestone emphasizes manual triggering through management commands and shared service logic.
- Django admin will provide operational visibility into runs, source rows, canonical entities, identity mappings, unmatched records, and merged rows.
- The minimal read API contract will expose only canonical merged data, not source-specific debug data.
- The minimal read API is an internal bootstrap contract, not a frozen long-term public API.
- The bootstrap read API will be unauthenticated for this phase.
- Minimal read endpoints will support list and detail access for canonical merged player-season data with practical filters such as competition, season, team, and position.
- Match logs are excluded from this milestone.
- Per-90 metrics, percentiles, custom scores, embeddings, archetype clusters, similarity pairs, and other analytics derivations are excluded from this milestone.
- Phase 1 is complete only when end-to-end ingestion, canonical matching, admin-based repair workflows, merged materialization, and minimal merged-only read APIs are all working for the configured live season slice.

## Testing Decisions

- Good tests should verify external behavior and contractual outcomes rather than implementation details.
- Tests should focus on what the system stores, exposes, retires, rejects, or recalculates, not on private helper structure or internal control flow.
- The highest-value tests are the ones that prove the ingestion pipeline behaves correctly at system boundaries: provider normalization, identity resolution, merge behavior, API output, and admin-triggered remediation.
- The ingestion service layer should be tested to confirm provider payloads are normalized into the correct source rows.
- Identity resolution should be tested to confirm known provider identities resolve correctly through local `reep` reference data.
- Identity failure behavior should be tested to confirm unmatched players and teams are quarantined rather than silently promoted.
- Manual override behavior should be tested to confirm admin-driven remapping updates the canonical linkage and triggers targeted reprocessing of affected records.
- Merge behavior should be tested to confirm strict field ownership, partial row creation, `NULL` handling, provenance recording, and soft retirement behavior.
- Validation behavior should be tested to confirm clear systemic anomalies fail the relevant run while isolated unmatched records do not invalidate an otherwise successful slice.
- Minimal read APIs should be tested to confirm they expose canonical merged data only, apply filters correctly, and return stable merged records rather than provider-specific internals.
- Admin-level behavior should be tested selectively where it protects important workflows, especially visibility into unmatched records and manual override actions.
- Model-level tests should cover important uniqueness and lifecycle constraints, especially around canonical entities, provider mappings, and season-grain records.
- Management command and task integration should be tested to confirm shared service logic can be invoked reliably from both manual and background execution paths.
- Tests should prefer fixtures or factory data that model realistic provider and identity edge cases, such as unmatched players, partial provider coverage, multiple clubs in a season, and missing stat groups.
- Prior art in the codebase should be followed where similar backend tests already exist, especially around Django model tests, serializer or API tests, management command tests, and service-level ingestion tests.
- If little or no prior test structure exists yet, the test suite should establish a pattern that favors service-level and API-contract tests over brittle low-level unit tests.
- Tests should avoid asserting on implementation-only details such as internal method names, private parsing steps, or exact intermediate object shapes unless those details are part of the external contract.

## Out of Scope

- Match-by-match ingestion.
- Match log models and APIs as a required deliverable of this phase.
- Per-90 metrics.
- Position-based percentiles.
- Custom scores such as attack, creation, finishing, ball-winning, involvement, or efficiency.
- Embeddings generation.
- Similarity score computation.
- Archetype clustering.
- UMAP or galaxy projection generation.
- Radar or pizza chart configuration logic.
- Any frontend matrix, profile, or galaxy UI work.
- Public-facing or production-hardened API versioning strategy.
- Authentication and authorization for the bootstrap read APIs.
- Full production scheduling or orchestration hardening beyond the initial manual-trigger plus background-task setup.
- Raw provider payload archival.
- A custom internal ops dashboard beyond basic Django admin support.
- Generic import of the entire public `reep` dataset.
- Full multi-league rollout beyond designing the schema and task interfaces to support it.

## Further Notes

- The most important architectural principle in this PRD is separation of concerns: provider ingestion truth, canonical identity resolution, and app-facing merged data are distinct layers and should remain distinct.
- Another core principle is safety over false completeness. The system should prefer quarantining questionable identities and exposing `NULL` for missing values over silently inventing matches or filling gaps with misleading values.
- The milestone is intentionally designed to end at a clean merged provider-data layer. That is the right place to stop before building percentiles, custom metrics, similarity, or product UIs.
- Because the first validation target is the live 2025-26 Premier League season, some provider data may change between runs. This is acceptable and useful, because it exercises freshness, rerun behavior, and soft-retirement logic early.
- The final product experience depends heavily on trusting the data layer. For that reason, admin visibility, provenance, and manual override workflows are not incidental operational features; they are part of the core usability of the ingestion system.
- The merged API should stay disciplined. If consumers begin depending on provider-specific source tables too early, the canonical data contract will erode and future iterations will become harder.
- The PRD assumes that current provider access patterns remain workable for backend ingestion. If provider access characteristics change materially, the implementation may need tactical adjustments without changing the high-level product contract described here.