from __future__ import annotations

from collections import OrderedDict

from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.api_cache import get_or_build_payload, joined_version, model_version, stable_cache_key
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


def _aggregate_metric_availability(items):
    payloads = [item for item in items if item]
    if not payloads:
        return None

    def intersect_list(key):
        sets = [set(payload.get(key) or []) for payload in payloads]
        if not sets:
            return []
        return sorted(set.intersection(*sets))

    def union_list(key):
        out = set()
        for payload in payloads:
            out.update(payload.get(key) or [])
        return sorted(out)

    low_coverage_metrics = {}
    for payload in payloads:
        low_coverage_metrics.update(payload.get("low_coverage_metrics") or {})

    scores = {}
    score_names = set()
    for payload in payloads:
        score_names.update((payload.get("scores") or {}).keys())
    for score_name in sorted(score_names):
        score_payloads = [
            (payload.get("scores") or {}).get(score_name)
            for payload in payloads
            if (payload.get("scores") or {}).get(score_name)
        ]
        scores[score_name] = {
            "available": bool(score_payloads) and all(item.get("available") for item in score_payloads),
        }

    return {
        "player_data_mode": "aggregate",
        "available_metrics": union_list("available_metrics"),
        "ui_available_metrics": intersect_list("ui_available_metrics"),
        "default_metrics": intersect_list("default_metrics"),
        "low_coverage_metrics": low_coverage_metrics,
        "unavailable_metrics": union_list("unavailable_metrics"),
        "scores": scores,
        "available_scores": sorted(
            score_name for score_name, payload in scores.items() if payload.get("available")
        ),
        "unavailable_scores": sorted(
            score_name for score_name, payload in scores.items() if not payload.get("available")
        ),
    }


class CompetitionSeasonsCatalogApi(APIView):
    """
    Active competition-season slices for UI dropdowns.
    Seasons are nested under each competition (a league may not have every season).
    """

    def get(self, request):
        cache_key = stable_cache_key("competition-seasons", {"path": request.path})
        source_version = joined_version("competition-seasons", model_version(CompetitionSeason))

        payload, _ = get_or_build_payload(
            cache_key=cache_key,
            source_version=source_version,
            builder=self._build_payload,
        )
        return Response(payload)

    def _build_payload(self) -> dict:
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
        all_season_availability: dict[str, list[dict]] = {}
        big_five_season_availability: dict[str, list[dict]] = {}
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
            all_season_availability.setdefault(cs.season.label, []).append(cs.metric_availability)
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
                big_five_season_availability.setdefault(cs.season.label, []).append(cs.metric_availability)

        aggregate_entries = []
        if all_seasons:
            for label, payload in all_seasons.items():
                payload["metric_availability"] = _aggregate_metric_availability(
                    all_season_availability.get(label) or []
                )
            aggregate_entries.append(
                {
                    "code": "ALL",
                    "name": "All",
                    "seasons": list(all_seasons.values()),
                }
            )
        if big_five_seasons:
            for label, payload in big_five_seasons.items():
                payload["metric_availability"] = _aggregate_metric_availability(
                    big_five_season_availability.get(label) or []
                )
            aggregate_entries.append(
                {
                    "code": "BIG5",
                    "name": "Big 5",
                    "seasons": list(big_five_seasons.values()),
                }
            )
        return {"competitions": aggregate_entries + list(by_code.values())}
