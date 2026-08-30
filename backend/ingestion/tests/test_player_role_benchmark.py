from pathlib import Path

from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase

from ingestion.services.player_role_benchmark import (
    BenchmarkWriteError,
    FLOAT_ABSOLUTE_TOLERANCE,
    REQUIRED_CORPUS_CLASSES,
    compare_values,
    load_corpus,
    read_only_queries,
)


class PlayerRoleBenchmarkContractTests(SimpleTestCase):
    def test_committed_corpus_covers_every_required_evidence_class(self):
        entries = load_corpus()
        covered = {category for entry in entries for category in entry.covers}
        self.assertEqual(covered, REQUIRED_CORPUS_CLASSES)
        self.assertEqual(
            [(entry.player_id, entry.team_id) for entry in entries if entry.player_id == 567],
            [(567, 34), (567, 30)],
        )
        substitute = next(entry for entry in entries if "low_minute_substitute" in entry.covers)
        self.assertEqual((substitute.player_id, substitute.team_id), (1046, 43))

    def test_comparator_allows_only_the_documented_float_tolerance(self):
        expected = {"exact": [1, "role", True, None], "value": 0.5}
        within_tolerance = {"exact": [1, "role", True, None], "value": 0.5 + FLOAT_ABSOLUTE_TOLERANCE / 2}
        outside_tolerance = {"exact": [1, "role", True, None], "value": 0.5 + FLOAT_ABSOLUTE_TOLERANCE * 2}

        self.assertEqual(compare_values(expected, within_tolerance), [])
        self.assertEqual(len(compare_values(expected, outside_tolerance)), 1)
        self.assertEqual(len(compare_values(expected, expected | {"exact": [1, "other", True, None]})), 1)

    def test_invalid_corpus_reports_missing_coverage(self):
        fixture = Path(__file__).resolve().parents[1] / "benchmarks" / "player_role_corpus_v1.json"
        entries = load_corpus(fixture)
        self.assertTrue(entries)


class PlayerRoleBenchmarkReadOnlyTests(TransactionTestCase):
    def test_database_write_guard_allows_reads_and_rejects_writes(self):
        with read_only_queries(), connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone(), (1,))
            with self.assertRaises(BenchmarkWriteError):
                cursor.execute("CREATE TEMPORARY TABLE benchmark_write_probe (id integer)")
