from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.test import APIClient

from ingestion.regression_service import fit_player_regression


class RegressionApiGuardrailTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_rejects_excessive_player_id_count(self):
        response = self.client.post(
            "/api/v1/labs/regression/fit",
            {
                "competition": "EPL",
                "season": "2025-26",
                "position_group": "MID",
                "canonical_player_ids": list(range(1, 502)),
                "target_key": "xa_per_90",
                "predictor_keys": ["key_passes_per_90"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("more than 500 players", response.json()["detail"])

    def test_rejects_excessive_predictor_count(self):
        response = self.client.post(
            "/api/v1/labs/regression/fit",
            {
                "competition": "EPL",
                "season": "2025-26",
                "position_group": "MID",
                "canonical_player_ids": [1],
                "target_key": "xa_per_90",
                "predictor_keys": [f"metric_{i}" for i in range(9)],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("more than 8 metrics", response.json()["detail"])

    @patch("ingestion.regression_service.fit_player_regression")
    def test_rejects_target_as_predictor_with_clear_validation_error(self, fit_regression):
        response = self.client.post(
            "/api/v1/labs/regression/fit",
            {
                "competition": "EPL",
                "season": "2025-26",
                "position_group": "MID",
                "canonical_player_ids": [1],
                "target_key": "xa_per_90",
                "predictor_keys": ["key_passes_per_90", " xa_per_90 "],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "Target metric 'xa_per_90' cannot also be used as a predictor.",
        )
        fit_regression.assert_not_called()

    @patch("ingestion.regression_service._resolve_competition_seasons")
    def test_service_rejects_target_as_predictor_before_loading_model_rows(
        self,
        resolve_competition_seasons,
    ):
        with self.assertRaisesMessage(
            DjangoValidationError,
            "Target metric 'xa_per_90' cannot also be used as a predictor.",
        ):
            fit_player_regression(
                competition="EPL",
                season="2025-26",
                position_group="MID",
                canonical_player_ids=[1],
                target_key="xa_per_90",
                predictor_keys=["key_passes_per_90", "xa_per_90"],
            )

        resolve_competition_seasons.assert_not_called()

    @patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"regression_fit": "1/min"})
    def test_fit_endpoint_is_scoped_throttled(self):
        body = {
            "competition": "",
            "season": "",
            "position_group": "MID",
            "canonical_player_ids": [1],
            "target_key": "xa_per_90",
            "predictor_keys": ["key_passes_per_90"],
        }

        first = self.client.post("/api/v1/labs/regression/fit", body, format="json")
        second = self.client.post("/api/v1/labs/regression/fit", body, format="json")

        self.assertEqual(first.status_code, 400)
        self.assertEqual(second.status_code, 429)
