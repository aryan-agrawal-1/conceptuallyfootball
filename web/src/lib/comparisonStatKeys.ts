import type { PositionGroup, StatMeta } from '../types/api'
import {
  COMPARISON_STAT_MAX,
  COMPARISON_STAT_MIN,
} from './comparisonConstants'
import { defaultPizzaMetricKeys } from './profileMetrics'

function filterValidMetricKeys(
  keys: string[],
  meta: StatMeta,
  positionGroup: PositionGroup,
): string[] {
  return keys.filter(
    k => k in meta.metrics && !(positionGroup === 'GK' && k === 'rating'),
  )
}

/**
 * Stat keys for the comparison chart/table.
 * - If URL provided enough valid keys (>= min), use them (capped at max).
 * - Otherwise use position defaults (pizza presets), padded from all metrics if needed.
 */
export function resolveComparisonStatKeys(
  urlStats: string[] | null,
  positionGroup: PositionGroup,
  meta: StatMeta,
): string[] {
  const excludeGkRating = (k: string) => !(positionGroup === 'GK' && k === 'rating')

  if (urlStats?.length) {
    const v = filterValidMetricKeys(urlStats, meta, positionGroup)
    if (v.length >= COMPARISON_STAT_MIN) {
      return v.slice(0, COMPARISON_STAT_MAX)
    }
  }

  const defaults = defaultPizzaMetricKeys(positionGroup).filter(
    k => k in meta.metrics && excludeGkRating(k),
  )

  let out = defaults.slice(0, COMPARISON_STAT_MAX)

  if (out.length < COMPARISON_STAT_MIN) {
    const rest = Object.keys(meta.metrics)
      .filter(k => excludeGkRating(k) && !out.includes(k))
      .sort((a, b) => a.localeCompare(b))
    for (const k of rest) {
      out.push(k)
      if (out.length >= COMPARISON_STAT_MIN) break
    }
  }

  return out.slice(0, COMPARISON_STAT_MAX)
}
