from __future__ import annotations

from collections import OrderedDict

from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.models import CompetitionSeason


class CompetitionSeasonsCatalogApi(APIView):
    """
    Active competition-season slices for UI dropdowns.
    Seasons are nested under each competition (a league may not have every season).
    """

    def get(self, request):
        rows = (
            CompetitionSeason.objects.filter(is_active=True)
            .select_related("competition", "season")
            .order_by("competition__short_code", "-season__sort_order", "-season__label")
        )
        by_code: OrderedDict[str, dict] = OrderedDict()
        for cs in rows:
            code = cs.competition.short_code
            if code not in by_code:
                by_code[code] = {
                    "code": code,
                    "name": cs.competition.name,
                    "seasons": [],
                }
            by_code[code]["seasons"].append(
                {
                    "label": cs.season.label,
                    "competition_season_id": cs.id,
                }
            )
        return Response({"competitions": list(by_code.values())})
