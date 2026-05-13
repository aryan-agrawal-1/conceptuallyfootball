from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from ingestion.services import sofascore_client


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
