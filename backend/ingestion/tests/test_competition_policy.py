from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from ingestion.competition_scope import resolve_public_scope
from ingestion.models import (
    CanonicalPlayer,
    Competition,
    CompetitionSeason,
    CompetitionType,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
    PlayerSeasonDerivedStats,
    PositionGroup,
    Season,
)
from ingestion.services.derived import _eligibility
from ingestion.services.galaxy import resolve_galaxy_competition_seasons
from ingestion.services.gk_derived import _gk_eligibility
from ingestion.services.publication import set_competition_season_published


class CompetitionPolicyTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.season = Season.objects.create(label="2026-27", sort_order=2027)
        self.domestic = Competition.objects.create(
            name="Premier League",
            short_code="ENG1",
            country="England",
        )

    def create_slice(
        self,
        competition: Competition,
        *,
        published: bool = False,
    ) -> CompetitionSeason:
        return CompetitionSeason.objects.create(
            competition=competition,
            season=self.season,
            is_published=published,
        )

    def create_derived_row(
        self,
        competition_season: CompetitionSeason,
        player: CanonicalPlayer,
        *,
        minutes: int,
        run: IngestionRun | None = None,
    ) -> PlayerSeasonDerivedStats:
        return PlayerSeasonDerivedStats.objects.create(
            competition_season=competition_season,
            canonical_player=player,
            derived_ingestion_run=run,
            formula_version="test",
            position_group=PositionGroup.FWD,
            minutes=minutes,
            percentiles_eligible=minutes >= competition_season.minimum_eligible_minutes,
            scores_eligible=minutes >= competition_season.minimum_eligible_minutes,
        )

    def test_unpublished_slice_is_hidden_from_catalog_and_direct_api(self) -> None:
        competition_season = self.create_slice(self.domestic)
        player = CanonicalPlayer.objects.create(display_name="Hidden Player")
        self.create_derived_row(competition_season, player, minutes=900)

        catalog = self.client.get("/api/v1/competition-seasons").json()
        direct = self.client.get(
            "/api/v1/player-seasons/derived-stats",
            {"competition": "ENG1", "season": self.season.label},
        )

        self.assertEqual(catalog["competitions"], [])
        self.assertEqual(direct.status_code, 400)

    def test_successful_materialization_requires_intentional_publication(self) -> None:
        competition_season = self.create_slice(self.domestic)
        run = IngestionRun.objects.create(
            kind=IngestionKind.DERIVED,
            competition_season=competition_season,
            status=IngestionRunStatus.SUCCESS,
        )
        player = CanonicalPlayer.objects.create(display_name="Published Player")
        self.create_derived_row(competition_season, player, minutes=900, run=run)

        set_competition_season_published(competition_season, published=True)

        catalog = self.client.get("/api/v1/competition-seasons").json()
        direct = self.client.get(
            "/api/v1/player-seasons/derived-stats",
            {"competition": "ENG1", "season": self.season.label, "include": "meta"},
        )
        self.assertTrue(competition_season.is_published)
        self.assertIn("ENG1", {entry["code"] for entry in catalog["competitions"]})
        self.assertEqual(direct.status_code, 200)
        self.assertEqual(direct.json()["meta"]["minimum_eligible_minutes"], 450)

    def test_publication_refuses_empty_or_failed_materialization(self) -> None:
        competition_season = self.create_slice(self.domestic)
        failed_run = IngestionRun.objects.create(
            kind=IngestionKind.DERIVED,
            competition_season=competition_season,
            status=IngestionRunStatus.FAILED,
        )
        player = CanonicalPlayer.objects.create(display_name="Failed Player")
        self.create_derived_row(competition_season, player, minutes=900, run=failed_run)

        with self.assertRaisesMessage(ValueError, "No current player rows"):
            set_competition_season_published(competition_season, published=True)

        competition_season.refresh_from_db()
        self.assertFalse(competition_season.is_published)

    def test_domestic_aggregates_exclude_continental_and_unpublished_slices(self) -> None:
        domestic_slice = self.create_slice(self.domestic, published=True)
        continental = Competition.objects.create(
            name="Champions League",
            short_code="UCL",
            country="Europe",
            competition_type=CompetitionType.CONTINENTAL_CUP,
            include_in_domestic_aggregates=False,
            minimum_eligible_minutes=270,
        )
        continental_slice = self.create_slice(continental, published=True)
        hidden_domestic = Competition.objects.create(
            name="Championship",
            short_code="ENG2",
            country="England",
        )
        self.create_slice(hidden_domestic)
        player = CanonicalPlayer.objects.create(display_name="Dual Membership")
        self.create_derived_row(domestic_slice, player, minutes=800)
        self.create_derived_row(continental_slice, player, minutes=300)

        all_scope = resolve_public_scope("ALL", self.season.label)
        galaxy_scope = resolve_galaxy_competition_seasons("ALL", self.season.label)
        search_player = self.client.get("/api/v1/search/entities").json()["players"][0]
        catalog = self.client.get("/api/v1/competition-seasons").json()["competitions"]

        self.assertEqual([row.id for row in all_scope], [domestic_slice.id])
        self.assertEqual([row.id for row in galaxy_scope], [domestic_slice.id])
        self.assertEqual(search_player["total_minutes"], 800)
        self.assertEqual(
            {membership["competition"] for membership in search_player["memberships"]},
            {"ENG1", "UCL"},
        )
        self.assertNotIn("ENG2", {entry["code"] for entry in catalog})
        self.assertEqual(next(entry for entry in catalog if entry["code"] == "UCL")["group"], "european")

    def test_domestic_and_uefa_eligibility_boundaries_share_one_rule(self) -> None:
        for threshold in (270, 450):
            for minutes, expected in (
                (threshold - 1, False),
                (threshold, True),
                (threshold + 1, True),
            ):
                with self.subTest(threshold=threshold, minutes=minutes):
                    self.assertEqual(
                        _eligibility(minutes, PositionGroup.FWD, threshold)[0],
                        expected,
                    )
                    self.assertEqual(_gk_eligibility(minutes, threshold)[0], expected)

    def test_continental_api_reports_its_effective_threshold(self) -> None:
        continental = Competition.objects.create(
            name="Champions League",
            short_code="UCL",
            country="Europe",
            competition_type=CompetitionType.CONTINENTAL_CUP,
            include_in_domestic_aggregates=False,
            minimum_eligible_minutes=270,
        )
        competition_season = self.create_slice(continental, published=True)
        player = CanonicalPlayer.objects.create(display_name="European Player")
        self.create_derived_row(competition_season, player, minutes=269)

        response = self.client.get(
            "/api/v1/player-seasons/derived-stats",
            {"competition": "UCL", "season": self.season.label, "include": "meta"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["minimum_eligible_minutes"], 270)
        self.assertEqual(payload["meta"]["eligibility_thresholds"], {"UCL": 270})
        self.assertEqual(payload["results"][0]["eligibility"]["minimum_eligible_minutes"], 270)
