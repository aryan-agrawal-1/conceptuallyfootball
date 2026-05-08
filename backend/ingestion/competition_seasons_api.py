from __future__ import annotations

from collections import OrderedDict

from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.derived_api import BIG_FIVE_COMPETITION_CODES
from ingestion.models import CompetitionSeason

COMPETITION_ORDER = {
    "ENG1": 0,
    "GER1": 1,
    "SPA1": 2,
    "FRA1": 3,
    "ITA1": 4,
    "SCO1": 5,
    "BEL1": 6,
    "NED1": 7,
    "POR1": 8,
    "ENG2": 9,
}


class CompetitionSeasonsCatalogApi(APIView):
    """
    Active competition-season slices for UI dropdowns.
    Seasons are nested under each competition (a league may not have every season).
    """

    def get(self, request):
        rows = (
            CompetitionSeason.objects.filter(is_active=True)
            .select_related("competition", "season")
            .order_by("-season__sort_order", "-season__label", "competition__short_code")
        )
        rows = sorted(
            rows,
            key=lambda cs: (
                COMPETITION_ORDER.get(cs.competition.short_code, 100),
                -cs.season.sort_order,
                cs.season.label,
            ),
        )
        by_code: OrderedDict[str, dict] = OrderedDict()
        all_seasons: OrderedDict[str, dict] = OrderedDict()
        big_five_seasons: OrderedDict[str, dict] = OrderedDict()
        for cs in rows:
            code = cs.competition.short_code
            if code not in by_code:
                by_code[code] = {
                    "code": code,
                    "name": cs.competition.name,
                    "seasons": [],
                }
            season_payload = {
                "label": cs.season.label,
                "competition_season_id": cs.id,
                "player_data_mode": cs.player_data_mode,
                "has_understat": cs.has_understat,
                "has_sofascore": cs.has_sofascore,
                "metric_availability": cs.metric_availability,
            }
            by_code[code]["seasons"].append(season_payload)
            all_seasons.setdefault(
                cs.season.label,
                {
                    "label": cs.season.label,
                    "competition_season_id": 0,
                    "player_data_mode": "aggregate",
                    "has_understat": None,
                    "has_sofascore": None,
                    "metric_availability": None,
                },
            )
            if code in BIG_FIVE_COMPETITION_CODES:
                big_five_seasons.setdefault(
                    cs.season.label,
                    {
                        "label": cs.season.label,
                        "competition_season_id": 0,
                        "player_data_mode": "aggregate",
                        "has_understat": None,
                        "has_sofascore": None,
                        "metric_availability": None,
                    },
                )

        aggregate_entries = []
        if big_five_seasons:
            aggregate_entries.append(
                {
                    "code": "BIG5",
                    "name": "Big 5",
                    "seasons": list(big_five_seasons.values()),
                }
            )
        if all_seasons:
            aggregate_entries.append(
                {
                    "code": "ALL",
                    "name": "All",
                    "seasons": list(all_seasons.values()),
                }
            )
        return Response({"competitions": aggregate_entries + list(by_code.values())})
