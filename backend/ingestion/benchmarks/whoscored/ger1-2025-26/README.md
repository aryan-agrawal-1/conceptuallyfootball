# GER1 2025-26 unoptimized baseline

This directory freezes the Batch 12 pre-optimization corpus and measurements.
Reports contain aggregate diagnostics and hashes only; raw WhoScored payloads
remain in private backend storage.

- `source-probe.json`: production-equivalent three-match source/orientation probe.
- `pre-backfill-inventory.json`: PostgreSQL and zero-scope inventory before ingestion.
- `unoptimized-10-match-smoke.json`: first successful live smoke run.
- `unoptimized-50-match-baseline.json`: frozen 50-match inventory, cached parse,
  acquisition/derivation/profile/role timings, peak RSS, and output digests.

The 50-match corpus is identified by the aggregate stored-payload digest
`aaca1f8da5333d9afaf1251d6d9e473db0c15349d3f0cd170e638902f2cdb05d`.
Future optimization comparisons must use these same 50 final payload checksums
and match the four materialized-output digests in the baseline report.

The final database size is not a clean per-50-match storage delta because the
profile and role stages were deliberately repeated to isolate their memory
high-water marks, retaining superseded version rows. Scope row counts, payload
bytes, current-output counts, and relation sizes remain recorded separately.

