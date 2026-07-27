# WhoScored source foundation

This runbook records the verified acquisition contract, safe fixture policy,
source checks, and pre-event-table storage baseline for
`docs/whoscored-event-profiles-v1.md`.

## Acquisition contract

The initial source is `soccerdata>=1.9,<2` and its Selenium-backed
`WhoScored` reader. Use:

```bash
backend/venv/bin/python backend/manage.py probe_whoscored_source \
  --league "ENG-Premier League" \
  --season "2025-26" \
  --match-count 3
```

The probe is intentionally capped at five matches. It emits schedule totals,
event-family counts, missing-player counts, canonical payload sizes/checksums,
coordinate diagnostics, and per-team shot-orientation summaries. It never
prints raw events, player dictionaries, commentary, or qualifiers.

`soccerdata` configures its log and data directories at import time. Run
through `manage.py`, which initializes `SOCCERDATA_DIR`, or set
`SOCCERDATA_DIR` to a writable private directory before importing
`soccerdata`. The adapter also supplies a project-local default and creates its
log directory before its lazy import.

The browser integration requires:

- a compatible local Chrome/Chromium and driver;
- JavaScript execution and access to WhoScored match pages;
- a writable ignored cache (normally `backend/.soccerdata/`);
- headed browser mode when headless access is challenged;
- serialized, paced requests. `soccerdata` 1.9 sets a five-second reader rate
  limit; ingestion must not add concurrent browser fetches;
- explicit, bounded retries. Access-control pages, consent UI changes, Selenium
  errors, and empty/null match data are source failures, not empty matches.

Use `--force` only for an intentional refetch. Normal probes reuse schedule and
event caches where possible.

WhoScored's `/tournaments/<stage>/data/` endpoint is displayed by current
Chrome versions as a JSON document inside an HTML page. `soccerdata` 1.9 wraps
that page a second time before calling `json.load`, which makes an otherwise
valid response unreadable. The project adapter handles only this exact endpoint
by reading `document.body.innerText`, validating that it is a JSON object, and
leaving all other soccerdata page validation unchanged. HTML challenges and
empty responses still fail closed.

### Local live-verification status

On 2026-07-27, two consecutive headed probes completed against
`ENG-Premier League` `2025-26`. They discovered 380 completed matches and
selected matches `1903370`, `1903373`, and `1903458`. The payloads contained
1,481, 1,409, and 1,472 events respectively, with zero coordinate errors.
All six assessed team sides attacked toward `x=100`; median shot x ranged from
84.9 to 93.65.

The match payload SHA-256 values were stable across both runs:

- `1903370`: `1bace0aca11b4896fc0bb149a0e127f735789acd2a174d4b9bf3475424f94066`
- `1903373`: `b7a81f5dd3d58a422ffd3bb50c2bbcefa0af671ca1ac2a6921489580e40cc6e7`
- `1903458`: `576566787e0bdac5aeabe51c1622ce1b74abc912fcee27e220ab93e6b60f9cfd`

The two sanitized reports were byte-identical and had report SHA-256
`40775f7e509ce7ef5be3950af128fb97f8f18b9d15caf32672f4d7c206914bbd`.
Raw payloads remain only in the ignored local soccerdata cache.

### Full payload requirement

In `soccerdata` 1.9.0, `read_events(output_fmt="raw")` returns only the
`events` list despite its docstring calling this the original JSON. The complete
`require.config.params['args'].matchCentreData` object is written under:

```text
<WhoScored data_dir>/events/<league>_<season>/<match_id>.json
```

`SoccerdataWhoScoredClient.fetch_match_payload()` therefore calls
`read_events(output_fmt=None)` to populate the cache and then reads and
validates that complete object. Downstream ingestion must use the returned
canonical bytes; it must not replace this with the events-only `raw` return
value.

## Safe fixtures

Fixtures under
`backend/ingestion/tests/fixtures/whoscored/` are synthetic and sanitized.
Their IDs, names, scores, and coordinates are hand-authored. Together they
exercise:

- schedule normalization for completed and scheduled matches;
- passes and representative typed qualifiers;
- every v1 shot outcome and optional shot coordinates;
- touches, take-ons, and every v1 defensive action family;
- cards, fouls, offside, and substitutions;
- a missing player ID;
- unknown event and qualifier IDs;
- the same synthetic player ID on a different synthetic team across matches.

Never commit a downloaded match-centre response, browser HTML, screenshot, or
soccerdata cache file. Full payloads remain in ignored local cache or approved
private backend storage. Probe reports are safe to retain because they contain
only aggregate diagnostics, but they are operational artifacts and do not
replace raw private storage.

## Checksums, coordinates, and orientation

Canonical payload bytes use UTF-8 JSON with sorted keys, compact separators,
no NaN values, and no ASCII escaping. SHA-256 is calculated over those
uncompressed bytes. Reordering object keys must not change the checksum.

Every coordinate present in `x`, `y`, `endX`, `endY`, `goalMouthY`,
`goalMouthZ`, `blockedX`, or `blockedY` must be numeric and within `0..100`.
Missing optional coordinates are allowed.

WhoScored's acting-team orientation is treated as confirmed only when:

- events for both home and away are stored without half/home-away flipping;
- for a team with at least three shots, the median shot `x` is at least 50;
- several representative live matches show both acting teams clustering
  toward `x=100`.

The median check is a drift detector, not a claim about shot quality. Matches
with fewer than three team shots are reported as unassessed and must be
combined with other representative matches before the orientation gate passes.

## Reconciliation rules

Reconcile against a single canonical payload version; never compare preliminary
events to a later final source summary.

- Raw `events` length must equal normalized rows plus explicitly rejected rows.
  Tolerance: **zero unaccounted events**.
- Recognized raw event-family counts must equal normalized event-family counts.
  Tolerance: **zero**.
- Raw `Goal`, shot-family, and `Pass` counts must reconcile exactly to their
  normalized attempts. Tolerance: **zero**. Do not compare pass events to a
  differently defined possession/pass percentage displayed in the UI.
- Home/away final score must equal non-own-goal/own-goal-adjusted event scoring
  after the normalizer implements those qualifiers. Tolerance: **zero**.
- Unknown event types and qualifier IDs remain in the private raw payload and
  are reported explicitly. They are never silently discarded or coerced to a
  known type.
- Missing player IDs do not fail match acquisition. They count toward identity
  coverage and the design's 1% warning / 5% publication-failure thresholds.
- A changed final checksum requires full match replacement and reconciliation;
  an unchanged checksum requires no event rewrite.

If the WhoScored UI and the cached match-centre object disagree, retain the
payload, record the UI observation and fetch time, and fail that match's pilot
gate rather than adding an unexplained percentage tolerance.

## PostgreSQL storage baseline

Capture the same measurements before and after event-table migrations/backfills:

```bash
backend/venv/bin/python backend/manage.py measure_database_storage \
  --output /tmp/statballer-storage-baseline.json
```

The command records `pg_database_size`, total/table/index bytes and estimated
live rows for every user relation. It intentionally fails on SQLite because
SQLite file size is not comparable to PostgreSQL relation/index measurements.

Environment-specific baseline captured 2026-07-27 before event tables were
added:

| Measure | Bytes |
| --- | ---: |
| PostgreSQL database (`statballer`) | 2,680,279,523 |
| User relations, total | 2,668,896,256 |
| User-relation indexes | 500,662,272 |
| User relation count | 40 |

Largest relations at capture time:

| Relation | Total bytes | Table bytes | Index bytes |
| --- | ---: | ---: | ---: |
| `ingestion_galaxysimilarity` | 1,658,699,776 | 1,446,649,856 | 211,615,744 |
| `ingestion_playerseasonderivedstats` | 298,508,288 | 225,525,760 | 72,900,608 |
| `ingestion_galaxyplayerembedding` | 179,732,480 | 149,667,840 | 28,573,696 |
| `ingestion_mergedplayerseason` | 139,984,896 | 85,524,480 | 54,403,072 |
| `ingestion_sofascoreplayerseasonsource` | 135,086,080 | 85,827,584 | 13,991,936 |

These values describe one local database and are not a production capacity
estimate. Store the complete JSON report with deployment/pilot operational
records rather than in the public repository.

## Foundation verification

Run:

```bash
STATBALLER_USE_SQLITE=1 backend/venv/bin/python backend/manage.py test \
  ingestion.tests.test_whoscored_client
```

The deterministic foundation is complete when these tests pass and a suitable
browser environment completes the three-match live probe with:

- three completed payloads read from the full cache objects;
- stable repeated SHA-256 values when the provider payload is unchanged;
- zero coordinate errors;
- both acting teams passing the shot-orientation check in enough
  representative matches;
- event counts reviewed against the cached source objects under the
  reconciliation rules above.
