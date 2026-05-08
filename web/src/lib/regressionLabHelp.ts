/** User-facing explainer copy for Regression Lab (keep sentences plain). */

export const LAB_HELP = {
  targetPanel:
    'The raw-stat outcome you want the model to explain or predict for each player in the cohort. Pick one target per run.',
  predictorsPanel:
    'Raw stats used as inputs. The model estimates how those pieces move together with the target. Scores cannot be predictors here (only metrics). Rows missing any selected predictor or the target are dropped before fitting.',
  coefficientsPanel:
    'Each value is the ridge coefficient on standardized predictors (mean 0, variance 1). That makes magnitudes more comparable across different stat scales. Signs show direction; overlapping stats can share credit — read as exploratory, not causal.',
  oofScatter:
    'Each point is one player. “OOF” means out-of-fold: the predicted value is from models that did not train on that player in cross-validation, so the cloud is closer to honest out-of-sample behaviour than training-only fit.',
  fitCvR2:
    'Cross-validated R²: roughly what fraction of the target’s spread is explained when each player takes a turn being held out. More trustworthy than training R² for “does this pattern generalise in this cohort?”',
  fitCvMae:
    'Cross-validated MAE: typical absolute error between actual target and OOF prediction, in the same units as the target (e.g. per-90 or score points). Lower is better.',
  fitCvRmse:
    'Cross-validated RMSE: like MAE but punishes large misses more. Useful if a few players are badly misfit.',
  fitTrainR2:
    'Training R²: fit on the full usable sample. Often higher than CV R²; if it is much higher, the model may be hugging noise — compare to CV R².',
  fitSample:
    'Cohort rows are players after your filters. Usable rows are those with non-null target and every selected predictor. The rest are dropped for this run.',
  colPlayer: 'Player name in the modeled cohort.',
  colClub: 'Display club for this league season slice.',
  colActual: 'Observed target value for that player after listwise complete-case filtering.',
  colPredOof:
    'Out-of-fold prediction: ridge model trained without that row in the fold, then applied. Compare to Actual to see who sits above or below the cohort pattern.',
  colResidual: 'Actual minus OOF prediction. Large positive means the player outperformed the model for this target; large negative the opposite.',
  coefColumn:
    'Ridge coefficient when predictors are standardized (zero mean, unit variance). Compare magnitudes across predictors on a similar scale; shrinkage pulls small/unstable effects toward zero.',
} as const
