import type { EventMapExportContext } from '../../lib/eventMaps/exportContext'
import type { StateDeltaMapContract } from '../../lib/eventMaps/deltaMap'
import type { ProfileRateMode } from '../../lib/profileMetrics'
import type {
  ActionGridCell,
  DefensiveActionFamily,
  PlayerPassFilter,
  PlayerPassOutcome,
  PlayerStateComparisonPayload,
  PlayerStateCohort,
  ShotOutcome,
  ShotZoneVariantKey,
  StateLensMetadata,
} from '../../types/eventMaps'
import { ALL_DEFENSIVE_ACTION_FAMILIES } from './defensiveActionFamilies'

export const PASS_FILTERS: Array<{ value: PlayerPassFilter; label: string }> = [
  { value: 'all', label: 'All types' },
  { value: 'progressive', label: 'Progressive' },
  { value: 'final_third_entry', label: 'Final third' },
  { value: 'box_entry', label: 'Box entries' },
  { value: 'key_pass', label: 'Key passes' },
  { value: 'cross', label: 'Crosses' },
  { value: 'long_ball', label: 'Long balls' },
]

export const CARRY_FILTERS = PASS_FILTERS.slice(0, 4)
export const SHARED_SPATIAL_FILTERS = new Set<PlayerPassFilter>(CARRY_FILTERS.map(filter => filter.value))

export const PASS_OUTCOMES: Array<{ value: PlayerPassOutcome; label: string }> = [
  { value: 'all', label: 'All outcomes' },
  { value: 'completed', label: 'Completed' },
  { value: 'incomplete', label: 'Incomplete' },
]

export type PassMapLayer = 'all' | 'passes' | 'carries'

export const PASS_MAP_LAYERS: Array<{ value: PassMapLayer; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'passes', label: 'Passes' },
  { value: 'carries', label: 'Carries' },
]

export type ShotOutcomeFilter = 'all' | ShotOutcome
export type ShotChanceFilter = 'all' | 'big_chance' | 'standard_chance'

export const SHOT_OUTCOME_FILTERS: Array<{ value: ShotOutcomeFilter; label: string }> = [
  { value: 'all', label: 'All outcomes' },
  { value: 'goal', label: 'Goals' },
  { value: 'saved', label: 'Saved' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'off_target', label: 'Off target' },
  { value: 'woodwork', label: 'Woodwork' },
]

export const SHOT_CHANCE_FILTERS: Array<{ value: ShotChanceFilter; label: string }> = [
  { value: 'all', label: 'All chances' },
  { value: 'big_chance', label: 'Big chances' },
  { value: 'standard_chance', label: 'Standard chances' },
]

export type PlayerEventMapTeam = { id: number; name: string }
export type PlayerMap = 'passes' | 'shots' | 'actions' | 'zones' | 'gk-zones'

export type PenaltyOption = ShotZoneVariantKey

export const PENALTY_OPTIONS: Array<{ value: PenaltyOption; label: string }> = [
  { value: 'all', label: 'All shots' },
  { value: 'open_play', label: 'Non-penalties' },
  { value: 'penalties_only', label: 'Penalties' },
]

export type PlayerAnalysisMode = 'overview' | 'passing' | 'shooting' | 'defending'

export function scopeLabel(value: string | null | undefined) {
  if (!value || value === 'all') return 'All states'
  return value.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase())
}

export function stateExportFilters(stateLens: StateLensMetadata) {
  const filters: EventMapExportContext['filters'] = [
    { label: 'State', value: scopeLabel(stateLens.selected.state) },
    { label: 'Verified exposure', value: `${stateLens.evidence.exposureMinutes.toLocaleString()} min · ${stateLens.evidence.matchCount.toLocaleString()} matches` },
  ]
  if (stateLens.comparison.enabled && stateLens.comparison.baseline) {
    filters.push({ label: 'Baseline', value: scopeLabel(stateLens.comparison.baseline.state) })
  }
  if (stateLens.selected.goalDifference != null) filters.push({ label: 'Goal difference', value: String(stateLens.selected.goalDifference) })
  if (stateLens.selected.phase) filters.push({ label: 'Phase', value: scopeLabel(stateLens.selected.phase) })
  return filters
}

export function cohortReliability(cohort: PlayerStateCohort): 'verified' | 'partial' | 'sparse' | 'unsupported' | 'unavailable' {
  if (cohort.exposureSeconds <= 0 || cohort.evidence.empty) return 'unavailable'
  if (cohort.summary.actions < 20 || cohort.evidence.matchCount < 2) return 'sparse'
  if (cohort.evidence.matchesExcluded > 0) return 'partial'
  return 'verified'
}

function deltaCohortEvidence(label: string, cohort: PlayerStateCohort, locationKey: 'touchLocation' | 'defensiveLocation') {
  return {
    label,
    exposureMinutes: cohort.exposureMinutes,
    matchCount: cohort.evidence.matchCount,
    episodeCount: cohort.evidence.episodeCount,
    eventCount: cohort.summary.actions,
    locatedEventCount: cohort[locationKey].sampleSize,
    excludedEventCount: 0,
    exclusions: cohort.evidence.exclusionReasons,
    reliability: cohortReliability(cohort),
  } as const
}

export function stateShiftContract(
  playerId: number,
  playerName: string,
  selected: PlayerStateCohort,
  baseline: PlayerStateCohort | null,
  selectedLabel: string,
  baselineLabel: string,
  teamSelected: PlayerStateCohort | null,
  teamBaseline: PlayerStateCohort | null,
  metricLabel = 'Touch territory State Shift',
  gridKey: 'touchGrid' | 'defensiveGrid' = 'touchGrid',
): StateDeltaMapContract | null {
  if (!baseline) return null
  const selectedGrid = selected[gridKey]
  const baselineGrid = baseline[gridKey]
  const locationKey = gridKey === 'defensiveGrid' ? 'defensiveLocation' : 'touchLocation'
  const selectedLocation = selected[locationKey]
  const baselineLocation = baseline[locationKey]
  const baselineCells = new Map(baselineGrid.map(cell => [`${cell.column}:${cell.row}`, cell]))
  const cells = selectedGrid.map(cell => {
    const other = baselineCells.get(`${cell.column}:${cell.row}`)
    const selectedSupported = selected.exposureSeconds > 0 && selectedLocation.sampleSize > 0
    const baselineSupported = baseline.exposureSeconds > 0 && baselineLocation.sampleSize > 0
    return {
      column: cell.column,
      row: cell.row,
      selectedValue: selectedSupported ? cell.share : null,
      baselineValue: baselineSupported ? (other?.share ?? 0) : null,
      delta: selectedSupported && baselineSupported ? cell.share - (other?.share ?? 0) : null,
      selectedRawCount: cell.rawCount,
      baselineRawCount: other?.rawCount ?? 0,
      selectedSupported,
      baselineSupported,
      selectedSparse: cell.rawCount > 0 && cell.rawCount < 3,
      baselineSparse: Boolean(other?.rawCount && other.rawCount < 3),
    }
  })
  const movement = selectedLocation.x != null
    && selectedLocation.y != null
    && baselineLocation.x != null
    && baselineLocation.y != null
    ? {
        from: { x: baselineLocation.x, y: baselineLocation.y },
        to: { x: selectedLocation.x, y: selectedLocation.y },
        distance: Math.hypot(selectedLocation.x - baselineLocation.x, selectedLocation.y - baselineLocation.y),
        label: gridKey === 'defensiveGrid' ? 'Player average defensive-action movement' : 'Player average touch movement',
      }
    : null
  const teamLocation = teamSelected?.[locationKey]
  const teamBaselineLocation = teamBaseline?.[locationKey]
  const teamReference = teamLocation?.x != null
    && teamLocation.y != null
    ? {
        id: 'matched-team-average',
        label: 'Matched team avg',
        coordinate: { x: teamLocation.x, y: teamLocation.y },
        sampleSize: teamLocation.sampleSize,
        tone: 'reference' as const,
        description: teamBaselineLocation?.x != null && teamBaselineLocation.y != null
          ? 'Team average during the same verified player intervals'
          : 'Team average during selected verified player intervals',
      }
    : null
  const teamReferenceMovement = teamLocation?.x != null
    && teamLocation.y != null
    && teamBaselineLocation?.x != null
    && teamBaselineLocation.y != null
    ? {
        from: { x: teamBaselineLocation.x, y: teamBaselineLocation.y },
        to: { x: teamLocation.x, y: teamLocation.y },
        distance: Math.hypot(teamLocation.x - teamBaselineLocation.x, teamLocation.y - teamBaselineLocation.y),
        label: 'Matched team average movement over the same verified player intervals',
      }
    : null
  return {
    contractVersion: 'state-delta-map/v1',
    subject: { type: 'player', id: playerId, name: playerName },
    metric: {
      label: metricLabel,
      unit: gridKey === 'defensiveGrid' ? 'share of player defensive actions' : 'share of player touches',
      mode: 'distribution',
      description: gridKey === 'defensiveGrid'
        ? 'Within-player located defensive-action distribution; raw totals are not subtracted.'
        : 'Within-player located-touch distribution; raw totals are not subtracted.',
      zeroEpsilon: 0.0001,
    },
    selected: deltaCohortEvidence(selectedLabel, selected, locationKey),
    baseline: deltaCohortEvidence(baselineLabel, baseline, locationKey),
    grid: { columns: 24, rows: 16, cells },
    markers: {
      selected: selectedLocation.x != null && selectedLocation.y != null ? {
        id: 'selected-average-touch',
        label: selectedLabel,
        coordinate: { x: selectedLocation.x, y: selectedLocation.y },
        sampleSize: selectedLocation.sampleSize,
        tone: 'selected',
      } : null,
      baseline: baselineLocation.x != null && baselineLocation.y != null ? {
        id: 'baseline-average-touch',
        label: baselineLabel,
        coordinate: { x: baselineLocation.x, y: baselineLocation.y },
        sampleSize: baselineLocation.sampleSize,
        tone: 'baseline',
      } : null,
      teamReference,
    },
    movement,
    teamReferenceMovement,
    notes: [
      'Cells are normalized within each verified player cohort; colours show selected minus baseline share.',
      'The dashed team marker is a matched-interval reference, not player movement.',
    ],
  }
}
function formatRate(cohort: PlayerStateCohort, key: string) {
  const value = cohort.rates[key]?.per90
  return value == null ? '—' : value.toFixed(2)
}

export function formatCohortMetric(cohort: PlayerStateCohort, key: string, rateMode: ProfileRateMode) {
  if (rateMode === 'per90') return formatRate(cohort, key)
  const value = cohort.summary[key]
  return typeof value === 'number' ? value.toLocaleString() : '—'
}

export function formatComparisonMetric(comparison: PlayerStateComparisonPayload, key: string, rateMode: ProfileRateMode) {
  if (rateMode === 'per90') return comparisonRate(comparison.comparison, key)
  if (!comparison.baseline) return '—'
  const selected = comparison.selected.summary[key]
  const baseline = comparison.baseline.summary[key]
  if (typeof selected !== 'number' || typeof baseline !== 'number') return '—'
  const delta = selected - baseline
  return `${delta >= 0 ? '+' : ''}${delta.toLocaleString()}`
}

function comparisonRate(comparison: PlayerStateComparisonPayload['comparison'], key: string) {
  const value = comparison?.selectedMinusBaseline[key]?.absolute
  return value == null ? '—' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}`
}

export function formatPercent(value: number | null | undefined) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

export function formatMetres(value: number | null | undefined) {
  return value == null ? '—' : `${value.toFixed(1)}m`
}

export function playerDefensiveSelection(cohort: PlayerStateCohort, families: DefensiveActionFamily[]) {
  if (families.length === ALL_DEFENSIVE_ACTION_FAMILIES.length) return cohort
  const familyRows = families.reduce<Array<NonNullable<PlayerStateCohort['defensiveByFamily'][DefensiveActionFamily]>>>((rows, family) => {
    const evidence = cohort.defensiveByFamily[family]
    if (evidence) rows.push(evidence)
    return rows
  }, [])
  const locatedCount = familyRows.reduce((sum, evidence) => sum + evidence.locatedCount, 0)
  const count = familyRows.reduce((sum, evidence) => sum + evidence.count, 0)
  const sourceGrid = familyRows[0]?.grid ?? cohort.defensiveGrid
  const defensiveGrid = sourceGrid.map((cell, index): ActionGridCell => {
    let rawCount = 0
    let per90Count = 0
    for (const evidence of familyRows) {
      const value = evidence.grid[index]
      if (!value) continue
      rawCount += value.rawCount
      per90Count += value.per90Count
    }
    return {
      column: cell.column,
      row: cell.row,
      rawCount,
      per90Count,
      share: locatedCount ? rawCount / locatedCount : 0,
    }
  })
  const weightedMean = familyRows.reduce((sum, evidence) => (
    sum + (evidence.height.mean ?? 0) * evidence.height.sampleSize
  ), 0)
  const yTotal = defensiveGrid.reduce((sum, cell) => (
    sum + ((cell.row + 0.5) / 16) * 100 * cell.rawCount
  ), 0)
  return {
    ...cohort,
    summary: { ...cohort.summary, defensive_actions: count },
    defensiveGrid,
    defensiveLocation: {
      x: locatedCount ? weightedMean / locatedCount : null,
      y: locatedCount ? yTotal / locatedCount : null,
      sampleSize: locatedCount,
    },
    defensiveHeight: {
      sampleSize: locatedCount,
      mean: locatedCount ? weightedMean / locatedCount : null,
      median: familyRows.length === 1 ? familyRows[0].height.median : null,
    },
  }
}
