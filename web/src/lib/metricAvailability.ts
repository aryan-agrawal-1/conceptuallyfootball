import type { PlayerRow } from '../types/api'
import { barKindForMetricKey, resolveProfileMetric, type ProfileRateMode } from './profileMetrics'
import { teamStatValueForMode } from './teamProfileMetrics'

export function hasMetricCoverage<T>(
  rows: T[],
  resolve: (row: T) => number | null | undefined,
): boolean {
  return rows.some(row => resolve(row) != null)
}

export function usablePlayerMetricKeys(
  keys: string[],
  rows: PlayerRow[],
  mode: ProfileRateMode,
  meta: Parameters<typeof resolveProfileMetric>[3],
): string[] {
  if (!rows.length) return keys
  return keys.filter(key =>
    hasMetricCoverage(rows, row =>
      resolveProfileMetric(row, mode, barKindForMetricKey(key), meta).value,
    ),
  )
}

export function usableTeamMetricKeys<T extends { stats: Record<string, number | null | undefined> }>(
  keys: string[],
  rows: T[],
  mode: ProfileRateMode,
): string[] {
  if (!rows.length) return keys
  return keys.filter(key =>
    hasMetricCoverage(rows, row =>
      teamStatValueForMode(key, row.stats[key], row.stats.matches ?? null, mode),
    ),
  )
}

export function filterMetricGroups<T extends { key: string; items: Array<{ key: string }> }>(
  groups: T[],
  usableKeys: string[],
): T[] {
  const usable = new Set(usableKeys)
  return groups
    .map(group => ({
      ...group,
      items: group.items.filter(item => usable.has(item.key)),
    }))
    .filter(group => group.items.length > 0)
}
