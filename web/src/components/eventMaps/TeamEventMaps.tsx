import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchTeamEventProfile } from '../../lib/eventMaps/api'
import { fetchTeamDefensiveTerritory, fetchTeamShotPressure } from '../../lib/eventMaps/stateAnalysisApi'
import { fetchTeamLeadControl } from '../../lib/eventMaps/leadControlApi'
import { fetchTeamResponseHalfLife } from '../../lib/eventMaps/responseHalfLifeApi'
import { fetchTeamStyleShape } from '../../lib/eventMaps/teamStyleShapeApi'
import { fetchTeamTransitionLeverage } from '../../lib/eventMaps/transitionLeverageApi'
import { eventMatchExportLabel, type EventMapExportContext } from '../../lib/eventMaps/exportContext'
import type { SelectablePitchEvent } from '../../lib/eventMaps/selection'
import type { ActionGridCell, EventShot, ShotPressurePenaltyMode, StateLensMetadata } from '../../types/eventMaps'
import { PortraitPitch } from './PortraitPitch'
import {
  EventMapCard, EventMapNotice, EventMatchFilter,
  EventPitchStage, EventSelectionDetails, ShotMapLegend,
} from './EventMapUi'
import { StateLensControls } from './StateLensControls'
import { TeamPassStateFlow } from './TeamPassStateFlow'
import { stateLensRequest } from '../../lib/eventMaps/stateLensUrl'
import { DefensiveTerritoryMap } from './DefensiveTerritoryMap'
import { ShotPressurePanel } from './ShotPressurePanel'
import { LeadControlPanel } from './LeadControlPanel'
import { ResponseHalfLifePanel } from './ResponseHalfLifePanel'
import { TeamStyleShapePanel } from './TeamStyleShapePanel'
import { TransitionLeveragePanel } from './TransitionLeveragePanel'

type TeamMap = 'flow' | 'defensive-territory' | 'shots-for' | 'shots-against' | 'shot-pressure' | 'style-shape'
type AnalysisMode = 'shooting' | 'passing' | 'defending' | 'interpretation'
type InterpretationMode = 'style' | 'lead' | 'response' | 'transitions'

const ANALYSIS_MODES: Array<{ value: AnalysisMode; label: string; description: string }> = [
  { value: 'shooting', label: 'Shooting', description: 'Shot locations, outcomes and pressure' },
  { value: 'passing', label: 'Passing', description: 'Volume, direction and completion' },
  { value: 'defending', label: 'Defending', description: 'Action height and territory' },
  { value: 'interpretation', label: 'Interpretation', description: 'Style, leads, responses and transitions' },
]

const INTERPRETATION_MODES: Array<{ value: InterpretationMode; label: string }> = [
  { value: 'style', label: 'Style Shape' },
  { value: 'lead', label: 'Lead Control' },
  { value: 'response', label: 'Response Half-Life' },
  { value: 'transitions', label: 'Transition Leverage' },
]

function MapStage({ map, expanded, setExpanded, children }: {
  map: TeamMap
  expanded: TeamMap | null
  setExpanded: (map: TeamMap | null) => void
  children: ReactNode
}) {
  return (
    <EventPitchStage expanded={expanded === map} onExpandedChange={next => setExpanded(next ? map : null)}>
      {children}
    </EventPitchStage>
  )
}

function shotPitchView(shots: EventShot[]) {
  return shots.some(shot => shot.location.x < 50) ? 'full' as const : 'attacking-half' as const
}

function includesShotForPenaltyMode(shot: EventShot, mode: ShotPressurePenaltyMode) {
  const isPenalty = shot.situation === 'penalty'
  if (mode === 'only') return isPenalty
  if (mode === 'exclude') return !isPenalty
  return true
}

function percentage(numerator: number | undefined, denominator: number | undefined) {
  if (!numerator || !denominator) return denominator === 0 ? '0.0%' : '—'
  return `${((numerator / denominator) * 100).toFixed(1)}%`
}

function scopeLabel(value: string) {
  return value.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase())
}

function stateExportFilters(metadata: StateLensMetadata): EventMapExportContext['filters'] {
  const selected = metadata.selected
  const filters: EventMapExportContext['filters'] = [
    { label: 'Game state', value: selected.state === 'all' ? 'All states' : scopeLabel(selected.state) },
  ]

  if (selected.goalDifference != null) {
    filters.push({ label: 'Goal difference', value: selected.goalDifference > 0 ? `+${selected.goalDifference}` : String(selected.goalDifference) })
  }
  if (selected.phase) filters.push({ label: 'Match phase', value: scopeLabel(selected.phase) })
  if (selected.drawProvenance) filters.push({ label: 'State provenance', value: scopeLabel(selected.drawProvenance) })
  if (selected.minimumStateAgeSeconds != null || selected.maximumStateAgeSeconds != null) {
    const minimum = selected.minimumStateAgeSeconds ?? 0
    const maximum = selected.maximumStateAgeSeconds == null ? 'No limit' : `${selected.maximumStateAgeSeconds}s`
    filters.push({ label: 'Time in state', value: `${minimum}s – ${maximum}` })
  }
  if (metadata.comparison.enabled && metadata.comparison.baseline) {
    const baseline = metadata.comparison.baseline.state
    filters.push({ label: 'Baseline', value: baseline === 'all' ? 'All states' : scopeLabel(baseline) })
  }
  filters.push({ label: 'State exposure', value: `${metadata.evidence.exposureMinutes.toLocaleString()} min · ${metadata.evidence.matchCount.toLocaleString()} matches` })

  return filters
}

export function TeamEventMaps({ teamId, competition, season }: {
  teamId: number
  competition: string
  season: string
}) {
  const [selection, setSelection] = useState<SelectablePitchEvent | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const matchRef = searchParams.get('match')
  const lensRequest = stateLensRequest(searchParams)
  const [expanded, setExpanded] = useState<TeamMap | null>(null)
  const [penaltyMode, setPenaltyMode] = useState<ShotPressurePenaltyMode>('exclude')
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>('shooting')
  const [interpretationMode, setInterpretationMode] = useState<InterpretationMode>('style')
  const profileQuery = useQuery({
    queryKey: ['team-event-profile', teamId, competition, season, matchRef, lensRequest],
    queryFn: () => fetchTeamEventProfile(teamId, competition, season, matchRef, lensRequest),
    staleTime: 10 * 60 * 1000,
  })
  const defensiveQuery = useQuery({
    queryKey: ['team-defensive-territory', teamId, competition, season, matchRef, lensRequest],
    queryFn: () => fetchTeamDefensiveTerritory(teamId, competition, season, matchRef, lensRequest),
    staleTime: 10 * 60 * 1000,
    enabled: analysisMode === 'defending',
  })
  const profile = profileQuery.data
  const shotPressureQuery = useQuery({
    queryKey: ['team-shot-pressure', teamId, competition, season, matchRef, lensRequest, penaltyMode],
    queryFn: () => fetchTeamShotPressure(teamId, competition, season, matchRef, lensRequest, penaltyMode),
    staleTime: 10 * 60 * 1000,
    enabled: analysisMode === 'shooting',
  })
  const styleShapeQuery = useQuery({
    queryKey: ['team-style-shape', teamId, competition, season, matchRef, lensRequest],
    queryFn: () => fetchTeamStyleShape(teamId, competition, season, matchRef, lensRequest),
    staleTime: 10 * 60 * 1000,
    enabled: analysisMode === 'interpretation' && interpretationMode === 'style',
  })
  const leadControlQuery = useQuery({
    queryKey: ['team-lead-control', teamId, competition, season, matchRef, lensRequest],
    queryFn: () => fetchTeamLeadControl(teamId, competition, season, matchRef, lensRequest),
    staleTime: 10 * 60 * 1000,
    enabled: analysisMode === 'interpretation' && interpretationMode === 'lead',
  })
  const responseHalfLifeQuery = useQuery({
    queryKey: ['team-response-half-life', teamId, competition, season, matchRef, lensRequest],
    queryFn: () => fetchTeamResponseHalfLife(teamId, competition, season, matchRef, lensRequest),
    staleTime: 10 * 60 * 1000,
    enabled: analysisMode === 'interpretation' && interpretationMode === 'response',
  })
  const transitionLeverageQuery = useQuery({
    queryKey: ['team-transition-leverage', teamId, competition, season, matchRef, lensRequest],
    queryFn: () => fetchTeamTransitionLeverage(teamId, competition, season, matchRef, lensRequest),
    staleTime: 10 * 60 * 1000,
    enabled: analysisMode === 'interpretation' && interpretationMode === 'transitions',
  })
  const setLensParams = (next: URLSearchParams) => {
    setSelection(null)
    setSearchParams(next)
  }
  if (profileQuery.isLoading) return <div className="space-y-3"><StateLensControls searchParams={searchParams} onChange={setLensParams} /><EventMapNotice kind="loading" title="Loading team event profile" /></div>
  if (profileQuery.isError || !profile) {
    return <div className="space-y-3"><StateLensControls searchParams={searchParams} onChange={setLensParams} /><EventMapNotice kind="error" title="Team event profile failed to load" onRetry={() => profileQuery.refetch()}>
      {profileQuery.error?.message ?? 'The event-profile service returned no data.'}
    </EventMapNotice></div>
  }

  const shotsFor = profile.shots.filter(shot => shot.perspective === 'for' && includesShotForPenaltyMode(shot, penaltyMode))
  const shotsAgainst = profile.shots.filter(shot => shot.perspective === 'against' && includesShotForPenaltyMode(shot, penaltyMode))
  const sharedShotPitchView = shotPitchView([...shotsFor, ...shotsAgainst])
  const exportContext: EventMapExportContext = {
    subjectName: profile.teamName,
    subjectType: 'Team',
    competition,
    season,
    filters: [
      { label: 'Match', value: eventMatchExportLabel(profile.matches, matchRef) },
      ...stateExportFilters(profile.stateLens),
    ],
  }

  const shotDensity = (kind: 'for' | 'against'): ActionGridCell[] => (
    shotPressureQuery.data?.selected.location[kind].cells.map(cell => ({
      column: cell.column,
      row: cell.row,
      rawCount: cell.shotCount,
      per90Count: cell.shotsPer90 ?? 0,
      share: cell.locationShare ?? 0,
    })) ?? []
  )

  const shotCard = (kind: 'for' | 'against', shots: EventShot[], map: TeamMap) => {
    const title = kind === 'for' ? 'Shots for' : 'Shots against'
    return (
      <EventMapCard key={map} expanded={expanded === map} onExpandedChange={next => setExpanded(next ? map : null)} title={title} description={sharedShotPitchView === 'attacking-half' ? 'Attacking half shown for both maps; all selected shots originate beyond halfway.' : 'Both maps use the full pitch so their territories stay directly comparable.'} exportContext={{
        ...exportContext,
        filters: [...exportContext.filters, { label: 'Penalties', value: penaltyMode === 'exclude' ? 'Excluded' : penaltyMode === 'include' ? 'Included' : 'Penalties only' }],
      }} footer={(
        <div className="space-y-2">
          <ShotMapLegend />
          <p className="text-[10px] text-ink-dim">Blue heat = relative shot-location density for this state scope.</p>
          {selection?.kind === 'shot' && shots.some(shot => shot.id === selection.id) ? <EventSelectionDetails selection={selection} matches={profile.matches} /> : <p className="text-[11px] text-ink-dim">Click, tap or focus a shot to inspect it.</p>}
        </div>
      )}>
        <MapStage map={map} expanded={expanded} setExpanded={setExpanded}>
          {shots.length ? <PortraitPitch className={sharedShotPitchView === 'attacking-half' ? 'mx-auto max-w-[360px]' : ''} shots={shots} densityCells={shotDensity(kind)} densityStyle="smooth" pitchView={sharedShotPitchView} eventSelectionMode="click" selectedEventId={selection?.kind === 'shot' ? selection.id : null} onSelectedEventChange={setSelection} ariaLabel={`${profile.teamName} ${title.toLowerCase()} map with shot-location density. ${sharedShotPitchView === 'attacking-half' ? 'Attacking half' : 'Full pitch'}; acting team attacks left to right.`} /> : <EventMapNotice kind="empty" title={`No ${title.toLowerCase()} recorded`} />}
        </MapStage>
      </EventMapCard>
    )
  }

  const headlineStats = analysisMode === 'shooting'
    ? [
        ['Shots for', shotsFor.length],
        ['Shots against', shotsAgainst.length],
        ['Goals for', shotsFor.filter(shot => shot.outcome === 'goal').length],
      ]
    : analysisMode === 'passing'
      ? [
          ['Pass attempts', profile.summary.pass_attempts],
          ['Pass completion', percentage(profile.summary.pass_completions, profile.summary.pass_attempts)],
          ['Progressive attempts', profile.summary.progressive_pass_attempts],
        ]
      : [
          ['Defensive actions', defensiveQuery.data?.selected.counts.included],
          ['Located actions', defensiveQuery.data?.selected.counts.withLocation],
          ['Average position', defensiveQuery.data?.selected.heights.all.mean == null ? '—' : `${defensiveQuery.data.selected.heights.all.mean.toFixed(1)}%`],
        ]

  return (
    <section aria-label="Team event maps">
      <div className="mb-2">
        <div className="mb-2 flex items-center justify-end gap-3">
          <EventMatchFilter matches={profile.matches} value={matchRef} onChange={value => {
            const next = new URLSearchParams(searchParams)
            if (value == null) next.delete('match')
            else next.set('match', value)
            setLensParams(next)
          }} />
        </div>
        <StateLensControls metadata={profile.stateLens} searchParams={searchParams} onChange={setLensParams} />
      </div>
      {expanded ? <div className="fixed left-3 right-16 top-3 z-[95] max-h-[45svh] overflow-y-auto sm:left-8 sm:right-20"><StateLensControls compact metadata={profile.stateLens} searchParams={searchParams} onChange={setLensParams} /></div> : null}
      <nav className="mb-2 grid grid-cols-2 border-b border-line-bright sm:grid-cols-4" aria-label="Event map analysis">
        {ANALYSIS_MODES.map(mode => <button key={mode.value} type="button" aria-pressed={analysisMode === mode.value} onClick={() => { setAnalysisMode(mode.value); setSelection(null) }} className={`border-b-2 px-2 py-2 text-left transition-colors hover:bg-raised sm:px-3 ${analysisMode === mode.value ? 'border-electric text-electric' : 'border-transparent text-ink'}`}><strong className="block text-[9px] uppercase tracking-[0.1em] sm:text-[10px] sm:tracking-[0.14em]">{mode.label}</strong><span className="mt-0.5 hidden text-[8px] text-ink-dim sm:block">{mode.description}</span></button>)}
      </nav>

      {analysisMode === 'interpretation' ? (
        <nav className="mb-2 grid grid-cols-2 gap-px bg-line sm:grid-cols-4" aria-label="Team interpretation product">
          {INTERPRETATION_MODES.map(mode => <button key={mode.value} type="button" aria-pressed={interpretationMode === mode.value} onClick={() => { setInterpretationMode(mode.value); setExpanded(null) }} className={`min-h-9 bg-panel px-2 py-2 text-[9px] font-bold uppercase tracking-[0.1em] transition-colors hover:bg-raised ${interpretationMode === mode.value ? 'text-electric' : 'text-control-fg'}`}>{mode.label}</button>)}
        </nav>
      ) : null}

      {analysisMode === 'shooting' ? (
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2 border-b border-line-bright pb-2">
          <p className="text-[10px] leading-relaxed text-ink-dim">Penalty treatment applies to both shot maps and all supporting shooting statistics.</p>
          <select className="event-lens-control w-auto min-w-48" aria-label="Shooting penalty treatment" value={penaltyMode} onChange={event => { setPenaltyMode(event.target.value as ShotPressurePenaltyMode); setSelection(null) }}><option value="exclude">Excluding penalties</option><option value="include">Including penalties</option><option value="only">Penalties only</option></select>
        </div>
      ) : null}

      {analysisMode !== 'interpretation' ? <div className="mb-2 flex flex-wrap items-center gap-x-6 gap-y-2 py-2">
        {headlineStats.map(([label, value]) => <p key={label as string} className="text-[10px] text-ink-dim"><span className="mr-1.5 uppercase tracking-[0.1em]">{label}</span><strong className="font-mono text-[13px] font-normal text-ink">{typeof value === 'number' ? value.toLocaleString() : value ?? '—'}</strong></p>)}
        <p className="ml-auto text-[10px] text-ink-dim">Coverage <span className={profile.coverage.complete ? 'text-mint' : 'text-gold'}>{profile.coverage.matchesIncluded}/{profile.coverage.matchesExpected || '—'} matches</span></p>
      </div> : null}

      <div className="space-y-3">
        {analysisMode === 'shooting' ? <>
          <div className="grid items-start gap-3 lg:grid-cols-2">
            {shotCard('for', shotsFor, 'shots-for')}
            {shotCard('against', shotsAgainst, 'shots-against')}
          </div>
          <ShotPressurePanel
          payload={shotPressureQuery.data}
          loading={shotPressureQuery.isLoading}
          error={shotPressureQuery.isError ? shotPressureQuery.error.message : undefined}
          onRetry={() => shotPressureQuery.refetch()}
          exportContext={exportContext}
          expanded={expanded === 'shot-pressure'}
          onExpandedChange={next => setExpanded(next ? 'shot-pressure' : null)}
          />
        </> : null}

        {analysisMode === 'passing' ? <TeamPassStateFlow
          teamId={teamId}
          teamName={profile.teamName}
          competition={competition}
          season={season}
          matchRef={matchRef}
          stateLens={lensRequest}
          stateLensMetadata={profile.stateLens}
          onComparisonChange={enabled => {
            const next = new URLSearchParams(searchParams)
            if (enabled) {
              next.set('baseline_state', 'all')
            } else {
              for (const key of Array.from(next.keys())) {
                if (key.startsWith('baseline_')) next.delete(key)
              }
            }
            setLensParams(next)
          }}
          exportContext={exportContext}
          expanded={expanded === 'flow'}
          onExpandedChange={next => setExpanded(next ? 'flow' : null)}
        /> : null}

        {analysisMode === 'defending' ? <DefensiveTerritoryMap
          payload={defensiveQuery.data}
          loading={defensiveQuery.isLoading}
          error={defensiveQuery.error?.message}
          retry={() => defensiveQuery.refetch()}
          exportContext={exportContext}
          expanded={expanded === 'defensive-territory'}
          onExpandedChange={next => setExpanded(next ? 'defensive-territory' : null)}
        /> : null}

        {analysisMode === 'interpretation' && interpretationMode === 'style' ? <TeamStyleShapePanel
          payload={styleShapeQuery.data}
          loading={styleShapeQuery.isLoading}
          error={styleShapeQuery.error?.message}
          onRetry={() => styleShapeQuery.refetch()}
          exportContext={exportContext}
          expanded={expanded === 'style-shape'}
          onExpandedChange={next => setExpanded(next ? 'style-shape' : null)}
          axisSelection={searchParams.get('style_axes')?.split(',').filter(Boolean)}
          onAxisSelectionChange={keys => {
            const next = new URLSearchParams(searchParams)
            if (keys.length) next.set('style_axes', keys.join(','))
            else next.delete('style_axes')
            setSearchParams(next)
          }}
        /> : null}

        {analysisMode === 'interpretation' && interpretationMode === 'lead' ? <LeadControlPanel
          payload={leadControlQuery.data}
          loading={leadControlQuery.isLoading}
          error={leadControlQuery.error?.message}
          onRetry={() => leadControlQuery.refetch()}
        /> : null}

        {analysisMode === 'interpretation' && interpretationMode === 'response' ? <ResponseHalfLifePanel
          payload={responseHalfLifeQuery.data}
          loading={responseHalfLifeQuery.isLoading}
          error={responseHalfLifeQuery.error?.message}
          onRetry={() => responseHalfLifeQuery.refetch()}
        /> : null}

        {analysisMode === 'interpretation' && interpretationMode === 'transitions' ? <TransitionLeveragePanel
          payload={transitionLeverageQuery.data}
          loading={transitionLeverageQuery.isLoading}
          error={transitionLeverageQuery.error?.message}
          onRetry={() => transitionLeverageQuery.refetch()}
        /> : null}
      </div>
    </section>
  )
}
