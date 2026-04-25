import type { ColumnUnit } from './columns'
import type { PlayerRow } from '../types/api'
import type { MatrixRateMode, ResolvedMatrixMetric } from './matrixRateMode'
import {
  cohortPercentileRank,
  per90ToSeasonApprox,
  totalToPer90,
} from './matrixRateMode'

type FullSource =
  | { kind: 'api'; key: string; formatUnit: ColumnUnit }
  | { kind: 'derived'; per90Key: string; formatUnit: ColumnUnit }

const GK_RATE_TOGGLE: Record<string, { per90Key: string; full: FullSource }> = {
  saves_per_90: {
    per90Key: 'saves_per_90',
    full: { kind: 'api', key: 'saves', formatUnit: 'integer' },
  },
  saved_shots_inside_box_per_90: {
    per90Key: 'saved_shots_inside_box_per_90',
    full: { kind: 'api', key: 'saved_shots_inside_box', formatUnit: 'integer' },
  },
  runs_out_per_90: {
    per90Key: 'runs_out_per_90',
    full: { kind: 'api', key: 'runs_out', formatUnit: 'integer' },
  },
  completed_passes_per_90: {
    per90Key: 'completed_passes_per_90',
    full: { kind: 'derived', per90Key: 'completed_passes_per_90', formatUnit: 'integer' },
  },
  accurate_long_balls_per_90: {
    per90Key: 'accurate_long_balls_per_90',
    full: { kind: 'derived', per90Key: 'accurate_long_balls_per_90', formatUnit: 'integer' },
  },
}

/** GK columns that use total→per90 cohort percentiles in per90 mode. */
const GK_TOTAL_RATE_TOGGLE: Record<string, { totalKey: string; fullUnit: ColumnUnit }> = {
  clean_sheets: { totalKey: 'clean_sheets', fullUnit: 'integer' },
  penalty_saves: { totalKey: 'penalty_saves', fullUnit: 'integer' },
}

const GK_GUESS_UNIT: Partial<Record<string, ColumnUnit>> = {
  rating: 'ratio',
  clean_sheet_rate: 'percentage',
  pass_accuracy: 'percentage',
}

export function headerTooltipGkMetricKey(columnId: string, rateMode: MatrixRateMode): string {
  const fromTotal = GK_TOTAL_RATE_TOGGLE[columnId]
  if (fromTotal) {
    return rateMode === 'per90' ? `${fromTotal.totalKey}_per90` : fromTotal.totalKey
  }
  const t = GK_RATE_TOGGLE[columnId]
  if (!t) return columnId
  if (rateMode === 'per90') return t.per90Key
  if (t.full.kind === 'api') return t.full.key
  return t.per90Key
}

export function resolveGkMatrixMetric(
  row: PlayerRow,
  columnId: string,
  rateMode: MatrixRateMode,
): ResolvedMatrixMetric {
  const fromTotal = GK_TOTAL_RATE_TOGGLE[columnId]
  if (fromTotal) {
    if (rateMode === 'per90') {
      return {
        value: totalToPer90(row.metrics[fromTotal.totalKey] ?? null, row.minutes),
        percentileKey: null,
        useCohortPercentile: true,
        formatUnit: 'per90',
      }
    }
    return {
      value: row.metrics[fromTotal.totalKey] ?? null,
      percentileKey: fromTotal.totalKey,
      useCohortPercentile: false,
      formatUnit: fromTotal.fullUnit,
    }
  }

  const def = GK_RATE_TOGGLE[columnId]
  if (!def) {
    const u = GK_GUESS_UNIT[columnId] ?? 'per90'
    return {
      value: row.metrics[columnId] ?? null,
      percentileKey: columnId,
      useCohortPercentile: false,
      formatUnit: u,
    }
  }

  if (rateMode === 'per90') {
    return {
      value: row.metrics[def.per90Key] ?? null,
      percentileKey: def.per90Key,
      useCohortPercentile: false,
      formatUnit: 'per90',
    }
  }

  const f = def.full
  if (f.kind === 'api') {
    return {
      value: row.metrics[f.key] ?? null,
      percentileKey: f.key,
      useCohortPercentile: false,
      formatUnit: f.formatUnit,
    }
  }

  const per90 = row.metrics[f.per90Key] ?? null
  const approx = per90ToSeasonApprox(per90, row.minutes)
  if (f.formatUnit === 'integer' && approx != null) {
    return {
      value: Math.round(approx),
      percentileKey: null,
      useCohortPercentile: true,
      formatUnit: 'integer',
    }
  }
  return {
    value: approx,
    percentileKey: null,
    useCohortPercentile: true,
    formatUnit: f.formatUnit,
  }
}

export function columnGkUsesCohortPercentile(columnId: string, rateMode: MatrixRateMode): boolean {
  if (rateMode === 'per90') return columnId in GK_TOTAL_RATE_TOGGLE
  const def = GK_RATE_TOGGLE[columnId]
  if (!def) return false
  return def.full.kind === 'derived'
}

const GK_COHORT_FULL_COLUMN_IDS = Object.keys(GK_RATE_TOGGLE).filter(
  id => GK_RATE_TOGGLE[id].full.kind === 'derived',
)

export function buildGkCohortPercentileMaps(
  players: PlayerRow[],
  rateMode: MatrixRateMode,
): Map<string, Map<number, number>> {
  const out = new Map<string, Map<number, number>>()
  const cohortColumnIds =
    rateMode === 'full'
      ? GK_COHORT_FULL_COLUMN_IDS
      : Object.keys(GK_TOTAL_RATE_TOGGLE)

  for (const colId of cohortColumnIds) {
    const resolved = players.map(p => ({
      id: p.canonical_player_id,
      v: resolveGkMatrixMetric(p, colId, 'full').value,
    }))

    const numeric = resolved
      .map(r => r.v)
      .filter((v): v is number => v != null && !Number.isNaN(v))

    const cohortByColumn = new Map<number, number>()
    for (const { id, v } of resolved) {
      if (v == null || Number.isNaN(v)) continue
      cohortByColumn.set(id, cohortPercentileRank(v, numeric))
    }
    out.set(colId, cohortByColumn)
  }

  return out
}

export function getGkSortValue(
  row: PlayerRow,
  columnId: string,
  rateMode: MatrixRateMode,
): number | string | null {
  switch (columnId) {
    case 'canonical_player_name':
      return row.canonical_player_name
    case 'canonical_team_name':
      return row.canonical_team_name ?? ''
    case 'minutes':
      return row.minutes
    case 'appearances':
      return row.appearances ?? null
    default:
      break
  }
  return resolveGkMatrixMetric(row, columnId, rateMode).value
}
