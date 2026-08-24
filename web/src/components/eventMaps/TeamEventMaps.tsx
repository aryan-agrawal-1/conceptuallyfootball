import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchTeamDefensiveTerritory, fetchTeamEventProfile, fetchTeamShotPressure } from '../../lib/eventMaps/api'
import type { SelectablePitchEvent } from '../../lib/eventMaps/selection'
import type { EventShot, ShotPressurePenaltyMode } from '../../types/eventMaps'
import { PortraitPitch } from './PortraitPitch'
import {
  EventCoverage, EventMapCard, EventMapNotice, EventMatchFilter, EventMetricStrip,
  EventPitchStage, EventSelectionDetails, ShotMapLegend,
} from './EventMapUi'
import { StateLensControls } from './StateLensControls'
import { TeamPassStateFlow } from './TeamPassStateFlow'
import { stateLensRequest } from '../../lib/eventMaps/stateLensUrl'
import { DefensiveTerritoryMap } from './DefensiveTerritoryMap'
import { ShotPressurePanel } from './ShotPressurePanel'

type TeamMap = 'flow' | 'defensive-territory' | 'shots-for' | 'shots-against'

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
  const profileQuery = useQuery({
    queryKey: ['team-event-profile', teamId, competition, season, matchRef, lensRequest],
    queryFn: () => fetchTeamEventProfile(teamId, competition, season, matchRef, lensRequest),
    staleTime: 10 * 60 * 1000,
  })
  const defensiveQuery = useQuery({
    queryKey: ['team-defensive-territory', teamId, competition, season, matchRef, lensRequest],
    queryFn: () => fetchTeamDefensiveTerritory(teamId, competition, season, matchRef, lensRequest),
    staleTime: 10 * 60 * 1000,
  })
  const profile = profileQuery.data
  const shotPressureQuery = useQuery({
    queryKey: ['team-shot-pressure', teamId, competition, season, matchRef, lensRequest, penaltyMode],
    queryFn: () => fetchTeamShotPressure(teamId, competition, season, matchRef, lensRequest, penaltyMode),
    staleTime: 10 * 60 * 1000,
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

  const shotsFor = profile.shots.filter(shot => shot.perspective === 'for')
  const shotsAgainst = profile.shots.filter(shot => shot.perspective === 'against')

  const shotCard = (kind: 'for' | 'against', shots: EventShot[], map: TeamMap) => {
    const pitchView = shotPitchView(shots)
    const title = kind === 'for' ? 'Shots for' : 'Shots against'
    return (
      <EventMapCard key={map} expanded={expanded === map} onExpandedChange={next => setExpanded(next ? map : null)} title={title} description={pitchView === 'attacking-half' ? 'Attacking half shown; every shot originates beyond halfway.' : 'Full pitch shown because at least one shot originates behind halfway.'} footer={(
        <div className="space-y-2">
          <ShotMapLegend />
          {selection?.kind === 'shot' && shots.some(shot => shot.id === selection.id) ? <EventSelectionDetails selection={selection} matches={profile.matches} /> : <p className="text-[9px] text-ink-dim">Click, tap or focus a shot to inspect it.</p>}
        </div>
      )}>
        <MapStage map={map} expanded={expanded} setExpanded={setExpanded}>
          {shots.length ? <PortraitPitch shots={shots} pitchView={pitchView} eventSelectionMode="click" selectedEventId={selection?.kind === 'shot' ? selection.id : null} onSelectedEventChange={setSelection} ariaLabel={`${profile.teamName} ${title.toLowerCase()} map. ${pitchView === 'attacking-half' ? 'Attacking half' : 'Full pitch'}; acting team attacks left to right.`} /> : <EventMapNotice kind="empty" title={`No ${title.toLowerCase()} recorded`} />}
        </MapStage>
      </EventMapCard>
    )
  }

  return (
    <section aria-label="Team event maps">
      <div className="mb-3"><StateLensControls metadata={profile.stateLens} searchParams={searchParams} onChange={setLensParams} /></div>
      {expanded ? <div className="fixed left-3 right-16 top-3 z-[95] max-h-[45svh] overflow-y-auto sm:left-8 sm:right-20"><StateLensControls compact metadata={profile.stateLens} searchParams={searchParams} onChange={setLensParams} /></div> : null}
      <div className="mb-3 grid gap-2 lg:grid-cols-[minmax(0,1fr)_minmax(220px,0.55fr)_auto]">
        <EventMetricStrip metrics={[
          { label: 'Passes', value: profile.summary.pass_attempts?.toLocaleString() ?? '—' },
          { label: 'Shots for', value: profile.summary.shots_for?.toLocaleString() ?? '—' },
          { label: 'Shots against', value: profile.summary.shots_against?.toLocaleString() ?? '—' },
        ]} />
        <EventCoverage coverage={profile.coverage} />
        <EventMatchFilter matches={profile.matches} value={matchRef} onChange={value => {
          const next = new URLSearchParams(searchParams)
          if (value == null) next.delete('match')
          else next.set('match', value)
          setLensParams(next)
        }} />
      </div>

      <div className="space-y-3">
        <ShotPressurePanel
          payload={shotPressureQuery.data}
          loading={shotPressureQuery.isLoading}
          error={shotPressureQuery.isError ? shotPressureQuery.error.message : undefined}
          penaltyMode={penaltyMode}
          onPenaltyModeChange={setPenaltyMode}
          onRetry={() => shotPressureQuery.refetch()}
        />

        <TeamPassStateFlow
          teamId={teamId}
          teamName={profile.teamName}
          competition={competition}
          season={season}
          matchRef={matchRef}
          stateLens={lensRequest}
          expanded={expanded === 'flow'}
          onExpandedChange={next => setExpanded(next ? 'flow' : null)}
        />

        <DefensiveTerritoryMap
          payload={defensiveQuery.data}
          loading={defensiveQuery.isLoading}
          error={defensiveQuery.error?.message}
          retry={() => defensiveQuery.refetch()}
          expanded={expanded === 'defensive-territory'}
          onExpandedChange={next => setExpanded(next ? 'defensive-territory' : null)}
        />

        <div className="grid items-start gap-3 lg:grid-cols-2">
          {shotCard('for', shotsFor, 'shots-for')}
          {shotCard('against', shotsAgainst, 'shots-against')}
        </div>
      </div>
    </section>
  )
}
