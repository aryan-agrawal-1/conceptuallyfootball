import type { VisualiserBarDatum } from '../components/visualizer/VisualiserBarChart'
import type { VisualiserScatterDatum } from '../components/visualizer/VisualiserScatterPlot'
import { formatValue } from './format'
import {
  barKindForMetricKey,
  resolveProfileMetric,
  type ProfileRateMode,
} from './profileMetrics'
import type { PlayerRow, StatMeta, TeamSeasonRow } from '../types/api'
import { formatTeamStatMode, teamStatValueForMode } from './teamProfileMetrics'
import {
  rankBarCandidates,
  rankScatterPointsByTopRight,
  scatterLabelIds,
  type BarRankDatum,
  type ScatterRankDatum,
} from './visualiserRanking'

export const AUTO_HIGHLIGHT_LIMIT = 3
export type ChartPinMode = 'auto' | 'manual'

/** Top-right ranked scatter points used as the default (auto) highlighted entities. */
export function autoHighlightIds<T extends ScatterRankDatum>(points: T[]): number[] {
  return rankScatterPointsByTopRight(points)
    .slice(0, AUTO_HIGHLIGHT_LIMIT)
    .map(item => item.point.id)
}

/**
 * Default highlights for bar-only surfaces, ranked in the same direction as the
 * visible top/bottom window.
 */
export function autoBarHighlightIds<T extends BarRankDatum>(
  rows: T[],
  window: 'top' | 'bottom' | 'all',
): number[] {
  return rankBarCandidates(rows, window).slice(0, AUTO_HIGHLIGHT_LIMIT).map(item => item.id)
}

/**
 * Manual pins are validated against the plotted cohort; auto mode ignores them
 * entirely and falls back to the default highlight ranking.
 */
export function effectivePinIds(
  mode: ChartPinMode,
  manualIds: number[],
  autoIds: number[],
  availableIds: Iterable<number>,
): number[] {
  if (mode !== 'manual') return autoIds
  const available = new Set(availableIds)
  return manualIds.filter(id => available.has(id))
}

/**
 * Ranked slice for bar charts. Pinned entities stay in view even when they fall
 * outside the selected top/bottom cut.
 */
export function finalizeBarRows<T extends { id: number; value: number }>(
  rows: T[],
  window: 'top' | 'bottom' | 'all',
  count: number,
  pinnedIds: number[],
): T[] {
  const sorted = rows.toSorted((left, right) => right.value - left.value)
  let base = sorted
  if (window === 'top') base = sorted.slice(0, count)
  if (window === 'bottom') base = sorted.toReversed().slice(0, count)
  if (window === 'all') base = sorted
  const baseIds = new Set(base.map(row => row.id))
  const pinnedIdSet = new Set(pinnedIds)
  const extras = sorted.filter(row => pinnedIdSet.has(row.id) && !baseIds.has(row.id))
  return [...base, ...extras]
}

/** Relevance-first ordering shared by the entity pickers on both chart surfaces. */
export function relevanceSortedOptions<T extends { id: number; label: string }>(
  options: T[],
  relevanceIds: number[],
): T[] {
  const order = new Map(relevanceIds.map((id, index) => [id, index]))
  return options.toSorted(
    (left, right) =>
      (order.get(left.id) ?? Number.MAX_SAFE_INTEGER) -
        (order.get(right.id) ?? Number.MAX_SAFE_INTEGER) ||
      left.label.localeCompare(right.label),
  )
}

/** Large scatter cohorts label pinned entities only; smaller ones label everything. */
export function scatterLabelsFor(pointIds: number[], pinnedIds: number[], labelsEnabled: boolean): number[] {
  return scatterLabelIds(pointIds, pinnedIds, labelsEnabled)
}

export function playerScatterPoints(
  rows: PlayerRow[],
  meta: StatMeta,
  mode: ProfileRateMode,
  xKey: string,
  yKey: string,
): VisualiserScatterDatum[] {
  return rows.flatMap(row => {
    const x = resolveProfileMetric(row, mode, barKindForMetricKey(xKey), meta)
    const y = resolveProfileMetric(row, mode, barKindForMetricKey(yKey), meta)
    if (x.value == null || y.value == null) return []
    return [
      {
        id: row.canonical_player_id,
        label: row.canonical_player_name,
        sublabel: row.canonical_team_name ?? undefined,
        profileCompetition: row.competition_code,
        profileSeason: row.season_label,
        x: x.value,
        y: y.value,
        xText: formatValue(x.value, x.formatUnit),
        yText: formatValue(y.value, y.formatUnit),
        tieBreak: row.minutes,
      },
    ]
  })
}

export function teamScatterPoints(
  rows: TeamSeasonRow[],
  mode: ProfileRateMode,
  xKey: string,
  yKey: string,
): VisualiserScatterDatum[] {
  return rows.flatMap(row => {
    const xValue = teamStatValueForMode(xKey, row.stats[xKey], row.stats.matches ?? null, mode)
    const yValue = teamStatValueForMode(yKey, row.stats[yKey], row.stats.matches ?? null, mode)
    if (xValue == null || yValue == null) return []
    return [
      {
        id: row.canonical_team_id,
        label: row.canonical_team_name,
        x: xValue,
        y: yValue,
        xText: formatTeamStatMode(xKey, row.stats[xKey], row.stats.matches ?? null, mode),
        yText: formatTeamStatMode(yKey, row.stats[yKey], row.stats.matches ?? null, mode),
        tieBreak: row.stats.matches ?? 0,
      },
    ]
  })
}

export function playerBarCandidates(
  rows: PlayerRow[],
  meta: StatMeta,
  mode: ProfileRateMode,
  key: string,
): VisualiserBarDatum[] {
  return rows.flatMap(row => {
    const resolved = resolveProfileMetric(row, mode, barKindForMetricKey(key), meta)
    if (resolved.value == null) return []
    return [
      {
        id: row.canonical_player_id,
        label: row.canonical_player_name,
        sublabel: row.canonical_team_name ?? undefined,
        profileCompetition: row.competition_code,
        profileSeason: row.season_label,
        value: resolved.value,
        valueText: formatValue(resolved.value, resolved.formatUnit),
      },
    ]
  })
}

export function teamBarCandidates(
  rows: TeamSeasonRow[],
  mode: ProfileRateMode,
  key: string,
): VisualiserBarDatum[] {
  return rows.flatMap(row => {
    const value = teamStatValueForMode(key, row.stats[key], row.stats.matches ?? null, mode)
    if (value == null) return []
    return [
      {
        id: row.canonical_team_id,
        label: row.canonical_team_name,
        value,
        valueText: formatTeamStatMode(key, row.stats[key], row.stats.matches ?? null, mode),
      },
    ]
  })
}
