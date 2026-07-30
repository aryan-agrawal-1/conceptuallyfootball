import type { RegressionLabPredictionRow } from '../../types/api'

// Tune these three values to change the chart's responsive silhouette.
export const REGRESSION_SCATTER_ASPECT_RATIO = 1.8
export const REGRESSION_SCATTER_MIN_HEIGHT = 240
export const REGRESSION_SCATTER_MAX_HEIGHT = 520

/**
 * Creates the one numerical domain used by both axes. A constant dataset gets
 * a symmetric interval based on its order of magnitude (or one neutral unit at
 * zero), avoiding an unrelated fixed half-unit expansion.
 */
export function buildRegressionScatterDomain(
  rows: RegressionLabPredictionRow[],
): [number, number] {
  let minimum = Number.POSITIVE_INFINITY
  let maximum = Number.NEGATIVE_INFINITY

  for (const row of rows) {
    if (Number.isFinite(row.predicted_oof)) {
      minimum = Math.min(minimum, row.predicted_oof)
      maximum = Math.max(maximum, row.predicted_oof)
    }
    if (Number.isFinite(row.actual)) {
      minimum = Math.min(minimum, row.actual)
      maximum = Math.max(maximum, row.actual)
    }
  }

  if (!Number.isFinite(minimum) || !Number.isFinite(maximum)) return [0, 1]

  if (minimum === maximum) {
    const magnitude = Math.abs(minimum)
    const halfSpan =
      magnitude === 0 ? 1 : 10 ** Math.floor(Math.log10(magnitude)) * 0.1
    return [minimum - halfSpan, maximum + halfSpan]
  }

  const span = maximum - minimum
  const padding = span * 0.07
  return [minimum - padding, maximum + padding]
}
