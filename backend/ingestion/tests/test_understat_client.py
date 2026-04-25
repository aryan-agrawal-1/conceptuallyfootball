from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from ingestion.services.understat_client import UnderstatLeagueConfig, fetch_league_players


class UnderstatClientTests(SimpleTestCase):
    @patch("ingestion.services.understat_client.requests.get")
    def test_provider_team_ids_use_league_team_title_map(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "teams": {
                "a": {"id": "71", "title": "Aston Villa"},
                "b": {"id": "78", "title": "Crystal Palace"},
            },
            "players": [
                {
                    "id": "1",
                    "player_name": "Example",
                    "team_title": "Aston Villa,Crystal Palace",
                    "games": "10",
                    "time": "500",
                }
            ],
        }
        mock_get.return_value = mock_resp

        rows = fetch_league_players(UnderstatLeagueConfig(league="EPL", season_year="2025"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["provider_team_ids"], ["71", "78"])
        self.assertEqual(rows[0]["team_id"], "71")
