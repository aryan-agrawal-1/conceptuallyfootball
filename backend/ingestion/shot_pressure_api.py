"""Cached public API for state-conditioned team shot pressure."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.api_cache import (
    get_or_build_payload_response,
    joined_version,
    model_version,
    stable_cache_key,
)
from ingestion.event_profile_api import (
    event_queryset,
    parse_optional_match,
    resolve_event_profile_competition_season,
    scope_queryset_to_match,
)
from ingestion.models import (
    MatchEventType,
    ProviderMatchEvent,
    ProviderMatchGameState,
    ProviderMatchTeamGameStateEpisode,
    TeamSeasonEventProfile,
)
from ingestion.services.shot_pressure import (
    PENALTY_MODES,
    SHOT_PRESSURE_FORMULA_VERSION,
    cohort_payload,
    penalty_mode_shots,
)
from ingestion.state_lens import parse_state_lens, scope_team_events, state_lens_metadata


SHOT_PRESSURE_API_VERSION = "v1"


def parse_penalty_mode(request) -> str:
    value = (request.query_params.get("penalty_mode") or "exclude").strip().lower()
    if value not in PENALTY_MODES:
        raise DjangoValidationError(
            "penalty_mode must be exclude, include, or only."
        )
    return value


class TeamShotPressureApi(APIView):
    def get(self, request, canonical_team_id: int):
        try:
            competition_season = resolve_event_profile_competition_season(request)
            profile = TeamSeasonEventProfile.objects.select_related(
                "team", "competition_season__competition", "competition_season__season"
            ).get(
                competition_season=competition_season,
                team_id=canonical_team_id,
                is_current=True,
            )
            match_ref = parse_optional_match(request)
            lens = parse_state_lens(request)
            penalty_mode = parse_penalty_mode(request)
            cache_key = stable_cache_key(
                f"shot-pressure:{competition_season.id}:team",
                {
                    "endpoint": "team-shot-pressure",
                    "team": canonical_team_id,
                    "competition": competition_season.competition.short_code,
                    "season": competition_season.season.label,
                    "match": match_ref,
                    "penalty_mode": penalty_mode,
                    "state_lens": lens.cache_scope(),
                    "formula_version": SHOT_PRESSURE_FORMULA_VERSION,
                },
            )
            source_version = joined_version(
                SHOT_PRESSURE_API_VERSION,
                SHOT_PRESSURE_FORMULA_VERSION,
                model_version(
                    ProviderMatchEvent,
                    {"provider_match__competition_season": competition_season},
                ),
                model_version(
                    ProviderMatchGameState,
                    {"provider_match__competition_season": competition_season},
                ),
                model_version(
                    ProviderMatchTeamGameStateEpisode,
                    {"provider_match__competition_season": competition_season},
                ),
            )
            response, _ = get_or_build_payload_response(
                cache_key=cache_key,
                source_version=source_version,
                builder=lambda: self.build_payload(
                    profile, match_ref, lens, penalty_mode
                ),
            )
            return response
        except DjangoValidationError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except TeamSeasonEventProfile.DoesNotExist:
            return Response(
                {"detail": "Team shot-pressure profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def build_payload(self, profile, match_ref, lens, penalty_mode: str) -> dict:
        team_match_ids = event_queryset(profile.competition_season).filter(
            team_id=profile.team_id
        ).values("provider_match_id")
        universe, matches, _references = scope_queryset_to_match(
            event_queryset(profile.competition_season).filter(
                provider_match_id__in=team_match_ids
            ),
            match_ref,
            profile.team_id,
        )
        match_ids = list(universe.values_list("provider_match_id", flat=True).distinct())
        shots = universe.filter(event_type=MatchEventType.SHOT)

        lens_metadata = state_lens_metadata(profile.team_id, match_ids, lens)

        def build_cohort(scope, evidence):
            scoped = scope_team_events(shots, profile.team_id, scope)
            return cohort_payload(
                focal_team_id=profile.team_id,
                match_ids=match_ids,
                scoped_shots=penalty_mode_shots(scoped, penalty_mode),
                scope=scope,
                evidence=evidence,
            )

        selected = build_cohort(lens.selected, lens_metadata["evidence"])
        baseline = (
            build_cohort(
                lens.baseline,
                lens_metadata["comparison"]["baseline_evidence"],
            )
            if lens.baseline is not None
            else None
        )
        return {
            "contract_version": SHOT_PRESSURE_API_VERSION,
            "formula_version": SHOT_PRESSURE_FORMULA_VERSION,
            "canonical_team_id": profile.team_id,
            "canonical_team_name": profile.team.name,
            "competition_season": profile.competition_season_id,
            "competition_code": profile.competition_season.competition.short_code,
            "season_label": profile.competition_season.season.label,
            "penalty_mode": penalty_mode,
            "penalty_note": (
                "Penalties are excluded from tactical frequency by default; use "
                "penalty_mode=include or penalty_mode=only explicitly."
            ),
            "fast_break_note": (
                "Fast break means provider-tagged fast-break shots only; it is not a "
                "complete counter-attack count."
            ),
            "measurement_note": (
                "Frequency, location share, and observed outcome are separate measures. "
                "No event-level xG or pseudo-xG is calculated."
            ),
            "state_lens": lens_metadata,
            "selected": selected,
            "comparison": {
                "enabled": baseline is not None,
                "baseline": baseline,
                "selected_minus_baseline": (
                    comparison_delta(selected, baseline) if baseline is not None else None
                ),
            },
            "matches": matches,
            "selected_match_ref": match_ref,
        }


def comparison_delta(selected: dict, baseline: dict) -> dict:
    """Rate differences on aligned cells; never event-dot subtraction."""

    def delta(value, other):
        if value is None or other is None:
            return None
        return round(value - other, 4)

    frequency = {}
    for perspective in ("for", "against"):
        frequency[perspective] = {}
        for metric, selected_value in selected["frequency"][perspective].items():
            baseline_value = baseline["frequency"][perspective][metric]
            frequency[perspective][metric] = {
                "per_minute": delta(
                    selected_value["per_minute"], baseline_value["per_minute"]
                ),
                "per_90": delta(selected_value["per_90"], baseline_value["per_90"]),
            }
    frequency["openness"] = {
        "shots_per_minute": delta(
            selected["frequency"]["openness"]["shots_per_minute"],
            baseline["frequency"]["openness"]["shots_per_minute"],
        ),
        "shots_per_90": delta(
            selected["frequency"]["openness"]["shots_per_90"],
            baseline["frequency"]["openness"]["shots_per_90"],
        ),
    }
    location = {}
    for perspective in ("for", "against"):
        location[perspective] = []
        for selected_cell, baseline_cell in zip(
            selected["location"][perspective]["cells"],
            baseline["location"][perspective]["cells"],
            strict=True,
        ):
            location[perspective].append(
                {
                    "column": selected_cell["column"],
                    "row": selected_cell["row"],
                    "shots_per_90_delta": delta(
                        selected_cell["shots_per_90"], baseline_cell["shots_per_90"]
                    ),
                    "location_share_delta": delta(
                        selected_cell["location_share"], baseline_cell["location_share"]
                    ),
                    "observed_conversion_delta": delta(
                        selected_cell["observed_conversion"],
                        baseline_cell["observed_conversion"],
                    ),
                }
            )
    return {"frequency": frequency, "location": location}
