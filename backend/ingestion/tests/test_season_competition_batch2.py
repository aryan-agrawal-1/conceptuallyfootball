from __future__ import annotations

from django.core.management import call_command
from django.test import TestCase

from ingestion.competition_seed_manifest import COMPETITION_SEED_MANIFEST, _sort_order
from ingestion.models import (
    CanonicalPlayer,
    Competition,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
    PlayerSeasonDerivedStats,
    PositionGroup,
    Season,
)
from ingestion.services.season_refresh_cutover import (
    apply_season_refresh_cutover,
    plan_season_refresh_cutover,
)


class CompetitionSeedBatch2Tests(TestCase):
    def test_manifest_has_expected_classifications_and_calendar_labels(self):
        by_code = {config["code"]: config for config in COMPETITION_SEED_MANIFEST}
        self.assertEqual(len(by_code), 28)
        for config in COMPETITION_SEED_MANIFEST:
            provider_season_ids = [
                row["sofascore_season_id"]
                for row in config["seasons"]
                if row["sofascore_season_id"] is not None
            ]
            self.assertEqual(
                len(provider_season_ids),
                len(set(provider_season_ids)),
                config["code"],
            )
        self.assertEqual(_sort_order("2026-27"), 2027)
        self.assertEqual(_sort_order("2026"), 2026)
        self.assertEqual(_sort_order("2026-2027"), 2027)
        self.assertEqual(
            next(row for row in by_code["EST1"]["seasons"] if row["label"] == "2025-26")[
                "sofascore_season_id"
            ],
            71438,
        )
        self.assertEqual(
            next(row for row in by_code["EST1"]["seasons"] if row["label"] == "2026-27")[
                "sofascore_season_id"
            ],
            89137,
        )
        self.assertEqual(
            next(row for row in by_code["NOR1"]["seasons"] if row["label"] == "2025-26")[
                "sofascore_season_id"
            ],
            70174,
        )
        self.assertEqual(
            next(row for row in by_code["NOR1"]["seasons"] if row["label"] == "2026-27")[
                "sofascore_season_id"
            ],
            87809,
        )
        self.assertEqual(
            [row["label"] for row in by_code["SWE1"]["seasons"]],
            ["2022", "2023", "2024", "2025", "2026"],
        )
        self.assertEqual(by_code["SWE1"]["seasons"][-1]["sofascore_season_id"], 87925)
        self.assertEqual(by_code["UCL"]["competition_type"], "continental_cup")
        self.assertFalse(by_code["UCL"]["include_in_domestic_aggregates"])
        self.assertEqual(by_code["UCL"]["minimum_eligible_minutes"], 270)
        self.assertTrue(by_code["BEL2"]["include_in_domestic_aggregates"])

    def test_seed_is_idempotent_and_keeps_new_slices_unpublished_and_disabled(self):
        call_command("seed_competition_slices")
        call_command("seed_competition_slices")

        self.assertEqual(Competition.objects.count(), 28)
        for config in COMPETITION_SEED_MANIFEST:
            competition = Competition.objects.get(short_code=config["code"])
            for season_config in config["seasons"]:
                rows = CompetitionSeason.objects.filter(
                    competition=competition,
                    season__label=season_config["label"],
                )
                self.assertEqual(rows.count(), 1)
                row = rows.get()
                if season_config["label"] == "2026-27" or config["code"] in {
                    "UCL",
                    "UEL",
                    "UECL",
                    "BEL2",
                    "FRA2",
                    "FRA3",
                    "SCO2",
                }:
                    self.assertTrue(row.is_active)
                    self.assertFalse(row.is_published)
                    self.assertFalse(row.refresh_enabled)


class SeasonRefreshCutoverTests(TestCase):
    def setUp(self):
        self.season_from = Season.objects.create(label="2025-26", sort_order=2026)
        self.season_to = Season.objects.create(label="2026-27", sort_order=2027)
        self.sources = []
        self.targets = []
        for code in ("ENG1", "ITA1"):
            competition = Competition.objects.create(name=code, short_code=code, country="Test")
            source = CompetitionSeason.objects.create(
                competition=competition,
                season=self.season_from,
                refresh_enabled=True,
                sofascore_unique_tournament_id=17,
                sofascore_season_id=76986,
            )
            target = CompetitionSeason.objects.create(
                competition=competition,
                season=self.season_to,
                sofascore_unique_tournament_id=17,
                sofascore_season_id=96518,
            )
            self.sources.append(source)
            self.targets.append(target)

        run = IngestionRun.objects.create(
            kind=IngestionKind.DERIVED,
            competition_season=self.targets[0],
            status=IngestionRunStatus.SUCCESS,
        )
        player = CanonicalPlayer.objects.create(display_name="Pilot")
        PlayerSeasonDerivedStats.objects.create(
            competition_season=self.targets[0],
            canonical_player=player,
            derived_ingestion_run=run,
            position_group=PositionGroup.FWD,
            minutes=900,
            is_current=True,
        )

    def test_dry_run_does_not_mutate_refresh_flags(self):
        plan = plan_season_refresh_cutover()
        self.assertEqual(plan.source_competitions, ("ENG1", "ITA1"))
        self.assertFalse(plan.applied)
        self.assertTrue(CompetitionSeason.objects.filter(refresh_enabled=True).exists())
        self.assertTrue(all(not target.refresh_enabled for target in self.targets))

    def test_apply_selects_all_targets_and_disables_old_slices(self):
        plan = apply_season_refresh_cutover()
        self.assertTrue(plan.applied)
        self.assertEqual(
            set(
                CompetitionSeason.objects.filter(refresh_enabled=True).values_list(
                    "competition__short_code", flat=True
                )
            ),
            {"ENG1", "ITA1"},
        )
        self.assertFalse(CompetitionSeason.objects.filter(refresh_enabled=True, season=self.season_from).exists())

    def test_pilot_materialization_is_required(self):
        PlayerSeasonDerivedStats.objects.filter(competition_season=self.targets[0]).delete()
        with self.assertRaisesMessage(ValueError, "Pilot target ENG1 2026-27 is not ready"):
            plan_season_refresh_cutover()

    def test_mixed_source_seasons_fail_clearly(self):
        Season.objects.create(label="2024-25", sort_order=2025)
        self.sources[1].season = Season.objects.get(label="2024-25")
        self.sources[1].save(update_fields=["season"])
        with self.assertRaisesMessage(ValueError, "All refresh-enabled source slices"):
            plan_season_refresh_cutover()

    def test_same_source_and_target_seasons_are_rejected(self):
        with self.assertRaisesMessage(ValueError, "must be different seasons"):
            plan_season_refresh_cutover(from_season="2025-26", to_season="2025-26")

    def test_incomplete_target_set_fails_clearly(self):
        self.targets[1].delete()
        with self.assertRaisesMessage(ValueError, "ITA1 2026-27; found 0"):
            plan_season_refresh_cutover()
