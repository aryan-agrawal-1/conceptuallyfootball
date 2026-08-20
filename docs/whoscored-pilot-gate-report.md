# WhoScored 50-match Premier League pilot gate report

Initial gate: 2026-08-08; Batch 7 headless/UI revalidation: 2026-08-20

Scope: internal-only `ENG1` / `2025-26` pilot

Decision: **PASS — proceed to the full-season backfill; branch isolation keeps the pilot out of main**

## Scope and release isolation

The production ingestion command selected the latest 50 completed Premier League matches available at execution time. The stored slice spans 2026-04-22 through 2026-05-24 and includes all 20 teams.

The pilot was materialized with `--internal-pilot`. Its latest materialization records `internal_pilot=true`, `public_complete=false`, and incomplete coverage of 50 observed matches against 380 completed/expected matches. The feature remains isolated from `main` through the stacked delivery branches, while the player and team event-profile APIs stay available for review on the feature branch.

Incomplete materialization on a published regular-stat slice still requires the explicit `--internal-pilot` operational acknowledgement. API availability is based on current materialized profiles rather than the full-season publication gate, so reviewers can exercise incomplete pilot profiles before the stack is merged to `main`.

## Acceptance gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Production ingestion | PASS | With `DISPLAY` and `WAYLAND_DISPLAY` unset, the default production command ran headlessly and run 2246 live-fetched and parsed 50/50 matches in 912.578 s: 51 requests (1 schedule, 50 detail), zero cache reuses, retries, fetch failures, validation failures, or per-match failures. Its run evidence records `browser.headless=true` and `browser.mode=headless`. |
| Competition and team identity | PASS | 50/50 matches use the intended competition-season; 100/100 home/away match sides and 74,272/74,272 events map to canonical teams. |
| Player identity | PASS | 73,439/73,482 player-bearing events map to canonical players: **99.9415%**. The 43 tolerated events belong to two ambiguous youth identities; neither affects the 99% hard gate. |
| Parser and vocabulary | PASS | All 50 final payloads reparsed to 74,272 events with zero validation errors, unknown event types, or unknown qualifiers. |
| Event totals | PASS | 74,272 source timeline events equal 74,272 normalized rows. Source and normalized totals also agree for 46,814 passes and 1,331 shots. All 50 full-time score pairs agree, and 141 goal events equal the aggregate score total. |
| Coordinates | PASS | Every stored coordinate is inside 0..100. No invalid values occurred for start, end, goal-mouth, or blocked-shot coordinates. |
| Shot orientation | PASS | Both sides of all 50 matches were assessed (100 team-match sides). Every side attacks toward x=100; the lowest team-side median shot x was 78.0, above the 50.0 gate. |
| Cached ingestion rerun | PASS | The same no-display command without `--force` produced run 2247 in 4.232 s with one schedule request, zero detail requests, and 50 raw-payload reuses. Event totals remained unchanged. |
| Forced refetch and checksum lifecycle | PASS | Headless runs 2242 and 2243 force-refetched match 1903397 through real provider navigation. The first observed a legitimate source change to checksum `0bbc8c…4f27` and transactionally replaced its 1,357 events; the second retained that checksum and exact event IDs 75,630..76,986. Full forced run 2246 then revalidated all 50 payloads without rebuilding this unchanged match. |
| Materialization determinism | PASS | Consecutive formula-v2 internal materializations (runs 2248 and 2249) produced 834 current player profiles and 20 current team profiles. Every player, team, and opponent action grid has 384 deterministic 24×16 cells; logical content across all 854 rows had identical SHA-256 `a156447d7c6a2adeb119389c1e6f2d289dc523485a976378c21394329af1ded3`. |
| Manual map checks | PASS | Real Erling Haaland and Trai Hume player maps plus Manchester City team maps were checked in the supported browser at 1440×900 and 390×844. Continuous desktop two-column/mobile one-column cards, true All-pass filtering, pass/shot inspection, expansion, average-touch overlay, complete shot legends, automatic half/full shot pitches, volume-scaled directional pass flow, focus/show-all controls, territory maps, and responsive scrolling all worked with no console errors or horizontal overflow. |
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

The real pilot and Batch 7 revalidation exposed five production-path issues, each fixed before the final gates:

1. Current match-centre payloads omit the redundant top-level `matchId`, and `OffsideGiven` companion events can omit `second`; both shapes now validate safely.
2. The current known qualifier vocabulary exceeded the fixture vocabulary; all observed semantic pass/shot qualifiers and deliberately private untyped qualifiers are now recognized.
3. Team materialization rebuilt the selected match-ID set for every opponent event, causing quadratic runtime. The set is now computed once per materialization.
4. Incomplete materialization on a published regular-stat slice now requires explicit `--internal-pilot` acknowledgement, while feature-branch APIs remain reviewable before the delivery stack reaches `main`.
5. WhoScored acquisition needed a production-safe VPS contract. Both supported commands now default to headless Chrome, headed mode requires explicit `--headed-debug`, browser startup fails closed instead of silently reading stale cache, access failures are classified, and stored failure evidence is categorical and sanitized.

## Verification

- Backend: 255 tests passed with the exact CI command (`python manage.py test --noinput`).
- Django: system check passed; migration drift check reported no changes.
- Python: ingestion package compilation passed.
- Frontend: product-source TypeScript check and production Vite build passed. The broad `npm run build` remains blocked only by local ignored frontend test files importing unavailable `vitest` and `@testing-library/react`; no production dependency was added and no frontend test was committed.
- ESLint: passed with zero errors and one existing TanStack Table React-compiler warning.
- Browser: real desktop/mobile player and team flows, automatic half/full shot pitches, flow focus/show-all, expansion, selection, and the prior 5,000-pass responsive gate passed with no page console errors.

## Decision and next step

Every Batch 7 hard gate is met. The 43 ambiguous player events and the source-summary differences are within the documented tolerances and do not represent dropped normalized events. Batch 8 may proceed with the complete Premier League backfill. The pilot remains off `main` until the delivery stack is ready, while its feature-branch profiles remain available for review.
