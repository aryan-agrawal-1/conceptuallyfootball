# Player Response Role Operations

Player roles run after a successful event-profile publication. The event-profile
command invokes the bounded full/affected role path automatically; do not run a
second role command alongside it for the same competition-season.

```bash
cd backend
venv/bin/python manage.py materialize_event_profiles --competition ENG1 --season 2025-26
```

The production default is five matches per bounded batch. Values above five are
rejected. Keep league refreshes on the existing `ingestion` worker with
concurrency `1`; this is the default sequential six-league execution policy and
prevents raw evidence for two leagues occupying RAM together.

## Standalone modes

```bash
# Full feature rebuild followed by complete-cohort scoring.
venv/bin/python manage.py materialize_player_season_roles --competition ENG1 --season 2025-26

# Affected feature refresh followed by complete-cohort scoring. Supply both lists.
venv/bin/python manage.py materialize_player_season_roles --competition ENG1 --season 2025-26 \
  --affected-player-id 123 --affected-team-id 45

# Reuse current feature snapshots; read no raw event or possession evidence.
venv/bin/python manage.py materialize_player_season_roles --competition ENG1 --season 2025-26 \
  --score-only

# Refresh only indexed goal/intentional-assist evidence, then score the full cohort.
venv/bin/python manage.py materialize_player_season_roles --competition ENG1 --season 2025-26 \
  --score-events-only
```

## Diagnostics and exclusion

Every attempt persists an `IngestionRun` with kind `player_roles`. Its `stats`
contain requested and resolved mode, affected/cohort counts, match batch size,
stage timings, rows processed by category, query count, RSS samples and peak RSS.
Inspect the latest attempt with:

```bash
venv/bin/python manage.py shell -c 'from ingestion.models import IngestionRun; r=IngestionRun.objects.filter(kind="player_roles").first(); print(r.id, r.status, r.error_detail, r.stats)'
```

The PostgreSQL advisory lock rejects overlapping role jobs for the same
competition-season. Different leagues still run one at a time on the
single-concurrency ingestion worker. A rejected or failed run is recorded and
the lock is released automatically.

## Retry and recovery

1. Inspect the failed run and leave the current feature/role rows in place.
2. If failure happened before feature publication, repeat the same full or
   affected command.
3. If `feature_publication` completed but cohort scoring/publication failed,
   run `--score-only`; it republishes the complete cohort from the current
   durable feature snapshots without rereading raw evidence.
4. If score-event correction failed, repeat `--score-events-only`.
5. Confirm the retry is `success`, `published_roles == cohort_snapshots`, and
   the API checks below show one miss followed by one hit.

Verification commands used for the failure/retry and API cache contract:

```bash
venv/bin/python manage.py test \
  ingestion.tests.test_player_role_orchestration \
  ingestion.tests.test_player_role_api_cache \
  ingestion.tests.test_player_state_comparison.PlayerStateComparisonTests.test_state_lens_cache_tracks_current_role_model_version \
  --keepdb
```

## Consumer contract

The outfield and goalkeeper detail payloads continue to embed `season_role` and
`season_roles`. State Lens continues to embed `season_role`; all three cache
keys include the current `PlayerSeasonRole` model version. Publication therefore
causes a cache miss containing the new scoring version, then ordinary payload
cache hits. The frontend `PlayerProfile` continues to render the embedded role
directly and makes no role-specific request.
