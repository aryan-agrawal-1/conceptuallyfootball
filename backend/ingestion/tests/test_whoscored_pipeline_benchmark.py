from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase

from ingestion.services.whoscored_pipeline_benchmark import (
    BenchmarkWriteError,
    QueryMetrics,
    benchmark_stage,
    measured_read_only_queries,
    materialized_output_digests,
    queryset_digest,
)


class WhoScoredPipelineBenchmarkContractTests(SimpleTestCase):
    def test_stage_records_timing_memory_queries_and_result(self):
        report = benchmark_stage("example", lambda: {"matches": 3})

        self.assertEqual(report["name"], "example")
        self.assertEqual(report["result"], {"matches": 3})
        self.assertGreaterEqual(report["wall_seconds"], 0)
        self.assertGreater(report["peak_rss_mb"], 0)
        self.assertGreaterEqual(report["peak_rss_mb"], report["rss_before_mb"])
        self.assertEqual(report["database_queries"], 0)


class WhoScoredPipelineBenchmarkReadOnlyTests(TransactionTestCase):
    def test_query_guard_allows_reads_and_rejects_writes(self):
        metrics = QueryMetrics()
        with measured_read_only_queries(metrics), connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone(), (1,))
            with self.assertRaises(BenchmarkWriteError):
                cursor.execute("CREATE TEMPORARY TABLE whoscored_benchmark_probe (id integer)")

        self.assertEqual(metrics.count, 1)
        self.assertGreaterEqual(metrics.elapsed_seconds, 0)

    def test_queryset_digest_ignores_excluded_fields(self):
        from ingestion.models import Season

        first = Season.objects.create(label="2025-26", sort_order=2026)
        digest = queryset_digest(
            Season.objects.all(),
            order_by=("label",),
            excluded={"id"},
        )
        first.id += 100

        self.assertEqual(digest["rows"], 1)
        self.assertEqual(len(digest["sha256"]), 64)

    def test_materialized_digest_ignores_version_row_metadata(self):
        from ingestion.models import (
            CanonicalPlayer,
            CanonicalTeam,
            Competition,
            CompetitionSeason,
            PlayerSeasonRole,
            PlayerSeasonRoleFeatureSnapshot,
            Season,
        )

        competition = Competition.objects.create(name="Test", short_code="TST")
        season = Season.objects.create(label="2024-25", sort_order=2025)
        competition_season = CompetitionSeason.objects.create(
            competition=competition,
            season=season,
        )
        team = CanonicalTeam.objects.create(name="Team")
        player = CanonicalPlayer.objects.create(display_name="Player")
        snapshots = []
        roles = []
        for current in (False, True):
            snapshot = PlayerSeasonRoleFeatureSnapshot.objects.create(
                competition_season=competition_season,
                player=player,
                team=team,
                feature_version="v1",
                features={"value": 1},
                source_event_version="v1",
                source_state_version="v1",
                source_participation_version="v1",
                source_possession_version="v1",
                is_current=current,
            )
            snapshots.append(snapshot)
            roles.append(PlayerSeasonRole.objects.create(
                competition_season=competition_season,
                player=player,
                team=team,
                feature_snapshot=snapshot,
                classification_shape="single",
                evidence_confidence="provisional",
                scoring_version="v1",
                is_current=current,
            ))

        current_digest = materialized_output_digests(competition_season)
        PlayerSeasonRoleFeatureSnapshot.objects.filter(pk=snapshots[1].pk).update(is_current=False)
        PlayerSeasonRoleFeatureSnapshot.objects.filter(pk=snapshots[0].pk).update(is_current=True)
        PlayerSeasonRole.objects.filter(pk=roles[1].pk).update(is_current=False)
        PlayerSeasonRole.objects.filter(pk=roles[0].pk).update(is_current=True)

        self.assertEqual(
            materialized_output_digests(competition_season),
            current_digest,
        )
