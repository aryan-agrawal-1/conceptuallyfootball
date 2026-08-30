from unittest.mock import patch

from django.db.models.query import QuerySet
from django.test import TestCase

from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    PlayerSeasonRole,
    PlayerSeasonRoleFeatureSnapshot,
    Season,
)
from ingestion.services.player_season_roles import score_player_season_roles


def carrying_features(player_id, team_id, competition_season_id, progressive_carries):
    return {
        "identity": {
            "player_id": player_id,
            "team_id": team_id,
            "competition_season_id": competition_season_id,
        },
        "position": {"group": "MID", "average_touch": {"x": 50, "y": 50}},
        "exposure": {"verified_seconds": 5400},
        "overall": {
            "summary": {"carries": 40, "progressive_carries": progressive_carries},
            "carrying": {
                "final_third_entries": 8,
                "box_entries": 2,
                "mean_forward_metres": progressive_carries,
            },
            "geometry": {"rates_per90": {}},
            "team_geometry": {},
            "team_action_shares": {
                "progressive_carries": {"share": progressive_carries / 40},
            },
        },
        "states": {},
        "transitions": {},
        "score_events": {},
    }


class PlayerSeasonRolePublicationTests(TestCase):
    def setUp(self):
        competition = Competition.objects.create(name="Test League", short_code="TL")
        season = Season.objects.create(label="2099-00")
        self.competition_season = CompetitionSeason.objects.create(
            competition=competition, season=season
        )
        self.team = CanonicalTeam.objects.create(name="Team")
        self.players = [
            CanonicalPlayer.objects.create(display_name="Player One"),
            CanonicalPlayer.objects.create(display_name="Player Two"),
        ]
        self.snapshots = []
        for player, carries in zip(self.players, (12, 24)):
            self.snapshots.append(PlayerSeasonRoleFeatureSnapshot.objects.create(
                competition_season=self.competition_season,
                player=player,
                team=self.team,
                feature_version="test",
                features=carrying_features(
                    player.id, self.team.id, self.competition_season.id, carries
                ),
                verified_exposure_seconds=5400,
                source_event_version="test",
                source_state_version="test",
                source_participation_version="test",
                source_possession_version="test",
            ))

    def ball_carrying_fit(self, player):
        role = PlayerSeasonRole.objects.get(
            competition_season=self.competition_season,
            player=player,
            team=self.team,
            is_current=True,
        )
        return next(
            candidate["fit"] for candidate in role.candidates
            if candidate["archetype"] == "Ball-Carrying Progressor"
        )

    def test_affected_feature_change_republishes_and_rescores_complete_cohort(self):
        first = score_player_season_roles(self.competition_season)
        initial_fit = self.ball_carrying_fit(self.players[1])
        initial_role_ids = set(PlayerSeasonRole.objects.filter(
            competition_season=self.competition_season, is_current=True
        ).values_list("id", flat=True))

        self.snapshots[0].features = carrying_features(
            self.players[0].id, self.team.id, self.competition_season.id, 36
        )
        self.snapshots[0].save(update_fields=["features"])
        second = score_player_season_roles(
            self.competition_season,
            affected_player_ids=[self.players[0].id],
        )

        current_roles = PlayerSeasonRole.objects.filter(
            competition_season=self.competition_season, is_current=True
        )
        self.assertEqual(first["published_roles"], 2)
        self.assertEqual(second["published_roles"], 2)
        self.assertEqual(current_roles.count(), 2)
        self.assertFalse(initial_role_ids & set(current_roles.values_list("id", flat=True)))
        self.assertNotEqual(self.ball_carrying_fit(self.players[1]), initial_fit)

    def test_role_activation_failure_preserves_previous_complete_cohort(self):
        score_player_season_roles(self.competition_season)
        initial_ids = set(PlayerSeasonRole.objects.filter(
            competition_season=self.competition_season,
            is_current=True,
        ).values_list("id", flat=True))
        original_update = QuerySet.update

        def fail_role_activation(queryset, **values):
            if (
                queryset.model is PlayerSeasonRole
                and values == {"is_current": True}
            ):
                raise RuntimeError("role activation failed")
            return original_update(queryset, **values)

        with patch.object(QuerySet, "update", new=fail_role_activation):
            with self.assertRaisesMessage(RuntimeError, "role activation failed"):
                score_player_season_roles(self.competition_season)

        current = PlayerSeasonRole.objects.filter(
            competition_season=self.competition_season,
            is_current=True,
        )
        self.assertEqual(set(current.values_list("id", flat=True)), initial_ids)
        self.assertEqual(PlayerSeasonRole.objects.count(), 2)
