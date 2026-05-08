from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from django.core.exceptions import ValidationError as DjangoValidationError
from sklearn.linear_model import Ridge, RidgeCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ingestion.derived_definitions import METRIC_FIELDS, METRIC_DEFINITIONS, SCORE_FIELDS
from ingestion.derived_api import BIG_FIVE_COMPETITION_CODES
from ingestion.models import CompetitionSeason, PlayerSeasonDerivedStats


@dataclass(frozen=True)
class RegressionFitResult:
    payload: dict[str, Any]


def _resolve_competition_season(competition: str, season: str) -> CompetitionSeason:
    try:
        return CompetitionSeason.objects.select_related("competition", "season").get(
            competition__short_code__iexact=competition,
            season__label__iexact=season,
        )
    except CompetitionSeason.DoesNotExist as exc:
        raise DjangoValidationError("Unknown competition and season combination.") from exc


def _resolve_competition_seasons(competition: str, season: str) -> tuple[str, str, list[CompetitionSeason]]:
    code = competition.strip().upper()
    if code not in {"BIG5", "ALL"}:
        cs = _resolve_competition_season(competition, season)
        return cs.competition.short_code, cs.season.label, [cs]

    rows = CompetitionSeason.objects.select_related("competition", "season").filter(
        is_active=True,
        season__label__iexact=season,
    )
    if code == "BIG5":
        rows = rows.filter(competition__short_code__in=BIG_FIVE_COMPETITION_CODES)
    competition_seasons = list(rows.order_by("competition__short_code"))
    if not competition_seasons:
        raise DjangoValidationError("Unknown competition and season combination.")
    return code, competition_seasons[0].season.label, competition_seasons


def _allowed_target_keys(position_group: str) -> set[str]:
    """Medium-curated raw-stat targets per outfield position."""
    if position_group == "FWD":
        return {
            "xg_per_90",
            "npxg_per_90",
            "goals_per_90",
            "shots_per_90",
            "assists_per_90",
            "key_passes_per_90",
            "chance_involvement_per_90",
            "goals_minus_npxg",
            "npxg_per_shot",
        }
    if position_group == "MID":
        return {
            "xg_per_90",
            "xa_per_90",
            "xgchain_per_90",
            "xgbuildup_per_90",
            "key_passes_per_90",
            "big_chances_created_per_90",
            "completed_passes_per_90",
            "pass_accuracy",
            "chance_involvement_per_90",
        }
    if position_group == "DEF":
        return {
            "tackles_per_90",
            "interceptions_per_90",
            "clearances_per_90",
            "defensive_action_density",
            "ball_recoveries_per_90",
            "xgbuildup_per_90",
            "xg_per_90",
            "xa_per_90",
            "pass_accuracy",
        }
    raise DjangoValidationError("position_group must be FWD, MID, or DEF.")


def _validate_predictors(predictor_keys: list[str]) -> None:
    seen: set[str] = set()
    for key in predictor_keys:
        if key in SCORE_FIELDS:
            raise DjangoValidationError("Predictors must be raw metrics only, not scores.")
        if key not in METRIC_FIELDS:
            raise DjangoValidationError(f"Unknown predictor metric '{key}'.")
        if key in seen:
            raise DjangoValidationError(f"Duplicate predictor '{key}'.")
        seen.add(key)


def _high_correlation_warnings(X: np.ndarray, predictor_keys: list[str], threshold: float = 0.9) -> list[str]:
    if X.shape[1] < 2 or X.shape[0] < 3:
        return []
    corr = np.corrcoef(X, rowvar=False)
    warnings: list[str] = []
    p = len(predictor_keys)
    for i in range(p):
        for j in range(i + 1, p):
            v = corr[i, j]
            if math.isfinite(v) and abs(v) >= threshold:
                a = METRIC_DEFINITIONS.get(predictor_keys[i], {}).get("label", predictor_keys[i])
                b = METRIC_DEFINITIONS.get(predictor_keys[j], {}).get("label", predictor_keys[j])
                warnings.append(
                    f"High correlation (|r|≈{abs(v):.2f}) between “{a}” and “{b}”. "
                    "Coefficients may split overlapping signal; interpret directionally."
                )
    return warnings


def fit_player_regression(
    *,
    competition: str,
    season: str,
    position_group: str,
    canonical_player_ids: list[int],
    target_key: str,
    predictor_keys: list[str],
) -> RegressionFitResult:
    if position_group not in {"FWD", "MID", "DEF"}:
        raise DjangoValidationError("position_group must be FWD, MID, or DEF.")

    allowed_targets = _allowed_target_keys(position_group)
    if target_key not in allowed_targets:
        raise DjangoValidationError(f"Target '{target_key}' is not allowed for {position_group}.")

    if not predictor_keys:
        raise DjangoValidationError("Select at least one predictor.")

    _validate_predictors(predictor_keys)

    competition_code, season_label, competition_seasons = _resolve_competition_seasons(competition, season)
    rows = list(
        PlayerSeasonDerivedStats.objects.filter(
            competition_season__in=competition_seasons,
            is_current=True,
            position_group__iexact=position_group,
            canonical_player_id__in=canonical_player_ids,
        ).select_related("canonical_player", "canonical_display_team")
    )
    cohort_rows = len(rows)
    if cohort_rows == 0:
        raise DjangoValidationError("No matching players for this cohort.")

    id_to_row = {r.canonical_player_id: r for r in rows}
    ordered_rows = [id_to_row[i] for i in canonical_player_ids if i in id_to_row]

    y_list: list[float] = []
    X_rows: list[list[float]] = []
    player_meta: list[tuple[int, str, str | None]] = []

    for row in ordered_rows:
        y_val = getattr(row, target_key, None)
        if y_val is None:
            continue
        x_vals: list[float] = []
        skip = False
        for pk in predictor_keys:
            xv = getattr(row, pk, None)
            if xv is None:
                skip = True
                break
            x_vals.append(float(xv))
        if skip:
            continue
        y_list.append(float(y_val))
        X_rows.append(x_vals)
        team_name = row.canonical_display_team.name if row.canonical_display_team else None
        player_meta.append((row.canonical_player_id, row.canonical_player.display_name, team_name))

    X = np.asarray(X_rows, dtype=float)
    y = np.asarray(y_list, dtype=float)
    usable = X.shape[0]
    dropped = cohort_rows - usable

    warnings: list[str] = []
    if usable < 30:
        raise DjangoValidationError(
            f"Need at least 30 players with non-null target and predictors; usable={usable}."
        )
    if usable < 50:
        warnings.append(
            f"Only {usable} usable rows after dropping missing values. "
            "Cross-validated metrics can be noisy; interpret cautiously."
        )
    if len(predictor_keys) > 6:
        warnings.append(
            f"{len(predictor_keys)} predictors selected. With n={usable}, large predictor sets "
            "increase overlap risk and make coefficients harder to read."
        )

    warnings.extend(_high_correlation_warnings(X, predictor_keys))

    n_splits = min(5, usable)
    cv = KFold(n_splits=n_splits, shuffle=True, random_state=42)
    alphas = np.logspace(-2.0, 4.0, num=22)

    ridge_cv = RidgeCV(alphas=alphas, cv=cv, scoring="neg_mean_squared_error")
    pipe_select = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("ridgecv", ridge_cv),
        ]
    )
    pipe_select.fit(X, y)
    alpha = float(pipe_select.named_steps["ridgecv"].alpha_)

    ridge_final = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("ridge", Ridge(alpha=alpha)),
        ]
    )
    y_oof = cross_val_predict(ridge_final, X, y, cv=cv)
    ridge_final.fit(X, y)
    y_hat_in = ridge_final.predict(X)

    r2_cv = float(r2_score(y, y_oof))
    mae_cv = float(mean_absolute_error(y, y_oof))
    rmse_cv = float(math.sqrt(mean_squared_error(y, y_oof)))
    r2_train = float(r2_score(y, y_hat_in))

    coefs = ridge_final.named_steps["ridge"].coef_
    intercept = float(ridge_final.named_steps["ridge"].intercept_)

    coef_payload = []
    order = sorted(range(len(predictor_keys)), key=lambda i: abs(float(coefs[i])), reverse=True)
    for i in order:
        key = predictor_keys[i]
        label = METRIC_DEFINITIONS.get(key, {}).get("label", key)
        coef_payload.append(
            {
                "key": key,
                "label": label,
                "coefficient_std": float(coefs[i]),
            }
        )

    predictions = []
    for idx, (pid, name, team) in enumerate(player_meta):
        actual = float(y[idx])
        pred_oof = float(y_oof[idx])
        predictions.append(
            {
                "canonical_player_id": pid,
                "canonical_player_name": name,
                "canonical_team_name": team,
                "actual": actual,
                "predicted_oof": pred_oof,
                "residual": float(actual - pred_oof),
            }
        )

    payload = {
        "model": "ridge",
        "alpha": alpha,
        "position_group": position_group,
        "competition_code": competition_code,
        "season_label": season_label,
        "sample": {
            "cohort_rows": cohort_rows,
            "usable_rows": usable,
            "dropped_rows": dropped,
        },
        "fit": {
            "r2_cv": r2_cv,
            "mae_cv": mae_cv,
            "rmse_cv": rmse_cv,
            "r2_train": r2_train,
        },
        "coefficients": coef_payload,
        "intercept": intercept,
        "predictions": predictions,
        "warnings": warnings,
    }
    return RegressionFitResult(payload=payload)
