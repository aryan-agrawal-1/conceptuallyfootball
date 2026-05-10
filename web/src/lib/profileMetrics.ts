import type { MetricDefinition, PlayerRow, PositionGroup } from '../types/api'
import type { ColumnUnit } from './columns'

/** Mirrors matrix "Per 90 | Season" naming. */
export type ProfileRateMode = 'per90' | 'full'

export type ProfileUiSection =
  | 'attacking'
  | 'passing_creative'
  | 'defending'
  | 'shot_stopping'
  | 'sweeper'
  | 'distribution'

export type ProfileBarKind =
  /** Value + percentile swap with toggle (both keys exist on API row). */
  | { kind: 'paired'; per90: string; full: string }
  /** Same metric & percentile in both modes (rates, %, deltas that do not have season toggles). */
  | { kind: 'invariant'; key: string }
  /**
   * Per-90 rate with no season total column: Season mode shows round(per90 × minutes ÷ 90);
   * percentile remains the per-90 cohort rank (documented in tooltip / footnote).
   */
  | { kind: 'derivedSeasonFromPer90'; per90: string; integerSeason?: boolean }

export interface ProfileBarSpec {
  id: string
  /** Short label if we want to override meta */
  label?: string
  section: ProfileUiSection
  bar: ProfileBarKind
}

/** Curated headline stats (4) — keys resolved via same rules as bars for the active rate mode. */
export interface ProfileHeaderCardSpec {
  id: string
  label: string
  bar: ProfileBarKind
}

/** Goalkeeper profile — mirrors `COLUMN_GROUPS_GK` / backend gk_definitions. */
export const PROFILE_BAR_SPECS_GK: ProfileBarSpec[] = [
  // Shot stopping
  { id: 'gk_saves', section: 'shot_stopping', bar: { kind: 'paired', per90: 'saves_per_90', full: 'saves' } },
  {
    id: 'gk_clean_sheet_rate',
    section: 'shot_stopping',
    bar: { kind: 'invariant', key: 'clean_sheet_rate' },
  },
  { id: 'gk_clean_sheets', section: 'shot_stopping', bar: { kind: 'invariant', key: 'clean_sheets' } },
  { id: 'gk_penalty_saves', section: 'shot_stopping', bar: { kind: 'invariant', key: 'penalty_saves' } },
  {
    id: 'gk_saved_shots_inside_box',
    section: 'shot_stopping',
    bar: { kind: 'paired', per90: 'saved_shots_inside_box_per_90', full: 'saved_shots_inside_box' },
  },
  // Sweeper
  { id: 'gk_runs_out', section: 'sweeper', bar: { kind: 'paired', per90: 'runs_out_per_90', full: 'runs_out' } },
  // Distribution
  { id: 'gk_pass_accuracy', section: 'distribution', bar: { kind: 'invariant', key: 'pass_accuracy' } },
  {
    id: 'gk_completed_passes',
    section: 'distribution',
    bar: { kind: 'derivedSeasonFromPer90', per90: 'completed_passes_per_90', integerSeason: true },
  },
  {
    id: 'gk_accurate_long_balls',
    section: 'distribution',
    bar: { kind: 'derivedSeasonFromPer90', per90: 'accurate_long_balls_per_90', integerSeason: true },
  },
]

export const PROFILE_SECTION_ORDER_OUTFIELD: ProfileUiSection[] = [
  'attacking',
  'passing_creative',
  'defending',
]

export const PROFILE_SECTION_ORDER_GK: ProfileUiSection[] = [
  'shot_stopping',
  'sweeper',
  'distribution',
]

export const PROFILE_SECTION_LABEL: Record<ProfileUiSection, string> = {
  attacking: 'Attacking',
  passing_creative: 'Passing / Creative',
  defending: 'Defending',
  shot_stopping: 'Shot stopping',
  sweeper: 'Sweeper',
  distribution: 'Distribution',
}

export function profileBarSpecsForPosition(pos: PositionGroup): ProfileBarSpec[] {
  return pos === 'GK' ? PROFILE_BAR_SPECS_GK : PROFILE_BAR_SPECS
}

export function profileSectionOrderForPosition(pos: PositionGroup): ProfileUiSection[] {
  return pos === 'GK' ? PROFILE_SECTION_ORDER_GK : PROFILE_SECTION_ORDER_OUTFIELD
}

export const PROFILE_BAR_SPECS: ProfileBarSpec[] = [
  // Attacking
  { id: 'xg', section: 'attacking', bar: { kind: 'paired', per90: 'xg_per_90', full: 'xg' } },
  { id: 'npxg', section: 'attacking', bar: { kind: 'paired', per90: 'npxg_per_90', full: 'npxg' } },
  { id: 'xa', section: 'attacking', bar: { kind: 'paired', per90: 'xa_per_90', full: 'xa' } },
  { id: 'xgchain', section: 'attacking', bar: { kind: 'paired', per90: 'xgchain_per_90', full: 'xgchain' } },
  { id: 'xgbuildup', section: 'attacking', bar: { kind: 'paired', per90: 'xgbuildup_per_90', full: 'xgbuildup' } },
  { id: 'goals', section: 'attacking', bar: { kind: 'derivedSeasonFromPer90', per90: 'goals_per_90', integerSeason: true } },
  { id: 'assists', section: 'attacking', bar: { kind: 'derivedSeasonFromPer90', per90: 'assists_per_90', integerSeason: true } },
  { id: 'shots', section: 'attacking', bar: { kind: 'derivedSeasonFromPer90', per90: 'shots_per_90', integerSeason: true } },
  { id: 'npxg_per_shot', section: 'attacking', bar: { kind: 'invariant', key: 'npxg_per_shot' } },
  // Passing / creative
  { id: 'passes', section: 'passing_creative', bar: { kind: 'derivedSeasonFromPer90', per90: 'completed_passes_per_90', integerSeason: true } },
  { id: 'key_passes', section: 'passing_creative', bar: { kind: 'derivedSeasonFromPer90', per90: 'key_passes_per_90', integerSeason: true } },
  { id: 'big_chances', section: 'passing_creative', bar: { kind: 'derivedSeasonFromPer90', per90: 'big_chances_created_per_90', integerSeason: true } },
  { id: 'dribbles', section: 'passing_creative', bar: { kind: 'derivedSeasonFromPer90', per90: 'successful_dribbles_per_90', integerSeason: true } },
  { id: 'pass_accuracy', section: 'passing_creative', bar: { kind: 'invariant', key: 'pass_accuracy' } },
  { id: 'dribble_pct', section: 'passing_creative', bar: { kind: 'invariant', key: 'successful_dribbles_percentage' } },
  { id: 'xa_per_kp', section: 'passing_creative', bar: { kind: 'invariant', key: 'xa_per_key_pass' } },
  { id: 'chance_inv', section: 'passing_creative', bar: { kind: 'derivedSeasonFromPer90', per90: 'chance_involvement_per_90' } },
  // Defending
  { id: 'tackles', section: 'defending', bar: { kind: 'paired', per90: 'tackles_per_90', full: 'tackles_won' } },
  { id: 'interceptions', section: 'defending', bar: { kind: 'derivedSeasonFromPer90', per90: 'interceptions_per_90', integerSeason: true } },
  { id: 'clearances', section: 'defending', bar: { kind: 'derivedSeasonFromPer90', per90: 'clearances_per_90', integerSeason: true } },
  { id: 'blocks', section: 'defending', bar: { kind: 'derivedSeasonFromPer90', per90: 'blocks_per_90', integerSeason: true } },
  { id: 'def_density', section: 'defending', bar: { kind: 'derivedSeasonFromPer90', per90: 'defensive_action_density' } },
  { id: 'ball_rec', section: 'defending', bar: { kind: 'paired', per90: 'ball_recoveries_per_90', full: 'ball_recoveries' } },
  { id: 'ground_duels', section: 'defending', bar: { kind: 'paired', per90: 'ground_duels_won_per_90', full: 'ground_duels_won' } },
  { id: 'aerial_duels', section: 'defending', bar: { kind: 'paired', per90: 'aerial_duels_won_per_90', full: 'aerial_duels_won' } },
  { id: 'fouls', section: 'defending', bar: { kind: 'paired', per90: 'fouls_per_90', full: 'fouls' } },
]

export const PROFILE_BARS_ORDERED: ProfileBarSpec[] = PROFILE_BAR_SPECS

function per90ToSeasonApprox(
  per90: number | null | undefined,
  minutes: number | null | undefined,
  integer: boolean,
): number | null {
  if (per90 == null || minutes == null || minutes <= 0) return null
  const raw = (per90 * minutes) / 90
  return integer ? Math.round(raw) : raw
}

export interface ResolvedProfileMetric {
  metricKey: string
  value: number | null
  percentile: number | null
  formatUnit: ColumnUnit
}

function unitFromMeta(metricKey: string, meta: { metrics: Record<string, MetricDefinition> }): ColumnUnit {
  const u = meta.metrics[metricKey]?.unit
  if (u === 'total') return 'total'
  if (u === 'per90') return 'per90'
  if (u === 'delta') return 'delta'
  if (u === 'ratio') return 'ratio'
  if (u === 'percentage') return 'percentage'
  if (u === 'share') return 'share'
  return 'per90'
}

/**
 * Resolve one profile metric for bars, header, or pizza slices.
 */
export function resolveProfileMetric(
  row: PlayerRow,
  mode: ProfileRateMode,
  bar: ProfileBarKind,
  meta: { metrics: Record<string, MetricDefinition> },
): ResolvedProfileMetric {
  const pctEligible = row.eligibility.percentiles_eligible

  if (bar.kind === 'invariant') {
    const v = row.metrics[bar.key] ?? null
    const p = pctEligible ? (row.percentiles[bar.key] ?? null) : null
    return {
      metricKey: bar.key,
      value: v,
      percentile: p,
      formatUnit: unitFromMeta(bar.key, meta),
    }
  }

  if (bar.kind === 'paired') {
    const key = mode === 'per90' ? bar.per90 : bar.full
    const v = row.metrics[key] ?? null
    const p = pctEligible ? (row.percentiles[key] ?? null) : null
    return { metricKey: key, value: v, percentile: p, formatUnit: unitFromMeta(key, meta) }
  }

  /* derivedSeasonFromPer90 */
  const per90Val = row.metrics[bar.per90] ?? null
  const p = pctEligible ? (row.percentiles[bar.per90] ?? null) : null
  if (mode === 'per90') {
    return {
      metricKey: bar.per90,
      value: per90Val,
      percentile: p,
      formatUnit: unitFromMeta(bar.per90, meta),
    }
  }
  const season = per90ToSeasonApprox(
    per90Val,
    row.minutes,
    bar.integerSeason ?? false,
  )
  return {
    metricKey: bar.per90,
    value: season,
    percentile: p,
    formatUnit: bar.integerSeason ? 'integer' : 'total',
  }
}


export function stripPer90Suffix(label: string): string {
  return label
    .replace(/\s*[/-]\s*90\b\.?$/i, '')
    .replace(/\s*\bper\s*90\b\.?$/i, '')
    .replace(/\s*\bp90\b\.?$/i, '')
    .trim()
}

export function labelForBarSpec(
  spec: ProfileBarSpec,
  meta: { metrics: Record<string, MetricDefinition> },
): string {
  if (spec.label) return spec.label
  const key =
    spec.bar.kind === 'invariant'
      ? spec.bar.key
      : spec.bar.kind === 'paired'
        ? spec.bar.per90
        : spec.bar.per90
  const raw = meta.metrics[key]?.label ?? spec.id
  return stripPer90Suffix(raw)
}

export function headerSpecsForPosition(pos: PositionGroup): ProfileHeaderCardSpec[] {
  switch (pos) {
    case 'FWD':
      return [
        { id: 'h1', label: 'Goals', bar: { kind: 'derivedSeasonFromPer90', per90: 'goals_per_90', integerSeason: true } },
        { id: 'h2', label: 'xG', bar: { kind: 'paired', per90: 'xg_per_90', full: 'xg' } },
        { id: 'h3', label: 'xA', bar: { kind: 'paired', per90: 'xa_per_90', full: 'xa' } },
        { id: 'h4', label: 'Shots', bar: { kind: 'derivedSeasonFromPer90', per90: 'shots_per_90', integerSeason: true } },
      ]
    case 'MID':
      return [
        { id: 'h1', label: 'xG', bar: { kind: 'paired', per90: 'xg_per_90', full: 'xg' } },
        { id: 'h2', label: 'xA', bar: { kind: 'paired', per90: 'xa_per_90', full: 'xa' } },
        { id: 'h3', label: 'Key passes', bar: { kind: 'derivedSeasonFromPer90', per90: 'key_passes_per_90', integerSeason: true } },
        { id: 'h4', label: 'xG Chain', bar: { kind: 'paired', per90: 'xgchain_per_90', full: 'xgchain' } },
      ]
    case 'DEF':
      return [
        { id: 'h1', label: 'Tackles', bar: { kind: 'paired', per90: 'tackles_per_90', full: 'tackles_won' } },
        { id: 'h2', label: 'Interceptions', bar: { kind: 'derivedSeasonFromPer90', per90: 'interceptions_per_90', integerSeason: true } },
        { id: 'h3', label: 'Clearances', bar: { kind: 'derivedSeasonFromPer90', per90: 'clearances_per_90', integerSeason: true } },
        { id: 'h4', label: 'Blocks', bar: { kind: 'derivedSeasonFromPer90', per90: 'blocks_per_90', integerSeason: true } },
      ]
    case 'GK':
      return [
        { id: 'h1', label: 'Saves/90', bar: { kind: 'derivedSeasonFromPer90', per90: 'saves_per_90' } },
        { id: 'h2', label: 'CS%', bar: { kind: 'invariant', key: 'clean_sheet_rate' } },
        { id: 'h3', label: 'Pass%', bar: { kind: 'invariant', key: 'pass_accuracy' } },
        {
          id: 'h4',
          label: 'Box saves/90',
          bar: { kind: 'derivedSeasonFromPer90', per90: 'saved_shots_inside_box_per_90' },
        },
      ]
    default:
      return [
        { id: 'h1', label: 'xG', bar: { kind: 'paired', per90: 'xg_per_90', full: 'xg' } },
        { id: 'h2', label: 'xA', bar: { kind: 'paired', per90: 'xa_per_90', full: 'xa' } },
        { id: 'h3', label: 'Minutes', bar: { kind: 'invariant', key: 'minutes_display' } },
        { id: 'h4', label: 'xG Chain', bar: { kind: 'paired', per90: 'xgchain_per_90', full: 'xgchain' } },
      ]
  }
}

/** Synthetic header metric: minutes played (not in metrics dict). */
export function resolveHeaderCard(
  row: PlayerRow,
  mode: ProfileRateMode,
  spec: ProfileHeaderCardSpec,
  meta: { metrics: Record<string, MetricDefinition> },
): ResolvedProfileMetric & { label: string } {
  if (spec.bar.kind === 'invariant' && spec.bar.key === 'minutes_display') {
    return {
      metricKey: 'minutes',
      label: spec.label,
      value: row.minutes,
      percentile: null,
      formatUnit: 'integer',
    }
  }
  const r = resolveProfileMetric(row, mode, spec.bar, meta)
  return { ...r, label: spec.label }
}

const PIZZA_DEFAULT_KEYS: Record<PositionGroup, string[]> = {
  FWD: [
    'xg_per_90',
    'goals_per_90',
    'xa_per_90',
    'shots_per_90',
    'key_passes_per_90',
    'successful_dribbles_per_90',
    'npxg_per_shot',
    'chance_involvement_per_90',
  ],
  MID: [
    'xg_per_90',
    'xa_per_90',
    'key_passes_per_90',
    'xgchain_per_90',
    'xgbuildup_per_90',
    'successful_dribbles_per_90',
    'completed_passes_per_90',
    'pass_accuracy',
  ],
  DEF: [
    'tackles_per_90',
    'interceptions_per_90',
    'clearances_per_90',
    'blocks_per_90',
    'ball_recoveries_per_90',
    'pass_accuracy',
    'xgbuildup_per_90',
    'defensive_action_density',
  ],
  GK: [
    'saves_per_90',
    'clean_sheet_rate',
    'saved_shots_inside_box_per_90',
    'runs_out_per_90',
    'pass_accuracy',
    'completed_passes_per_90',
    'accurate_long_balls_per_90',
    'penalty_saves',
  ],
  UNK: [
    'xg_per_90',
    'xa_per_90',
    'xgchain_per_90',
    'pass_accuracy',
    'tackles_per_90',
    'interceptions_per_90',
    'key_passes_per_90',
    'goals_per_90',
  ],
}

export const PIZZA_SLICE_MIN = 4
export const PIZZA_SLICE_SOFT_MAX = 12

export const PIZZA_STORAGE_KEY = 'conceptually-football:pizza-axes:v1'

export function defaultPizzaMetricKeys(position: PositionGroup): string[] {
  return [...(PIZZA_DEFAULT_KEYS[position] ?? PIZZA_DEFAULT_KEYS.UNK)]
}

/** Map backend definition group to profile UI section for the axis picker. */
export function metricUiSection(defGroup: string): ProfileUiSection {
  if (defGroup === 'defending') return 'defending'
  if (defGroup === 'attack') return 'attacking'
  if (defGroup === 'shot_stopping') return 'shot_stopping'
  if (defGroup === 'sweeper') return 'sweeper'
  if (defGroup === 'distribution') return 'distribution'
  return 'passing_creative'
}

const ALL_PROFILE_BAR_SPECS: ProfileBarSpec[] = [...PROFILE_BAR_SPECS, ...PROFILE_BAR_SPECS_GK]

export function barKindForMetricKey(metricKey: string): ProfileBarKind {
  const spec = ALL_PROFILE_BAR_SPECS.find(s => {
    const b = s.bar
    if (b.kind === 'invariant') return b.key === metricKey
    if (b.kind === 'paired') return b.per90 === metricKey || b.full === metricKey
    return b.per90 === metricKey
  })
  if (spec) return spec.bar
  return { kind: 'invariant', key: metricKey }
}

/** Group metrics by backend `def.group` for the pizza axis picker (works for outfield + GK). */
export function groupMetricsForPizzaPicker(
  meta: {
    metrics: Record<string, MetricDefinition>
    metric_groups: Record<string, string>
  },
  excludeKeys?: readonly string[],
): Record<string, Array<{ key: string; label: string }>> {
  const exclude = excludeKeys?.length ? new Set(excludeKeys) : null
  const result: Record<string, Array<{ key: string; label: string }>> = {}
  for (const g of Object.keys(meta.metric_groups)) {
    result[g] = []
  }
  for (const [key, def] of Object.entries(meta.metrics)) {
    if (exclude?.has(key)) continue
    const g = def.group
    if (!result[g]) result[g] = []
    result[g].push({ key, label: stripPer90Suffix(def.label) })
  }
  for (const k of Object.keys(result)) {
    result[k].sort((a, b) => a.label.localeCompare(b.label))
  }
  return result
}
