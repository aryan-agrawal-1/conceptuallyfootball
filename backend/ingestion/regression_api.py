from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from ingestion.regression_service import fit_player_regression

MAX_REGRESSION_PLAYER_IDS = 500
MAX_REGRESSION_PREDICTORS = 8


class RegressionLabFitApi(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "regression_fit"

    """
    POST body:
    {
      "competition": "EPL",
      "season": "2025-26",
      "position_group": "MID",
      "canonical_player_ids": [1, 2, ...],
      "target_key": "creation_score",
      "predictor_keys": ["key_passes_per_90", ...]
    }
    """

    def post(self, request):
        data = request.data
        competition = (data.get("competition") or "").strip()
        season = (data.get("season") or "").strip()
        position_group = (data.get("position_group") or "").strip().upper()
        ids = data.get("canonical_player_ids")
        target_key = (data.get("target_key") or "").strip()
        predictor_keys = data.get("predictor_keys")

        if not competition or not season:
            return Response(
                {"detail": "competition and season are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (
            not isinstance(ids, list)
            or not ids
            or not all(isinstance(i, int) and i > 0 for i in ids)
        ):
            return Response(
                {"detail": "canonical_player_ids must be a non-empty list of positive integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(ids) > MAX_REGRESSION_PLAYER_IDS:
            return Response(
                {"detail": f"canonical_player_ids cannot contain more than {MAX_REGRESSION_PLAYER_IDS} players."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(predictor_keys, list) or not predictor_keys:
            return Response(
                {"detail": "predictor_keys must be a non-empty list of strings."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not all(isinstance(k, str) and k.strip() for k in predictor_keys):
            return Response(
                {"detail": "Each predictor key must be a non-empty string."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(predictor_keys) > MAX_REGRESSION_PREDICTORS:
            return Response(
                {"detail": f"predictor_keys cannot contain more than {MAX_REGRESSION_PREDICTORS} metrics."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        predictor_keys = [k.strip() for k in predictor_keys]

        try:
            result = fit_player_regression(
                competition=competition,
                season=season,
                position_group=position_group,
                canonical_player_ids=ids,
                target_key=target_key,
                predictor_keys=predictor_keys,
            )
        except DjangoValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result.payload, status=status.HTTP_200_OK)
