import type { ColumnUnit } from './columns'
import type { PlayerRow } from '../types/api'

export type MatrixRateMode = 'per90' | 'full'

/** Match backend `_percentile_rank` for a value against a cohort (same formula as ingestion `derived.py`). */
export function cohortPercentileRank(value: number, cohort: number[]): number {
  if (!cohort.length) return 0
  let less = 0
  let lessOrEqual = 0
  for (const other of cohort) {
    if (other < value) less += 1
    if (other <= value) lessOrEqual += 1
  }
  return ((less + lessOrEqual) / 2 / cohort.length) * 100
}

export function buildPercentileLookup(values: number[]): Map<number, number> {
  const sorted = [...values].sort((left, right) => left - right)
  const percentileByValue = new Map<number, number>()
  const total = sorted.length
  let start = 0

  while (start < total) {
    const value = sorted[start]
    let end = start + 1
    while (end < total && sorted[end] === value) end += 1
    percentileByValue.set(value, ((start + end) / 2 / total) * 100)
    start = end
  }

  return percentileByValue
}

export function per90ToSeasonApprox(per90: number | null, minutes: number | null | undefined): number | null {
  if (per90 == null || minutes == null || minutes <= 0) return null
  return (per90 * minutes) / 90
}

export function totalToPer90(total: number | null, minutes: number | null | undefined): number | null {
  if (total == null || minutes == null || minutes <= 0) return null
  return (total * 90) / minutes
}

type FullSource =
  | { kind: 'api'; key: string; formatUnit: ColumnUnit }
  | { kind: 'derived'; per90Key: string; formatUnit: ColumnUnit }

/** Columns whose displayed metric changes between per-90 and season (full) views. */
const RATE_TOGGLE: Record<string, { per90Key: string; full: FullSource }> = {
  tackles_per_90: {
    per90Key: 'tackles_per_90',
    full: { kind: 'derived', per90Key: 'tackles_per_90', formatUnit: 'integer' },
  },
  interceptions_per_90: {
    per90Key: 'interceptions_per_90',
    full: { kind: 'derived', per90Key: 'interceptions_per_90', formatUnit: 'integer' },
  },
  clearances_per_90: {
    per90Key: 'clearances_per_90',
    full: { kind: 'derived', per90Key: 'clearances_per_90', formatUnit: 'integer' },
  },
  blocks_per_90: {
    per90Key: 'blocks_per_90',
    full: { kind: 'derived', per90Key: 'blocks_per_90', formatUnit: 'integer' },
  },
  defensive_action_density: {
    per90Key: 'defensive_action_density',
    full: { kind: 'derived', per90Key: 'defensive_action_density', formatUnit: 'total' },
  },
  completed_passes_per_90: {
    per90Key: 'completed_passes_per_90',
    full: { kind: 'derived', per90Key: 'completed_passes_per_90', formatUnit: 'integer' },
  },
  key_passes_per_90: {
    per90Key: 'key_passes_per_90',
    full: { kind: 'derived', per90Key: 'key_passes_per_90', formatUnit: 'integer' },
  },
  big_chances_created_per_90: {
    per90Key: 'big_chances_created_per_90',
    full: { kind: 'derived', per90Key: 'big_chances_created_per_90', formatUnit: 'integer' },
  },
  successful_dribbles_per_90: {
    per90Key: 'successful_dribbles_per_90',
    full: { kind: 'derived', per90Key: 'successful_dribbles_per_90', formatUnit: 'integer' },
  },
  xgbuildup_per_90: {
    per90Key: 'xgbuildup_per_90',
    full: { kind: 'api', key: 'xgbuildup', formatUnit: 'total' },
  },
  xgchain_per_90: {
    per90Key: 'xgchain_per_90',
    full: { kind: 'api', key: 'xgchain', formatUnit: 'total' },
  },
  chance_involvement_per_90: {
    per90Key: 'chance_involvement_per_90',
    full: { kind: 'derived', per90Key: 'chance_involvement_per_90', formatUnit: 'total' },
  },
  npxg_per_90: {
    per90Key: 'npxg_per_90',
    full: { kind: 'api', key: 'npxg', formatUnit: 'total' },
  },
  xa_per_90: {
    per90Key: 'xa_per_90',
    full: { kind: 'api', key: 'xa', formatUnit: 'total' },
  },
  goals_per_90: {
    per90Key: 'goals_per_90',
    full: { kind: 'derived', per90Key: 'goals_per_90', formatUnit: 'integer' },
  },
  assists_per_90: {
    per90Key: 'assists_per_90',
    full: { kind: 'derived', per90Key: 'assists_per_90', formatUnit: 'integer' },
  },
  shots_per_90: {
    per90Key: 'shots_per_90',
    full: { kind: 'derived', per90Key: 'shots_per_90', formatUnit: 'integer' },
  },
}

/**
 * Columns stored as season totals in API that should show /90 in per90 mode.
 * Percentiles for per90 mode are computed client-side over the active matrix cohort.
 */
const TOTAL_RATE_TOGGLE: Record<
  string,
  { totalKey: string; fullUnit: ColumnUnit }
> = {
  tackles_won: { totalKey: 'tackles_won', fullUnit: 'total' },
  shots_on_target: { totalKey: 'shots_on_target', fullUnit: 'total' },
  shots_off_target: { totalKey: 'shots_off_target', fullUnit: 'total' },
  aerial_duels_won: { totalKey: 'aerial_duels_won', fullUnit: 'total' },
  ground_duels_won: { totalKey: 'ground_duels_won', fullUnit: 'total' },
  ball_recoveries: { totalKey: 'ball_recoveries', fullUnit: 'total' },
  fouls: { totalKey: 'fouls', fullUnit: 'total' },
  offsides: { totalKey: 'offsides', fullUnit: 'total' },
}

/** Tooltip / meta keys for column headers — use underlying metric that matches the headline stat. */
export function headerTooltipMetricKey(columnId: string, rateMode: MatrixRateMode): string {
  const fromTotal = TOTAL_RATE_TOGGLE[columnId]
  if (fromTotal) {
    return rateMode === 'per90' ? `${fromTotal.totalKey}_per90` : fromTotal.totalKey
  }
  const t = RATE_TOGGLE[columnId]
  if (!t) return columnId
  if (rateMode === 'per90') return t.per90Key
  if (t.full.kind === 'api') return t.full.key
  return t.per90Key
}

export interface ResolvedMatrixMetric {
  value: number | null
  /** When set, read percentile from `row.percentiles[percentileKey]` (if eligible). */
  percentileKey: string | null
  /** When true, percentile must come from cohort ranking of `value` across filtered players. */
  useCohortPercentile: boolean
  formatUnit: ColumnUnit
}

export function resolveMatrixMetric(
  row: PlayerRow,
  columnId: string,
  rateMode: MatrixRateMode,
): ResolvedMatrixMetric {
  const fromTotal = TOTAL_RATE_TOGGLE[columnId]
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

  const def = RATE_TOGGLE[columnId]
  if (!def) {
    const u = GUESS_UNIT[columnId] ?? 'per90'
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

/** Fallback units for invariant columns not listed in RATE_TOGGLE (must match `columns.ts`). */
const GUESS_UNIT: Partial<Record<string, ColumnUnit>> = {
  pass_accuracy: 'percentage',
  tackles_won: 'total',
  tackles_won_percentage: 'percentage',
  shots_on_target: 'total',
  shots_off_target: 'total',
  aerial_duels_won: 'total',
  ground_duels_won: 'total',
  ball_recoveries: 'total',
  successful_dribbles_percentage: 'percentage',
  fouls: 'total',
  offsides: 'total',
  xa_per_key_pass: 'ratio',
  buildup_share: 'share',
  npxg_per_shot: 'ratio',
  goals_minus_xg: 'delta',
  goals_minus_npxg: 'delta',
}

export function columnUsesCohortPercentile(columnId: string, rateMode: MatrixRateMode): boolean {
  if (rateMode === 'per90') return columnId in TOTAL_RATE_TOGGLE
  const def = RATE_TOGGLE[columnId]
  if (!def) return false
  return def.full.kind === 'derived'
}

const COHORT_FULL_COLUMN_IDS = Object.keys(RATE_TOGGLE).filter(
  id => RATE_TOGGLE[id].full.kind === 'derived',
)

/** For each column whose full value is derived client-side, map player id -> percentile rank (0–100). */
export function buildCohortPercentileMaps(
  players: PlayerRow[],
  rateMode: MatrixRateMode,
): Map<string, Map<number, number>> {
  const out = new Map<string, Map<number, number>>()
  const cohortColumnIds =
    rateMode === 'full'
      ? COHORT_FULL_COLUMN_IDS
      : Object.keys(TOTAL_RATE_TOGGLE)

  for (const colId of cohortColumnIds) {
    const resolved = players.map(p => ({
      id: p.canonical_player_id,
      v: resolveMatrixMetric(p, colId, 'full').value,
    }))

    const numeric = resolved
      .map(r => r.v)
      .filter((v): v is number => v != null && !Number.isNaN(v))
    const percentileByValue = buildPercentileLookup(numeric)

    const cohortByColumn = new Map<number, number>()
    for (const { id, v } of resolved) {
      if (v == null || Number.isNaN(v)) continue
      const percentile = percentileByValue.get(v)
      if (percentile != null) cohortByColumn.set(id, percentile)
    }
    out.set(colId, cohortByColumn)
  }

  return out
}
