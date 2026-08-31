"""Shared public State Lens contract for team event-profile endpoints."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
from typing import Mapping, TypeVar

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q, QuerySet

from ingestion.models import (
    MatchEventGameState,
    MatchGameStateExclusionReason,
    MatchStateDrawProvenance,
    MatchStatePhase,
    ProviderMatchGameState,
    ProviderMatchTeamGameStateEpisode,
)
from ingestion.services.game_state import (
    GAME_STATE_CALCULATION_VERSION,
    scope_events_to_focal_state,
)


STATE_LENS_API_VERSION = "state_lens_v1"
STATE_VALUES = {
    "drawing": MatchEventGameState.DRAWING,
    "winning": MatchEventGameState.WINNING,
    "losing": MatchEventGameState.LOSING,
}
PHASE_VALUES = {value for value, _ in MatchStatePhase.choices}
PROVENANCE_VALUES = {value for value, _ in MatchStateDrawProvenance.choices}
SCOPE_FIELDS = (
    "state",
    "goal_difference",
    "phase",
    "draw_provenance",
    "minimum_state_age_seconds",
    "maximum_state_age_seconds",
)
Cohort = TypeVar("Cohort")


@dataclass(frozen=True, slots=True)
class StateLensScope:
    state: str = "all"
    goal_difference: int | None = None
    phase: str | None = None
    draw_provenance: str | None = None
    minimum_state_age_seconds: int | None = None
    maximum_state_age_seconds: int | None = None

    @property
    def is_default(self) -> bool:
        return self == StateLensScope()

    def event_filters(self) -> dict:
        return {
            "state": STATE_VALUES.get(self.state),
            "goal_difference": self.goal_difference,
            "phase": self.phase,
            "draw_provenance": self.draw_provenance,
            "minimum_state_age_seconds": self.minimum_state_age_seconds,
            "maximum_state_age_seconds": self.maximum_state_age_seconds,
        }

    def public(self) -> dict:
        return {field: getattr(self, field) for field in SCOPE_FIELDS}

    def cache_scope(self) -> tuple:
        return tuple(getattr(self, field) for field in SCOPE_FIELDS)

    def matches_context(self, context: Mapping) -> bool:
        if self.state != "all" and context.get("state") != self.state:
            return False
        for field in ("goal_difference", "phase", "draw_provenance"):
            expected = getattr(self, field)
            if expected is not None and context.get(field) != expected:
                return False
        age = context.get("state_age_seconds")
        return not (
            self.minimum_state_age_seconds is not None
            and (age is None or age < self.minimum_state_age_seconds)
            or self.maximum_state_age_seconds is not None
            and (age is None or age >= self.maximum_state_age_seconds)
        )


@dataclass(frozen=True, slots=True)
class StateLens:
    selected: StateLensScope
    baseline: StateLensScope | None

    @property
    def comparison_enabled(self) -> bool:
        return self.baseline is not None

    def cache_scope(self) -> dict:
        return {
            "contract": STATE_LENS_API_VERSION,
            "selected": self.selected.cache_scope(),
            "baseline": self.baseline.cache_scope() if self.baseline else None,
        }

    def source_token(self) -> str:
        raw = json.dumps(self.cache_scope(), sort_keys=True, separators=(",", ":"))
        return f"{STATE_LENS_API_VERSION}:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def parse_state_lens(request) -> StateLens:
    selected = parse_scope(request, prefix="")
    baseline_present = any(
        f"baseline_{field}" in request.query_params for field in SCOPE_FIELDS
    )
    baseline = parse_scope(request, prefix="baseline_") if baseline_present else None
    return StateLens(selected=selected, baseline=baseline)


def parse_scope(request, *, prefix: str) -> StateLensScope:
    def value(name: str):
        raw = request.query_params.get(f"{prefix}{name}")
        return raw.strip().lower() if raw not in (None, "") else None

    state = value("state") or "all"
    if state not in {"all", *STATE_VALUES}:
        raise lens_error(prefix, "state", "must be all, drawing, winning, or losing")

    goal_difference = parse_integer(request, prefix, "goal_difference", signed=True)
    minimum_age = parse_integer(
        request, prefix, "minimum_state_age_seconds", signed=False
    )
    maximum_age = parse_integer(
        request, prefix, "maximum_state_age_seconds", signed=False
    )
    phase = value("phase")
    if phase is not None and phase not in PHASE_VALUES:
        raise lens_error(
            prefix,
            "phase",
            "must be first_half, second_half, first_extra_time, or second_extra_time",
        )
    provenance = value("draw_provenance")
    if provenance is not None and provenance not in PROVENANCE_VALUES:
        raise lens_error(
            prefix,
            "draw_provenance",
            "must be none, neutral, restored, or surrendered",
        )

    if minimum_age is not None and maximum_age is not None and minimum_age >= maximum_age:
        raise lens_error(
            prefix,
            "state_age",
            "minimum_state_age_seconds must be less than maximum_state_age_seconds",
        )
    if goal_difference is not None:
        expected = (
            "winning" if goal_difference > 0 else "losing" if goal_difference < 0 else "drawing"
        )
        if state not in {"all", expected}:
            raise lens_error(
                prefix,
                "goal_difference",
                f"{goal_difference} is incompatible with state={state}",
            )
    drawing_scope = state == "drawing" or goal_difference == 0
    non_drawing_scope = state in {"winning", "losing"} or (
        goal_difference is not None and goal_difference != 0
    )
    if provenance == MatchStateDrawProvenance.NONE and drawing_scope:
        raise lens_error(prefix, "draw_provenance", "none is incompatible with a drawing scope")
    if provenance not in (None, MatchStateDrawProvenance.NONE) and non_drawing_scope:
        raise lens_error(
            prefix,
            "draw_provenance",
            f"{provenance} is only valid for drawing observations",
        )

    return StateLensScope(
        state=state,
        goal_difference=goal_difference,
        phase=phase,
        draw_provenance=provenance,
        minimum_state_age_seconds=minimum_age,
        maximum_state_age_seconds=maximum_age,
    )


def parse_integer(request, prefix: str, name: str, *, signed: bool) -> int | None:
    raw = request.query_params.get(f"{prefix}{name}")
    if raw in (None, ""):
        return None
    try:
        result = int(raw)
    except (TypeError, ValueError) as exc:
        qualifier = "an integer" if signed else "a non-negative integer"
        raise lens_error(prefix, name, f"must be {qualifier}") from exc
    if not signed and result < 0:
        raise lens_error(prefix, name, "must be a non-negative integer")
    return result


def lens_error(prefix: str, field: str, message: str) -> DjangoValidationError:
    parameter = f"{prefix}{field}"
    return DjangoValidationError(f"Invalid State Lens parameter '{parameter}': {message}.")


def scope_team_events(queryset: QuerySet, focal_team_id: int, scope: StateLensScope):
    if scope.is_default:
        return queryset
    return scope_events_to_focal_state(
        queryset, focal_team_id, **scope.event_filters()
    )


def state_lens_metadata(
    focal_team_id: int,
    matches,
    lens: StateLens,
) -> dict:
    match_ids = [int(getattr(match, "pk", match)) for match in matches]
    selected_evidence = scope_evidence(focal_team_id, match_ids, lens.selected)
    baseline_evidence = (
        scope_evidence(focal_team_id, match_ids, lens.baseline)
        if lens.baseline is not None
        else None
    )
    return {
        "contract_version": STATE_LENS_API_VERSION,
        "selected": lens.selected.public(),
        "evidence": selected_evidence,
        "eligible_refinements": eligible_refinements(focal_team_id, match_ids),
        "comparison": {
            "enabled": lens.comparison_enabled,
            "baseline": lens.baseline.public() if lens.baseline else None,
            "baseline_evidence": baseline_evidence,
            "comparison": lens.selected.public(),
            "comparison_evidence": selected_evidence,
        },
    }


def build_state_lens_cohorts(
    lens: StateLens,
    metadata: dict,
    builder: Callable[[StateLensScope, dict], Cohort],
) -> tuple[Cohort, Cohort | None]:
    selected = builder(lens.selected, metadata["evidence"])
    baseline = (
        builder(lens.baseline, metadata["comparison"]["baseline_evidence"])
        if lens.baseline is not None
        else None
    )
    return selected, baseline


def scope_evidence(focal_team_id: int, match_ids: list[int], scope: StateLensScope) -> dict:
    rows = episode_rows(focal_team_id, match_ids, scope)
    exposure_seconds = 0
    episodes = set()
    included_matches = set()
    for row in rows:
        start = row.start_second
        end = row.end_second
        if scope.minimum_state_age_seconds is not None:
            start = max(start, row.state_entry_second + scope.minimum_state_age_seconds)
        if scope.maximum_state_age_seconds is not None:
            end = min(end, row.state_entry_second + scope.maximum_state_age_seconds)
        if end <= start:
            continue
        exposure_seconds += end - start
        episodes.add((row.provider_match_id, row.episode_index))
        included_matches.add(row.provider_match_id)

    audits = ProviderMatchGameState.objects.filter(provider_match_id__in=match_ids)
    audit_counts = audits.aggregate(
        total=Count("id"),
        eligible=Count("id", filter=Q(eligible=True)),
    )
    reasons = {
        str(row["exclusion_reason"] or MatchGameStateExclusionReason.INVALID_SCORE_REPLAY): row["count"]
        for row in audits.filter(eligible=False)
        .values("exclusion_reason")
        .annotate(count=Count("id"))
    }
    missing = len(match_ids) - audit_counts["total"]
    if missing:
        key = str(MatchGameStateExclusionReason.INVALID_SCORE_REPLAY)
        reasons[key] = reasons.get(key, 0) + missing
    return {
        "exposure_seconds": exposure_seconds,
        "exposure_minutes": round(exposure_seconds / 60, 2),
        "episode_count": len(episodes),
        "match_count": len(included_matches),
        "matches_included": audit_counts["eligible"],
        "matches_excluded": len(match_ids) - audit_counts["eligible"],
        "exclusion_reasons": dict(sorted(reasons.items())),
        "formula_version": GAME_STATE_CALCULATION_VERSION,
        "empty": exposure_seconds == 0,
        "reliability": {
            "eligible_only": True,
            "timeline": "half_open_played_seconds",
            "shootouts_included": False,
        },
    }


def episode_rows(focal_team_id: int, match_ids: list[int], scope: StateLensScope):
    rows = ProviderMatchTeamGameStateEpisode.objects.filter(
        provider_match_id__in=match_ids,
        focal_team_id=focal_team_id,
    )
    filters = {
        "state": STATE_VALUES.get(scope.state),
        "goal_difference": scope.goal_difference,
        "phase": scope.phase,
        "draw_provenance": scope.draw_provenance,
    }
    return rows.filter(**{key: value for key, value in filters.items() if value is not None})


def eligible_refinements(focal_team_id: int, match_ids: list[int]) -> dict:
    rows = list(
        ProviderMatchTeamGameStateEpisode.objects.filter(
            provider_match_id__in=match_ids,
            focal_team_id=focal_team_id,
        ).values_list(
            "state",
            "goal_difference",
            "phase",
            "draw_provenance",
            "state_entry_second",
            "end_second",
            named=True,
        )
    )
    states = {
        MatchEventGameState.DRAWING: "drawing",
        MatchEventGameState.WINNING: "winning",
        MatchEventGameState.LOSING: "losing",
    }
    return {
        "states": sorted(
            {states[row.state] for row in rows if row.state in states}
        ),
        "goal_differences": sorted({row.goal_difference for row in rows}),
        "phases": sorted({row.phase for row in rows}),
        "draw_provenances": sorted({row.draw_provenance for row in rows}),
        "state_age_seconds": {
            "minimum": 0 if rows else None,
            "maximum": max(
                (row.end_second - row.state_entry_second for row in rows),
                default=None,
            ),
        },
    }
