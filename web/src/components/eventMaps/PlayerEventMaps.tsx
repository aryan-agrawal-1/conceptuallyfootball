import { useQuery } from '@tanstack/react-query'
import { ChevronDown } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchGkShotZones, fetchPlayerEventProfile, fetchPlayerPassMap, fetchPlayerShotZones, fetchPlayerStateComparison } from '../../lib/eventMaps/api'
import { eventMatchExportLabel, type EventMapExportContext } from '../../lib/eventMaps/exportContext'
import { stateLensRequest } from '../../lib/eventMaps/stateLensUrl'
import type { SelectablePitchEvent } from '../../lib/eventMaps/selection'
import type { PlayerPassFilter, PlayerPassOutcome, PlayerStateComparisonPayload, PlayerStateCohort, ShotOutcome, ShotZoneVariantKey, StateLensMetadata } from '../../types/eventMaps'
import type { StateDeltaMapContract } from '../../lib/eventMaps/deltaMap'
import { PortraitPitch } from './PortraitPitch'
import { GoalZoneGridView, GoalZoneTotals } from './GoalZones'
import { StateDeltaMap } from './StateDeltaMap'
import { StateLensControls } from './StateLensControls'
import {
  EventCoverage, EventMapCard, EventMapNotice, EventMatchFilter, EventMetricStrip,
  EventMapViewTabs, EventPitchStage, EventSelectionDetails, ShotMapLegend,
} from './EventMapUi'

const PASS_FILTERS: Array<{ value: PlayerPassFilter; label: string }> = [
  { value: 'all', label: 'All types' },
  { value: 'progressive', label: 'Progressive' },
  { value: 'final_third_entry', label: 'Final third' },
  { value: 'box_entry', label: 'Box entries' },
  { value: 'key_pass', label: 'Key passes' },
  { value: 'cross', label: 'Crosses' },
  { value: 'long_ball', label: 'Long balls' },
]

const CARRY_FILTERS = PASS_FILTERS.slice(0, 4)
const SHARED_SPATIAL_FILTERS = new Set<PlayerPassFilter>(CARRY_FILTERS.map(filter => filter.value))

const PASS_OUTCOMES: Array<{ value: PlayerPassOutcome; label: string }> = [
  { value: 'all', label: 'All outcomes' },
  { value: 'completed', label: 'Completed' },
  { value: 'incomplete', label: 'Incomplete' },
]

type PassMapLayer = 'all' | 'passes' | 'carries'

const PASS_MAP_LAYERS: Array<{ value: PassMapLayer; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'passes', label: 'Passes' },
  { value: 'carries', label: 'Carries' },
]

type ShotOutcomeFilter = 'all' | ShotOutcome
type ShotChanceFilter = 'all' | 'big_chance' | 'standard_chance'

const SHOT_OUTCOME_FILTERS: Array<{ value: ShotOutcomeFilter; label: string }> = [
  { value: 'all', label: 'All outcomes' },
  { value: 'goal', label: 'Goals' },
  { value: 'saved', label: 'Saved' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'off_target', label: 'Off target' },
  { value: 'woodwork', label: 'Woodwork' },
]

const SHOT_CHANCE_FILTERS: Array<{ value: ShotChanceFilter; label: string }> = [
  { value: 'all', label: 'All chances' },
  { value: 'big_chance', label: 'Big chances' },
  { value: 'standard_chance', label: 'Standard chances' },
]

export type PlayerEventMapTeam = { id: number; name: string }
type PlayerMap = 'passes' | 'shots' | 'actions' | 'zones' | 'gk-zones'

type PenaltyOption = ShotZoneVariantKey

const PENALTY_OPTIONS: Array<{ value: PenaltyOption; label: string }> = [
  { value: 'all', label: 'All shots' },
  { value: 'open_play', label: 'Non-penalties' },
  { value: 'penalties_only', label: 'Penalties' },
]

type PlayerAnalysisMode = 'overview' | 'passing' | 'shooting' | 'defending'

function scopeLabel(value: string | null | undefined) {
  if (!value || value === 'all') return 'All states'
  return value.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase())
}

function stateExportFilters(stateLens: StateLensMetadata) {
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

function stateShiftContract(
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

function EvidenceRow({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-t border-line-bright pt-2 text-[10px]">
      <span className="text-ink-dim">{label}</span>
      <span className="text-right font-mono text-ink">{value}{detail ? <span className="ml-1 text-[8px] text-ink-muted">{detail}</span> : null}</span>
    </div>
  )
}

function PlayerPassingEvidence({ comparison }: { comparison: PlayerStateComparisonPayload }) {
  const selected = comparison.selected
  const baseline = comparison.baseline
  const passesShare = selected.teamActionShares.passes
  const progressiveShare = selected.teamActionShares.progressive_actions
  const shareChange = comparison.comparison?.actionShareChange
  return (
    <section className="border border-line-bright bg-panel p-3" aria-label="Player passing and carrying evidence">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
        <h3 className="text-[11px] font-black uppercase tracking-[0.14em] text-ink">Passing & carrying evidence</h3>
        <p className="text-[9px] text-ink-muted">Counts are raw; rates use verified state minutes.</p>
      </div>
      <div className="mt-3 grid gap-x-5 gap-y-3 sm:grid-cols-2">
        <div className="space-y-2">
          <p className="text-[9px] font-bold uppercase tracking-[0.1em] text-electric">Passing</p>
          <EvidenceRow label="Attempts" value={`${selected.passing.attempts.toLocaleString()} · ${formatRate(selected, 'pass_attempts')}`} detail="raw · /90" />
          <EvidenceRow label="Completion" value={`${selected.passing.completed.toLocaleString()}/${selected.passing.attempts.toLocaleString()} · ${formatPercent(selected.passing.completionRate)}`} detail="raw · rate" />
          <EvidenceRow label="Progressive" value={`${selected.passing.progressive.toLocaleString()} · ${formatRate(selected, 'progressive_passes')}`} detail="raw · /90" />
          <EvidenceRow label="Length / forward" value={`${formatMetres(selected.passing.meanLengthMetres)} · ${formatMetres(selected.passing.meanForwardMetres)}`} detail="mean" />
          <EvidenceRow label="Forward share" value={formatPercent(selected.passing.forwardShare)} />
        </div>
        <div className="space-y-2">
          <p className="text-[9px] font-bold uppercase tracking-[0.1em] text-gold">Carrying & matched team</p>
          <EvidenceRow label="Carries" value={`${selected.carrying.attempts.toLocaleString()} · ${formatRate(selected, 'carries')}`} detail="raw · /90" />
          <EvidenceRow label="Progressive carries" value={`${selected.carrying.progressive.toLocaleString()} · ${formatRate(selected, 'progressive_carries')}`} detail="raw · /90" />
          <EvidenceRow label="Carry length / forward" value={`${formatMetres(selected.carrying.meanLengthMetres)} · ${formatMetres(selected.carrying.meanForwardMetres)}`} detail="mean" />
          <EvidenceRow label="Team pass share" value={passesShare ? `${formatPercent(passesShare.share)}${shareChange?.passes == null ? '' : ` · ${shareChange.passes >= 0 ? '+' : ''}${(shareChange.passes * 100).toFixed(1)}pp`}` : '—'} detail="matched intervals" />
          <EvidenceRow label="Team progression share" value={progressiveShare ? `${formatPercent(progressiveShare.share)}${shareChange?.progressive_actions == null ? '' : ` · ${shareChange.progressive_actions >= 0 ? '+' : ''}${(shareChange.progressive_actions * 100).toFixed(1)}pp`}` : '—'} detail="matched intervals" />
        </div>
      </div>
      {baseline ? <p className="mt-3 border-t border-line-bright pt-2 text-[9px] leading-relaxed text-ink-muted">Selected-minus-baseline rate changes are shown in Overview; this panel keeps individual pass/carry units explicit. {comparison.teamContext.available ? 'Team shares use team events and derived carries from the same verified intervals.' : 'Choose one team split to enable matched-team shares.'}</p> : null}
    </section>
  )
}

function PlayerShootingEvidence({ comparison }: { comparison: PlayerStateComparisonPayload }) {
  const selected = comparison.selected
  const shotShare = selected.teamActionShares.shots
  const shotShareChange = comparison.comparison?.actionShareChange.shots
  return (
    <section className="border border-line-bright bg-panel p-3" aria-label="Player shooting evidence">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
        <h3 className="text-[11px] font-black uppercase tracking-[0.14em] text-ink">Shooting evidence</h3>
        <p className="text-[9px] text-ink-muted">Rare shots and goals stay visibly qualified.</p>
      </div>
      <div className="mt-3 grid gap-x-5 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
        <EvidenceRow label="Shots" value={`${selected.summary.shots.toLocaleString()} · ${formatRate(selected, 'shots')}`} detail="raw · /90" />
        <EvidenceRow label="Goals" value={`${selected.summary.goals.toLocaleString()} · ${formatRate(selected, 'goals')}`} detail="raw · /90" />
        <EvidenceRow label="Big chances" value={`${selected.summary.big_chance_shots.toLocaleString()} · ${formatRate(selected, 'big_chance_shots')}`} detail="raw · /90" />
        <EvidenceRow label="Team shot share" value={shotShare ? `${formatPercent(shotShare.share)}${shotShareChange == null ? '' : ` · ${shotShareChange >= 0 ? '+' : ''}${(shotShareChange * 100).toFixed(1)}pp`}` : '—'} detail="matched intervals" />
      </div>
      <p className="mt-3 border-t border-line-bright pt-2 text-[9px] leading-relaxed text-ink-muted">Shot locations and goal zones remain event-backed. A low raw count is descriptive evidence, not a stable finishing or clutch claim.</p>
    </section>
  )
}

function PlayerExposureCard({ label, cohort }: { label: string; cohort: PlayerStateCohort }) {
  const reliability = cohortReliability(cohort)
  return (
    <div className="border border-control-border bg-raised/35 px-3 py-2" data-player-state-cohort={label}>
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[10px] font-bold uppercase tracking-[0.1em] text-ink">{label}</p>
        <span className={`text-[9px] font-bold uppercase tracking-[0.08em] ${reliability === 'verified' ? 'text-mint' : reliability === 'unavailable' ? 'text-ember' : 'text-gold'}`}>{reliability}</span>
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

function PenaltyToggle({ value, onChange }: {
  value: PenaltyOption
  onChange: (value: PenaltyOption) => void
}) {
  return (
    <span className="relative inline-flex">
      <select
        aria-label="Penalty inclusion"
        value={value}
        onChange={event => onChange(event.target.value as PenaltyOption)}
        className="h-8 max-w-36 appearance-none border border-control-border bg-raised py-0 pl-2.5 pr-9 text-[9px] font-bold uppercase tracking-[0.08em] text-control-fg outline-none focus:border-electric"
      >
        {PENALTY_OPTIONS.map(option => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
      <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-control-fg" aria-hidden="true" />
    </span>
  )
}

function ShotMapFilters({
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
      <span className="relative inline-flex">
        <select
          aria-label="Shot outcome"
          value={outcome}
          onChange={event => onOutcomeChange(event.target.value as ShotOutcomeFilter)}
          className="h-8 max-w-36 appearance-none border border-control-border bg-raised py-0 pl-2.5 pr-9 text-[9px] font-bold uppercase tracking-[0.08em] text-control-fg outline-none focus:border-electric"
        >
          {SHOT_OUTCOME_FILTERS.map(option => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-control-fg" aria-hidden="true" />
      </span>
      <span className="relative inline-flex">
        <select
          aria-label="Shot chance classification"
          value={chance}
          onChange={event => onChanceChange(event.target.value as ShotChanceFilter)}
          className="h-8 max-w-40 appearance-none border border-control-border bg-raised py-0 pl-2.5 pr-9 text-[9px] font-bold uppercase tracking-[0.08em] text-control-fg outline-none focus:border-electric"
        >
          {SHOT_CHANCE_FILTERS.map(option => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-control-fg" aria-hidden="true" />
      </span>
    </span>
  )
}

function MapStage({ map, expanded, setExpanded, children }: {
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

export function PlayerEventMaps({ playerId, competition, season, teams, positionGroup }: {
  playerId: number
  competition: string
  season: string
  teams: PlayerEventMapTeam[]
  positionGroup?: string
}) {
  const [searchParams, setSearchParams] = useSearchParams()
  const lensRequest = stateLensRequest(searchParams)
  const [passFilter, setPassFilter] = useState<PlayerPassFilter>('all')
  const [passOutcome, setPassOutcome] = useState<PlayerPassOutcome>('all')
  const [passMapLayer, setPassMapLayer] = useState<PassMapLayer>('all')
  const [shotOutcome, setShotOutcome] = useState<ShotOutcomeFilter>('all')
  const [shotChance, setShotChance] = useState<ShotChanceFilter>('all')
  const [selection, setSelection] = useState<SelectablePitchEvent | null>(null)
  const [expanded, setExpanded] = useState<PlayerMap | null>(null)
  const [shotPenalties, setShotPenalties] = useState<PenaltyOption>('all')
  const [analysisMode, setAnalysisMode] = useState<PlayerAnalysisMode>('overview')
  const matchRef = searchParams.get('match')
  const teamIdValue = searchParams.get('team')
  const teamId = teamIdValue ? Number(teamIdValue) : null
  const isGoalkeeper = positionGroup === 'GK'
  const setLensParams = (next: URLSearchParams) => {
    setSelection(null)
    setSearchParams(next)
  }
  const profileQuery = useQuery({
    queryKey: ['player-event-profile', playerId, competition, season, teamId, matchRef, lensRequest],
    queryFn: () => fetchPlayerEventProfile(playerId, competition, season, teamId, matchRef, lensRequest),
    staleTime: 10 * 60 * 1000,
  })
  const comparisonQuery = useQuery({
    queryKey: ['player-state-comparison', playerId, competition, season, teamId, matchRef, lensRequest],
    queryFn: () => fetchPlayerStateComparison(playerId, competition, season, teamId, matchRef, lensRequest),
    enabled: profileQuery.data != null,
    staleTime: 10 * 60 * 1000,
  })
  const profile = profileQuery.data
  const passQuery = useQuery({
    queryKey: ['player-event-passes', playerId, competition, season, teamId, matchRef, passFilter, passOutcome, lensRequest],
    queryFn: () => fetchPlayerPassMap(playerId, competition, season, passFilter, passOutcome, teamId, matchRef, lensRequest),
    enabled: profile?.modules.passMap.available === true,
    staleTime: 10 * 60 * 1000,
  })
  const zoneVariantKey: ShotZoneVariantKey = shotPenalties
  const shotZonesQuery = useQuery({
    queryKey: ['player-shot-zones', playerId, competition, season, teamId, matchRef, lensRequest],
    queryFn: () => fetchPlayerShotZones(playerId, competition, season, teamId, matchRef, lensRequest),
    enabled: !isGoalkeeper && profile?.modules.shotMap.available === true,
    staleTime: 10 * 60 * 1000,
  })
  const gkZonesQuery = useQuery({
    queryKey: ['player-gk-shot-zones', playerId, competition, season, matchRef, lensRequest],
    queryFn: () => fetchGkShotZones(playerId, competition, season, matchRef, lensRequest),
    enabled: isGoalkeeper,
    staleTime: 10 * 60 * 1000,
  })
  const locatedTouchCount = useMemo(
    () => profile?.touchGrid.reduce((total, cell) => total + cell.rawCount, 0) ?? 0,
    [profile?.touchGrid],
  )
  const visiblePasses = passMapLayer === 'carries' ? [] : passQuery.data?.passes ?? []
  const visibleCarries = passMapLayer === 'passes' ? [] : passQuery.data?.carries ?? []
  const categoryFilters = passMapLayer === 'carries' ? CARRY_FILTERS : PASS_FILTERS
  const passCountLabel = `${passQuery.data?.totalMatching.toLocaleString() ?? '—'} ${PASS_OUTCOMES.find(item => item.value === passOutcome)?.label.toLowerCase()} · ${PASS_FILTERS.find(item => item.value === passFilter)?.label.toLowerCase()}`
  const carryCountLabel = `${passQuery.data?.totalCarries.toLocaleString() ?? '—'} derived carries · ${PASS_FILTERS.find(item => item.value === passFilter)?.label.toLowerCase()}`
  const passMapDescription = passMapLayer === 'all'
    ? `${passCountLabel} · ${carryCountLabel} in this scope.`
    : `${passMapLayer === 'passes' ? passCountLabel : carryCountLabel} in this scope.`
  const filteredShots = useMemo(
    () => profile?.shots.filter(shot => (
      (shotOutcome === 'all' || shot.outcome === shotOutcome)
      && (shotChance === 'all'
        || (shotChance === 'big_chance' ? shot.bigChance : !shot.bigChance))
    )) ?? [],
    [profile?.shots, shotChance, shotOutcome],
  )
  const shotMapDescription = profile?.shots.length
    ? `${filteredShots.length.toLocaleString()} of ${profile.shots.length.toLocaleString()} shots shown · ${SHOT_OUTCOME_FILTERS.find(option => option.value === shotOutcome)?.label.toLowerCase()} · ${SHOT_CHANCE_FILTERS.find(option => option.value === shotChance)?.label.toLowerCase()}.`
    : 'No shots were recorded in this scope.'

  if (profileQuery.isLoading) return <div className="space-y-3"><StateLensControls searchParams={searchParams} onChange={setLensParams} /><EventMapNotice kind="loading" title="Loading player event profile" /></div>
  if (profileQuery.isError || !profile) {
    return <div className="space-y-3"><StateLensControls searchParams={searchParams} onChange={setLensParams} /><EventMapNotice kind="error" title="Player event profile failed to load" onRetry={() => profileQuery.refetch()}>
      {profileQuery.error?.message ?? 'The event-profile service returned no data.'}
    </EventMapNotice></div>
  }

  const stateLens = profile.stateLens
  const comparison = comparisonQuery.data
  const selectedStateLabel = scopeLabel(stateLens?.selected.state)
  const baselineStateLabel = scopeLabel(stateLens?.comparison.baseline?.state)
  const touchShift = comparison
      ? stateShiftContract(
        playerId,
        profile.playerName,
        comparison.selected,
        comparison.baseline,
        selectedStateLabel,
        baselineStateLabel,
        comparison.teamContext.selected,
        comparison.teamContext.baseline,
      )
    : null
  const defensiveShift = comparison
      ? stateShiftContract(
        playerId,
        profile.playerName,
        comparison.selected,
        comparison.baseline,
        selectedStateLabel,
        baselineStateLabel,
        comparison.teamContext.selected,
        comparison.teamContext.baseline,
        'Defensive territory State Shift',
        'defensiveGrid',
      )
    : null

  const exportContext: EventMapExportContext = {
    subjectName: profile.playerName,
    subjectType: 'Player',
    competition,
    season,
    filters: [
      { label: 'Match', value: eventMatchExportLabel(profile.matches, matchRef) },
      { label: 'Team', value: profile.teamName ?? (teams.length === 1 ? teams[0].name : 'All teams') },
      ...(stateLens ? stateExportFilters(stateLens) : []),
    ],
  }
  const mapExportContext = (filters: EventMapExportContext['filters'] = []): EventMapExportContext => ({
    ...exportContext,
    filters: [...exportContext.filters, ...filters],
  })

  return (
    <section aria-label="Player event maps" className="relative">
      <div className="mb-3 flex flex-col gap-2 lg:flex-row lg:items-stretch">
        <div className="min-w-0 flex-1">
          <EventMetricStrip metrics={[
            { label: 'Passes', value: profile.summary.pass_attempts?.toLocaleString() ?? '—' },
            { label: 'Carries', value: passQuery.data?.totalAllCarries.toLocaleString() ?? '—' },
            { label: 'Shots', value: profile.summary.shots?.toLocaleString() ?? '—' },
            { label: 'Touches', value: locatedTouchCount.toLocaleString() },
          ]} />
        </div>
        <div className="min-w-[220px]"><EventCoverage coverage={profile.coverage} /></div>
        <EventMatchFilter matches={profile.matches} value={matchRef} onChange={value => {
          const next = new URLSearchParams(searchParams)
          if (value == null) next.delete('match')
          else next.set('match', value)
          setLensParams(next)
        }} />
        {teams.length > 1 ? (
          <label className="flex items-center justify-between gap-2 border border-line-bright bg-panel px-3 text-[9px] font-bold uppercase tracking-[0.14em] text-ink-dim sm:justify-start">
            Team split
            <select aria-label="Player team split" value={teamId ?? ''} onChange={event => {
              const next = new URLSearchParams(searchParams)
              if (event.target.value) next.set('team', event.target.value)
              else next.delete('team')
              next.delete('match')
              setLensParams(next)
            }} className="h-9 min-w-40 max-w-full border border-control-border bg-panel px-3 text-[10px] text-control-fg outline-none hover:border-electric focus:border-electric">
              <option value="">Season total</option>
              {teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}
            </select>
          </label>
        ) : null}
      </div>

      {stateLens ? <div className="mb-3">
        <StateLensControls metadata={stateLens} searchParams={searchParams} onChange={setLensParams} />
      </div> : null}
      {expanded && stateLens ? <div className="fixed left-3 right-16 top-3 z-[95] max-h-[45svh] overflow-y-auto sm:left-8 sm:right-20">
        <StateLensControls compact metadata={stateLens} searchParams={searchParams} onChange={setLensParams} />
      </div> : null}

      <nav className="mb-3 grid grid-cols-4 border-b border-line-bright" aria-label="Player state analysis">
        {([
          ['overview', 'Overview', 'Compare player state exposure and movement'],
          ['passing', 'Passing & Carrying', 'Inspect selected passes and derived carries'],
          ['shooting', 'Shooting', 'Inspect selected shots and goal zones'],
          ['defending', 'Defending', 'Inspect defensive territory and height'],
        ] as const).map(([value, label, description]) => (
          <button key={value} type="button" aria-pressed={analysisMode === value} onClick={() => { setAnalysisMode(value); setSelection(null) }} className={`border-b-2 px-2 py-2 text-left transition-colors hover:bg-raised sm:px-3 ${analysisMode === value ? 'border-electric text-electric' : 'border-transparent text-ink'}`}>
            <strong className="block text-[9px] uppercase tracking-[0.08em] sm:text-[10px] sm:tracking-[0.1em]">{label}</strong>
            <span className="mt-0.5 hidden text-[8px] text-ink-dim sm:block">{description}</span>
          </button>
        ))}
      </nav>

      {analysisMode === 'overview' ? (
        <section aria-label="Player State Lens overview" className="mb-3 space-y-3">
          {comparisonQuery.isLoading ? <EventMapNotice kind="loading" title="Loading verified player comparison" /> : comparisonQuery.isError || !comparison ? (
            <EventMapNotice kind="error" title="Player state comparison failed to load" onRetry={() => comparisonQuery.refetch()}>
              {comparisonQuery.error?.message ?? 'The verified player comparison service returned no data.'}
            </EventMapNotice>
          ) : (
            <>
              <div className="border border-line-bright bg-panel px-3 py-3">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <h2 className="text-[11px] font-black uppercase tracking-[0.14em] text-ink">What changed?</h2>
                    <p className="mt-1 max-w-3xl text-[10px] leading-relaxed text-ink-dim">
                      Rates use verified player minutes only. Team shares use the same team, matches, state cohorts, and on-pitch intervals.
                      {isGoalkeeper ? ' Goalkeeper evidence is limited to distribution, passing and shot-facing records.' : ' Position group: ' + (positionGroup ?? 'unknown') + '.'}
                    </p>
                  </div>
                  <div className="shrink-0 text-right text-[9px] uppercase tracking-[0.1em] text-electric">
                    {selectedStateLabel}{comparison.baseline ? ` · baseline ${baselineStateLabel}` : ''}
                  </div>
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  <PlayerExposureCard label={selectedStateLabel} cohort={comparison.selected} />
                  {comparison.baseline ? <PlayerExposureCard label={baselineStateLabel} cohort={comparison.baseline} /> : (
                    <div className="border border-control-border bg-raised/35 px-3 py-2 text-[10px] leading-relaxed text-ink-dim">
                      Select a comparison baseline in Refine state to see before/after rates, shares, movement and response-role evidence.
                    </div>
                  )}
                </div>
                <div className="mt-3 grid gap-x-4 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
                  {(['touches', 'pass_attempts', 'progressive_actions', 'shots', 'defensive_actions', 'carries', 'box_entries', 'take_ons'] as const).map(key => (
                    <div key={key} className="flex items-baseline justify-between gap-2 border-t border-line-bright pt-2 text-[10px]">
                      <span className="text-ink-dim">{key.replaceAll('_', ' ')}</span>
                      <span className="font-mono text-ink">{formatRate(comparison.selected, key)} <span className="text-[8px] text-ink-muted">/90</span>{comparison.baseline ? <span className={comparisonRate(comparison.comparison, key).startsWith('+') ? 'text-mint' : comparisonRate(comparison.comparison, key).startsWith('-') ? 'text-ember' : 'text-ink-muted'}> ({comparisonRate(comparison.comparison, key)})</span> : null}</span>
                    </div>
                  ))}
                </div>
                {comparison.teamContext.available && Object.keys(comparison.selected.teamActionShares).length ? <div className="mt-3 border-t border-line-bright pt-3">
                  <p className="text-[9px] font-bold uppercase tracking-[0.1em] text-ink-dim">Share of matched team actions</p>
                  <div className="mt-2 grid gap-x-4 gap-y-1.5 sm:grid-cols-2 lg:grid-cols-5">
                    {Object.entries(comparison.selected.teamActionShares).map(([key, share]) => {
                      const change = comparison.comparison?.actionShareChange[key]
                      return <div key={key} className="flex items-baseline justify-between gap-2 text-[10px]">
                        <span className="text-ink-dim">{key.replaceAll('_', ' ')}</span>
                        <span className="font-mono text-ink">{share.share == null ? '—' : `${(share.share * 100).toFixed(1)}%`}{change == null ? '' : <span className={change >= 0 ? 'text-mint' : 'text-ember'}> ({change >= 0 ? '+' : ''}{(change * 100).toFixed(1)}pp)</span>}</span>
                      </div>
                    })}
                  </div>
                  {comparison.comparison?.movement.matchedTeam ? <p className="mt-2 text-[9px] leading-relaxed text-ink-muted">Matched team movement: {comparison.comparison.movement.matchedTeam.x == null ? '—' : `${comparison.comparison.movement.matchedTeam.x >= 0 ? '+' : ''}${comparison.comparison.movement.matchedTeam.x.toFixed(1)} x`} · {comparison.comparison.movement.matchedTeam.y == null ? '—' : `${comparison.comparison.movement.matchedTeam.y >= 0 ? '+' : ''}${comparison.comparison.movement.matchedTeam.y.toFixed(1)} y`} pitch points. This reference covers the same verified player intervals.</p> : null}
                </div> : null}
                {!comparison.teamContext.available ? <EventMapNotice kind="sparse" title="Choose a team split for team-relative evidence">
                  This player has multiple team contexts. Select a team above before reading action shares or response roles.
                </EventMapNotice> : null}
              </div>

              {touchShift ? <div className="border border-line-bright bg-panel p-3"><StateDeltaMap contract={touchShift} /></div> : null}

              {comparison.responseRoles.length ? (
                <div className="border border-line-bright bg-panel px-3 py-3" aria-label="Evidence-backed response roles">
                  <div className="flex items-baseline justify-between gap-2">
                    <h3 className="text-[11px] font-black uppercase tracking-[0.14em] text-ink">Response observations</h3>
                    <span className="text-[9px] uppercase tracking-[0.1em] text-electric">Not a quality score</span>
                  </div>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    {comparison.responseRoles.map(role => <div key={role.label} className="border border-control-border bg-raised/35 px-3 py-2">
                      <p className="text-[10px] font-bold uppercase tracking-[0.1em] text-ink">{role.label} <span className="font-normal text-electric">· {role.confidence}</span></p>
                      <p className="mt-1 text-[10px] leading-relaxed text-ink-dim">{role.formula}</p>
                      <p className="mt-1 text-[9px] text-ink-muted">{role.reliability.verified_exposure_seconds.toLocaleString()} verified seconds · {role.reliability.matches} matches · {role.reliability.events} actions</p>
                      <details className="mt-2 border-t border-line-bright pt-2 text-[9px] leading-relaxed text-ink-dim">
                        <summary className="cursor-pointer font-bold uppercase tracking-[0.08em] text-electric">Show supporting observations</summary>
                        <div className="mt-2 space-y-1">
                          <p>Player touches: {formatRate(comparison.selected, 'touches')} /90 selected vs {comparison.baseline ? formatRate(comparison.baseline, 'touches') : '—'} baseline; progressive actions: {formatRate(comparison.selected, 'progressive_actions')} vs {comparison.baseline ? formatRate(comparison.baseline, 'progressive_actions') : '—'} /90.</p>
                          <p>Matched team progressive-action share: {comparison.selected.teamActionShares.progressive_actions?.share == null ? '—' : formatPercent(comparison.selected.teamActionShares.progressive_actions.share)} selected vs {comparison.baseline?.teamActionShares.progressive_actions?.share == null ? '—' : formatPercent(comparison.baseline.teamActionShares.progressive_actions.share)} baseline.</p>
                          <p>Average touch movement: {comparison.comparison?.movement.player.x == null || comparison.comparison.movement.player.y == null ? 'unsupported' : `${comparison.comparison.movement.player.x >= 0 ? '+' : ''}${comparison.comparison.movement.player.x.toFixed(1)} x · ${comparison.comparison.movement.player.y >= 0 ? '+' : ''}${comparison.comparison.movement.player.y.toFixed(1)} y pitch points`}; position group {comparison.positionGroup}.</p>
                          <p>Minimum evidence: {role.reliability.evidence_type ?? 'actions'} {role.reliability.evidence_count ?? '—'} / {role.reliability.minimum_evidence_count ?? '—'}; observations are directional and do not imply quality or causality.</p>
                        </div>
                      </details>
                    </div>)}
                  </div>
                </div>
              ) : comparison.baseline ? (
                <div className="border border-control-border bg-raised/30 px-3 py-2 text-[10px] leading-relaxed text-ink-dim">
                  No stable response role is assigned. Role labels require both verified cohorts, minimum events and matches, matched team evidence, and compatible observations.
                </div>
              ) : null}
              {comparison.baseline ? <details className="border border-control-border bg-raised/20 px-3 py-2 text-[9px] leading-relaxed text-ink-dim">
                <summary className="cursor-pointer font-bold uppercase tracking-[0.1em] text-electric">Role rules and thresholds</summary>
                <ul className="mt-2 space-y-1">
                  {comparison.roleFormulae.map(rule => {
                    const label = typeof rule.label === 'string' ? rule.label : 'Unnamed role'
                    const formula = typeof rule.formula === 'string' ? rule.formula : 'Formula unavailable'
                    const evidenceType = typeof rule.minimum_evidence_type === 'string' ? rule.minimum_evidence_type : 'evidence'
                    const evidenceCount = typeof rule.minimum_evidence_count === 'number' ? rule.minimum_evidence_count : '—'
                    const minimumEvents = typeof rule.minimum_events === 'number' ? rule.minimum_events : '—'
                    const positions = Array.isArray(rule.eligible_positions) ? rule.eligible_positions.join(', ') : '—'
                    return <li key={label}><span className="font-bold text-ink">{label}:</span> {formula} · {evidenceType} ≥ {evidenceCount} · actions ≥ {minimumEvents} · positions {positions}.</li>
                  })}
                </ul>
                <p className="mt-2 text-ink-muted">All roles require at least 15 verified minutes, two matches, both cohorts, and matched-team context. Shot-specific rules use a separate low-count threshold; labels describe observed response patterns, not player quality or causality.</p>
              </details> : null}
            </>
          )}
        </section>
      ) : null}

      {analysisMode === 'defending' ? (
        <div className="mb-3 grid gap-3 lg:grid-cols-12">
          <EventMapCard className="lg:col-span-8" expanded={expanded === 'actions'} onExpandedChange={next => setExpanded(next ? 'actions' : null)} title="Defensive territory" description="Located defensive actions, normalized within each verified player state cohort." exportContext={mapExportContext()} footer={(
            <div className="space-y-2 text-[10px] leading-relaxed text-ink-dim">
              <p>Action territory is event-backed; it is not a settled high-, mid- or low-block claim.</p>
              {comparison?.selected ? <p>{comparison.selected.defensiveHeight.sampleSize.toLocaleString()} located defensive actions · median height {comparison.selected.defensiveHeight.median == null ? '—' : `${comparison.selected.defensiveHeight.median.toFixed(1)}%`}.</p> : null}
            </div>
          )}>
            <MapStage map="actions" expanded={expanded} setExpanded={setExpanded}>
              {defensiveShift ? <StateDeltaMap contract={defensiveShift} /> : comparison?.selected.defensiveGrid.some(cell => cell.rawCount > 0) ? (
                <PortraitPitch densityCells={comparison.selected.defensiveGrid} densityStyle="smooth" ariaLabel={`${profile.playerName} located defensive action territory. Event-backed location only.`} />
              ) : <EventMapNotice kind="empty" title="No located defensive actions in this scope" />}
            </MapStage>
          </EventMapCard>
          <div className="lg:col-span-4 border border-line-bright bg-panel p-3">
            <h3 className="text-[11px] font-black uppercase tracking-[0.14em] text-ink">Defensive evidence</h3>
            {comparison?.selected ? <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-[10px] text-ink-dim">
              <div><dt>Actions / 90</dt><dd className="font-mono text-ink">{formatRate(comparison.selected, 'defensive_actions')}</dd></div>
              <div><dt>Recoveries / 90</dt><dd className="font-mono text-ink">{formatRate(comparison.selected, 'recoveries')}</dd></div>
              <div><dt>Tackles / 90</dt><dd className="font-mono text-ink">{formatRate(comparison.selected, 'tackles')}</dd></div>
              <div><dt>Interceptions / 90</dt><dd className="font-mono text-ink">{formatRate(comparison.selected, 'interceptions')}</dd></div>
              <div className="col-span-2 border-t border-line-bright pt-2"><dt>Median action height</dt><dd className="font-mono text-ink">{comparison.selected.defensiveHeight.median == null ? '—' : `${comparison.selected.defensiveHeight.median.toFixed(1)}%`} <span className="text-[8px] text-ink-muted">event location</span></dd></div>
            </dl> : <p className="mt-2 text-[10px] text-ink-dim">Loading verified defensive evidence…</p>}
          </div>
        </div>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-12">
        {analysisMode === 'passing' && profile.modules.passMap.available ? (
          <EventMapCard className={isGoalkeeper ? 'lg:col-span-12' : 'lg:col-span-6'} expanded={expanded === 'passes'} onExpandedChange={next => setExpanded(next ? 'passes' : null)} title="Pass & carry map" description={passMapDescription} exportContext={mapExportContext([
            { label: 'Layers', value: PASS_MAP_LAYERS.find(layer => layer.value === passMapLayer)?.label ?? passMapLayer },
            { label: 'Category', value: PASS_FILTERS.find(filter => filter.value === passFilter)?.label ?? passFilter },
            ...(passMapLayer === 'carries' ? [] : [{ label: 'Pass outcome', value: PASS_OUTCOMES.find(outcome => outcome.value === passOutcome)?.label ?? passOutcome }]),
          ])} controls={(
            <EventMapViewTabs
              value={passMapLayer}
              options={PASS_MAP_LAYERS}
              label="Pass map layers"
              onChange={value => {
                setSelection(null)
                setPassMapLayer(value)
                if (value === 'carries' && !SHARED_SPATIAL_FILTERS.has(passFilter)) setPassFilter('all')
              }}
            />
          )} footer={(
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[8px] font-bold uppercase tracking-[0.1em] text-ink-dim" aria-label="Pass map legend">
                {passMapLayer !== 'carries' ? <span className="inline-flex items-center gap-1.5"><span className="h-px w-4 bg-electric" aria-hidden /> Pass</span> : null}
                {passMapLayer !== 'passes' ? <span className="inline-flex items-center gap-1.5 text-gold"><span className="inline-block h-px w-4 border-t border-dashed border-gold" aria-hidden /> Derived carry</span> : null}
              </div>
              {passQuery.data?.truncated && passMapLayer !== 'carries' ? (
                <EventMapNotice kind="truncated" title="Pass response capped at 5,000 rows">{passQuery.data.totalMatching.toLocaleString()} passes match; choose a narrower category to inspect every row.</EventMapNotice>
              ) : passQuery.data?.carriesTruncated && passMapLayer !== 'passes' ? (
                <EventMapNotice kind="truncated" title="Carry response capped at 5,000 rows">{passQuery.data.totalCarries.toLocaleString()} carries match this scope; choose an individual match to inspect every row.</EventMapNotice>
              ) : selection?.kind === 'pass' || selection?.kind === 'carry' ? (
                <EventSelectionDetails selection={selection} matches={passQuery.data?.matches ?? {}} />
              ) : <p className="text-[9px] text-ink-dim">Click, tap or focus a visible event to inspect it.</p>}
            </div>
          )}>
            <MapStage map="passes" expanded={expanded} setExpanded={setExpanded}>
              <div className="w-full">
                <div className="mb-2 flex flex-wrap justify-end gap-1.5" aria-label="Pass and carry filters">
                  {passMapLayer !== 'carries' ? (
                    <span className="relative inline-flex">
                      <select aria-label="Pass outcome" value={passOutcome} onChange={event => { setSelection(null); setPassOutcome(event.target.value as PlayerPassOutcome) }} className="h-9 max-w-40 appearance-none border border-control-border bg-raised py-0 pl-2.5 pr-9 text-[9px] font-bold uppercase tracking-[0.08em] text-control-fg outline-none focus:border-electric">
                        {PASS_OUTCOMES.map(outcome => <option key={outcome.value} value={outcome.value}>{outcome.label}</option>)}
                      </select>
                      <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-control-fg" aria-hidden="true" />
                    </span>
                  ) : null}
                  <span className="relative inline-flex">
                    <select aria-label="Pass and carry category" value={passFilter} onChange={event => { setSelection(null); setPassFilter(event.target.value as PlayerPassFilter) }} className="h-9 max-w-40 appearance-none border border-control-border bg-raised py-0 pl-2.5 pr-9 text-[9px] font-bold uppercase tracking-[0.08em] text-control-fg outline-none focus:border-electric">
                      {categoryFilters.map(filter => <option key={filter.value} value={filter.value}>{filter.label}</option>)}
                    </select>
                    <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-control-fg" aria-hidden="true" />
                  </span>
                </div>
                {passQuery.isLoading ? <EventMapNotice kind="loading" title="Loading pass rows" /> : passQuery.isError || !passQuery.data ? (
                  <EventMapNotice kind="error" title="Pass map failed to load" onRetry={() => passQuery.refetch()} />
                ) : visiblePasses.length || visibleCarries.length ? (
                  <PortraitPitch passes={visiblePasses} carries={visibleCarries} eventSelectionMode="click" selectedEventId={selection?.kind === 'pass' || selection?.kind === 'carry' ? selection.id : null} onSelectedEventChange={setSelection} ariaLabel={`${profile.playerName} ${passMapLayer === 'all' ? 'pass and carry' : passMapLayer} map. Attacking left to right.`} />
                ) : <EventMapNotice kind="empty" title={`No ${passMapLayer === 'all' ? 'passes or carries' : passMapLayer} match this scope`} />}
              </div>
            </MapStage>
          </EventMapCard>
        ) : null}

        {analysisMode === 'shooting' && profile.modules.shotMap.available ? (
          <EventMapCard className="lg:col-span-6" expanded={expanded === 'shots'} onExpandedChange={next => setExpanded(next ? 'shots' : null)} title="Shot map" description={shotMapDescription} exportContext={mapExportContext([
            { label: 'Outcome', value: SHOT_OUTCOME_FILTERS.find(outcome => outcome.value === shotOutcome)?.label ?? shotOutcome },
            { label: 'Chance', value: SHOT_CHANCE_FILTERS.find(chance => chance.value === shotChance)?.label ?? shotChance },
          ])} controls={(
            <ShotMapFilters
              outcome={shotOutcome}
              chance={shotChance}
              onOutcomeChange={value => { setSelection(null); setShotOutcome(value) }}
              onChanceChange={value => { setSelection(null); setShotChance(value) }}
            />
          )} footer={(
            <div className="space-y-2">
              <ShotMapLegend />
              {selection?.kind === 'shot' ? <EventSelectionDetails selection={selection} matches={profile.matches} /> : <p className="text-[9px] text-ink-dim">Click, tap or focus a shot to inspect it.</p>}
            </div>
          )}>
            <MapStage map="shots" expanded={expanded} setExpanded={setExpanded}>
              {filteredShots.length ? <PortraitPitch shots={filteredShots} eventSelectionMode="click" selectedEventId={selection?.kind === 'shot' ? selection.id : null} onSelectedEventChange={setSelection} ariaLabel={`${profile.playerName} shot map, ${SHOT_OUTCOME_FILTERS.find(option => option.value === shotOutcome)?.label.toLowerCase()}, ${SHOT_CHANCE_FILTERS.find(option => option.value === shotChance)?.label.toLowerCase()}. Attacking left to right.`} /> : <EventMapNotice kind="empty" title={profile.shots.length ? 'No shots match these filters' : 'No shots recorded'} />}
            </MapStage>
          </EventMapCard>
        ) : null}

        {analysisMode === 'shooting' && !isGoalkeeper && profile.modules.shotMap.available ? (
          <EventMapCard className="lg:col-span-6" expanded={expanded === 'zones'} onExpandedChange={next => setExpanded(next ? 'zones' : null)} title="Shooting zones" description={`Where ${profile.playerName}'s on-target shots end up in the goal, split into a 3×2 grid. Blocked and off-target shots are excluded.`} exportContext={mapExportContext([
            { label: 'Shot scope', value: PENALTY_OPTIONS.find(option => option.value === shotPenalties)?.label ?? shotPenalties },
          ])} controls={(
            <PenaltyToggle value={shotPenalties} onChange={setShotPenalties} />
          )} footer={
            shotZonesQuery.data ? (
              <GoalZoneTotals variant={shotZonesQuery.data.variants[zoneVariantKey]} mode="shooter" />
            ) : null
          }>
            <MapStage map="zones" expanded={expanded} setExpanded={setExpanded}>
              <div className="w-full">
                {expanded === 'zones' && shotZonesQuery.data ? (
                  <div className="mx-auto mb-3 max-w-[860px]">
                    <GoalZoneTotals variant={shotZonesQuery.data.variants[zoneVariantKey]} mode="shooter" />
                  </div>
                ) : null}
                {shotZonesQuery.isLoading ? <EventMapNotice kind="loading" title="Loading shooting zones" /> : shotZonesQuery.isError || !shotZonesQuery.data ? (
                  <EventMapNotice kind="error" title="Shooting zones failed to load" onRetry={() => shotZonesQuery.refetch()} />
                ) : shotZonesQuery.data.shotCount === 0 ? (
                  <EventMapNotice kind="empty" title="No shots recorded in this scope" />
                ) : (
                  <GoalZoneGridView grid={shotZonesQuery.data.grid} variant={shotZonesQuery.data.variants[zoneVariantKey]} mode="shooter" />
                )}
              </div>
            </MapStage>
          </EventMapCard>
        ) : null}

        {analysisMode === 'shooting' && isGoalkeeper ? (
          <EventMapCard className="lg:col-span-6" expanded={expanded === 'gk-zones'} onExpandedChange={next => setExpanded(next ? 'gk-zones' : null)} title="Shot-facing zones" description="Where opponents' on-target shots were aimed at this goalkeeper's goal, with save rates per zone." exportContext={mapExportContext([
            { label: 'Shot scope', value: PENALTY_OPTIONS.find(option => option.value === shotPenalties)?.label ?? shotPenalties },
          ])} controls={(
            <PenaltyToggle value={shotPenalties} onChange={setShotPenalties} />
          )} footer={(
            <div className="space-y-2">
              {gkZonesQuery.data ? <GoalZoneTotals variant={gkZonesQuery.data.variants[zoneVariantKey]} mode="keeper" /> : null}
              {gkZonesQuery.data && gkZonesQuery.data.matchesExcluded > 0 ? (
                <EventMapNotice kind="sparse" title="Some matches excluded">
                  {gkZonesQuery.data.matchesIncluded} of {gkZonesQuery.data.matchesIncluded + gkZonesQuery.data.matchesExcluded} matches included — only matches with one verifiable goalkeeper are counted.
                </EventMapNotice>
              ) : null}
            </div>
          )}>
            <MapStage map="gk-zones" expanded={expanded} setExpanded={setExpanded}>
              <div className="w-full">
                {expanded === 'gk-zones' && gkZonesQuery.data ? (
                  <div className="mx-auto mb-3 max-w-[860px]">
                    <GoalZoneTotals variant={gkZonesQuery.data.variants[zoneVariantKey]} mode="keeper" />
                  </div>
                ) : null}
                {gkZonesQuery.isLoading ? <EventMapNotice kind="loading" title="Loading shot-facing zones" /> : gkZonesQuery.isError || !gkZonesQuery.data ? (
                  <EventMapNotice kind="error" title="Shot-facing zones failed to load" onRetry={() => gkZonesQuery.refetch()} />
                ) : !gkZonesQuery.data.selectedMatchIncluded ? (
                  <EventMapNotice kind="empty" title="Keeper attribution unverified for this match">
                    The selected match could not be attributed to a single goalkeeper, so it is excluded.
                  </EventMapNotice>
                ) : gkZonesQuery.data.shotsFaced === 0 ? (
                  <EventMapNotice kind="empty" title="No on-target shots faced in this scope" />
                ) : (
                  <GoalZoneGridView grid={gkZonesQuery.data.grid} variant={gkZonesQuery.data.variants[zoneVariantKey]} mode="keeper" />
                )}
              </div>
            </MapStage>
          </EventMapCard>
        ) : null}

        {analysisMode === 'overview' && (locatedTouchCount > 0 || matchRef !== null) ? (
          <EventMapCard className="lg:col-span-6" expanded={expanded === 'actions'} onExpandedChange={next => setExpanded(next ? 'actions' : null)} title="Touch heatmap" description="Smoothed density of located touches only, with the average touch position overlaid." exportContext={mapExportContext()} footer={(
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-3 text-[8px] font-bold uppercase tracking-[0.1em] text-ink-dim">
              <span className="inline-flex items-center gap-1.5"><span className="size-3 rounded-full bg-mint/55 blur-[2px]" aria-hidden /> Higher touch density</span>
              {profile.averageTouchLocation ? <span className="inline-flex items-center gap-1.5 text-electric"><span aria-hidden>◆</span> Average touch · {profile.averageTouchLocation.sampleSize.toLocaleString()} touches</span> : null}
              </div>
              {locatedTouchCount < 100 ? <EventMapNotice kind="sparse" title="Small located-touch sample">The heatmap is directional context, not a settled season tendency.</EventMapNotice> : null}
            </div>
          )}>
            <MapStage map="actions" expanded={expanded} setExpanded={setExpanded}>
              {locatedTouchCount ? <PortraitPitch densityCells={profile.touchGrid} densityStyle="smooth" markers={profile.averageTouchLocation ? [{ id: 'average-touch', coordinate: profile.averageTouchLocation, kind: 'jersey', ariaLabel: `Average touch location from ${profile.averageTouchLocation.sampleSize} located touches`, label: 'Avg touch', tone: 'accent' }] : []} ariaLabel={`${profile.playerName} touch-only heatmap with average touch overlay. Attacking left to right.`} /> : <EventMapNotice kind="empty" title="No located touches recorded" />}
            </MapStage>
          </EventMapCard>
        ) : null}
      </div>

      {analysisMode === 'passing' ? (
        comparisonQuery.isLoading ? <EventMapNotice kind="loading" title="Loading passing and carrying evidence" /> : comparisonQuery.isError || !comparison ? (
          <EventMapNotice kind="error" title="Passing and carrying evidence failed to load" onRetry={() => comparisonQuery.refetch()} />
        ) : <PlayerPassingEvidence comparison={comparison} />
      ) : null}
      {analysisMode === 'shooting' ? (
        comparisonQuery.isLoading ? <EventMapNotice kind="loading" title="Loading shooting evidence" /> : comparisonQuery.isError || !comparison ? (
          <EventMapNotice kind="error" title="Shooting evidence failed to load" onRetry={() => comparisonQuery.refetch()} />
        ) : <PlayerShootingEvidence comparison={comparison} />
      ) : null}
    </section>
  )
}
