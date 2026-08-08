# WhoScored 50-match Premier League pilot gate report

Date: 2026-08-08

Scope: internal-only `ENG1` / `2025-26` pilot

Decision: **PASS — proceed to the full-season backfill; branch isolation keeps the pilot out of main**

## Scope and release isolation

The production ingestion command selected the latest 50 completed Premier League matches available at execution time. The stored slice spans 2026-04-22 through 2026-05-24 and includes all 20 teams.

The pilot was materialized with `--internal-pilot`. Its latest materialization records `internal_pilot=true`, `public_complete=false`, and incomplete coverage of 50 observed matches against 380 completed/expected matches. The feature remains isolated from `main` through the stacked delivery branches, while the player and team event-profile APIs stay available for review on the feature branch.

Incomplete materialization on a published regular-stat slice still requires the explicit `--internal-pilot` operational acknowledgement. API availability is based on current materialized profiles rather than the full-season publication gate, so reviewers can exercise incomplete pilot profiles before the stack is merged to `main`.

## Acceptance gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Production ingestion | PASS | Run 2231 fetched and parsed 50/50 matches in 710.293 s: 51 requests (1 schedule, 50 detail), no retries, fetch failures, validation failures, or per-match failures. |
| Competition and team identity | PASS | 50/50 matches use the intended competition-season; 100/100 home/away match sides and 74,272/74,272 events map to canonical teams. |
| Player identity | PASS | 73,439/73,482 player-bearing events map to canonical players: **99.9415%**. The 43 tolerated events belong to two ambiguous youth identities; neither affects the 99% hard gate. |
| Parser and vocabulary | PASS | All 50 final payloads reparsed to 74,272 events with zero validation errors, unknown event types, or unknown qualifiers. |
| Event totals | PASS | 74,272 source timeline events equal 74,272 normalized rows. Source and normalized totals also agree for 46,814 passes and 1,331 shots. All 50 full-time score pairs agree, and 141 goal events equal the aggregate score total. |
| Coordinates | PASS | Every stored coordinate is inside 0..100. No invalid values occurred for start, end, goal-mouth, or blocked-shot coordinates. |
| Shot orientation | PASS | Both sides of all 50 matches were assessed (100 team-match sides). Every side attacks toward x=100; the lowest team-side median shot x was 78.0, above the 50.0 gate. |
| Cached ingestion rerun | PASS | Run 2232 completed in 6.444 s with one schedule request, zero detail requests, and 50 raw-payload reuses. Event count and row IDs remained unchanged. |
| Forced refetch and checksum lifecycle | PASS | A real forced refetch of match 1903397 found a source change: checksum `5117f6…bf09` became `197cba…92f`, and its 1,357 events were transactionally replaced. A second real forced refetch retained checksum `197cba…92f` and the exact event ID range 74,273..75,629, proving unchanged payloads do not rebuild rows. Both runs used one schedule and one detail request with no retry or validation failure. |
| Materialization determinism | PASS | Consecutive internal materializations produced 834 current player profiles and 20 current team profiles. Logical content across all 854 rows had the identical SHA-256 `34ca7efcfa911551abc717b1eff0f7630cf00ea3a4327a6ddb979a174639592a`; the optimized rerun completed in 5.486 s. |
| Manual map checks | PASS | Real Bernardo Silva player maps and Manchester City team maps were checked in the supported browser at 1440×1000 and 390×844. Player pass filters, shots, action density, average touch, team pass flow, shots for/against, territory, opponent territory, responsive scrolling, and tab changes were plausible and produced no console errors. |
| 5,000-pass browser gate | PASS | The production `PortraitPitch` component was exercised with 5,000 pass lines through a temporary local QA injection that was removed immediately afterward. Desktop and 390 px mobile layouts rendered without console errors or page-level horizontal overflow; switching from the dense pass map to Actions completed in 282 ms. |
| Feature-branch review access | PASS | Manchester City and Erling Haaland detail flags report `event_profile.available=true`; their event-profile endpoints return 200 while coverage metadata clearly remains incomplete. The delivery stack is not yet merged to `main`. |

## Documented source-summary differences

WhoScored's per-minute `home.stats` / `away.stats` summary buckets are not a lossless count of its event timeline. Across this slice they report 43,010 passes, 3,804 fewer than the 46,814 `Pass` timeline events; every match differs by 53–104 passes. They report 1,326 shots, one fewer timeline shot in five matches. These are tolerated source-internal summary differences, not normalization loss: the normalized database agrees exactly with every timeline event and with all match scores and goal totals. The raw summary remains private and is not used to build public event profiles.

## Storage and response measurements

Measurements were taken from the development PostgreSQL database after the pilot and repeated materializations.

| Item | Rows / responses | Table or raw bytes | Index or gzip bytes | Total / range |
| --- | ---: | ---: | ---: | ---: |
| Raw payloads | 50 | 53,090,663 uncompressed | 4,823,302 compressed | 86,092–107,669 compressed per match |
| Normalized event relation | 74,272 | 42,287,104 | 17,129,472 | 59,457,536 |
| Player aggregate relation | 1,668 physical rows after two retained runs; 834 current | 4,890,624 | 720,896 | 5,652,480 |
| Team aggregate relation | 40 physical rows after two retained runs; 20 current | 204,800 | 147,456 | 671,744 |
| Materialized API cache relation | 18 pre-existing/QA rows at measurement | 8,192 | 303,104 | 12,025,856 including PostgreSQL TOAST/churn |

The full development database was 3,093,484,003 bytes; this is contextual and mostly consists of pre-existing similarity and derived-stat data.

Representative gzip-enabled localhost API measurements:

| Response | Uncached | Cached | JSON bytes | Gzip bytes |
| --- | ---: | ---: | ---: | ---: |
| Player profile | 63.44 ms | 32.21 ms | 17,720 | 2,171 |
| Player completed passes | 79.46 ms | 29.00 ms | 97,877 | 8,521 |
| Team profile | 63.12 ms | 34.09 ms | 112,287 | 11,254 |

The API defensive cap was previously measured with a real 5,002-row fixture: 5,000 rows returned, 1,154,631 bytes JSON / 30,148 bytes gzip, 314.75 ms uncached / 7.15 ms cached. Batch 7 adds the missing supported-browser rendering and interaction evidence above.

## Defects found and resolved

The real pilot exposed four production-path issues, each fixed before the final gates:

1. Current match-centre payloads omit the redundant top-level `matchId`, and `OffsideGiven` companion events can omit `second`; both shapes now validate safely.
2. The current known qualifier vocabulary exceeded the fixture vocabulary; all observed semantic pass/shot qualifiers and deliberately private untyped qualifiers are now recognized.
3. Team materialization rebuilt the selected match-ID set for every opponent event, causing quadratic runtime. The set is now computed once per materialization.
4. Incomplete materialization on a published regular-stat slice now requires explicit `--internal-pilot` acknowledgement, while feature-branch APIs remain reviewable before the delivery stack reaches `main`.

## Verification

- Backend: 249 tests passed with the exact CI command (`python manage.py test --noinput`).
- Django: system check passed; migration drift check reported no changes.
- Python: ingestion package compilation passed.
- Frontend: product-source TypeScript check and production Vite build passed.
- ESLint: passed with zero errors and one existing TanStack Table React-compiler warning.
- Browser: real desktop/mobile player and team flows plus the 5,000-pass responsive gate passed with no page console errors.

## Decision and next step

Every Batch 7 hard gate is met. The 43 ambiguous player events and the source-summary differences are within the documented tolerances and do not represent dropped normalized events. Batch 8 may proceed with the complete Premier League backfill. The pilot remains off `main` until the delivery stack is ready, while its feature-branch profiles remain available for review.
