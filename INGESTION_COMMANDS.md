# Statballer ingestion — commands and data sources

This file lists the exact commands to run the pipeline end-to-end: PostgreSQL, Redis, Celery, Django, reep (CSV or JSON), Understat, Sofascore, merge, and the internal merged API.

Paths assume the repo root is `statballer/` and the Django project lives in `backend/`.

---

## 1. Prerequisites (manual install, no Docker)

Install and start **PostgreSQL** and **Redis** locally (Homebrew example):

```bash
brew install postgresql@16 redis
brew services start postgresql@16
brew services start redis
```

Create the database and role (names must match `backend/backend/settings.py` defaults or your env overrides):

```bash
createuser statballer -s || true
createdb statballer -O statballer || true
psql -d postgres -c "ALTER USER statballer PASSWORD 'statballer';" || true
```

---

## 2. Python environment and Django

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Environment file (example `.env` in `backend/` or export in shell):

```bash
export DJANGO_DEBUG=1
export STATBALLER_DB_NAME=statballer
export STATBALLER_DB_USER=statballer
export STATBALLER_DB_PASSWORD=statballer
export STATBALLER_DB_HOST=127.0.0.1
export STATBALLER_DB_PORT=5432
export CELERY_BROKER_URL='redis://127.0.0.1:6379/0'
export CELERY_RESULT_BACKEND='redis://127.0.0.1:6379/0'
export STATBALLER_HTTP_USER_AGENT='Mozilla/5.0 (compatible; StatballerIngestion/1.0)'
# Sofascore often blocks bare bots — use a real browser UA string in production.

# reep: prefer official CSV dump directory (clone reep repo or copy data/)
export STATBALLER_REEP_CSV_DIR="$HOME/src/reep/data"

# Optional legacy JSON subset instead of CSV:
# export STATBALLER_REEP_DATA_PATH="$HOME/src/statballer-reep-subset.json"

# Optional: lower minimum row count for dev slices (default 200)
# export STATBALLER_INGEST_MIN_ROWS=200

# Optional: provider/batch pacing for large Sofascore refreshes.
# Defaults are intentionally conservative to reduce IP challenge/block risk.
# Per-request delay between Sofascore API pages / team-stat requests.
# export STATBALLER_SOFASCORE_REQUEST_DELAY_SECONDS=1.5
# Base sleep for transient Sofascore 403/429/5xx retries; actual backoff is 1x, 2x, 3x.
# export STATBALLER_SOFASCORE_RETRY_BASE_SLEEP_SECONDS=8.0
# Sleep between competition-season slices in batch runners.
# export STATBALLER_BATCH_SLICE_SLEEP_SECONDS=20.0
# Longer sleep when a batch runner moves from one league to the next.
# export STATBALLER_BATCH_LEAGUE_SLEEP_SECONDS=120.0

# Live Sofascore season for Premier League / ENG1
export SOFASCORE_PL_UNIQUE_TOURNAMENT_ID=17
export SOFASCORE_PL_SEASON_ID=76986

# Understat league segment (EPL) and season year segment used in /league/EPL/{year}
export UNDERSTAT_PL_SEASON_YEAR=2025
```

Run migrations and create an admin user:

```bash
cd backend
source venv/bin/activate
unset STATBALLER_USE_SQLITE
python manage.py migrate
python manage.py createsuperuser
```

---

## 3. Seed competition seasons from the manifest

```bash
cd backend
source venv/bin/activate
python manage.py seed_competition_slices
```

This upserts the checked-in league manifest, including `ENG1`, `ITA1`, `SPA1`, `GER1`,
`FRA1`, `POR1`, `NED1`, `BEL1`, `SCO1`, and `ENG2` across their configured seasons.
You can still edit **Competition season** in Django admin if provider IDs change, then
re-run the command to resync from version-controlled config.

---

## 4. reep identity sync (CSV — recommended)

Official register: [withqwerty/reep](https://github.com/withqwerty/reep). Published files are `**data/people.csv`** and `**data/teams.csv`** (not JSON).

**What reep can match for this product**


| Entity                     | Understat                                                                          | Sofascore                                                                              | Notes                                                                                   |
| -------------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **Players**                | `people.csv` → `key_understat`                                                     | `people.csv` → `key_sofascore`                                                         | Same row shares one `reep_id`. Coverage is incomplete: many rows omit one or both keys. |
| **Teams**                  | Often **missing** in published `teams.csv` (no `key_understat` in upstream schema) | `teams.csv` → `key_sofascore`                                                          | Expect **quarantined Understat teams** unless you add custom mappings or extend CSV.    |
| **Competitions / seasons** | Not used for player ID in this pipeline                                            | Tournament/season IDs are configured in `CompetitionSeason`, not from reep player CSV. |                                                                                         |


Clone or unpack CSVs, then:

```bash
cd backend
source venv/bin/activate
python manage.py sync_reep --csv-dir "$STATBALLER_REEP_CSV_DIR"
```

JSON subset (legacy helper format) still works:

```bash
python manage.py sync_reep --path /path/to/subset.json
```

---

## 5. Celery worker (optional but intended architecture)

Terminal A — Redis already running.

```bash
cd backend
source venv/bin/activate
celery -A backend worker -l info
```

Terminal B — invoke tasks (examples):

```bash
cd backend
source venv/bin/activate
python manage.py shell -c "from ingestion.tasks import task_sync_reep; print(task_sync_reep())"
python manage.py shell -c "from ingestion.tasks import task_ingest_understat; print(task_ingest_understat(<CS_ID>))"
```

---

## 6. Provider ingest + merge (management commands)

Replace `<CS_ID>` with your `CompetitionSeason` primary key.

```bash
cd backend
source venv/bin/activate

python manage.py ingest_understat <CS_ID>
python manage.py ingest_sofascore <CS_ID>
python manage.py run_merge <CS_ID>
```

After fixing unmatched identities in **Django admin**:

```bash
python manage.py reprocess_slice_identities <CS_ID>
python manage.py run_merge <CS_ID>
```

---

## 7. Internal merged API (read-only, no auth in Phase 1)

With `runserver`:

```bash
cd backend
source venv/bin/activate
python manage.py runserver 8000
```

Examples:

```bash
curl -sS 'http://127.0.0.1:8000/internal/api/merged-player-seasons/?competition=ENG1&season=2025-26' | head
curl -sS 'http://127.0.0.1:8000/internal/api/merged-player-seasons/1/'
```

---

## 8. Sofascore API — verified response shape (reference)

Live samples were taken from:

`GET https://www.sofascore.com/api/v1/unique-tournament/17/season/61627/statistics`

with query params: `limit`, `offset`, `order=-rating`, `accumulation=total`, `group=<group>`.

Each `results[]` element includes nested `player` and `team` plus flat camelCase metrics. Stored verbatim (minus `player`/`team`) on `SofascorePlayerSeasonSource.group_stats` per group.


| `group`      | Example metric keys on the row                                                                                         |
| ------------ | ---------------------------------------------------------------------------------------------------------------------- |
| `summary`    | `goals`, `expectedGoals`, `successfulDribbles`, `tackles`, `assists`, `accuratePassesPercentage`, `rating`             |
| `defence`    | `tackles`, `interceptions`, `clearances`, `errorLeadToGoal`, `outfielderBlocks`, `rating`                              |
| `passing`    | `bigChancesCreated`, `assists`, `accuratePasses`, `accuratePassesPercentage`, `keyPasses`, `rating`                    |
| `goalkeeper` | `saves`, `cleanSheet`, `penaltySave`, `savedShotsFromInsideTheBox`, `runsOut`, `rating`                                |
| `attack`     | `goals`, `expectedGoals`, `bigChancesMissed`, `successfulDribbles`, `totalShots`, `goalConversionPercentage`, `rating` |


**Note:** On the sampled season, `summary` did **not** include `minutesPlayed` / `appearances`; the importer still reads those keys when present. **Attack** stats are stored in `group_stats` only — merged attacking numbers stay **Understat-owned** per product rules.

HTTP client headers (already in code): `User-Agent`, `Accept`, `Referer`, `Origin` pointing at `https://www.sofascore.com/`.

---

## 9. Tests (SQLite in-memory)

```bash
cd backend
source venv/bin/activate
export STATBALLER_USE_SQLITE=1
python manage.py test ingestion.tests -v 2
```
