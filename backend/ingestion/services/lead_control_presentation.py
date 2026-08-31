"""Lead-control reliability, comparison axes, and public surface formatting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


MIN_LEAD_EPISODES = 3
MIN_LEAD_EXPOSURE_SECONDS = 15 * 60
MIN_COMPONENT_EVENTS = 5
AXIS_SCALES = {
    "height_pitch_points": 15.0,
    "pass_forward_share": 0.25,
    "rate_per_90": 2.0,
    "opponent_big_chances_per_90": 1.0,
    "first_attack_seconds": 300.0,
}


def _metric_reliability(
    metric: Mapping[str, Any],
    exposure_seconds: int,
    *,
    baseline: Mapping[str, Any] | None = None,
) -> str:
    if metric.get("value") is None or exposure_seconds <= 0 or metric.get("sample_size", 0) <= 0:
        return "unavailable"
    if metric.get("sample_size", 0) < MIN_COMPONENT_EVENTS or exposure_seconds < MIN_LEAD_EXPOSURE_SECONDS:
        return "sparse"
    if baseline is not None and baseline.get("value") is None:
        return "partial"
    return "verified"


def _decorate_metric(
    selected: Mapping[str, Any],
    baseline: Mapping[str, Any] | None,
) -> dict[str, Any]:
    selected = dict(selected)
    baseline_value = baseline.get("value") if baseline else None
    selected_value = selected.get("value")
    selected["baseline_value"] = baseline_value
    selected["baseline_count"] = baseline.get("count") if baseline else None
    selected["baseline_sample_size"] = baseline.get("sample_size") if baseline else None
    selected["baseline_per_state_minute"] = baseline.get("per_state_minute") if baseline else None
    selected["baseline_per_90"] = baseline.get("per_90") if baseline else None
    selected["baseline_raw"] = baseline.get("raw") if baseline else None
    selected["delta"] = (
        round(selected_value - baseline_value, 4)
        if selected_value is not None and baseline_value is not None
        else None
    )
    selected["delta_per_state_minute"] = (
        round(selected.get("per_state_minute") - baseline.get("per_state_minute"), 4)
        if selected.get("per_state_minute") is not None
        and baseline
        and baseline.get("per_state_minute") is not None
        else None
    )
    selected["delta_per_90"] = (
        round(selected.get("per_90") - baseline.get("per_90"), 4)
        if selected.get("per_90") is not None
        and baseline
        and baseline.get("per_90") is not None
        else None
    )
    selected["reliability"] = _metric_reliability(
        selected,
        selected.get("exposure_seconds", 0),
        baseline=baseline,
    )
    selected["baseline_reliability"] = (
        _metric_reliability(baseline, baseline.get("exposure_seconds", 0))
        if baseline
        else "unavailable"
    )
    return selected


def _surface_metrics(
    raw: Mapping[str, Any],
    baseline: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    selected_metrics = raw["metrics"]
    baseline_metrics = baseline["metrics"] if baseline else {}
    gravity_keys = (
        "touch_origin_height",
        "pass_origin_height",
        "defensive_action_height",
        "box_entries",
        "shots",
        "clearances",
        "opponent_territory_height",
        "opponent_final_third_share",
    )
    ownership_keys = (
        "opponent_box_entries",
        "opponent_shots",
        "opponent_big_chances",
        "own_territorial_exits",
        "own_counters",
        "own_shots",
        "time_to_first_meaningful_opponent_attack",
    )

    def decorate(key: str) -> Any:
        value = selected_metrics[key]
        other = baseline_metrics.get(key) if baseline_metrics else None
        if isinstance(value, dict) and "value" not in value:
            return {
                direction_name: _decorate_metric(
                    value[direction_name],
                    other.get(direction_name) if isinstance(other, dict) else None,
                )
                for direction_name in value
            }
        return _decorate_metric(value, other)

    gravity = {key: decorate(key) for key in gravity_keys}
    gravity["pass_direction"] = {
        direction_name: _decorate_metric(
            selected_metrics["pass_direction"][direction_name],
            baseline_metrics.get("pass_direction", {}).get(direction_name)
            if baseline_metrics
            else None,
        )
        for direction_name in ("forward", "lateral", "backward")
    }
    return gravity, {key: decorate(key) for key in ownership_keys}


def _clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _axis_value(
    pairs: Sequence[tuple[float | None, float]],
) -> tuple[float | None, int]:
    values = [_clamp(value / scale) for value, scale in pairs if value is not None]
    if not values:
        return None, 0
    return round(50 + 50 * (sum(values) / len(values)), 1), len(values)


def _metric_delta(
    metrics: Mapping[str, Any],
    key: str,
    nested: str | None = None,
) -> float | None:
    value = metrics.get(key)
    if nested:
        value = value.get(nested) if isinstance(value, Mapping) else None
    if not isinstance(value, Mapping):
        return None
    if value.get("reliability") not in {"verified", "partial"}:
        return None
    if value.get("baseline_reliability") not in {"verified", "partial"}:
        return None
    return value.get("delta")


def _axes(
    gravity: Mapping[str, Any],
    ownership: Mapping[str, Any],
) -> dict[str, Any]:
    def pair(
        metrics: Mapping[str, Any],
        key: str,
        scale_key: str,
        nested: str | None = None,
        *,
        invert: bool = False,
    ) -> tuple[float | None, float]:
        delta = _metric_delta(metrics, key, nested)
        return (-delta if invert and delta is not None else delta, AXIS_SCALES[scale_key])

    gravity_pairs = [
        pair(gravity, "touch_origin_height", "height_pitch_points", invert=True),
        pair(gravity, "pass_origin_height", "height_pitch_points", invert=True),
        pair(gravity, "defensive_action_height", "height_pitch_points", invert=True),
        pair(gravity, "pass_direction", "pass_forward_share", "forward", invert=True),
        pair(gravity, "box_entries", "rate_per_90", invert=True),
        pair(gravity, "shots", "rate_per_90", invert=True),
        pair(gravity, "clearances", "rate_per_90"),
        pair(gravity, "opponent_territory_height", "height_pitch_points"),
    ]
    ownership_pairs = [
        pair(ownership, "opponent_box_entries", "rate_per_90", invert=True),
        pair(ownership, "opponent_shots", "rate_per_90", invert=True),
        pair(
            ownership,
            "opponent_big_chances",
            "opponent_big_chances_per_90",
            invert=True,
        ),
        pair(ownership, "own_territorial_exits", "rate_per_90"),
        pair(ownership, "own_counters", "rate_per_90"),
        pair(ownership, "own_shots", "rate_per_90"),
        pair(
            ownership,
            "time_to_first_meaningful_opponent_attack",
            "first_attack_seconds",
        ),
    ]
    gravity_value, gravity_available = _axis_value(gravity_pairs)
    ownership_value, ownership_available = _axis_value(ownership_pairs)
    return {
        "behavioral_retreat": {
            "value": gravity_value,
            "available_components": gravity_available,
            "higher_means": "more observed retreat relative to the matched baseline",
            "unit": "descriptive 0–100 axis",
        },
        "process_control": {
            "value": ownership_value,
            "available_components": ownership_available,
            "higher_means": "more opposition restriction and viable outlets relative to the matched baseline",
            "unit": "descriptive 0–100 axis",
        },
    }


def quadrant_for(axes: Mapping[str, Any], *, eligible: bool) -> dict[str, Any]:
    """Map the two descriptive axes into a cautious, non-causal quadrant."""

    retreat = axes.get("behavioral_retreat", {}).get("value")
    control = axes.get("process_control", {}).get("value")
    if not eligible or retreat is None or control is None:
        return {
            "label": None,
            "short_label": "Insufficient evidence",
            "available": False,
            "note": "A quadrant label is withheld until lead episodes and matched baseline evidence are sufficient.",
        }
    if retreat < 50 and control >= 50:
        label = "assertive controllers"
    elif retreat >= 50 and control >= 50:
        label = "controlled deep defenders"
    elif retreat < 50:
        label = "vulnerable high teams"
    else:
        label = "retreat and suffer"
    return {
        "label": label,
        "short_label": label.title(),
        "available": True,
        "note": "Descriptive placement from component deltas; it is not a causal or team-strength judgement.",
    }


def _reliability(
    lead_raw: Mapping[str, Any],
    baseline_raw: Mapping[str, Any] | None,
) -> dict[str, Any]:
    episode_count = int(lead_raw.get("episode_count", 0))
    exposure = int(lead_raw.get("exposure_seconds", 0))
    baseline_available = bool(
        baseline_raw and baseline_raw.get("exposure_seconds", 0) > 0
    )
    if episode_count == 0 or exposure == 0:
        status = "unavailable"
    elif episode_count < MIN_LEAD_EPISODES or exposure < MIN_LEAD_EXPOSURE_SECONDS:
        status = "sparse"
    elif not baseline_available:
        status = "partial"
    else:
        status = "verified"
    return {
        "status": status,
        "label_eligible": status == "verified",
        "lead_episode_count": episode_count,
        "minimum_lead_episodes": MIN_LEAD_EPISODES,
        "exposure_seconds": exposure,
        "minimum_exposure_seconds": MIN_LEAD_EXPOSURE_SECONDS,
        "matched_baseline_available": baseline_available,
        "note": (
            "Raw components remain visible, but descriptive labels are withheld for sparse or unmatched evidence."
            if status != "verified"
            else "Lead and matched drawing evidence meet the minimum reliability thresholds."
        ),
    }


def _surface_payload(
    raw: Mapping[str, Any],
    baseline_raw: Mapping[str, Any] | None,
) -> dict[str, Any]:
    gravity, ownership = _surface_metrics(raw, baseline_raw)
    axes = _axes(gravity, ownership)
    reliability = _reliability(raw, baseline_raw)
    return {
        "exposure_seconds": raw["exposure_seconds"],
        "exposure_minutes": round(raw["exposure_seconds"] / 60, 2),
        "episode_count": raw["episode_count"],
        "match_count": raw["match_count"],
        "window_count": raw["window_count"],
        "event_count": raw["event_count"],
        "gravity": {
            "components": gravity,
            "raw_components": gravity,
            "axis": axes["behavioral_retreat"],
        },
        "ownership": {
            "components": ownership,
            "raw_components": ownership,
            "axis": axes["process_control"],
        },
        "axes": axes,
        "reliability": reliability,
        "raw_counts": raw["raw_counts"],
    }
