import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchGkShotZones, fetchPlayerEventProfile, fetchPlayerPassMap, fetchPlayerShotZones, fetchPlayerStateComparison } from '../../lib/eventMaps/api'
import { eventMatchExportLabel, type EventMapExportContext } from '../../lib/eventMaps/exportContext'
import { stateLensRequest } from '../../lib/eventMaps/stateLensUrl'
import type { SelectablePitchEvent } from '../../lib/eventMaps/selection'
import type { DefensiveActionFamily, PlayerPassFilter, PlayerPassOutcome, ShotZoneVariantKey } from '../../types/eventMaps'
import type { ProfileRateMode } from '../../lib/profileMetrics'
import { PortraitPitch } from './PortraitPitch'
import { PairedStatePitch } from './PairedStatePitch'
import { ProfileSelectControl } from '../profile/ProfileScopeSelector'
import { statePresentation } from '../../lib/eventMaps/statePresentation'
import { GoalZoneGridView, GoalZoneTotals } from './GoalZones'
import { StateDeltaMap } from './StateDeltaMap'
import { StateLensControls } from './StateLensControls'
import { DefensiveActionSelector } from './DefensiveActionSelector'
import { ALL_DEFENSIVE_ACTION_FAMILIES } from './defensiveActionFamilies'
import {
  EventCoverageLine, EventMapCard, EventMapNotice, EventMatchFilter,
  EventMapViewTabs, EventSelectionDetails, ShotMapLegend,
} from './EventMapUi'
import {
  EvidenceRow,
  MapStage,
  PenaltyToggle,
  PlayerExposureCard,
  PlayerPassingEvidence,
  PlayerShootingEvidence,
  ShotMapFilters,
  StateEvidenceCard,
} from './PlayerEventMapSupport'
import {
  CARRY_FILTERS,
  PASS_FILTERS,
  PASS_MAP_LAYERS,
  PASS_OUTCOMES,
  PENALTY_OPTIONS,
  SHARED_SPATIAL_FILTERS,
  SHOT_CHANCE_FILTERS,
  SHOT_OUTCOME_FILTERS,
  formatCohortMetric,
  formatComparisonMetric,
  playerDefensiveSelection,
  scopeLabel,
  stateExportFilters,
  stateShiftContract,
  type PassMapLayer,
  type PenaltyOption,
  type PlayerAnalysisMode,
  type PlayerEventMapTeam,
  type PlayerMap,
  type ShotChanceFilter,
  type ShotOutcomeFilter,
} from './PlayerEventMapLogic'

export function PlayerEventMaps({ playerId, competition, season, teams, positionGroup, rateMode }: {
  playerId: number
  competition: string
  season: string
  teams: PlayerEventMapTeam[]
  positionGroup?: string
  rateMode: ProfileRateMode
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
  const [defensiveFamilies, setDefensiveFamilies] = useState<DefensiveActionFamily[]>(ALL_DEFENSIVE_ACTION_FAMILIES)
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
    placeholderData: previous => previous,
  })
  const comparisonQuery = useQuery({
    queryKey: ['player-state-comparison', playerId, competition, season, teamId, matchRef, lensRequest],
    queryFn: () => fetchPlayerStateComparison(playerId, competition, season, teamId, matchRef, lensRequest),
    enabled: profileQuery.data != null,
    staleTime: 10 * 60 * 1000,
    placeholderData: previous => previous,
  })
  const profile = profileQuery.data
  const passQuery = useQuery({
    queryKey: ['player-event-passes', playerId, competition, season, teamId, matchRef, passFilter, passOutcome, lensRequest],
    queryFn: () => fetchPlayerPassMap(playerId, competition, season, passFilter, passOutcome, teamId, matchRef, lensRequest),
    enabled: profile?.modules.passMap.available === true,
    staleTime: 10 * 60 * 1000,
  })
  const baselineLensRequest = Object.fromEntries(
    Object.entries(lensRequest)
      .filter(([key]) => key.startsWith('baseline_'))
      .map(([key, value]) => [key.replace(/^baseline_/, ''), value]),
  )
  const baselinePassQuery = useQuery({
    queryKey: ['player-event-passes-baseline', playerId, competition, season, teamId, matchRef, passFilter, passOutcome, baselineLensRequest],
    queryFn: () => fetchPlayerPassMap(playerId, competition, season, passFilter, passOutcome, teamId, matchRef, baselineLensRequest),
    enabled: profile?.modules.passMap.available === true && Boolean(lensRequest.baseline_state),
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
  const hasPassComparison = Boolean(baselinePassQuery.data)
  const selectedRouteColor = statePresentation(comparisonQuery.data?.stateLens.selected.state).color
  const baselineRouteColor = statePresentation(comparisonQuery.data?.stateLens.comparison.baseline?.state).color
  const selectedPassColor = hasPassComparison ? selectedRouteColor : '#4A9EF5'
  const selectedCarryColor = hasPassComparison ? selectedRouteColor : '#F0A832'
  const visiblePasses = passMapLayer === 'carries' ? [] : [
    ...(passQuery.data?.passes ?? []).map(pass => ({ ...pass, id: `selected-${pass.id}`, color: selectedPassColor })),
    ...(baselinePassQuery.data?.passes ?? []).map(pass => ({ ...pass, id: `baseline-${pass.id}`, color: baselineRouteColor })),
  ]
  const visibleCarries = passMapLayer === 'passes' ? [] : [
    ...(passQuery.data?.carries ?? []).map(carry => ({ ...carry, id: `selected-${carry.id}`, color: selectedCarryColor })),
    ...(baselinePassQuery.data?.carries ?? []).map(carry => ({ ...carry, id: `baseline-${carry.id}`, color: baselineRouteColor })),
  ]
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
  const stateTransitionLoading = profileQuery.isFetching || comparisonQuery.isFetching || (analysisMode === 'passing' && baselinePassQuery.isFetching)
  const selectedDefensiveCohort = comparison ? playerDefensiveSelection(comparison.selected, defensiveFamilies) : null
  const baselineDefensiveCohort = comparison?.baseline ? playerDefensiveSelection(comparison.baseline, defensiveFamilies) : null
  const selectedStateLabel = scopeLabel(stateLens?.selected.state)
  const baselineStateLabel = scopeLabel(stateLens?.comparison.baseline?.state)
  const touchShift = comparison
      ? stateShiftContract(
        playerId,
        profile.playerName,
        selectedDefensiveCohort ?? comparison.selected,
        baselineDefensiveCohort,
        selectedStateLabel,
        baselineStateLabel,
        defensiveFamilies.length === ALL_DEFENSIVE_ACTION_FAMILIES.length ? comparison.teamContext.selected : null,
        defensiveFamilies.length === ALL_DEFENSIVE_ACTION_FAMILIES.length ? comparison.teamContext.baseline : null,
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
      {teams.length > 1 ? <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
          <ProfileSelectControl compact label="Team split" ariaLabel="Player team split" value={teamId == null ? '' : String(teamId)} onChange={value => {
              const next = new URLSearchParams(searchParams)
              if (value) next.set('team', value)
              else next.delete('team')
              next.delete('match')
              setLensParams(next)
            }} className="min-w-56" options={[{ value: '', label: 'Season total' }, ...teams.map(team => ({ value: String(team.id), label: team.name }))]} />
      </div> : null}

      {stateLens ? <div className="mb-2">
        <StateLensControls metadata={stateLens} searchParams={searchParams} onChange={setLensParams} controls={<EventMatchFilter matches={profile.matches} value={matchRef} onChange={value => {
          const next = new URLSearchParams(searchParams)
          if (value == null) next.delete('match')
          else next.set('match', value)
          setLensParams(next)
        }} />} />
      </div> : null}
      {expanded && stateLens ? <div className="fixed left-3 right-16 top-3 z-[95] max-h-[45svh] overflow-y-auto sm:left-8 sm:right-20">
        <StateLensControls compact metadata={stateLens} searchParams={searchParams} onChange={setLensParams} />
      </div> : null}

      <nav className="mb-2 grid grid-cols-4 border-b border-line-bright" aria-label="Player event analysis">
        {([
          ['overview', 'Touches'],
          ['passing', 'Passing & Carrying'],
          ['shooting', 'Shooting'],
          ['defending', 'Defending'],
        ] as const).map(([value, label]) => (
          <button key={value} type="button" aria-pressed={analysisMode === value} onClick={() => { setAnalysisMode(value); setSelection(null) }} className={`border-b-2 px-2 py-2 text-left transition-colors hover:bg-raised sm:px-3 ${analysisMode === value ? 'border-electric text-electric' : 'border-transparent text-ink'}`}>
            <strong className="block text-[9px] uppercase tracking-[0.08em] sm:text-[10px] sm:tracking-[0.1em]">{label}</strong>
          </button>
        ))}
      </nav>

      <div className="mb-2 flex flex-wrap items-center gap-x-5 gap-y-1.5 py-1">
        {([
          ['Touches', rateMode === 'per90' && comparison ? formatCohortMetric(comparison.selected, 'touches', rateMode) : locatedTouchCount.toLocaleString()],
          ['Passes', rateMode === 'per90' && comparison ? formatCohortMetric(comparison.selected, 'pass_attempts', rateMode) : profile.summary.pass_attempts?.toLocaleString() ?? '—'],
          ['Carries', rateMode === 'per90' && comparison ? formatCohortMetric(comparison.selected, 'carries', rateMode) : passQuery.data?.totalAllCarries.toLocaleString() ?? '—'],
          ['Shots', rateMode === 'per90' && comparison ? formatCohortMetric(comparison.selected, 'shots', rateMode) : profile.summary.shots?.toLocaleString() ?? '—'],
        ] as const).map(([label, value]) => <p key={label} className="text-[9px] text-ink-dim"><span className="mr-1 uppercase tracking-[0.08em]">{label}</span><strong className="font-mono text-[12px] font-normal text-ink">{value}</strong></p>)}
        <span className="ml-auto"><EventCoverageLine coverage={profile.coverage} minutes={profile.coverage.minutes} /></span>
      </div>

      {stateTransitionLoading ? <EventMapNotice kind="loading" title={`Loading ${analysisMode === 'overview' ? 'touch' : analysisMode} state evidence`}>
        The previous state's maps and metrics are hidden while this context loads.
      </EventMapNotice> : null}

      {!stateTransitionLoading && analysisMode === 'overview' && (locatedTouchCount > 0 || matchRef !== null) ? (
        <div className="mb-3 grid gap-3 lg:grid-cols-12">
          <EventMapCard className="lg:col-span-8" expanded={expanded === 'actions'} onExpandedChange={next => setExpanded(next ? 'actions' : null)} title="Touch map" description="Smoothed density of located touches, with the average position overlaid." exportContext={mapExportContext()} footer={(
            <div className="flex flex-wrap items-center gap-3 text-[8px] font-bold uppercase tracking-[0.1em] text-ink-dim">
              <span className="inline-flex items-center gap-1.5"><span className="size-3 rounded-full bg-mint/55 blur-[2px]" aria-hidden /> Higher density</span>
              {profile.averageTouchLocation ? <span className="inline-flex items-center gap-1.5 text-electric"><span aria-hidden>◆</span> Average touch · {profile.averageTouchLocation.sampleSize.toLocaleString()}</span> : null}
            </div>
          )}>
            <MapStage map="actions" expanded={expanded} setExpanded={setExpanded}>
              {comparison?.baseline ? <PairedStatePitch
                selected={{ state: comparison.stateLens.selected.state, label: selectedStateLabel, cells: comparison.selected.touchGrid, average: comparison.selected.touchLocation.x == null || comparison.selected.touchLocation.y == null ? null : { x: comparison.selected.touchLocation.x, y: comparison.selected.touchLocation.y, sampleSize: comparison.selected.touchLocation.sampleSize }, exposureMinutes: comparison.selected.exposureMinutes, matchCount: comparison.selected.evidence.matchCount }}
                comparison={{ state: comparison.stateLens.comparison.baseline?.state ?? 'all', label: baselineStateLabel, cells: comparison.baseline.touchGrid, average: comparison.baseline.touchLocation.x == null || comparison.baseline.touchLocation.y == null ? null : { x: comparison.baseline.touchLocation.x, y: comparison.baseline.touchLocation.y, sampleSize: comparison.baseline.touchLocation.sampleSize }, exposureMinutes: comparison.baseline.exposureMinutes, matchCount: comparison.baseline.evidence.matchCount }}
                ariaLabel={`${profile.playerName} paired touch territory comparison`}
              /> : locatedTouchCount ? <PortraitPitch densityCells={profile.touchGrid} densityStyle="smooth" markers={profile.averageTouchLocation ? [{ id: 'average-touch', coordinate: profile.averageTouchLocation, kind: 'jersey', ariaLabel: `Average touch location from ${profile.averageTouchLocation.sampleSize} located touches`, label: 'Avg touch', tone: 'accent' }] : []} ariaLabel={`${profile.playerName} touch-only heatmap with average touch overlay. Attacking left to right.`} /> : <EventMapNotice kind="empty" title="No located touches recorded" />}
            </MapStage>
          </EventMapCard>
          <aside className="flex flex-col justify-between border border-line-bright bg-panel p-3 lg:col-span-4">
            <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-ink-dim">Touch evidence</p>
            {comparison ? <div className="mt-3 space-y-3">
              <StateEvidenceCard label={selectedStateLabel} state={comparison.stateLens.selected.state}>
                <EvidenceRow label="Located touches" value={comparison.selected.touchLocation.sampleSize.toLocaleString()} />
                <EvidenceRow label="Average position" value={comparison.selected.touchLocation.x == null || comparison.selected.touchLocation.y == null ? '—' : `${comparison.selected.touchLocation.x.toFixed(1)} × ${comparison.selected.touchLocation.y.toFixed(1)}`} />
                <EvidenceRow label="Exposure" value={`${comparison.selected.exposureMinutes.toFixed(0)} min`} />
              </StateEvidenceCard>
              {comparison.baseline ? <StateEvidenceCard label={baselineStateLabel} state={comparison.stateLens.comparison.baseline?.state ?? 'all'}>
                <EvidenceRow label="Located touches" value={comparison.baseline.touchLocation.sampleSize.toLocaleString()} />
                <EvidenceRow label="Average position" value={comparison.baseline.touchLocation.x == null || comparison.baseline.touchLocation.y == null ? '—' : `${comparison.baseline.touchLocation.x.toFixed(1)} × ${comparison.baseline.touchLocation.y.toFixed(1)}`} />
                <EvidenceRow label="Exposure" value={`${comparison.baseline.exposureMinutes.toFixed(0)} min`} />
              </StateEvidenceCard> : null}
            </div> : <div className="mt-3">
              <p className="font-mono text-2xl text-ink">{locatedTouchCount.toLocaleString()}</p>
              <p className="text-[10px] text-ink-dim">located touches</p>
              {profile.averageTouchLocation ? <p className="mt-4 text-[10px] leading-relaxed text-ink-dim">Average position <span className="font-mono text-ink">{profile.averageTouchLocation.x.toFixed(1)} × {profile.averageTouchLocation.y.toFixed(1)}</span></p> : null}
            </div>}
            {locatedTouchCount < 100 ? <p className="mt-3 border-l-2 border-gold pl-2 text-[9px] leading-relaxed text-gold">Small sample; read as directional context.</p> : null}
          </aside>
        </div>
      ) : null}

      {!stateTransitionLoading && analysisMode === 'overview' ? (
        <section aria-label="Player context analysis" className="mb-3 space-y-3">
          {comparisonQuery.isLoading ? <EventMapNotice kind="loading" title="Loading verified player comparison" /> : comparisonQuery.isError || !comparison ? (
            <EventMapNotice kind="error" title="Player state comparison failed to load" onRetry={() => comparisonQuery.refetch()}>
              {comparisonQuery.error?.message ?? 'The verified player comparison service returned no data.'}
            </EventMapNotice>
          ) : (
            <>
              <details className="group border border-line-bright bg-panel">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2.5 text-[10px] font-bold uppercase tracking-[0.12em] text-control-fg hover:text-ink">
                  <span>Context comparison</span>
                  <span className="font-normal normal-case tracking-normal text-ink-dim">{selectedStateLabel}{comparison.baseline ? ` vs ${baselineStateLabel}` : ''} · view evidence</span>
                </summary>
                <div className="space-y-3 border-t border-line-bright p-3">
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
                      Select a comparison state in Context to see changes in rates, shares, movement and response-role evidence.
                    </div>
                  )}
                </div>
                <div className="mt-3 grid gap-x-4 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
                  {(['touches', 'pass_attempts', 'progressive_actions', 'shots', 'defensive_actions', 'carries', 'box_entries', 'take_ons'] as const).map(key => (
                    <div key={key} className="flex items-baseline justify-between gap-2 border-t border-line-bright pt-2 text-[10px]">
                      <span className="text-ink-dim">{key.replaceAll('_', ' ')}</span>
                      <span className="font-mono text-ink">{formatCohortMetric(comparison.selected, key, rateMode)}{comparison.baseline ? <span className={formatComparisonMetric(comparison, key, rateMode).startsWith('+') ? 'text-mint' : formatComparisonMetric(comparison, key, rateMode).startsWith('-') ? 'text-ember' : 'text-ink-muted'}> ({formatComparisonMetric(comparison, key, rateMode)})</span> : null}</span>
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

              {touchShift ? <details className="border border-line-bright bg-panel px-3 py-2 text-[9px] text-ink-dim"><summary className="cursor-pointer text-control-fg">Change evidence</summary><div className="mt-2"><StateDeltaMap contract={touchShift} compact /></div></details> : null}
                </div>
              </details>
            </>
          )}
        </section>
      ) : null}

      {!stateTransitionLoading && analysisMode === 'defending' ? (
        <div className="mb-3 grid gap-3 lg:grid-cols-12">
          <EventMapCard className="lg:col-span-8" expanded={expanded === 'actions'} onExpandedChange={next => setExpanded(next ? 'actions' : null)} title="Defensive territory" description="Located defensive actions, normalized within each verified player state cohort." controls={<DefensiveActionSelector selected={defensiveFamilies} onChange={setDefensiveFamilies} />} exportContext={mapExportContext([{ label: 'Defensive actions', value: defensiveFamilies.length === ALL_DEFENSIVE_ACTION_FAMILIES.length ? 'All action types' : `${defensiveFamilies.length} selected types` }])} footer={(
            <div className="space-y-2 text-[10px] leading-relaxed text-ink-dim">
              <p>Action territory is event-backed; it is not a settled high-, mid- or low-block claim.</p>
              {selectedDefensiveCohort ? <p>{selectedDefensiveCohort.defensiveHeight.sampleSize.toLocaleString()} located defensive actions · {selectedDefensiveCohort.defensiveHeight.median == null ? 'combined median unavailable' : `median height ${selectedDefensiveCohort.defensiveHeight.median.toFixed(1)}%`}.</p> : null}
            </div>
          )}>
            <div className="w-full">
              <MapStage map="actions" expanded={expanded} setExpanded={setExpanded}>
                {selectedDefensiveCohort && baselineDefensiveCohort ? <PairedStatePitch
                  selected={{ state: comparison?.stateLens.selected.state ?? 'all', label: selectedStateLabel, cells: selectedDefensiveCohort.defensiveGrid, average: selectedDefensiveCohort.defensiveLocation.x == null || selectedDefensiveCohort.defensiveLocation.y == null ? null : { x: selectedDefensiveCohort.defensiveLocation.x, y: selectedDefensiveCohort.defensiveLocation.y, sampleSize: selectedDefensiveCohort.defensiveLocation.sampleSize }, exposureMinutes: selectedDefensiveCohort.exposureMinutes, matchCount: selectedDefensiveCohort.evidence.matchCount }}
                  comparison={{ state: comparison?.stateLens.comparison.baseline?.state ?? 'all', label: baselineStateLabel, cells: baselineDefensiveCohort.defensiveGrid, average: baselineDefensiveCohort.defensiveLocation.x == null || baselineDefensiveCohort.defensiveLocation.y == null ? null : { x: baselineDefensiveCohort.defensiveLocation.x, y: baselineDefensiveCohort.defensiveLocation.y, sampleSize: baselineDefensiveCohort.defensiveLocation.sampleSize }, exposureMinutes: baselineDefensiveCohort.exposureMinutes, matchCount: baselineDefensiveCohort.evidence.matchCount }}
                  unit="share of located defensive actions"
                  ariaLabel={`${profile.playerName} paired defensive territory comparison`}
                /> : selectedDefensiveCohort?.defensiveGrid.some(cell => cell.rawCount > 0) ? (
                  <PortraitPitch densityCells={selectedDefensiveCohort.defensiveGrid} densityStyle="smooth" ariaLabel={`${profile.playerName} located defensive action territory. Event-backed location only.`} />
                ) : <EventMapNotice kind="empty" title="No located defensive actions in this scope" />}
              </MapStage>
              {defensiveShift ? <details className="mt-3 border border-line-bright px-3 py-2 text-[9px] text-ink-dim"><summary className="cursor-pointer text-control-fg">Change evidence</summary><div className="mt-2"><StateDeltaMap contract={defensiveShift} compact /></div></details> : null}
            </div>
          </EventMapCard>
          <div className="lg:col-span-4 border border-line-bright bg-panel p-3">
            <h3 className="text-[11px] font-black uppercase tracking-[0.14em] text-ink">Defensive evidence</h3>
            {selectedDefensiveCohort ? <div className="mt-3 space-y-3">
              {[
                { label: selectedStateLabel, state: comparison?.stateLens.selected.state ?? 'all', cohort: selectedDefensiveCohort },
                ...(baselineDefensiveCohort ? [{ label: baselineStateLabel, state: comparison?.stateLens.comparison.baseline?.state ?? 'all', cohort: baselineDefensiveCohort }] : []),
              ].map(item => <StateEvidenceCard key={`${item.state}-${item.label}`} label={item.label} state={item.state}>
                <EvidenceRow label="Actions" value={rateMode === 'per90' ? item.cohort.exposureMinutes > 0 ? ((item.cohort.summary.defensive_actions * 90) / item.cohort.exposureMinutes).toFixed(2) : '—' : item.cohort.summary.defensive_actions.toLocaleString()} />
                <EvidenceRow label="Located" value={item.cohort.defensiveLocation.sampleSize.toLocaleString()} />
                <EvidenceRow label="Action height" value={item.cohort.defensiveHeight.median == null ? item.cohort.defensiveHeight.mean == null ? '—' : `${item.cohort.defensiveHeight.mean.toFixed(1)}% mean` : `${item.cohort.defensiveHeight.median.toFixed(1)}% median`} />
              </StateEvidenceCard>)}
            </div> : <p className="mt-2 text-[10px] text-ink-dim">Loading verified defensive evidence…</p>}
          </div>
        </div>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-12">
        {!stateTransitionLoading && analysisMode === 'passing' && profile.modules.passMap.available ? (
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
                {hasPassComparison ? <>
                  <span className="inline-flex items-center gap-1.5"><span className="h-px w-4" style={{ backgroundColor: selectedRouteColor }} aria-hidden /> {selectedStateLabel}</span>
                  <span className="inline-flex items-center gap-1.5"><span className="h-px w-4" style={{ backgroundColor: baselineRouteColor }} aria-hidden /> {baselineStateLabel}</span>
                </> : <>
                  {passMapLayer !== 'carries' ? <span className="inline-flex items-center gap-1.5"><span className="h-px w-4 bg-electric" aria-hidden /> Pass</span> : null}
                  {passMapLayer !== 'passes' ? <span className="inline-flex items-center gap-1.5"><span className="h-px w-4 bg-gold" aria-hidden /> Carry</span> : null}
                </>}
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
                    <ProfileSelectControl ariaLabel="Pass outcome" value={passOutcome} options={PASS_OUTCOMES} onChange={next => { setSelection(null); setPassOutcome(next as PlayerPassOutcome) }} className="w-40" />
                  ) : null}
                  <ProfileSelectControl ariaLabel="Pass and carry category" value={passFilter} options={categoryFilters} onChange={next => { setSelection(null); setPassFilter(next as PlayerPassFilter) }} className="w-40" />
                </div>
                {passQuery.isLoading ? <EventMapNotice kind="loading" title="Loading pass rows" /> : passQuery.isError || !passQuery.data ? (
                  <EventMapNotice kind="error" title="Pass map failed to load" onRetry={() => passQuery.refetch()} />
                ) : visiblePasses.length || visibleCarries.length ? (
                  <PortraitPitch passes={visiblePasses} carries={visibleCarries} eventSelectionMode="click" selectedEventId={selection?.kind === 'pass' || selection?.kind === 'carry' ? selection.id : null} onSelectedEventChange={setSelection} ariaLabel={`${profile.playerName} ${passMapLayer === 'all' ? 'pass and carry' : passMapLayer} map. Attacking left to right.`} />
                ) : <EventMapNotice kind="empty" title={`No ${passMapLayer === 'all' ? 'passes or carries' : passMapLayer} match this scope`} />}
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-line-bright pt-2 text-[8px] font-bold uppercase tracking-[0.1em] text-ink-dim" aria-label="Visible pass map key">
                  {hasPassComparison ? <>
                    <span className="inline-flex items-center gap-1.5"><span className="h-px w-4" style={{ backgroundColor: selectedRouteColor }} aria-hidden /> {selectedStateLabel}</span>
                    <span className="inline-flex items-center gap-1.5"><span className="h-px w-4" style={{ backgroundColor: baselineRouteColor }} aria-hidden /> {baselineStateLabel}</span>
                  </> : <>
                    {passMapLayer !== 'carries' ? <span className="inline-flex items-center gap-1.5"><span className="h-px w-4 bg-electric" aria-hidden /> Pass</span> : null}
                    {passMapLayer !== 'passes' ? <span className="inline-flex items-center gap-1.5"><span className="h-px w-4 bg-gold" aria-hidden /> Carry</span> : null}
                  </>}
                  {passMapLayer !== 'passes' ? <span className="inline-flex items-center gap-1.5 text-gold"><span className="inline-block h-px w-4 border-t border-dashed border-gold" aria-hidden /> Derived carry</span> : null}
                </div>
              </div>
            </MapStage>
          </EventMapCard>
        ) : null}

        {!stateTransitionLoading && analysisMode === 'passing' ? <div className="lg:col-span-6">
          {comparisonQuery.isLoading ? <EventMapNotice kind="loading" title="Loading passing and carrying evidence" /> : comparisonQuery.isError || !comparison ? <EventMapNotice kind="error" title="Passing and carrying evidence failed to load" onRetry={() => comparisonQuery.refetch()} /> : <PlayerPassingEvidence comparison={comparison} rateMode={rateMode} />}
        </div> : null}

        {!stateTransitionLoading && analysisMode === 'shooting' && profile.modules.shotMap.available ? (
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

        {!stateTransitionLoading && analysisMode === 'shooting' && !isGoalkeeper && profile.modules.shotMap.available ? (
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

        {!stateTransitionLoading && analysisMode === 'shooting' && isGoalkeeper ? (
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

      </div>

      {!stateTransitionLoading && analysisMode === 'shooting' ? (
        comparisonQuery.isLoading ? <EventMapNotice kind="loading" title="Loading shooting evidence" /> : comparisonQuery.isError || !comparison ? (
          <EventMapNotice kind="error" title="Shooting evidence failed to load" onRetry={() => comparisonQuery.refetch()} />
        ) : <PlayerShootingEvidence comparison={comparison} rateMode={rateMode} />
      ) : null}
    </section>
  )
}
