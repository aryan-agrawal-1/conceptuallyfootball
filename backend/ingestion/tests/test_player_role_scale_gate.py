from unittest.mock import patch

from django.db.models.query import QuerySet
from django.test import TestCase

from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    IngestionKind,
    IngestionRun,
    PlayerSeasonRole,
    PlayerSeasonRoleFeatureSnapshot,
    Season,
)
from ingestion.services.player_role_benchmark import score_only_shadow
from ingestion.services.player_role_orchestration import run_player_role_materialization
from ingestion.services.player_season_roles import score_player_season_roles


def minimal_role_features(player_id, team_id, competition_season_id):
    return {
        "identity": {
            "player_id": player_id,
            "team_id": team_id,
            "competition_season_id": competition_season_id,
        },
        "position": {"group": "MID", "average_touch": {"x": 50, "y": 50}},
        "exposure": {"verified_seconds": 5_400},
        "overall": {
            "summary": {},
            "geometry": {},
            "team_geometry": {},
            "team_action_shares": {},
            "passing": {},
            "carrying": {},
        },
        "states": {},
        "transitions": {},
        "score_events": {},
        "state_spatial": {},
    }


class PlayerRoleCohortMixin:
    def setUp(self):
        competition = Competition.objects.create(name="Test League", short_code="TL")
        season = Season.objects.create(label="2099-00")
        self.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
        )
        team = CanonicalTeam.objects.create(name="Team")
        for index in range(2):
            player = CanonicalPlayer.objects.create(display_name=f"Player {index}")
            PlayerSeasonRoleFeatureSnapshot.objects.create(
                competition_season=self.competition_season,
                player=player,
                team=team,
                feature_version="test",
                features=minimal_role_features(
                    player.id,
                    team.id,
                    self.competition_season.id,
                ),
                verified_exposure_seconds=5_400,
                source_event_version="test",
                source_state_version="test",
                source_participation_version="test",
                source_possession_version="test",
            )
        score_player_season_roles(self.competition_season)

class PlayerRoleScoreOnlyShadowTests(PlayerRoleCohortMixin, TestCase):
    def test_score_only_shadow_reads_no_raw_evidence_and_matches_published_roles(self):
        report = score_only_shadow(self.competition_season)

        self.assertEqual(report["snapshot_count"], 2)
        self.assertEqual(report["role_differences"], 0)
        self.assertEqual(report["raw_evidence_query_count"], 0)
        self.assertGreater(report["query_count"], 0)
        self.assertGreater(report["wall_time_seconds"], 0)


class PlayerRolePublicationRetryTests(PlayerRoleCohortMixin, TestCase):
    def test_failed_role_publication_and_retry_leave_one_complete_current_cohort(self):
        initial_role_ids = set(PlayerSeasonRole.objects.filter(
            competition_season=self.competition_season,
            is_current=True,
        ).values_list("id", flat=True))
        original_update = QuerySet.update

        def fail_role_activation(queryset, **values):
            if queryset.model is PlayerSeasonRole and values == {"is_current": True}:
                raise RuntimeError("role activation failed")
            return original_update(queryset, **values)

        with patch.object(QuerySet, "update", new=fail_role_activation):
            with self.assertRaisesMessage(RuntimeError, "role activation failed"):
                run_player_role_materialization(self.competition_season, score_only=True)

        self.assertEqual(
            set(PlayerSeasonRole.objects.filter(
                competition_season=self.competition_season,
                is_current=True,
            ).values_list("id", flat=True)),
            initial_role_ids,
        )
        self.assertEqual(PlayerSeasonRole.objects.filter(
            competition_season=self.competition_season,
            is_current=True,
        ).count(), 2)
        self.assertEqual(PlayerSeasonRoleFeatureSnapshot.objects.filter(
            competition_season=self.competition_season,
            is_current=True,
        ).count(), 2)

        retry = run_player_role_materialization(self.competition_season, score_only=True)

        self.assertEqual(retry["scoring"]["published_roles"], 2)
        self.assertEqual(PlayerSeasonRole.objects.filter(
            competition_season=self.competition_season,
            is_current=True,
        ).count(), 2)
        self.assertEqual(PlayerSeasonRoleFeatureSnapshot.objects.filter(
            competition_season=self.competition_season,
            is_current=True,
        ).count(), 2)
        self.assertEqual(
            IngestionRun.objects.filter(
                competition_season=self.competition_season,
                kind=IngestionKind.PLAYER_ROLES,
            ).count(),
            2,
        )
