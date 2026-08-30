from unittest.mock import patch

from django.db.models.query import QuerySet
from django.test import TestCase

from ingestion.models import (
    CanonicalPlayer,
    CanonicalTeam,
    Competition,
    CompetitionSeason,
    EventProfileSplitType,
    IngestionKind,
    IngestionRun,
    PlayerSeasonEventProfile,
    PlayerSeasonRoleFeatureSnapshot,
    Season,
)
from ingestion.services.player_role_materialization import (
    FULL_EXTRACTION_PROFILE_RATIO,
    FeatureExtractionScope,
    feature_extraction_scope,
    materialize_bounded_player_role_features,
    preserve_accepted_rounding,
    publish_feature_snapshots,
)


class PlayerRoleMaterializationTests(TestCase):
    def setUp(self):
        competition = Competition.objects.create(name="Test League", short_code="TL")
        season = Season.objects.create(label="2099-00")
        self.competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
        )
        self.team = CanonicalTeam.objects.create(name="Team")
        self.players = [
            CanonicalPlayer.objects.create(display_name=f"Player {index}")
            for index in range(5)
        ]
        run = IngestionRun.objects.create(
            kind=IngestionKind.EVENT_PROFILES,
            competition_season=self.competition_season,
        )
        for player in self.players:
            PlayerSeasonEventProfile.objects.create(
                competition_season=self.competition_season,
                player=player,
                team=self.team,
                split_type=EventProfileSplitType.TEAM,
                materialized_ingestion_run=run,
            )

    def snapshot(self, player, *, current=True):
        return PlayerSeasonRoleFeatureSnapshot(
            competition_season=self.competition_season,
            player=player,
            team=self.team,
            feature_version="test",
            features={"identity": {"player_id": player.id, "team_id": self.team.id}},
            source_event_version="event",
            source_state_version="state",
            source_participation_version="participation",
            source_possession_version="possession",
            is_current=current,
        )

    def test_benchmarked_threshold_selects_incremental_then_full_scope(self):
        self.assertEqual(FULL_EXTRACTION_PROFILE_RATIO, 0.8)
        incremental = feature_extraction_scope(
            self.competition_season,
            affected_player_ids=[player.id for player in self.players[:3]],
            affected_team_ids=None,
        )
        full = feature_extraction_scope(
            self.competition_season,
            affected_player_ids=[player.id for player in self.players[:4]],
            affected_team_ids=None,
        )

        self.assertEqual(incremental.mode, "incremental")
        self.assertEqual(len(incremental.profiles), 3)
        self.assertEqual(full.mode, "full")
        self.assertEqual(len(full.profiles), 5)

    def test_only_proven_float_order_ties_reuse_accepted_rounding(self):
        candidate = {"mean": 6.76, "changed": 2.0, "rows": [{"x": 1.2346}]}
        exact = {"mean": 6.75, "changed": 2.0, "rows": [{"x": 1.2345}]}
        reference = {"mean": 6.75, "changed": 1.99, "rows": [{"x": 1.2345}]}

        self.assertEqual(
            preserve_accepted_rounding(candidate, exact, candidate, reference),
            {"mean": 6.75, "changed": 2.0, "rows": [{"x": 1.2345}]},
        )

    def test_incremental_publication_preserves_unaffected_current_rows_and_is_retry_safe(self):
        old_rows = [self.snapshot(player) for player in self.players[:2]]
        PlayerSeasonRoleFeatureSnapshot.objects.bulk_create(old_rows)
        scope = FeatureExtractionScope(
            mode="incremental",
            cohort_count=5,
            profiles=(),
            affected_player_ids=frozenset({self.players[0].id}),
            affected_team_ids=None,
        )

        first = [self.snapshot(self.players[0], current=False)]
        publish_feature_snapshots(self.competition_season, first, scope)
        second = [self.snapshot(self.players[0], current=False)]
        publish_feature_snapshots(self.competition_season, second, scope)

        current = PlayerSeasonRoleFeatureSnapshot.objects.filter(
            competition_season=self.competition_season,
            is_current=True,
        )
        self.assertEqual(current.count(), 2)
        self.assertEqual(
            current.get(player=self.players[0]).pk,
            second[0].pk,
        )
        self.assertEqual(current.get(player=self.players[1]).pk, old_rows[1].pk)

    def test_publication_failure_rolls_back_current_switch(self):
        old = self.snapshot(self.players[0])
        old.save()
        replacement = [self.snapshot(self.players[0], current=False)]
        scope = FeatureExtractionScope(
            mode="full",
            cohort_count=1,
            profiles=(),
            affected_player_ids=None,
            affected_team_ids=None,
        )
        original_update = QuerySet.update

        def fail_activation(queryset, **values):
            if values == {"is_current": True}:
                raise RuntimeError("activation failed")
            return original_update(queryset, **values)

        with patch.object(QuerySet, "update", new=fail_activation):
            with self.assertRaisesMessage(RuntimeError, "activation failed"):
                publish_feature_snapshots(self.competition_season, replacement, scope)

        current = PlayerSeasonRoleFeatureSnapshot.objects.get(
            competition_season=self.competition_season,
            player=self.players[0],
            team=self.team,
            is_current=True,
        )
        self.assertEqual(current.pk, old.pk)
        self.assertEqual(
            PlayerSeasonRoleFeatureSnapshot.objects.filter(
                competition_season=self.competition_season,
            ).count(),
            1,
        )

    def test_extraction_failure_leaves_current_rows_unchanged(self):
        old = self.snapshot(self.players[0])
        old.save()
        with patch(
            "ingestion.services.player_role_materialization.build_bounded_feature_rows",
            side_effect=RuntimeError("extraction failed"),
        ):
            with self.assertRaisesMessage(RuntimeError, "extraction failed"):
                materialize_bounded_player_role_features(
                    self.competition_season,
                    affected_player_ids=[self.players[0].id],
                )

        old.refresh_from_db()
        self.assertTrue(old.is_current)
        self.assertEqual(
            PlayerSeasonRoleFeatureSnapshot.objects.filter(
                competition_season=self.competition_season,
            ).count(),
            1,
        )
