import type { MetricSemanticColor } from '../types/api'

/** Minutes below which we warn on comparisons (matches matrix default filter). */
export const COMPARISON_MIN_MINUTES_WARNING = 900

/** Same floor as profile polar chart. */
export const COMPARISON_STAT_MIN = 4

/** Matches the shared full-profile template while keeping custom selections bounded. */
export const COMPARISON_STAT_MAX = 12

/** Fixed slot colors: stroke + translucent fill (HUD-aligned). */
export const COMPARISON_SLOT_STROKES = [
  'rgba(74, 158, 245, 0.95)',
  'rgba(52, 211, 153, 0.95)',
  'rgba(251, 191, 36, 0.95)',
] as const

export const COMPARISON_SLOT_FILLS = [
  'rgba(74, 158, 245, 0.24)',
  'rgba(52, 211, 153, 0.24)',
  'rgba(251, 191, 36, 0.24)',
] as const

/**
 * Presentation-only position for aligned comparison charts.
 * The stored statistical percentile is always displayed unchanged.
 */
export function comparisonPlotPercentile(
  percentile: number | null,
  semanticColor: MetricSemanticColor,
): number | null {
  if (percentile == null) return null
  const bounded = Math.max(0, Math.min(100, percentile))
  return semanticColor === 'negative' ? 100 - bounded : bounded
}

export function comparisonPercentileLabel(percentile: number): string {
  const rounded = Math.round(percentile)
  const suffix = percentileOrdinalSuffix(rounded)
  return `${rounded}${suffix} percentile`
}

export function comparisonCompactPercentileLabel(percentile: number): string {
  const rounded = Math.round(percentile)
  return `${rounded}${percentileOrdinalSuffix(rounded)}%`
}

function percentileOrdinalSuffix(percentile: number): string {
  return percentile % 100 >= 11 && percentile % 100 <= 13
    ? 'th'
    : percentile % 10 === 1
      ? 'st'
      : percentile % 10 === 2
        ? 'nd'
        : percentile % 10 === 3
          ? 'rd'
          : 'th'
}
