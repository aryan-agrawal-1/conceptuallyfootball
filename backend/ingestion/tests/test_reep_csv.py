from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import TestCase

from ingestion.models import ReepPlayerRow, ReepTeamRow
from ingestion.services.reep_csv import sync_reep_from_csv_dir


class ReepCsvSyncTests(TestCase):
    def test_csv_columns_match_official_reep_files(self):
        d = Path(tempfile.mkdtemp())
        (d / "people.csv").write_text(
            "reep_id,type,name,full_name,key_understat,key_sofascore\n"
            "reep_p1,player,Bob,Bob The,x1,501\n"
            "reep_c9,coach,Ignore,Coach,,,\n",
            encoding="utf-8",
        )
        (d / "teams.csv").write_text(
            "reep_id,name,key_understat,key_sofascore\n"
            "reep_t1,Alpha FC,,99\n",
            encoding="utf-8",
        )
        stats = sync_reep_from_csv_dir(d)
        self.assertEqual(stats, {"players": 1, "teams": 1})
        p = ReepPlayerRow.objects.get(reep_id="reep_p1")
        self.assertEqual(p.understat_player_id, "x1")
        self.assertEqual(p.sofascore_player_id, "501")
        t = ReepTeamRow.objects.get(reep_id="reep_t1")
        self.assertIsNone(t.understat_team_id)
        self.assertEqual(t.sofascore_team_id, "99")

    def test_team_csv_overrides_fix_known_understat_team_ids(self):
        d = Path(tempfile.mkdtemp())
        (d / "people.csv").write_text(
            "reep_id,type,name,full_name,key_understat,key_sofascore\n",
            encoding="utf-8",
        )
        (d / "teams.csv").write_text(
            "reep_id,name,key_understat,key_sofascore\n"
            "reep_tfa99f7f9,Brighton & Hove Albion F.C.,,\n"
            "reep_te6c8eca5,West Ham United F.C.,,\n"
            "reep_t70979bf6,SC Freiburg,220,\n",
            encoding="utf-8",
        )

        sync_reep_from_csv_dir(d)

        brighton = ReepTeamRow.objects.get(reep_id="reep_tfa99f7f9")
        west_ham = ReepTeamRow.objects.get(reep_id="reep_te6c8eca5")
        self.assertEqual(brighton.understat_team_id, "220")
        self.assertEqual(west_ham.understat_team_id, "81")
        self.assertFalse(ReepTeamRow.objects.filter(reep_id="reep_t70979bf6").exists())
