import type { PlayerRow, PositionGroup, StatMeta } from '../types/api'
import {
  PIZZA_SLICE_MIN,
  PROFILE_BAR_SPECS,
  PROFILE_BAR_SPECS_GK,
  barKindForMetricKey,
  defaultPizzaMetricKeys,
  labelForBarSpec,
  resolveProfileMetric,
  stripPer90Suffix,
  type ProfileBarSpec,
  type ProfileRateMode,
} from './profileMetrics'

export type ProfileExportTheme = 'conceptually-football' | 'boring'

export interface ProfileExportTile {
  key: string
  label: string
}

export interface ProfileExportPreset {
  theme: ProfileExportTheme
  rateMode: ProfileRateMode
  stats: ProfileExportTile[]
  chartEnabled: boolean
  chartMetricKeys: string[]
  notesEnabled: boolean
  showPercentiles: boolean
}

const EXPORT_PRESET_VERSION = 1
export const PROFILE_EXPORT_STORAGE_KEY = 'conceptually-football:profile-export:v1'

interface StoredProfileExportPreset extends ProfileExportPreset {
  version: number
}

type StoredProfileExportState = Partial<Record<string, StoredProfileExportPreset>>

const DEFAULT_TILE_COUNT = 8

const FULL_COVERAGE_SENTINELS = ['npxg_per_90', 'npxg_per_shot']

const EXPORT_STAT_CANDIDATES_FULL: Record<PositionGroup, string[]> = {
  FWD: [
    'goals_per_90',
    'xg_per_90',
    'npxg_per_90',
    'xa_per_90',
    'shots_per_90',
    'key_passes_per_90',
    'successful_dribbles_per_90',
    'npxg_per_shot',
    'chance_involvement_per_90',
    'assists_per_90',
    'big_chances_created_per_90',
    'xgchain_per_90',
  ],
  MID: [
    'xa_per_90',
    'key_passes_per_90',
    'xgchain_per_90',
    'xgbuildup_per_90',
    'completed_passes_per_90',
    'pass_accuracy',
    'successful_dribbles_per_90',
    'chance_involvement_per_90',
    'xg_per_90',
    'assists_per_90',
    'big_chances_created_per_90',
    'interceptions_per_90',
  ],
  DEF: [
    'tackles_per_90',
    'interceptions_per_90',
    'clearances_per_90',
    'blocks_per_90',
    'ball_recoveries_per_90',
    'aerial_duels_won_per_90',
    'ground_duels_won_per_90',
    'pass_accuracy',
    'xgbuildup_per_90',
    'defensive_action_density',
    'completed_passes_per_90',
  ],
  GK: [
    'saves_per_90',
    'clean_sheet_rate',
    'clean_sheets',
    'saved_shots_inside_box_per_90',
    'pass_accuracy',
    'completed_passes_per_90',
    'accurate_long_balls_per_90',
    'runs_out_per_90',
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
    'completed_passes_per_90',
    'shots_per_90',
  ],
}

const EXPORT_STAT_CANDIDATES_LIMITED: Record<PositionGroup, string[]> = {
  FWD: [
    'goals_per_90',
    'xg_per_90',
    'xa_per_90',
    'shots_per_90',
    'key_passes_per_90',
    'successful_dribbles_per_90',
    'chance_involvement_per_90',
    'assists_per_90',
    'big_chances_created_per_90',
    'xgchain_per_90',
    'xgbuildup_per_90',
    'pass_accuracy',
  ],
  MID: [
    'xa_per_90',
    'key_passes_per_90',
    'xgchain_per_90',
    'xgbuildup_per_90',
    'completed_passes_per_90',
    'pass_accuracy',
    'successful_dribbles_per_90',
    'chance_involvement_per_90',
    'xg_per_90',
    'assists_per_90',
    'big_chances_created_per_90',
    'interceptions_per_90',
  ],
  DEF: [
    'tackles_per_90',
    'interceptions_per_90',
    'clearances_per_90',
    'blocks_per_90',
    'ball_recoveries_per_90',
    'aerial_duels_won_per_90',
    'ground_duels_won_per_90',
    'pass_accuracy',
    'xgbuildup_per_90',
    'defensive_action_density',
    'completed_passes_per_90',
  ],
  GK: [
    'saves_per_90',
    'clean_sheet_rate',
    'clean_sheets',
    'saved_shots_inside_box_per_90',
    'pass_accuracy',
    'completed_passes_per_90',
    'accurate_long_balls_per_90',
    'runs_out_per_90',
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
    'completed_passes_per_90',
    'shots_per_90',
  ],
}

function storageKeyForPosition(position: PositionGroup): string {
  return `player:${position}`
}

function readStoredState(): StoredProfileExportState {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(PROFILE_EXPORT_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function writeStoredState(state: StoredProfileExportState) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(PROFILE_EXPORT_STORAGE_KEY, JSON.stringify(state))
}

export function loadProfileExportPreset(position: PositionGroup): ProfileExportPreset | null {
  const stored = readStoredState()[storageKeyForPosition(position)]
  if (!stored || stored.version !== EXPORT_PRESET_VERSION) return null
  return {
    theme: stored.theme,
    rateMode: stored.rateMode,
    stats: stored.stats,
    chartEnabled: stored.chartEnabled,
    chartMetricKeys: stored.chartMetricKeys,
    notesEnabled: stored.notesEnabled,
    showPercentiles: stored.showPercentiles,
  }
}

export function saveProfileExportPreset(position: PositionGroup, preset: ProfileExportPreset) {
  const state = readStoredState()
  state[storageKeyForPosition(position)] = {
    version: EXPORT_PRESET_VERSION,
    ...preset,
  }
  writeStoredState(state)
}

function keyForSpec(spec: ProfileBarSpec): string {
  const bar = spec.bar
  if (bar.kind === 'invariant') return bar.key
  if (bar.kind === 'paired') return bar.per90
  return bar.per90
}

export function curatedProfileMetricSpecs(position: PositionGroup): ProfileBarSpec[] {
  return position === 'GK' ? PROFILE_BAR_SPECS_GK : PROFILE_BAR_SPECS
}

export function curatedProfileMetricKeys(position: PositionGroup): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const spec of curatedProfileMetricSpecs(position)) {
    const key = keyForSpec(spec)
    if (position === 'GK' && key === 'rating') continue
    if (!seen.has(key)) {
      seen.add(key)
      out.push(key)
    }
  }
  return out
}

export function profileExportLabelForKey(key: string, meta: StatMeta): string {
  const spec = [...PROFILE_BAR_SPECS, ...PROFILE_BAR_SPECS_GK].find(s => keyForSpec(s) === key)
  if (spec) return labelForBarSpec(spec, meta)
  return stripPer90Suffix(meta.metrics[key]?.label ?? key)
}

export function isUsableExportMetric(
  player: PlayerRow,
  meta: StatMeta,
  rateMode: ProfileRateMode,
  key: string,
): boolean {
  if (!(key in meta.metrics)) return false
  if (player.position_group === 'GK' && key === 'rating') return false
  return resolveProfileMetric(player, rateMode, barKindForMetricKey(key), meta).value != null
}

export function defaultProfileExportStats(
  player: PlayerRow,
  meta: StatMeta,
  rateMode: ProfileRateMode,
): ProfileExportTile[] {
  const curated = curatedProfileMetricKeys(player.position_group)
  const curatedSet = new Set(curated)
  const hasFullCoverage = FULL_COVERAGE_SENTINELS.some(key =>
    isUsableExportMetric(player, meta, rateMode, key),
  )
  const candidateSet = hasFullCoverage ? EXPORT_STAT_CANDIDATES_FULL : EXPORT_STAT_CANDIDATES_LIMITED
  const candidates = [
    ...(candidateSet[player.position_group] ?? candidateSet.UNK),
    ...curated,
  ]
  const seen = new Set<string>()
  const out: ProfileExportTile[] = []

  for (const key of candidates) {
    if (seen.has(key) || !curatedSet.has(key)) continue
    seen.add(key)
    if (!isUsableExportMetric(player, meta, rateMode, key)) continue
    out.push({ key, label: profileExportLabelForKey(key, meta) })
    if (out.length >= DEFAULT_TILE_COUNT) break
  }

  return out
}

export function defaultProfileExportChartKeys(
  player: PlayerRow,
  meta: StatMeta,
  rateMode: ProfileRateMode,
): string[] {
  const curated = curatedProfileMetricKeys(player.position_group)
  const curatedSet = new Set(curated)
  const candidates = [...defaultPizzaMetricKeys(player.position_group), ...curated]
  const seen = new Set<string>()
  const out: string[] = []

  for (const key of candidates) {
    if (seen.has(key) || !curatedSet.has(key)) continue
    seen.add(key)
    if (!isUsableExportMetric(player, meta, rateMode, key)) continue
    out.push(key)
    if (out.length >= Math.max(PIZZA_SLICE_MIN, DEFAULT_TILE_COUNT)) break
  }

  return out
}

export function buildDefaultProfileExportPreset(
  player: PlayerRow,
  meta: StatMeta,
  rateMode: ProfileRateMode,
): ProfileExportPreset {
  return {
    theme: 'conceptually-football',
    rateMode,
    stats: defaultProfileExportStats(player, meta, rateMode),
    chartEnabled: player.eligibility.percentiles_eligible,
    chartMetricKeys: defaultProfileExportChartKeys(player, meta, rateMode),
    notesEnabled: false,
    showPercentiles: player.eligibility.percentiles_eligible,
  }
}

export function hydrateProfileExportPreset(
  player: PlayerRow,
  meta: StatMeta,
  initialRateMode: ProfileRateMode,
): ProfileExportPreset {
  const stored = loadProfileExportPreset(player.position_group)
  if (!stored) return buildDefaultProfileExportPreset(player, meta, initialRateMode)

  const fallback = buildDefaultProfileExportPreset(player, meta, stored.rateMode ?? initialRateMode)
  const seen = new Set<string>()
  const stats = stored.stats
    .filter(tile => {
      if (seen.has(tile.key)) return false
      seen.add(tile.key)
      return isUsableExportMetric(player, meta, stored.rateMode ?? initialRateMode, tile.key)
    })
    .map(tile => ({
      key: tile.key,
      label: tile.label || profileExportLabelForKey(tile.key, meta),
    }))
  const statKeys = new Set(stats.map(tile => tile.key))
  const paddedStats = [
    ...stats,
    ...fallback.stats.filter(tile => !statKeys.has(tile.key)),
  ].slice(0, Math.max(DEFAULT_TILE_COUNT, stats.length))
  const chartKeys = stored.chartMetricKeys.filter(key =>
    isUsableExportMetric(player, meta, stored.rateMode ?? initialRateMode, key),
  )
  const chartKeySet = new Set(chartKeys)
  const paddedChartKeys = [
    ...chartKeys,
    ...fallback.chartMetricKeys.filter(key => !chartKeySet.has(key)),
  ]

  return {
    theme: stored.theme === 'boring' ? 'boring' : 'conceptually-football',
    rateMode: stored.rateMode ?? initialRateMode,
    stats: paddedStats.length ? paddedStats : fallback.stats,
    chartEnabled: player.eligibility.percentiles_eligible ? stored.chartEnabled : false,
    chartMetricKeys: paddedChartKeys.length ? paddedChartKeys : fallback.chartMetricKeys,
    notesEnabled: stored.notesEnabled,
    showPercentiles: player.eligibility.percentiles_eligible && stored.showPercentiles,
  }
}
