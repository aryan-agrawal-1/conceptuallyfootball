from __future__ import annotations

import json
from collections import Counter
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APIClient

from ingestion.models import (
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    CompetitionType,
    IngestionKind,
    IngestionRun,
    IngestionRunStatus,
    MatchMethod,
    MergedTeamSeason,
    Provider,
    ProviderTeamMapping,
    Season,
    SofascoreTeamSeasonSource,
    UnmatchedProviderTeam,
)
from ingestion.services.identity import resolve_canonical_team
from ingestion.services.ingest import ingest_sofascore_team_slice
from ingestion.services.rollover_diagnostics import diagnose_season_rollover


class SeasonRolloverFixture(TestCase):
    def setUp(self) -> None:
        self.eng1 = Competition.objects.create(
            name="Premier League",
            short_code="ENG1",
            country="England",
        )
        self.eng2 = Competition.objects.create(
            name="Championship",
            short_code="ENG2",
            country="England",
        )
        self.season_2025 = Season.objects.create(label="2025-26", sort_order=2026)
        self.season_2026 = Season.objects.create(label="2026-27", sort_order=2027)

    def create_slice(
        self,
        competition: Competition,
        season: Season,
        *,
        expected_team_count: int = 1,
    ) -> CompetitionSeason:
        return CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            has_understat=False,
            understat_league=None,
            understat_season_year=None,
            sofascore_unique_tournament_id=17,
            sofascore_season_id=season.sort_order,
            expected_team_count=expected_team_count,
            min_merged_team_count=1,
            min_team_stats_coverage_count=0,
            is_published=True,
        )

    def create_source(
        self,
        competition_season: CompetitionSeason,
        *,
        provider_team_id: str,
        team_name: str,
        canonical_team: CanonicalTeam | None,
    ) -> SofascoreTeamSeasonSource:
        run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE_TEAM,
            competition_season=competition_season,
            status=IngestionRunStatus.SUCCESS,
        )
        return SofascoreTeamSeasonSource.objects.create(
            competition_season=competition_season,
            ingestion_run=run,
            provider_team_id=provider_team_id,
            team_name=team_name,
            canonical_team=canonical_team,
        )

    def resolve_team(
        self,
        competition_season: CompetitionSeason,
        *,
        provider_team_id: str = "42",
        team_name: str = "Rollover FC",
    ) -> CanonicalTeam:
        team = resolve_canonical_team(
            competition_season=competition_season,
            provider=Provider.SOFASCORE,
            provider_team_id=provider_team_id,
            team_name=team_name,
            run=None,
        )
        assert team is not None
        return team


class SeasonRolloverIdentityTests(SeasonRolloverFixture):
    def assert_rollover_preserves_identity_and_memberships(
        self,
        previous_competition: Competition,
        current_competition: Competition,
    ) -> None:
        previous_slice = self.create_slice(previous_competition, self.season_2025)
        current_slice = self.create_slice(current_competition, self.season_2026)

        previous_team = self.resolve_team(previous_slice)
        previous_row = MergedTeamSeason.objects.create(
            competition_season=previous_slice,
            canonical_team=previous_team,
            matches=46,
            rank=1,
        )
        current_team = self.resolve_team(current_slice)
        MergedTeamSeason.objects.create(
            competition_season=current_slice,
            canonical_team=current_team,
            matches=38,
            rank=17,
        )

        self.assertEqual(previous_team.id, current_team.id)
        self.assertEqual(CanonicalTeam.objects.count(), 1)
        self.assertEqual(
            ProviderTeamMapping.objects.filter(
                provider=Provider.SOFASCORE,
                provider_team_id="42",
            ).count(),
            1,
        )
        previous_row.refresh_from_db()
        self.assertEqual(previous_row.matches, 46)
        self.assertTrue(previous_row.is_current)
        self.assertSetEqual(
            set(
                MergedTeamSeason.objects.filter(canonical_team=current_team).values_list(
                    "competition_season__competition__short_code",
                    "competition_season__season__label",
                )
            ),
            {
                (previous_competition.short_code, "2025-26"),
                (current_competition.short_code, "2026-27"),
            },
        )

    def test_promotion_reuses_canonical_team_and_preserves_history(self) -> None:
        self.assert_rollover_preserves_identity_and_memberships(self.eng2, self.eng1)

    def test_relegation_reuses_canonical_team_and_preserves_history(self) -> None:
        self.assert_rollover_preserves_identity_and_memberships(self.eng1, self.eng2)

    def test_club_has_only_one_domestic_membership_per_season(self) -> None:
        previous_slice = self.create_slice(self.eng2, self.season_2025)
        current_slice = self.create_slice(self.eng1, self.season_2026)
        team = self.resolve_team(previous_slice)
        MergedTeamSeason.objects.create(
            competition_season=previous_slice,
            canonical_team=team,
        )
        MergedTeamSeason.objects.create(
            competition_season=current_slice,
            canonical_team=self.resolve_team(current_slice),
        )

        memberships_by_season = Counter(
            MergedTeamSeason.objects.filter(canonical_team=team).values_list(
                "competition_season__season__label",
                flat=True,
            )
        )
        self.assertEqual(memberships_by_season, {"2025-26": 1, "2026-27": 1})

    def test_stable_sofascore_id_with_renamed_club_does_not_duplicate(self) -> None:
        previous_slice = self.create_slice(self.eng2, self.season_2025)
        current_slice = self.create_slice(self.eng1, self.season_2026)

        original = self.resolve_team(previous_slice, team_name="Old Borough FC")
        renamed = self.resolve_team(current_slice, team_name="New Borough FC")

        self.assertEqual(original.id, renamed.id)
        self.assertEqual(CanonicalTeam.objects.count(), 1)

    def test_search_and_detail_api_expose_historical_and_current_memberships(self) -> None:
        previous_slice = self.create_slice(self.eng2, self.season_2025)
        current_slice = self.create_slice(self.eng1, self.season_2026)
        team = self.resolve_team(previous_slice)
        MergedTeamSeason.objects.create(
            competition_season=previous_slice,
            canonical_team=team,
            matches=46,
            rank=1,
        )
        MergedTeamSeason.objects.create(
            competition_season=current_slice,
            canonical_team=self.resolve_team(current_slice),
            matches=38,
            rank=17,
        )

        client = APIClient()
        search_response = client.get("/api/v1/search/entities")

        self.assertEqual(search_response.status_code, 200)
        search_team = search_response.json()["teams"][0]
        self.assertEqual(search_team["canonical_team_id"], team.id)
        self.assertEqual(
            {
                (membership["competition"], membership["season"])
                for membership in search_team["memberships"]
            },
            {("ENG2", "2025-26"), ("ENG1", "2026-27")},
        )
        for competition, season in (("ENG2", "2025-26"), ("ENG1", "2026-27")):
            detail_response = client.get(
                f"/api/v1/team-seasons/stats/{team.id}",
                {"competition": competition, "season": season},
            )
            self.assertEqual(detail_response.status_code, 200)
            self.assertEqual(detail_response.json()["competition_code"], competition)
            self.assertEqual(detail_response.json()["season_label"], season)


class RolloverDiagnosticTests(SeasonRolloverFixture):
    def test_continental_membership_is_not_treated_as_second_domestic_league(self) -> None:
        target_slice = self.create_slice(self.eng1, self.season_2026)
        continental = Competition.objects.create(
            name="Champions League",
            short_code="UCL",
            country="Europe",
            competition_type=CompetitionType.CONTINENTAL_CUP,
            include_in_domestic_aggregates=False,
        )
        continental_slice = self.create_slice(continental, self.season_2026)
        team = CanonicalTeam.objects.create(name="Continental FC")
        ProviderTeamMapping.objects.create(
            canonical_team=team,
            provider=Provider.SOFASCORE,
            provider_team_id="42",
        )
        self.create_source(
            target_slice,
            provider_team_id="42",
            team_name="Continental FC",
            canonical_team=team,
        )
        MergedTeamSeason.objects.create(
            competition_season=target_slice,
            canonical_team=team,
        )
        MergedTeamSeason.objects.create(
            competition_season=continental_slice,
            canonical_team=team,
        )

        report = diagnose_season_rollover(target_slice)

        self.assertTrue(report.ready_for_publication)
        self.assertNotIn(
            "multiple_domestic_competitions",
            {anomaly.code for anomaly in report.anomalies},
        )

    def test_reports_count_duplicate_unmatched_name_and_domestic_anomalies(self) -> None:
        previous_slice = self.create_slice(self.eng2, self.season_2025)
        target_slice = self.create_slice(self.eng1, self.season_2026, expected_team_count=4)
        same_season_eng2 = self.create_slice(self.eng2, self.season_2026)
        team = CanonicalTeam.objects.create(name="Alpha FC")
        ProviderTeamMapping.objects.create(
            canonical_team=team,
            provider=Provider.SOFASCORE,
            provider_team_id="42",
            match_method=MatchMethod.AUTO,
        )
        ProviderTeamMapping.objects.create(
            canonical_team=team,
            provider=Provider.SOFASCORE,
            provider_team_id="43",
            match_method=MatchMethod.AUTO,
        )
        self.create_source(
            previous_slice,
            provider_team_id="42",
            team_name="Alpha Athletic",
            canonical_team=team,
        )
        self.create_source(
            target_slice,
            provider_team_id="42",
            team_name="Alpha FC",
            canonical_team=team,
        )
        self.create_source(
            target_slice,
            provider_team_id="43",
            team_name="Alpha FC",
            canonical_team=team,
        )
        self.create_source(
            target_slice,
            provider_team_id="99",
            team_name="Unknown FC",
            canonical_team=None,
        )
        UnmatchedProviderTeam.objects.create(
            competition_season=target_slice,
            provider=Provider.SOFASCORE,
            provider_team_id="99",
            team_name="Unknown FC",
        )
        MergedTeamSeason.objects.create(
            competition_season=target_slice,
            canonical_team=team,
        )
        MergedTeamSeason.objects.create(
            competition_season=same_season_eng2,
            canonical_team=team,
        )

        report = diagnose_season_rollover(
            target_slice,
            previous_competition_season=previous_slice,
        )

        codes = {anomaly.code for anomaly in report.anomalies}
        self.assertFalse(report.ready_for_publication)
        self.assertTrue(
            {
                "duplicate_canonical_team",
                "expected_team_count_mismatch",
                "multiple_domestic_competitions",
                "provider_identity_requires_review",
                "provider_name_change",
                "unmatched_canonical_team",
                "unknown_provider_team_id",
            }.issubset(codes)
        )

    def test_changed_unknown_provider_id_is_reviewed_without_creating_identity(self) -> None:
        previous_slice = self.create_slice(self.eng2, self.season_2025)
        target_slice = self.create_slice(self.eng1, self.season_2026)
        team = CanonicalTeam.objects.create(name="Rollover FC")
        ProviderTeamMapping.objects.create(
            canonical_team=team,
            provider=Provider.SOFASCORE,
            provider_team_id="42",
        )
        self.create_source(
            previous_slice,
            provider_team_id="42",
            team_name="Rollover FC",
            canonical_team=team,
        )
        identity_counts_before = (
            CanonicalTeam.objects.count(),
            ProviderTeamMapping.objects.count(),
        )

        report = diagnose_season_rollover(
            target_slice,
            previous_competition_season=previous_slice,
            candidate_rows=[
                {"provider_team_id": "999", "team_name": "Rollover FC"},
            ],
        )

        self.assertEqual(
            {anomaly.code for anomaly in report.anomalies},
            {"provider_id_change", "unknown_provider_team_id", "unmatched_canonical_team"},
        )
        self.assertEqual(
            identity_counts_before,
            (CanonicalTeam.objects.count(), ProviderTeamMapping.objects.count()),
        )

    def test_management_command_outputs_json_without_writes(self) -> None:
        target_slice = self.create_slice(self.eng1, self.season_2026)
        team = CanonicalTeam.objects.create(name="Clean FC")
        ProviderTeamMapping.objects.create(
            canonical_team=team,
            provider=Provider.SOFASCORE,
            provider_team_id="42",
        )
        self.create_source(
            target_slice,
            provider_team_id="42",
            team_name="Clean FC",
            canonical_team=team,
        )
        counts_before = (
            CanonicalTeam.objects.count(),
            ProviderTeamMapping.objects.count(),
            SofascoreTeamSeasonSource.objects.count(),
        )
        output = StringIO()

        call_command("diagnose_season_rollover", target_slice.id, stdout=output)

        payload = json.loads(output.getvalue().split("Season-rollover preflight passed.")[0])
        self.assertTrue(payload["ready_for_publication"])
        self.assertEqual(payload["anomalies"], [])
        self.assertEqual(
            counts_before,
            (
                CanonicalTeam.objects.count(),
                ProviderTeamMapping.objects.count(),
                SofascoreTeamSeasonSource.objects.count(),
            ),
        )

    def test_management_command_can_fail_release_check_on_anomaly(self) -> None:
        target_slice = self.create_slice(self.eng1, self.season_2026)
        output = StringIO()

        with self.assertRaisesMessage(CommandError, "preflight found 1 anomaly"):
            call_command(
                "diagnose_season_rollover",
                target_slice.id,
                fail_on_anomaly=True,
                stdout=output,
            )

        payload = json.loads(output.getvalue())
        self.assertFalse(payload["ready_for_publication"])
        self.assertEqual(payload["anomalies"][0]["code"], "expected_team_count_mismatch")

    @patch("ingestion.services.ingest.build_team_season_rows", return_value=[])
    def test_wrong_candidate_count_fails_before_current_source_replacement(
        self,
        mock_build_rows,
    ) -> None:
        target_slice = self.create_slice(self.eng1, self.season_2026)
        team = CanonicalTeam.objects.create(name="Existing FC")
        existing = self.create_source(
            target_slice,
            provider_team_id="42",
            team_name="Existing FC",
            canonical_team=team,
        )
        run = IngestionRun.objects.create(
            kind=IngestionKind.SOFASCORE_TEAM,
            competition_season=target_slice,
            status=IngestionRunStatus.PENDING,
        )

        ingest_sofascore_team_slice(target_slice, run=run)

        run.refresh_from_db()
        self.assertEqual(run.status, IngestionRunStatus.FAILED)
        self.assertIn("below expected threshold", run.error_detail)
        self.assertTrue(SofascoreTeamSeasonSource.objects.filter(pk=existing.pk).exists())
        mock_build_rows.assert_called_once()
