from __future__ import annotations

from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase
from rest_framework.test import APIClient

from ingestion.competition_scope import resolve_public_scope
from ingestion.models import (
    CanonicalPlayer,
    Competition,
    CompetitionSeason,
    CompetitionType,
    IngestionRunStatus,
    PlayerSeasonDerivedStats,
    PlayerSeasonGkDerivedStats,
    PositionGroup,
    Season,
)
from ingestion.services.aggregate_season_alignment import calendar_aggregate_coverage
from ingestion.services.season_labels import (
    aggregate_constituent_season_labels,
    aggregate_season_label,
)


class AggregateSeasonLabelTests(TestCase):
    def test_calendar_labels_align_by_convention_without_competition_aliases(self):
        self.assertEqual(aggregate_season_label("2025"), "2025-26")
        self.assertEqual(aggregate_season_label("2026"), "2026-27")
        self.assertEqual(aggregate_season_label("2025-26"), "2025-26")
        self.assertEqual(
            aggregate_constituent_season_labels("2025-26"),
            ["2025-26", "2025"],
        )


class AggregateSeasonConstituentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.eng = Competition.objects.create(name="Premier League", short_code="ENG1")
        self.swe = Competition.objects.create(name="Allsvenskan", short_code="SWE1")
        self.nor = Competition.objects.create(name="Eliteserien", short_code="NOR1")
        self.est = Competition.objects.create(name="Premium Liiga", short_code="EST1")
        self.ucl = Competition.objects.create(
            name="Champions League",
            short_code="UCL",
            competition_type=CompetitionType.CONTINENTAL_CUP,
            include_in_domestic_aggregates=False,
        )
        self.slices = {}
        for year in (2025, 2026):
            split = Season.objects.create(label=f"{year}-{(year + 1) % 100:02d}", sort_order=year + 1)
            calendar = Season.objects.create(label=str(year), sort_order=year)
            self.slices[("ENG1", year)] = self.create_slice(self.eng, split)
            self.slices[("SWE1", year)] = self.create_slice(self.swe, calendar)
            self.slices[("NOR1", year)] = self.create_slice(self.nor, calendar)
            self.slices[("EST1", year)] = self.create_slice(self.est, calendar)
            self.slices[("UCL", year)] = self.create_slice(self.ucl, split)

    @staticmethod
    def create_slice(competition: Competition, season: Season) -> CompetitionSeason:
        return CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            is_published=True,
            metric_availability={"available_metrics": [competition.short_code.lower()]},
        )

    def test_all_resolves_two_consecutive_aligned_years_without_big5_or_uefa_leakage(self):
        for year in (2025, 2026):
            aggregate_label = f"{year}-{(year + 1) % 100:02d}"
            all_codes = {row.competition.short_code for row in resolve_public_scope("ALL", aggregate_label)}
            big5_codes = {row.competition.short_code for row in resolve_public_scope("BIG5", aggregate_label)}
            self.assertEqual(all_codes, {"ENG1", "SWE1", "NOR1", "EST1"})
            self.assertEqual(big5_codes, {"ENG1"})

    def test_concrete_scope_and_catalog_keep_canonical_calendar_labels(self):
        self.assertEqual(
            resolve_public_scope("SWE1", "2025")[0],
            self.slices[("SWE1", 2025)],
        )
        catalog = self.client.get("/api/v1/competition-seasons").json()["competitions"]
        by_code = {entry["code"]: entry for entry in catalog}
        self.assertEqual(
            [season["label"] for season in by_code["SWE1"]["seasons"]],
            ["2026", "2025"],
        )
        all_2025 = next(
            season for season in by_code["ALL"]["seasons"] if season["label"] == "2025-26"
        )
        self.assertEqual(
            set(all_2025["eligibility_thresholds"]),
            {"ENG1", "SWE1", "NOR1", "EST1"},
        )

    def test_outfield_goalkeeper_and_search_payloads_share_aligned_constituents(self):
        player_ids = {}
        for code in ("ENG1", "SWE1", "NOR1", "EST1", "UCL"):
            player = CanonicalPlayer.objects.create(display_name=f"{code} Player")
            player_ids[code] = player.id
            competition_season = self.slices[(code, 2025)]
            PlayerSeasonDerivedStats.objects.create(
                competition_season=competition_season,
                canonical_player=player,
                formula_version="test",
                position_group=PositionGroup.FWD,
                minutes=900,
                percentiles_eligible=True,
                scores_eligible=True,
            )
            goalkeeper = CanonicalPlayer.objects.create(display_name=f"{code} Goalkeeper")
            PlayerSeasonGkDerivedStats.objects.create(
                competition_season=competition_season,
                canonical_player=goalkeeper,
                minutes=900,
                percentiles_eligible=True,
            )

        outfield = self.client.get(
            "/api/v1/player-seasons/derived-stats",
            {"competition": "ALL", "season": "2025-26", "include": "meta"},
        ).json()
        goalkeepers = self.client.get(
            "/api/v1/player-seasons/gk-derived-stats",
            {"competition": "ALL", "season": "2025-26", "include": "meta"},
        ).json()
        search = self.client.get("/api/v1/search/entities").json()

        self.assertEqual(outfield["count"], 4)
        self.assertEqual(goalkeepers["count"], 4)
        self.assertEqual(
            set(outfield["meta"]["eligibility_thresholds"]),
            {"ENG1", "SWE1", "NOR1", "EST1"},
        )
        swe_membership = next(
            membership
            for player in search["players"]
            if player["canonical_player_id"] == player_ids["SWE1"]
            for membership in player["memberships"]
        )
        self.assertEqual(swe_membership["season"], "2025")
        self.assertEqual(swe_membership["aggregate_season"], "2025-26")

        profile = self.client.get(
            f"/api/v1/player-seasons/derived-stats/{player_ids['SWE1']}",
            {
                "competition": "SWE1",
                "season": "2025",
                "comparison_scope": "ALL",
                "include": "profile_distributions",
            },
        ).json()
        self.assertEqual(profile["comparison_scope"], "ALL")
        self.assertEqual(
            profile["comparison_profile_distributions"]["cohort_count"],
            4,
        )
        self.assertEqual(
            set(
                profile["comparison_profile_distributions"]["context"][
                    "competition_season_ids"
                ]
            ),
            {
                self.slices[("ENG1", 2025)].id,
                self.slices[("SWE1", 2025)].id,
                self.slices[("NOR1", 2025)].id,
                self.slices[("EST1", 2025)].id,
            },
        )


class AggregateSeasonDiagnosticTests(TestCase):
    def setUp(self):
        calendar = Season.objects.create(label="2025", sort_order=2025)
        competition = Competition.objects.create(name="Future League", short_code="NEW1")
        self.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=calendar,
            is_published=True,
        )

    def test_diagnostic_reports_every_published_calendar_slice(self):
        report = calendar_aggregate_coverage()
        row = report["calendar_slices"][0]
        self.assertEqual(row["competition"], "NEW1")
        self.assertEqual(row["aggregate_season"], "2025-26")
        self.assertTrue(row["included_in_all_scope"])

    @patch("ingestion.services.aggregate_season_alignment.resolve_public_scope", return_value=[])
    def test_fail_on_warning_detects_label_only_omission(self, resolve_scope):
        with self.assertRaisesMessage(CommandError, "alignment warnings detected"):
            call_command("repair_aggregate_season_alignment", "--fail-on-warning")
        resolve_scope.assert_called_once_with("ALL", "2025-26")

    @patch(
        "ingestion.management.commands.repair_aggregate_season_alignment.invalidate_materialized_api_payloads",
        return_value=3,
    )
    @patch("ingestion.services.galaxy.materialize_galaxy_scope")
    def test_apply_repairs_every_affected_aggregate_and_invalidates_payloads(
        self,
        materialize_scope,
        invalidate_payloads,
    ):
        def succeed(scope, season, *, run):
            run.status = IngestionRunStatus.SUCCESS
            run.save(update_fields=["status"])

        materialize_scope.side_effect = succeed

        call_command("repair_aggregate_season_alignment", "--apply")

        materialize_scope.assert_called_once()
        self.assertEqual(materialize_scope.call_args.args, ("ALL", "2025-26"))
        invalidate_payloads.assert_called_once_with()
