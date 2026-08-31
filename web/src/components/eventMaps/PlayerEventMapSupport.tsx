/* eslint-disable react-refresh/only-export-components */
import type { ReactNode } from 'react'
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
import { ProfileSelectControl } from '../profile/ProfileScopeSelector'
import { statePresentation } from '../../lib/eventMaps/statePresentation'
import { ALL_DEFENSIVE_ACTION_FAMILIES } from './defensiveActionFamilies'
import { EventPitchStage } from './EventMapUi'

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

function cohortReliability(cohort: PlayerStateCohort): 'verified' | 'partial' | 'sparse' | 'unsupported' | 'unavailable' {
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

function formatPercent(value: number | null | undefined) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

function formatMetres(value: number | null | undefined) {
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

export function EvidenceRow({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-t border-line-bright pt-2 text-[10px]">
      <span className="text-ink-dim">{label}</span>
      <span className="text-right font-mono text-ink">{value}{detail ? <span className="ml-1 text-[8px] text-ink-muted">{detail}</span> : null}</span>
    </div>
  )
}

function ReliabilityBadge({ status, label }: { status: 'verified' | 'partial' | 'sparse' | 'unsupported' | 'unavailable'; label?: string }) {
  return <span className={`text-[9px] font-bold uppercase tracking-[0.08em] ${status === 'verified' ? 'text-mint' : status === 'unavailable' ? 'text-ember' : 'text-gold'}`}>{label ?? status}</span>
}

export function StateEvidenceCard({ label, state, children }: { label: string; state: string; children: ReactNode }) {
  const presentation = statePresentation(state)
  return (
    <section className="border border-line/60 bg-paper/40 px-3 py-2" style={{ borderTopColor: presentation.color }}>
      <p className="text-[9px] font-bold uppercase tracking-[0.1em]" style={{ color: presentation.color }}>{label}</p>
      <div className="mt-2 space-y-2">{children}</div>
    </section>
  )
}

function PassingCohortCard({ label, state, cohort, rateMode }: { label: string; state: string; cohort: PlayerStateCohort; rateMode: ProfileRateMode }) {
  return (
    <StateEvidenceCard label={label} state={state}>
      <EvidenceRow label="Attempts" value={formatCohortMetric(cohort, 'pass_attempts', rateMode)} />
      <EvidenceRow label="Completion" value={formatPercent(cohort.passing.completionRate)} />
      <EvidenceRow label="Progressive passes" value={formatCohortMetric(cohort, 'progressive_passes', rateMode)} />
      <EvidenceRow label="Mean length · forward" value={`${formatMetres(cohort.passing.meanLengthMetres)} · ${formatMetres(cohort.passing.meanForwardMetres)}`} />
      <EvidenceRow label="Forward share" value={formatPercent(cohort.passing.forwardShare)} />
      <EvidenceRow label="Carries" value={formatCohortMetric(cohort, 'carries', rateMode)} />
      <EvidenceRow label="Progressive carries" value={formatCohortMetric(cohort, 'progressive_carries', rateMode)} />
      <EvidenceRow label="Carry length · forward" value={`${formatMetres(cohort.carrying.meanLengthMetres)} · ${formatMetres(cohort.carrying.meanForwardMetres)}`} />
      <EvidenceRow label="Team pass share" value={formatPercent(cohort.teamActionShares.passes?.share)} detail="matched" />
      <EvidenceRow label="Team progression share" value={formatPercent(cohort.teamActionShares.progressive_actions?.share)} detail="matched" />
    </StateEvidenceCard>
  )
}

export function PlayerPassingEvidence({ comparison, rateMode }: { comparison: PlayerStateComparisonPayload; rateMode: ProfileRateMode }) {
  const selected = comparison.selected
  const baseline = comparison.baseline
  const selectedState = comparison.stateLens.selected.state
  const baselineState = comparison.stateLens.comparison.baseline?.state ?? 'all'
  return (
    <section className="border border-line-bright bg-panel p-3" aria-label="Player passing and carrying evidence">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
        <h3 className="text-[11px] font-black uppercase tracking-[0.14em] text-ink">Passing & carrying evidence</h3>
        <p className="text-[9px] text-ink-muted">{rateMode === 'per90' ? 'Rate view · verified state minutes' : 'Selected-context totals'}</p>
      </div>
      <div className={`mt-3 grid gap-3 ${baseline ? 'sm:grid-cols-2' : ''}`}>
        <PassingCohortCard label={scopeLabel(selectedState)} state={selectedState} cohort={selected} rateMode={rateMode} />
        {baseline ? <PassingCohortCard label={scopeLabel(baselineState)} state={baselineState} cohort={baseline} rateMode={rateMode} /> : null}
      </div>
      {baseline ? <div className="mt-3 border-t border-line-bright pt-2">
        <p className="text-[8px] font-bold uppercase tracking-[0.12em] text-ink-dim">Selected minus comparison</p>
        <div className="mt-2 grid gap-x-4 gap-y-1 sm:grid-cols-2">
          {(['pass_attempts', 'progressive_passes', 'carries', 'progressive_carries'] as const).map(key => <EvidenceRow key={key} label={key.replaceAll('_', ' ')} value={formatComparisonMetric(comparison, key, rateMode)} />)}
          <EvidenceRow label="Team pass share" value={comparison.comparison?.actionShareChange.passes == null ? '—' : `${comparison.comparison.actionShareChange.passes >= 0 ? '+' : ''}${(comparison.comparison.actionShareChange.passes * 100).toFixed(1)}pp`} />
          <EvidenceRow label="Team progression share" value={comparison.comparison?.actionShareChange.progressive_actions == null ? '—' : `${comparison.comparison.actionShareChange.progressive_actions >= 0 ? '+' : ''}${(comparison.comparison.actionShareChange.progressive_actions * 100).toFixed(1)}pp`} />
        </div>
      </div> : null}
      <p className="mt-3 border-t border-line-bright pt-2 text-[9px] leading-relaxed text-ink-muted">{comparison.teamContext.available ? 'Team shares use team events and derived carries from the same verified intervals.' : 'Choose one team split to enable matched-team shares.'}</p>
    </section>
  )
}

export function PlayerShootingEvidence({ comparison, rateMode }: { comparison: PlayerStateComparisonPayload; rateMode: ProfileRateMode }) {
  const selected = comparison.selected
  const baseline = comparison.baseline
  const card = (label: string, state: string, cohort: PlayerStateCohort) => <StateEvidenceCard label={label} state={state}>
    <EvidenceRow label="Shots" value={formatCohortMetric(cohort, 'shots', rateMode)} />
    <EvidenceRow label="Goals" value={formatCohortMetric(cohort, 'goals', rateMode)} />
    <EvidenceRow label="Big chances" value={formatCohortMetric(cohort, 'big_chance_shots', rateMode)} />
    <EvidenceRow label="Team shot share" value={formatPercent(cohort.teamActionShares.shots?.share)} detail="matched" />
  </StateEvidenceCard>
  return (
    <section className="border border-line-bright bg-panel p-3" aria-label="Player shooting evidence">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
        <h3 className="text-[11px] font-black uppercase tracking-[0.14em] text-ink">Shooting evidence</h3>
        <p className="text-[9px] text-ink-muted">Rare shots and goals stay visibly qualified.</p>
      </div>
      <div className={`mt-3 grid gap-3 ${baseline ? 'sm:grid-cols-2' : ''}`}>
        {card(scopeLabel(comparison.stateLens.selected.state), comparison.stateLens.selected.state, selected)}
        {baseline ? card(scopeLabel(comparison.stateLens.comparison.baseline?.state ?? 'all'), comparison.stateLens.comparison.baseline?.state ?? 'all', baseline) : null}
      </div>
      <p className="mt-3 border-t border-line-bright pt-2 text-[9px] leading-relaxed text-ink-muted">Shot locations and goal zones remain event-backed. A low raw count is descriptive evidence, not a stable finishing or clutch claim.</p>
    </section>
  )
}

export function PlayerExposureCard({ label, cohort }: { label: string; cohort: PlayerStateCohort }) {
  const reliability = cohortReliability(cohort)
  return (
    <div className="border border-control-border bg-raised/35 px-3 py-2" data-player-state-cohort={label}>
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[10px] font-bold uppercase tracking-[0.1em] text-ink">{label}</p>
        <ReliabilityBadge status={reliability} />
      </div>
      <div className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-[10px] text-ink-dim">
        <span>{cohort.exposureMinutes.toLocaleString()} verified min</span>
        <span>{cohort.evidence.matchCount.toLocaleString()} matches</span>
        <span>{cohort.evidence.episodeCount.toLocaleString()} episodes</span>
        <span>{cohort.summary.actions.toLocaleString()} actions</span>
        <span>{cohort.touchLocation.sampleSize.toLocaleString()} located touches</span>
        <span className={cohort.evidence.matchesExcluded ? 'text-gold' : ''}>{cohort.evidence.matchesExcluded.toLocaleString()} excluded matches</span>
      </div>
    </div>
  )
}

export function PenaltyToggle({ value, onChange }: {
  value: PenaltyOption
  onChange: (value: PenaltyOption) => void
}) {
  return (
    <ProfileSelectControl compact ariaLabel="Penalty inclusion" value={value} options={PENALTY_OPTIONS} onChange={next => onChange(next as PenaltyOption)} className="w-36" />
  )
}

export function ShotMapFilters({
  outcome,
  chance,
  onOutcomeChange,
  onChanceChange,
}: {
  outcome: ShotOutcomeFilter
  chance: ShotChanceFilter
  onOutcomeChange: (value: ShotOutcomeFilter) => void
  onChanceChange: (value: ShotChanceFilter) => void
}) {
  return (
    <span className="flex flex-wrap justify-end gap-1.5">
      <ProfileSelectControl compact ariaLabel="Shot outcome" value={outcome} options={SHOT_OUTCOME_FILTERS} onChange={next => onOutcomeChange(next as ShotOutcomeFilter)} className="w-36" />
      <ProfileSelectControl compact ariaLabel="Shot chance classification" value={chance} options={SHOT_CHANCE_FILTERS} onChange={next => onChanceChange(next as ShotChanceFilter)} className="w-40" />
    </span>
  )
}

export function MapStage({ map, expanded, setExpanded, children }: {
  map: PlayerMap
  expanded: PlayerMap | null
  setExpanded: (map: PlayerMap | null) => void
  children: ReactNode
}) {
  return (
    <EventPitchStage expanded={expanded === map} onExpandedChange={next => setExpanded(next ? map : null)}>
      {children}
    </EventPitchStage>
  )
}
