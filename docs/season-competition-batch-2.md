# Season and competition batch 2 operations

This note is the checked-in operator record for the 2026-27 season manifest,
UEFA stage handling, and the lower-domestic additions. It is documentation
only: do not run a seed or backfill while reviewing this change.

## Verified manifest

The existing 20 domestic competitions receive an active, unpublished,
refresh-disabled `2026-27` slice. The provider season IDs and Understat
mappings for the four dual-provider competitions are:

| Code | SofaScore tournament/season | Understat |
| --- | --- | --- |
| ENG1 | 17 / 96668 | EPL / 2026 |
| ITA1 | 23 / 95836 | Serie_A / 2026 |
| SPA1 | 8 / 97268 | La_liga / 2026 |
| GER1 | 35 / 97464 | Bundesliga / 2026 |
| GER2 | 44 / 97406 | SofaScore only |
| GER3 | 491 / 98012 | SofaScore only |
| FRA1 | 34 / 96127 | Ligue_1 / 2026 |
| POR1 | 238 / 97436 | SofaScore only |
| NED1 | 37 / 96143 | SofaScore only |
| BEL1 | 38 / 96616 | SofaScore only |
| SCO1 | 36 / 96658 | SofaScore only |
| ENG2 | 18 / 97037 | SofaScore only |
| POL1 | 202 / 96144 | SofaScore only |
| CZE1 | 172 / 96966 | SofaScore only |
| DEN1 | 39 / 95785 | SofaScore only |
| GRE1 | 185 / 98659 | SofaScore only |
| CYP1 | 171 / 99321 | SofaScore only |
| TUR1 | 52 / 98080 | SofaScore only |
| EST1 | 178 / 89137 | SofaScore only; provider calendar 2026 (2025-26 is 71438) |
| NOR1 | 20 / 87809 | SofaScore only; provider calendar 2026 (2025-26 is 70174) |

The existing split-year labels are intentionally retained for EST1 and NOR1:
`2025-26` maps to each league's provider calendar/start year 2025
(Premium Liiga 71438, Eliteserien 70174), and `2026-27` maps to provider
calendar year 2026 (89137, 87809). The corrected 2025 IDs avoid duplicate
provider slices while preserving the established UI labels.
The 2026-27 expected team counts are the manifest defaults except BEL1=18,
CZE1=16, and CYP1=14; minimum merged counts are generally expected minus two.
Season-level fields carry these exceptions so historical slices are not
rewritten by a later seed.

UEFA competitions are SofaScore-only continental cups, with a 270-minute
eligibility threshold and no domestic aggregate membership:

| Code (tournament) | 2022-23 | 2023-24 | 2024-25 | 2025-26 | 2026-27 |
| --- | --- | --- | --- | --- | --- |
| UCL (7) | 41897 / 32 | 52162 / 32 | 61644 / 36 | 76953 / 36 | 96518 / 36 |
| UEL (679) | 44509 / 40 | 53654 / 40 | 61645 / 36 | 76984 / 36 | 96522 / 36 |
| UECL (17015) | 42224 / 40 | 52327 / 40 | 61648 / 36 | 76960 / 36 | 96529 / 36 |

Each cell is `SofaScore season ID / expected main-stage teams`; minimum merged
counts are two below expected (minimum one) and team-overall coverage is zero.

The new domestic aggregate members use the 450-minute threshold and
SofaScore-only mode:

| Code (tournament) | 2022-23 | 2023-24 | 2024-25 | 2025-26 | 2026-27 |
| --- | --- | --- | --- | --- | --- |
| BEL2 (9) | 42422 / 12 | 52384 / 16 | 61412 / 16 | 77849 / 17 | 96912 / 15 |
| FRA2 (182) | 42272 / 20 | 52572 / 21 | 61737 / 20 | 77357 / 20 | 96109 / 18 |
| FRA3 (183) | 42921 / 18 | 53055 / 18 | 64124 / 18 | 78599 / 18 | 97457 / 18 |
| SCO2 (206) | 41958 / 13 | 52606 / 13 | 62411 / 13 | 77037 / 13 | 96614 / 10 |

Allsvenskan (SWE1, tournament 40) uses calendar labels and IDs/counts:
`2022=40406/17`, `2023=47730/17`, `2024=57284/17`,
`2025=69956/17`, `2026=87925/16`.

## UEFA stage inclusion

SofaScore's `/season/{id}/teams` endpoint includes qualifier-only teams. For a
continental slice, team ingestion now intersects that response with
`provider_team_id` values already present in that slice's
`SofascorePlayerSeasonSource` aggregate. The player-stat aggregate therefore
defines group/league-phase membership (UCL 32/32/36/36/36; UEL and UECL
40/40/36/36/36). An empty allowed set is a hard, clearly reported failure;
qualifier teams are never ingested as a fallback. Domestic team ingestion is
unchanged.

## Known provider gaps

Correct SofaScore endpoints currently return zero summary/wide player-stat
pages for BEL2 2022-23 and FRA3 2022-23 and 2023-24. These slices remain
unpublished; do not invent alternate IDs or mark them publishable.

## Safe rollover and later backfill

`cutover_season_refresh` is read-only by default. It derives the current
refresh-enabled source set, validates a complete configured target set, checks
the ENG1 pilot's successful derived materialization, and only mutates flags
when `--apply` is supplied. It never changes publication defaults.

The following is the exact #34 procedure from the repository root. These are
later operator commands only; none of them were executed in this change.

1. Seed the manifest, then inspect the source and target IDs. Seeding does not
   perform rollover:

   ```bash
   backend/venv/bin/python backend/manage.py seed_competition_slices
   backend/venv/bin/python backend/manage.py shell -c "from ingestion.models import CompetitionSeason; print(list(CompetitionSeason.objects.filter(competition__short_code='ENG1', season__label__in=['2025-26','2026-27']).order_by('season__sort_order').values('id','competition__short_code','season__label','sofascore_unique_tournament_id','sofascore_season_id','is_published','refresh_enabled')))"
   ```

2. Wait until 2026-27 provider statistics have real coverage (new-season
   endpoints can be empty before a competition starts or before its league
   phase). Do not run the pilot backfill while coverage is empty:

   ```bash
   backend/venv/bin/python backend/manage.py backfill_history --skip-seed --stop-on-error --no-sleep --competitions ENG1 --seasons 2026-27 --output reports/batch-2-eng1-2026-27.json
   ```

3. Using the IDs printed in step 1, compare the pilot's team identities with
   its prior slice. Replace the angle-bracket placeholders with those integer
   IDs:

   ```bash
   backend/venv/bin/python backend/manage.py diagnose_season_rollover <TARGET_ENG1_2026_27_ID> --previous-competition-season-id <SOURCE_ENG1_2025_26_ID> --fail-on-anomaly
   backend/venv/bin/python backend/manage.py set_competition_season_publication <TARGET_ENG1_2026_27_ID> --publish
   ```

4. Run the read-only cutover preflight, then apply only after the pilot is
   intentionally published and ready. Both commands derive the source set
   from current `refresh_enabled` flags; #37/#39 slices remain disabled:

   ```bash
   backend/venv/bin/python backend/manage.py cutover_season_refresh --from-season 2025-26 --to-season 2026-27 --pilot-competition ENG1
   backend/venv/bin/python backend/manage.py cutover_season_refresh --from-season 2025-26 --to-season 2026-27 --pilot-competition ENG1 --apply
   ```

5. Verify the resulting daily-refresh plan without jitter:

   ```bash
   backend/venv/bin/python backend/manage.py orchestrate_daily_refresh --no-jitter
   ```

After this procedure, diagnose and publish additional slices individually.
Run these later, explicitly reported backfills only after coverage and the
pilot validation are complete:

```bash
backend/venv/bin/python backend/manage.py backfill_history \
  --skip-seed --stop-on-error \
  --competitions UCL,UEL,UECL \
  --seasons 2022-23,2023-24,2024-25,2025-26,2026-27 \
  --output reports/batch-2-uefa.json
```

```bash
backend/venv/bin/python backend/manage.py backfill_history \
  --skip-seed --stop-on-error \
  --competitions BEL2,FRA2,FRA3,SCO2 \
  --seasons 2022-23,2023-24,2024-25,2025-26,2026-27 \
  --output reports/batch-2-domestic-split-year.json
```

```bash
backend/venv/bin/python backend/manage.py backfill_history \
  --skip-seed --stop-on-error \
  --competitions SWE1 \
  --seasons 2022,2023,2024,2025,2026 \
  --output reports/batch-2-swe1-calendar.json
```

The commands above are intentionally not part of deployment or seeding; they
are an operator runbook for a later, validated backfill. The known blockers
remain exact: BEL2 2022-23 and FRA3 2022-23/2023-24 return zero correct
SofaScore summary/wide player-stat pages and must not be papered over.
