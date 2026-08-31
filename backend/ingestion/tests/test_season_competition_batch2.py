from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from ingestion.competition_seed_manifest import COMPETITION_SEED_MANIFEST, _sort_order
from ingestion.competition_scope import resolve_public_scope
from ingestion.models import (
    CanonicalPlayer,
    Competition,
    CompetitionSeason,
    GalaxySnapshot,
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
from ingestion.services.season_refresh_activation import (
    apply_season_refresh_activation,
    plan_season_refresh_activation,
)


class CompetitionSeedBatch2Tests(TestCase):
    def test_manifest_has_expected_classifications_and_calendar_labels(self):
        by_code = {config["code"]: config for config in COMPETITION_SEED_MANIFEST}
        self.assertEqual(len(by_code), 28)
        unavailable = {
            ("BEL2", "2022-23", 42422),
            ("FRA3", "2022-23", 42921),
            ("FRA3", "2023-24", 53055),
        }
        for code, label, provider_season_id in unavailable:
            self.assertFalse(
                any(
                    row["label"] == label and row["sofascore_season_id"] == provider_season_id
                    for row in by_code[code]["seasons"]
                )
            )
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
            [row["label"] for row in by_code["EST1"]["seasons"]],
            ["2021", "2022", "2023", "2024", "2025", "2026"],
        )
        self.assertEqual(
            [row["sofascore_season_id"] for row in by_code["EST1"]["seasons"]],
            [35341, 40593, 48281, 57905, 71438, 89137],
        )
        self.assertEqual(
            [row["legacy_label_alias"] for row in by_code["EST1"]["seasons"]],
            ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26", "2026-27"],
        )
        self.assertEqual(
            [row["label"] for row in by_code["NOR1"]["seasons"]],
            ["2021", "2022", "2023", "2024", "2025", "2026"],
        )
        self.assertEqual(
            [row["sofascore_season_id"] for row in by_code["NOR1"]["seasons"]],
            [35403, 40405, 47806, 57322, 70174, 87809],
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
        bundesliga = next(
            row for row in by_code["GER1"]["seasons"] if row["label"] == "2025-26"
        )
        self.assertEqual(
            {
                "has_whoscored": bundesliga["has_whoscored"],
                "league": bundesliga["whoscored_league"],
                "season": bundesliga["whoscored_season"],
                "expected": bundesliga["whoscored_expected_match_count"],
            },
            {
                "has_whoscored": True,
                "league": "GER-Bundesliga",
                "season": "2025-26",
                "expected": 306,
            },
        )

    def test_seed_is_idempotent_and_keeps_new_slices_unpublished_and_disabled(self):
        call_command("seed_competition_slices")
        call_command("seed_competition_slices")

        self.assertEqual(Competition.objects.count(), 28)
        expected_slice_count = sum(len(config["seasons"]) for config in COMPETITION_SEED_MANIFEST)
        self.assertEqual(CompetitionSeason.objects.count(), expected_slice_count)
        for code, label, provider_season_id in (
            ("BEL2", "2022-23", 42422),
            ("FRA3", "2022-23", 42921),
            ("FRA3", "2023-24", 53055),
        ):
            self.assertFalse(
                CompetitionSeason.objects.filter(
                    competition__short_code=code,
                    season__label=label,
                ).exists()
            )
            self.assertFalse(
                CompetitionSeason.objects.filter(sofascore_season_id=provider_season_id).exists()
            )
        for config in COMPETITION_SEED_MANIFEST:
            competition = Competition.objects.get(short_code=config["code"])
            for season_config in config["seasons"]:
                rows = CompetitionSeason.objects.filter(
                    competition=competition,
                    season__label=season_config["label"],
                )
                self.assertEqual(rows.count(), 1)
                row = rows.get()
                if config["code"] == "GER1" and season_config["label"] == "2025-26":
                    self.assertTrue(row.supports_whoscored)
                    self.assertEqual(row.whoscored_expected_match_count, 306)
                if season_config["label"] == "2026-27" or (
                    config["code"] in {"EST1", "NOR1"} and season_config["label"] == "2026"
                ) or config["code"] in {
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

    def test_seed_applies_and_repairs_season_threshold_overrides(self):
        call_command("seed_competition_slices")

        competition = Competition.objects.get(short_code="UCL")
        competition_config = next(
            config for config in COMPETITION_SEED_MANIFEST if config["code"] == "UCL"
        )
        self.assertEqual(competition_config["expected_team_count"], 36)
        self.assertEqual(competition_config["min_merged_team_count"], 34)
        slice_obj = CompetitionSeason.objects.get(
            competition=competition,
            season__label="2022-23",
        )
        self.assertEqual(slice_obj.expected_team_count, 32)
        self.assertEqual(slice_obj.min_merged_team_count, 30)
        self.assertEqual(slice_obj.min_team_stats_coverage_count, 0)

        CompetitionSeason.objects.filter(pk=slice_obj.pk).update(
            expected_team_count=36,
            min_merged_team_count=34,
            min_team_stats_coverage_count=18,
        )
        call_command("seed_competition_slices")

        slice_obj.refresh_from_db()
        self.assertEqual(slice_obj.expected_team_count, 32)
        self.assertEqual(slice_obj.min_merged_team_count, 30)
        self.assertEqual(slice_obj.min_team_stats_coverage_count, 0)

    def test_seed_preserves_unpinned_historical_thresholds(self):
        call_command("seed_competition_slices")

        slice_obj = CompetitionSeason.objects.get(
            competition__short_code="ENG1",
            season__label="2021-22",
        )
        CompetitionSeason.objects.filter(pk=slice_obj.pk).update(
            expected_team_count=19,
            min_merged_team_count=17,
            min_team_stats_coverage_count=16,
        )
        call_command("seed_competition_slices")

        slice_obj.refresh_from_db()
        self.assertEqual(slice_obj.expected_team_count, 19)
        self.assertEqual(slice_obj.min_merged_team_count, 17)
        self.assertEqual(slice_obj.min_team_stats_coverage_count, 16)


class CalendarLabelReconciliationTests(TestCase):
    def setUp(self):
        self.config = deepcopy(next(config for config in COMPETITION_SEED_MANIFEST if config["code"] == "EST1"))
        self.competition = Competition.objects.create(
            name="Premium Liiga",
            short_code="EST1",
            country="Estonia",
        )

    def _seed_only_calendar_manifest(self):
        return patch(
            "ingestion.management.commands.seed_competition_slices.COMPETITION_SEED_MANIFEST",
            [self.config],
        )

    def test_relabel_preserves_pk_related_rows_publication_and_is_idempotent(self):
        legacy_season = Season.objects.create(label="2025-26", sort_order=2026)
        legacy_slice = CompetitionSeason.objects.create(
            competition=self.competition,
            season=legacy_season,
            is_published=True,
            refresh_enabled=True,
            sofascore_unique_tournament_id=178,
            sofascore_season_id=71438,
        )
        related_run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE,
            competition_season=legacy_slice,
            status=IngestionRunStatus.SUCCESS,
        )
        galaxy_snapshot = GalaxySnapshot.objects.create(
            scope_code="EST1",
            season_label="2025-26",
        )

        with self._seed_only_calendar_manifest():
            call_command("seed_competition_slices")

        legacy_slice.refresh_from_db()
        self.assertEqual(legacy_slice.season.label, "2025")
        self.assertEqual(legacy_slice.pk, related_run.competition_season_id)
        self.assertTrue(legacy_slice.is_published)
        self.assertTrue(legacy_slice.refresh_enabled)
        galaxy_snapshot.refresh_from_db()
        self.assertEqual(galaxy_snapshot.season_label, "2025")
        self.assertEqual(CompetitionSeason.objects.filter(competition=self.competition).count(), 6)

        with self._seed_only_calendar_manifest():
            call_command("seed_competition_slices")
        self.assertEqual(CompetitionSeason.objects.filter(competition=self.competition).count(), 6)
        self.assertEqual(CompetitionSeason.objects.get(pk=legacy_slice.pk).season.label, "2025")

    def test_alias_and_canonical_collision_rolls_back_atomically(self):
        legacy_season = Season.objects.create(label="2025-26", sort_order=2026)
        canonical_season = Season.objects.create(label="2025", sort_order=2025)
        legacy_slice = CompetitionSeason.objects.create(
            competition=self.competition,
            season=legacy_season,
            sofascore_unique_tournament_id=178,
            sofascore_season_id=71438,
        )
        canonical_slice = CompetitionSeason.objects.create(
            competition=self.competition,
            season=canonical_season,
            sofascore_unique_tournament_id=178,
            sofascore_season_id=71438,
        )
        with self._seed_only_calendar_manifest():
            with self.assertRaisesMessage(ValueError, "both legacy and canonical slices exist"):
                call_command("seed_competition_slices")

        self.assertEqual(CompetitionSeason.objects.filter(competition=self.competition).count(), 2)
        self.assertEqual(CompetitionSeason.objects.get(pk=legacy_slice.pk).season_id, legacy_season.id)
        self.assertEqual(CompetitionSeason.objects.get(pk=canonical_slice.pk).season_id, canonical_season.id)
        self.assertFalse(Season.objects.filter(label="2021").exists())

    def test_galaxy_current_snapshot_collision_rolls_back_slice_relabel(self):
        legacy_season = Season.objects.create(label="2025-26", sort_order=2026)
        legacy_slice = CompetitionSeason.objects.create(
            competition=self.competition,
            season=legacy_season,
            sofascore_unique_tournament_id=178,
            sofascore_season_id=71438,
        )
        GalaxySnapshot.objects.create(
            scope_code="EST1",
            season_label="2025-26",
        )
        GalaxySnapshot.objects.create(
            scope_code="EST1",
            season_label="2025",
        )

        with self._seed_only_calendar_manifest():
            with self.assertRaisesMessage(ValueError, "both labels have a current snapshot"):
                call_command("seed_competition_slices")

        legacy_slice.refresh_from_db()
        self.assertEqual(legacy_slice.season_id, legacy_season.id)
        self.assertEqual(
            set(GalaxySnapshot.objects.values_list("season_label", flat=True)),
            {"2025", "2025-26"},
        )

    def test_individual_legacy_lookup_resolves_before_and_after_reconciliation(self):
        canonical_season = Season.objects.create(label="2025", sort_order=2025)
        canonical_slice = CompetitionSeason.objects.create(
            competition=self.competition,
            season=canonical_season,
            is_published=True,
        )
        self.assertEqual(resolve_public_scope("EST1", "2025-26")[0].id, canonical_slice.id)
        self.assertEqual(resolve_public_scope("ALL", "2025-26")[0].id, canonical_slice.id)

        canonical_slice.delete()
        legacy_season = Season.objects.create(label="2025-26", sort_order=2026)
        legacy_slice = CompetitionSeason.objects.create(
            competition=self.competition,
            season=legacy_season,
            is_published=True,
        )
        self.assertEqual(resolve_public_scope("EST1", "2025")[0].id, legacy_slice.id)

    def test_catalog_exposes_canonical_label_and_alias(self):
        canonical_season = Season.objects.create(label="2025", sort_order=2025)
        CompetitionSeason.objects.create(
            competition=self.competition,
            season=canonical_season,
            is_published=True,
        )
        response = APIClient().get("/api/v1/competition-seasons")
        self.assertEqual(response.status_code, 200)
        entry = next(item for item in response.json()["competitions"] if item["code"] == "EST1")
        option = next(item for item in entry["seasons"] if item["label"] == "2025")
        self.assertIn("2025-26", option["aliases"])


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
                is_published=True,
                refresh_enabled=True,
                sofascore_unique_tournament_id=17,
                sofascore_season_id=76986,
            )
            target = CompetitionSeason.objects.create(
                competition=competition,
                season=self.season_to,
                is_published=True,
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

    def test_apply_mixed_cutover_preserves_other_enabled_label(self):
        Season.objects.create(label="2024-25", sort_order=2025)
        preserved = self.sources[1]
        preserved.season = Season.objects.get(label="2024-25")
        preserved.save(update_fields=["season"])
        plan = apply_season_refresh_cutover()
        self.assertEqual(plan.source_competitions, ("ENG1",))
        self.assertEqual(plan.preserved_competitions, ("ITA1",))
        enabled = set(CompetitionSeason.objects.filter(refresh_enabled=True).values_list("pk", flat=True))
        self.assertEqual(enabled, {self.targets[0].id, preserved.id})

    def test_cutover_rolls_back_when_resulting_selection_mismatches(self):
        with patch(
            "ingestion.services.season_refresh_cutover.validate_refresh_selection",
            side_effect=ValueError("forced resulting-selection failure"),
        ):
            with self.assertRaisesMessage(ValueError, "forced resulting-selection failure"):
                apply_season_refresh_cutover()
        self.assertTrue(all(source.refresh_enabled for source in self.sources))
        self.assertTrue(all(not target.refresh_enabled for target in self.targets))

    def test_pilot_materialization_is_required(self):
        PlayerSeasonDerivedStats.objects.filter(competition_season=self.targets[0]).delete()
        with self.assertRaisesMessage(ValueError, "Pilot target ENG1 2026-27 is not ready"):
            plan_season_refresh_cutover()

    def test_preflight_rejects_unpublished_non_pilot_target(self):
        self.targets[1].is_published = False
        self.targets[1].save(update_fields=["is_published"])
        with self.assertRaisesMessage(ValueError, "ITA1 2026-27 is selected for refresh but unpublished"):
            plan_season_refresh_cutover()

    def test_mixed_source_seasons_preserve_other_labels(self):
        Season.objects.create(label="2024-25", sort_order=2025)
        self.sources[1].season = Season.objects.get(label="2024-25")
        self.sources[1].save(update_fields=["season"])
        plan = plan_season_refresh_cutover()
        self.assertEqual(plan.source_competitions, ("ENG1",))
        self.assertEqual(plan.preserved_competitions, ("ITA1",))
        self.assertEqual(plan.preserved_season_labels, ("2024-25",))

    def test_same_source_and_target_seasons_are_rejected(self):
        with self.assertRaisesMessage(ValueError, "must be different seasons"):
            plan_season_refresh_cutover(from_season="2025-26", to_season="2025-26")

    def test_incomplete_target_set_fails_clearly(self):
        self.targets[1].delete()
        with self.assertRaisesMessage(ValueError, "ITA1 2026-27; found 0"):
            plan_season_refresh_cutover()


class SeasonRefreshActivationTests(TestCase):
    def setUp(self):
        self.season_old = Season.objects.create(label="2025", sort_order=2025)
        self.season_new = Season.objects.create(label="2026", sort_order=2026)
        competition = Competition.objects.create(name="Allsvenskan", short_code="SWE1", country="Sweden")
        self.old_slice = CompetitionSeason.objects.create(
            competition=competition,
            season=self.season_old,
            is_published=True,
            refresh_enabled=True,
            sofascore_unique_tournament_id=40,
            sofascore_season_id=69956,
        )
        self.new_slice = CompetitionSeason.objects.create(
            competition=competition,
            season=self.season_new,
            is_published=True,
            sofascore_unique_tournament_id=40,
            sofascore_season_id=87925,
        )
        other_competition = Competition.objects.create(name="Premier League", short_code="ENG1")
        self.other_slice = CompetitionSeason.objects.create(
            competition=other_competition,
            season=self.season_old,
            is_published=True,
            refresh_enabled=True,
            sofascore_unique_tournament_id=17,
            sofascore_season_id=76986,
        )
        run = IngestionRun.objects.create(
            kind=IngestionKind.DERIVED,
            competition_season=self.new_slice,
            status=IngestionRunStatus.SUCCESS,
        )
        PlayerSeasonDerivedStats.objects.create(
            competition_season=self.new_slice,
            canonical_player=CanonicalPlayer.objects.create(display_name="SWE Pilot"),
            derived_ingestion_run=run,
            position_group=PositionGroup.FWD,
            minutes=900,
            is_current=True,
        )

    def test_activation_dry_run_preserves_refresh_flags(self):
        plan = plan_season_refresh_activation("SWE1", "2026")
        self.assertFalse(plan.applied)
        self.assertEqual(plan.disabled_ids, (self.old_slice.id,))
        self.assertTrue(self.old_slice.refresh_enabled)
        self.assertFalse(self.new_slice.refresh_enabled)

    def test_activation_apply_replaces_same_competition_and_preserves_others(self):
        plan = apply_season_refresh_activation("SWE1", "2026")
        self.assertTrue(plan.applied)
        self.old_slice.refresh_from_db()
        self.new_slice.refresh_from_db()
        self.assertFalse(self.old_slice.refresh_enabled)
        self.assertTrue(self.new_slice.refresh_enabled)
        self.assertTrue(self.other_slice.refresh_enabled)

    def test_activation_requires_published_ready_target(self):
        PlayerSeasonDerivedStats.objects.filter(competition_season=self.new_slice).delete()
        with self.assertRaisesMessage(ValueError, "is not ready"):
            plan_season_refresh_activation("SWE1", "2026")

    def test_activation_rolls_back_on_resulting_selection_failure(self):
        with patch(
            "ingestion.services.season_refresh_activation.validate_refresh_selection",
            side_effect=ValueError("forced activation failure"),
        ):
            with self.assertRaisesMessage(ValueError, "forced activation failure"):
                apply_season_refresh_activation("SWE1", "2026")
        self.old_slice.refresh_from_db()
        self.new_slice.refresh_from_db()
        self.assertTrue(self.old_slice.refresh_enabled)
        self.assertFalse(self.new_slice.refresh_enabled)
