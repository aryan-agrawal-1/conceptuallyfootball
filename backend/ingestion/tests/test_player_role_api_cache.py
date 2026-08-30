from django.test import TestCase
from rest_framework.test import APIClient

from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    PlayerSeasonDerivedStats,
    PlayerSeasonGkDerivedStats,
    PlayerSeasonRole,
    PlayerSeasonRoleFeatureSnapshot,
    Season,
)


class PlayerRoleDetailApiCacheTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        competition = Competition.objects.create(name="Test League", short_code="TST")
        season = Season.objects.create(label="2025-26", sort_order=2026)
        self.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
            is_published=True,
        )
        self.team = CanonicalTeam.objects.create(name="Test Team")
        self.outfield = CanonicalPlayer.objects.create(display_name="Outfield Player")
        self.goalkeeper = CanonicalPlayer.objects.create(display_name="Goalkeeper")
        PlayerSeasonDerivedStats.objects.create(
            competition_season=self.competition_season,
            canonical_player=self.outfield,
            canonical_display_team=self.team,
            position_group="MID",
            minutes=900,
        )
        PlayerSeasonGkDerivedStats.objects.create(
            competition_season=self.competition_season,
            canonical_player=self.goalkeeper,
            canonical_display_team=self.team,
            minutes=900,
        )
        self.publish_role(self.outfield, "Connector", "role-v1")
        self.publish_role(self.goalkeeper, "Shot Stopper", "role-v1")

    def publish_role(self, player, archetype, scoring_version):
        snapshot, _ = PlayerSeasonRoleFeatureSnapshot.objects.get_or_create(
            competition_season=self.competition_season,
            player=player,
            team=self.team,
            is_current=True,
            defaults={
                "feature_version": "features-v1",
                "features": {
                    "identity": {"player_id": player.id, "team_id": self.team.id},
                    "exposure": {"verified_seconds": 54_000},
                },
                "verified_exposure_seconds": 54_000,
                "source_event_version": "event-v1",
                "source_state_version": "state-v1",
                "source_participation_version": "participation-v1",
                "source_possession_version": "possession-v1",
            },
        )
        PlayerSeasonRole.objects.filter(
            competition_season=self.competition_season,
            player=player,
            team=self.team,
            is_current=True,
        ).update(is_current=False)
        return PlayerSeasonRole.objects.create(
            competition_season=self.competition_season,
            player=player,
            team=self.team,
            feature_snapshot=snapshot,
            primary_archetype=archetype,
            primary_fit=0.8,
            classification_shape="clear",
            evidence_confidence="established",
            traits=[],
            candidates=[],
            evidence={"explanation": archetype},
            scoring_version=scoring_version,
        )

    def assert_cache_refreshes_after_role_publication(self, path, player, replacement):
        params = {"competition": "TST", "season": "2025-26"}
        first = self.client.get(path, params)
        second = self.client.get(path, params)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first["X-Materialized-Payload"], "miss")
        self.assertEqual(second["X-Materialized-Payload"], "hit")

        self.publish_role(player, replacement, "role-v2")
        refreshed = self.client.get(path, params)
        cached = self.client.get(path, params)

        self.assertEqual(refreshed["X-Materialized-Payload"], "miss")
        self.assertEqual(refreshed.json()["season_role"]["primary_archetype"], replacement)
        self.assertEqual(refreshed.json()["season_role"]["scoring_version"], "role-v2")
        self.assertEqual(cached["X-Materialized-Payload"], "hit")

    def test_outfield_detail_cache_tracks_current_role_model_version(self):
        self.assert_cache_refreshes_after_role_publication(
            f"/api/v1/player-seasons/derived-stats/{self.outfield.id}",
            self.outfield,
            "Ball Winner",
        )

    def test_goalkeeper_detail_cache_tracks_current_role_model_version(self):
        self.assert_cache_refreshes_after_role_publication(
            f"/api/v1/player-seasons/gk-derived-stats/{self.goalkeeper.id}",
            self.goalkeeper,
            "Sweeper Keeper",
        )
