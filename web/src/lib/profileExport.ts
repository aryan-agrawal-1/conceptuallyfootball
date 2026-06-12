import type { PlayerRow, PositionGroup, StatMeta } from '../types/api'
import {
  PIZZA_SLICE_MIN,
  PROFILE_BAR_SPECS,
  PROFILE_BAR_SPECS_GK,
  barKindForMetricKey,
  defaultPizzaMetricKeys,
  headerSpecsForPosition,
  labelForBarSpec,
  resolveProfileMetric,
  resolveHeaderCard,
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
  similarEnabled: boolean
  showPercentiles: boolean
}

const EXPORT_PRESET_VERSION = 1
const PROFILE_EXPORT_STORAGE_KEY = 'conceptually-football:profile-export:v1'

interface StoredProfileExportPreset extends ProfileExportPreset {
  version: number
}

type StoredProfileExportState = Partial<Record<string, StoredProfileExportPreset>>

export const PROFILE_EXPORT_STAT_LIMIT = 4

const DEFAULT_TILE_COUNT = PROFILE_EXPORT_STAT_LIMIT
const DEFAULT_CHART_AXIS_COUNT = 8

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

function loadProfileExportPreset(position: PositionGroup): ProfileExportPreset | null {
  const stored = readStoredState()[storageKeyForPosition(position)]
  if (!stored || stored.version !== EXPORT_PRESET_VERSION) return null
  return {
    theme: stored.theme,
    rateMode: stored.rateMode,
    stats: stored.stats,
    chartEnabled: stored.chartEnabled,
    chartMetricKeys: stored.chartMetricKeys,
    notesEnabled: stored.notesEnabled,
    similarEnabled: stored.similarEnabled ?? false,
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

function curatedProfileMetricSpecs(position: PositionGroup): ProfileBarSpec[] {
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

function defaultProfileExportStats(
  player: PlayerRow,
  meta: StatMeta,
  rateMode: ProfileRateMode,
): ProfileExportTile[] {
  const seen = new Set<string>()
  const standoutStats = curatedProfileMetricSpecs(player.position_group)
    .flatMap(spec => {
      const resolved = resolveProfileMetric(player, rateMode, spec.bar, meta)
      if (resolved.value == null || resolved.percentile == null) return []
      if (seen.has(resolved.metricKey)) return []
      seen.add(resolved.metricKey)
      return [{
        key: resolved.metricKey,
        label: labelForBarSpec(spec, meta),
        value: resolved.value,
        percentile: resolved.percentile,
      }]
    })
    .toSorted((left, right) =>
      right.percentile - left.percentile ||
      right.value - left.value,
    )
    .slice(0, DEFAULT_TILE_COUNT)

  if (standoutStats.length) {
    return standoutStats.map(({ key, label }) => ({ key, label }))
  }

  const fallbackStats = headerSpecsForPosition(player.position_group).flatMap(spec => {
    const resolved = resolveHeaderCard(player, rateMode, spec, meta)
    if (resolved.value == null) return []
    return [{ key: resolved.metricKey, label: resolved.label }]
  })
  const fallbackKeys = new Set(fallbackStats.map(tile => tile.key))
  const rawFallbackStats = Object.entries(meta.metrics).flatMap(([key, def]) => {
    if (fallbackKeys.has(key)) return []
    if (player.position_group === 'GK' && key === 'rating') return []
    const resolved = resolveProfileMetric(player, rateMode, barKindForMetricKey(key), meta)
    if (resolved.value == null) return []
    return [{ key: resolved.metricKey, label: stripPer90Suffix(def.label) }]
  })

  return [...fallbackStats, ...rawFallbackStats].slice(0, DEFAULT_TILE_COUNT)
}

function defaultProfileExportChartKeys(
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
    if (out.length >= Math.max(PIZZA_SLICE_MIN, DEFAULT_CHART_AXIS_COUNT)) break
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
    similarEnabled: false,
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
  const stats = stored.stats.flatMap(tile => {
    if (seen.has(tile.key)) return []
    seen.add(tile.key)
    if (!isUsableExportMetric(player, meta, stored.rateMode ?? initialRateMode, tile.key)) return []
    return [{
      key: tile.key,
      label: tile.label || profileExportLabelForKey(tile.key, meta),
    }]
  })
  const statKeys = new Set(stats.map(tile => tile.key))
  const paddedStats = [
    ...stats,
    ...fallback.stats.filter(tile => !statKeys.has(tile.key)),
  ].slice(0, DEFAULT_TILE_COUNT)
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
    similarEnabled: stored.similarEnabled ?? false,
    showPercentiles: player.eligibility.percentiles_eligible && stored.showPercentiles,
  }
}
