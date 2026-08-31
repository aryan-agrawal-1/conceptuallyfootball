from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase

from ingestion.services.whoscored_pipeline_benchmark import (
    BenchmarkWriteError,
    QueryMetrics,
    benchmark_stage,
    measured_read_only_queries,
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
