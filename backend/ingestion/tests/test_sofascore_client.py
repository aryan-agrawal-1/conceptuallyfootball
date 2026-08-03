from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from ingestion.services import sofascore_client
from ingestion.services.sofascore_team_client import build_team_season_rows


class SofascoreRequestClientTests(SimpleTestCase):
    @override_settings(STATBALLER_SOFASCORE_PROXY_URL="http://user:pass@geo.iproyal.com:12321")
    @patch("ingestion.services.sofascore_client.plain_requests.get")
    def test_request_get_falls_back_to_plain_requests_after_browser_transport_error(self, mock_plain_get):
        browser_get = Mock(side_effect=RuntimeError("TLS connect error"))
        plain_response = Mock(status_code=200)
        mock_plain_get.return_value = plain_response

        with patch.object(sofascore_client, "browser_requests", Mock(get=browser_get)):
            sofascore_client.reset_request_metrics()

            response = sofascore_client._request_get(
                "https://www.sofascore.com/api/v1/unique-tournament/17/season/76986/teams",
                params={},
                timeout=45,
            )

        self.assertEqual(response, plain_response)
        self.assertEqual(browser_get.call_count, 1)
        self.assertEqual(mock_plain_get.call_count, 1)
        self.assertEqual(sofascore_client.snapshot_request_metrics()["request_count"], 1)


class SofascoreTeamStageFilterTests(SimpleTestCase):
    @patch("ingestion.services.sofascore_team_client.fetch_team_overall_statistics")
    @patch("ingestion.services.sofascore_team_client.fetch_total_standings")
    @patch("ingestion.services.sofascore_team_client.fetch_season_teams")
    def test_allowed_provider_ids_exclude_qualifier_teams(
        self,
        mock_fetch_teams,
        mock_fetch_standings,
        mock_fetch_overall,
    ):
        mock_fetch_teams.return_value = [
            {"id": 10, "name": "Main stage"},
            {"id": 20, "name": "Qualifier"},
        ]
        mock_fetch_standings.return_value = []
        mock_fetch_overall.return_value = {"statistics": {}}

        rows = build_team_season_rows(
            sofascore_client.SofascoreSeasonConfig(unique_tournament_id=7, season_id=1),
            delay_seconds=0,
            allowed_provider_team_ids={"10"},
        )

        self.assertEqual([row["provider_team_id"] for row in rows], ["10"])

    @patch("ingestion.services.sofascore_team_client.fetch_season_teams")
    def test_empty_allowed_provider_ids_fail_instead_of_ingesting_all_teams(
        self,
        mock_fetch_teams,
    ):
        with self.assertRaisesMessage(ValueError, "no main-stage provider teams"):
            build_team_season_rows(
                sofascore_client.SofascoreSeasonConfig(unique_tournament_id=7, season_id=1),
                delay_seconds=0,
                allowed_provider_team_ids=set(),
            )

        mock_fetch_teams.assert_not_called()
