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

export const COMPARISON_SLOT_MARKERS = ['circle', 'square', 'diamond'] as const
export type ComparisonMarkerShape = (typeof COMPARISON_SLOT_MARKERS)[number]

export function comparisonMarkerForSlot(slot: number): ComparisonMarkerShape {
  return COMPARISON_SLOT_MARKERS[slot % COMPARISON_SLOT_MARKERS.length]
}

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
  const suffix =
    rounded % 100 >= 11 && rounded % 100 <= 13
      ? 'th'
      : rounded % 10 === 1
        ? 'st'
        : rounded % 10 === 2
          ? 'nd'
          : rounded % 10 === 3
            ? 'rd'
            : 'th'
  return `${rounded}${suffix} percentile`
}
