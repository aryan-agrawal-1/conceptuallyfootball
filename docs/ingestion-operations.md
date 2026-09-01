# Ingestion operations

Run commands from the repository root. Replace competition-season IDs and
competition/season labels with the intended concrete scope. Never use `ALL` or
`BIG5` for provider acquisition.

## Historical backfills

Start with the existing SofaScore/Understat chain for one bounded slice:

```bash
backend/venv/bin/python backend/manage.py backfill_history \
  --competitions GER1 \
  --seasons 2025-26
```

Then acquire WhoScored. The command is resumable: final payloads are reused,
and each match commits independently. A complete season exceeds the default
50-match safety cap and therefore requires the explicit override.

```bash
backend/venv/bin/python backend/manage.py ingest_whoscored_events \
  --competition GER1 \
  --season 2025-26 \
  --allow-over-cap
```

Use `--dry-run` before a live rerun. Prefer `--last-completed`, `--match-id`, or
`--from-date` with `--to-date` for bounded repairs. `--force` deliberately
refetches the selected match details; do not use it for an ordinary resume.

After acquisition and identity reconciliation, publish event profiles and
player roles together:

```bash
backend/venv/bin/python backend/manage.py materialize_event_profiles \
  --competition GER1 \
  --season 2025-26
```

For a corrected match, pass its provider match ID. This command deliberately
uses a full deterministic entity scope because the current event set cannot
identify entities removed by a correction; scheduled lifecycle processing
uses the stored old-union-new entity IDs for a narrow rebuild.

```bash
backend/venv/bin/python backend/manage.py materialize_event_profiles \
  --competition GER1 \
  --season 2025-26 \
  --affected-match-id 1908319
```

## Daily maintenance

The daily planner covers SofaScore, SofaScore teams, Understat where supported,
team/player merges, position resolution, derived statistics, Galaxy products,
and cache invalidation. It checks every 15 minutes and chooses one randomized
start inside the configured 01:00–07:00 Europe/London window.

```bash
backend/venv/bin/python backend/manage.py orchestrate_daily_refresh
backend/venv/bin/python backend/manage.py orchestrate_daily_refresh \
  --enqueue --competition GER1
backend/venv/bin/python backend/manage.py orchestrate_daily_refresh \
  --requeue-item <item-id>
```

Automatic execution requires `STATBALLER_DAILY_REFRESH_ENABLED=1`.

## Weekly WhoScored maintenance

Automatic WhoScored work is disabled unless
`STATBALLER_WHOSCORED_WEEKLY_ENABLED=1`. Beat plans it at 07:30 Europe/London
every Tuesday. A 15-minute lightweight scan separately enqueues preliminary
payloads once their 12-hour settlement delay is due.

The rolling selector fetches only:

- completed matches at least three hours after kickoff with no payload in the
  previous 28 days;
- every due preliminary payload;
- final matches kicked off in the previous 14 days, once per weekly workflow.

Older final matches are schedule metadata only. The per-league cap defaults to
50 selected details. Change the window or cap only after reviewing provider
load and the resulting backlog.

Inspect the plan, enqueue a manual league, scan settlements, inspect leases, or
requeue a failed item:

```bash
backend/venv/bin/python backend/manage.py orchestrate_whoscored_refresh
backend/venv/bin/python backend/manage.py orchestrate_whoscored_refresh \
  --enqueue --competition GER1 --force
backend/venv/bin/python backend/manage.py orchestrate_whoscored_refresh \
  --settlements --force
backend/venv/bin/python backend/manage.py orchestrate_whoscored_refresh \
  --leases
backend/venv/bin/python backend/manage.py orchestrate_whoscored_refresh \
  --requeue-item <item-id> --force
```

`--force` on this orchestration command bypasses only the scheduler kill switch;
it does not force-refetch every match. Match selection remains bounded.

## Celery processes

Run one worker for each queue:

```bash
cd backend
venv/bin/celery -A backend worker -Q ingestion-planner -c 1 \
  -l INFO -n planner@%h --prefetch-multiplier=1 --max-tasks-per-child=100
venv/bin/celery -A backend worker -Q ingestion -c 1 \
  -l INFO -n ingestion@%h --prefetch-multiplier=1 --max-tasks-per-child=1
venv/bin/celery -A backend worker -Q whoscored -c 1 \
  -l INFO -n whoscored@%h --prefetch-multiplier=1 --max-tasks-per-child=1 \
  --max-memory-per-child=1200000
venv/bin/celery -A backend beat -l INFO
```

The daily and WhoScored queues share an expiring `heavy-maintenance` database
lease, so their provider/materialization work cannot overlap. WhoScored also
uses one lease per competition-season and one queued-settlement lease. A live
lease must never be deleted to bypass contention. Expired leases are reclaimed
automatically by the next task.

The representative Bundesliga measurements were approximately 129 MB peak RSS
for a production-paced SofaScore player refresh, 286 MB for WhoScored
acquisition, 542 MB for an affected role refresh, and 875 MB for a clean full
season event-profile build. The direct SofaScore-plus-WhoScored process-RSS
projection is therefore about 416 MB during acquisition, 671 MB during affected
roles, or 1.0 GB during a full profile build, before PostgreSQL, Redis, web,
Chrome child processes, and operating-system headroom. Serialization is
mandatory; these figures are capacity guidance, not permission to overlap.

Inspect `Ingestion batches`, `Ingestion batch items`, `Ingestion runs`, and
`Ingestion leases` in Django admin. A failed weekly item can be requeued after
the cause is corrected. Successfully committed matches and correction checks
from the original workflow are reused on retry.

## Relevant settings

```text
STATBALLER_DAILY_REFRESH_ENABLED=0
STATBALLER_WHOSCORED_WEEKLY_ENABLED=0
STATBALLER_WHOSCORED_COMPLETION_GRACE_HOURS=3
STATBALLER_WHOSCORED_SETTLEMENT_DELAY_HOURS=12
STATBALLER_WHOSCORED_CORRECTION_WINDOW_DAYS=14
STATBALLER_WHOSCORED_RECOVERY_WINDOW_DAYS=28
STATBALLER_WHOSCORED_MAX_MATCHES_PER_RUN=50
STATBALLER_INGESTION_LEASE_TTL_SECONDS=9000
```

Keep both automatic feature flags off during initial deployment. Run a source
probe, one bounded manual league update, a due-settlement check, and API smoke
checks before enabling the Tuesday schedule.
