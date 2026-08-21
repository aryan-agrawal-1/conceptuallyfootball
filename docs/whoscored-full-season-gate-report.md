# WhoScored 2025/26 Premier League full-season gate report

Gate date: 2026-08-21

Scope: published `ENG1` / `2025-26` complete season

Decision: **PASS — the complete-season event-profile dataset is current and public**

## Release gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Production-equivalent acquisition | PASS | Run 2252 used the default headless path with `DISPLAY` and `WAYLAND_DISPLAY` unset. It considered 380 completed matches, reused the 50 pilot payloads, fetched the remaining 330, and made 331 provider requests (one schedule plus 330 details) with zero retries, fetch failures, validation failures, or per-match failures. Ingestion elapsed time was 6,956.193 seconds. |
| Complete payload coverage | PASS | All 380 expected/completed matches have final checksum-valid payloads: expected and completed coverage are both 1.0. |
| Normalized events and team identity | PASS | The complete slice contains 577,884 normalized events. All 577,884 events map to canonical teams. |
| Player identity | PASS | 571,801 of 571,844 player-bearing events map to canonical players. The remaining 43 events are 30 for Jesse Derry and 13 for Jerome Abbey, or **0.00752%**. Explicit same-team manual mappings resolved Maximilian Kilman (1,099 events) and Hamed Traorè (12 events) before final publication. |
| Complete publication | PASS | Materialisation runs 2255 and 2256 each published `public_complete=true` with 380 observed/expected/completed matches. The current version contains 1,084 player profiles and 20 team profiles. |
| Determinism | PASS | Logical player/team content from runs 2255 and 2256 has identical SHA-256 `c9cc64a147070eccf83fa368fe8bd3907e63159906585ab1ea33af0985592774`. |
| API and cache | PASS | Erling Haaland player, all-pass, and Manchester City team endpoints returned 200. Their ETags were stable between cold and warm requests. |
| Browser responsiveness | PASS | Real Erling Haaland and Manchester City Event Maps passed at 1440x900 and 390x844. Player pass, shot, and touch maps and team pass-flow, shots-for, and shots-against rendered without console errors or horizontal overflow. |
| Export isolation | PASS | Event Maps remain a profile tab and are not part of the existing profile export flow. |

## Resource measurements

Measurements were taken on the development Mac and describe this machine, not a guaranteed VPS footprint. The full headless command took 9,142.14 seconds wall time, 2,747.07 seconds user CPU, and 579.54 seconds system CPU. `/usr/bin/time -l` recorded 741,097,472 bytes (706.8 MiB) maximum RSS for the command process and zero swaps.

Process-tree samples every 30–60 seconds showed why a before/after snapshot is insufficient:

- Early Chrome multi-process navigation briefly peaked near **4.8 GiB aggregate RSS**.
- The first browser session generally settled around **1.5–3.0 GiB**, with individual renderers reaching roughly 628 MiB and burst CPU occasionally exceeding one core.
- After Chrome restarted its temporary headless profile, the whole tracked tree stayed near **0.5–0.7 GiB**, with Django around 190–235 MiB and CPU usually 11–27% outside navigation bursts.
- The host swap-out counter did not increase during the successful run.

The safe operational conclusion is to provision from the observed peak plus operating-system, PostgreSQL, and worker margin. A 1–2 GiB VPS is not a safe assumption for this browser lifecycle. **At least 6 GiB RAM is the prudent starting point for a dedicated single-worker ingestion host; 8 GiB provides useful release headroom.** CPU is less constraining: two vCPUs should work for paced single-worker ingestion, while four vCPUs reduce navigation bursts and contention with PostgreSQL.

## Storage growth

PostgreSQL database size grew from 3,124,351,459 to 3,337,433,571 bytes: **213,082,112 bytes (203.2 MiB)**. Relation growth includes retained validation materialisations, so it is a conservative operational measurement rather than the irreducible one-version footprint.

| Relation | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Raw payloads | 6,529,024 | 39,813,120 | 33,284,096 |
| Normalized events | 55,771,136 | 213,024,768 | 157,253,632 |
| Player profiles | 22,822,912 | 43,515,904 | 20,692,992 |
| Team profiles | 2,195,456 | 3,964,928 | 1,769,472 |

## Representative API measurements

Local Django test-client timings include application serialization but not a production reverse proxy or network transit.

| Response | Cold | Warm | JSON bytes | Gzip bytes |
| --- | ---: | ---: | ---: | ---: |
| Erling Haaland profile | 217.10 ms | 10.76 ms | 138,010 | 8,829 |
| Erling Haaland all passes | 44.84 ms | 11.20 ms | 68,782 | 6,755 |
| Manchester City profile | 178.84 ms | 10.56 ms | 496,074 | 48,214 |

## Verification

- Backend: 256 tests passed with the non-TTY CI-style command.
- Django system check passed; migration drift check reported no changes.
- Frontend ESLint passed with zero errors and the existing TanStack Table compiler warning.
- Production Vite build passed. The broad `npm run build` TypeScript wrapper remains blocked only by ignored local Event Maps tests importing unavailable `vitest` and Testing Library packages; no production dependency was added.
- Browser: desktop/mobile player and team Event Maps passed with no console errors or horizontal overflow.

No application-code change was required for the full-season release. This report is the durable Batch 8 delivery evidence.
