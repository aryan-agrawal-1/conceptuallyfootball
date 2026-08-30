# Player role materialization benchmark

This is the Batch 1 benchmark and equivalence contract for issue #122. It measures the accepted
`player_role_features_v4` construction path without publishing feature snapshots or roles. It also
provides the oracle that later bounded-memory implementations must match before they can replace
the accepted path.

## Representative corpus

The committed manifest is
`backend/ingestion/benchmarks/player_role_corpus_v1.json`. It pins six player-team contexts from
competition-season 4 (`ENG1 2025-26`) rather than selecting whichever profiles happen to rank
highest in a changing database:

| Profile | Evidence classes |
| --- | --- |
| Djordje Petrovic — Bournemouth | goalkeeper |
| Virgil van Dijk — Liverpool | high-minute outfield, all losing/drawing/winning states, goals and assists |
| Eberechi Eze — Crystal Palace | sparse exposure, first transfer/team context |
| Eberechi Eze — Arsenal | second transfer/team context |
| Nilson Angulo — Sunderland | low-minute substitute (under 450 verified minutes) |
| Elliot Anderson — Nottingham Forest | transition involvement |

The manifest loader fails if any required evidence class is omitted or a player-team key is
duplicated. Transfer stints deliberately remain separate.

## Run the benchmark

Use a fresh process for every reported size so peak RSS is not inherited from an earlier run.
The command requires the normalized season-4 source data described in issue #122 and the current
feature cohort. From the repository root:

```bash
backend/venv/bin/python backend/manage.py benchmark_player_role_features 4 \
  --oracle backend/ingestion/benchmarks/player_role_oracle_v1.json \
  --output /tmp/player-role-full.json
```

To reproduce the increasing-size curve, run these separately:

```bash
backend/venv/bin/python backend/manage.py benchmark_player_role_features 4 \
  --match-count 10 --output /tmp/player-role-10.json

backend/venv/bin/python backend/manage.py benchmark_player_role_features 4 \
  --match-count 50 --output /tmp/player-role-50.json
```

Matches are selected deterministically by `(kickoff_at, id)`. A size-limited run measures feature
construction but cannot be compared to the full-season oracle. The default run uses all matches.

The report contains:

- total wall time and timings for profile loading, match loading, event hydration, assist
  resolution, goal context, each corpus profile, combined feature construction, cohort snapshot
  loading, and pure cohort scoring;
- SQL query count;
- actual Django model instances hydrated during the run, grouped by model;
- RSS at process start, process peak RSS, and peak growth;
- feature/scoring versions, match count, and corpus profile count.

The database connection is guarded during feature construction: any SQL operation other than a
read raises `BenchmarkWriteError`. The benchmark never calls either publication service. `--output`
and `--write-oracle` only write JSON files on the local filesystem.

## Equivalence contract

`backend/ingestion/benchmarks/player_role_oracle_v1.json` captures the accepted current feature JSON
and resulting complete-cohort candidate, classification, and trait output for every corpus context.
Comparison is recursive and automatic:

- object keys, array order and length, strings, booleans, nulls, and integers are exact;
- floats use absolute tolerance `0.000001` and relative tolerance `0`;
- unexpected and missing values fail the command;
- the scoring candidate replaces the corpus profiles in the complete current 549-snapshot cohort,
  so cohort-relative output is checked against the accepted distribution.

Regenerate the oracle only after an intentional football-semantics change has been reviewed:

```bash
backend/venv/bin/python backend/manage.py benchmark_player_role_features 4 \
  --write-oracle backend/ingestion/benchmarks/player_role_oracle_v1.json
```

An optimization must compare against the existing oracle; it must not regenerate the oracle and
then use that newly generated file as proof of equivalence.

## Recorded baseline — 30 August 2026

The issue-level representative-profile baseline remains the production control: approximately
5.4 seconds and 31 queries for one profile, with 577,884 normalized events, 112,253 carries,
96,124 state-exposure rows, 136,511 possessions, 505,926 possession-event links, and 549 current
feature snapshots. Loading and purely scoring all 549 snapshots took approximately 1.34 seconds.

The committed six-profile harness produced this size curve on the same local season-4 PostgreSQL
dataset. These are diagnostic observations, not performance thresholds:

| Matches | Wall time | Event load | Feature builds | Cohort load + score | Queries | Peak RSS |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 2.94 s | 0.37 s | 1.13 s | 1.38 s | 170 | 605 MB |
| 50 | 6.94 s | 1.97 s | 3.54 s | 1.31 s | 178 | 896 MB |
| 380 | 53.30 s | 14.76 s | 36.31 s | 1.49 s | 186 | 3,231 MB |

At 380 matches the harness hydrated 916,684 `ProviderMatchEvent`, 26,231
`ProviderMatchCarry`, 12,536 `ProviderMatchPlayerStateExposure`, 28,079
`ProviderMatchPossession`, and 105,509 `ProviderMatchPossessionEvent` instances while constructing
only six profiles. The near-linear match-size growth and repeated related-object hydration make the
Batch 3 bounded-row target directly measurable.

The machine-readable observations are committed in
`backend/ingestion/benchmarks/player_role_baseline_2026-08-30.json`.
